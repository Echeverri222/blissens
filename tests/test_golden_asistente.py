"""Golden cases del asistente: preguntas del día a día, con las herramientas que deben responderlas.

Cada caso `tests/golden_asistente/<perfil>/<caso>.yaml` es una pregunta real de alguien de la clínica (o de un paciente) sobre
el mundo de `tests/mundo_clinica.py`. Su formato está en `tests/golden_asistente/README.md`.

Tres modos:
- Sin modelo (siempre): la estructura del caso, que las herramientas esperadas existan para ese perfil, y que las llamadas
  canónicas devuelvan el contexto que la respuesta necesita (y nada que no deba salir). Más la cobertura del catálogo.
- En vivo (`ASISTENTE_EN_VIVO=1` y `ASISTENTE_EVAL_KEY`): manda la pregunta al modelo real con `conversar` y califica qué
  herramientas usó, qué propuestas preparó y qué dijo. Deja un informe en `.logs/golden-asistente/`.
- Charla (`ASISTENTE_PREGUNTA`, opcional `ASISTENTE_ACTOR`): una pregunta libre al modelo real; imprime la respuesta, las
  herramientas con sus argumentos y las propuestas. Es la puerta que usan los agentes que simulan usuarios.

Los dos modos con modelo envían el mundo ficticio a la API de Anthropic: nunca con datos reales.
"""
import json
import os
import time
import unicodedata
from pathlib import Path

import pytest
import yaml

from estudia import catalog, clock, db, settings
from estudia.asistente import CATALOGO, ejecutar, herramientas_de
from estudia.asistente.conversacion import conversar, herramientas_precargadas

from .conftest import URL, vaciar
from .mundo_clinica import AHORA, PACIENTES, construir

RAIZ = Path(__file__).parent / "golden_asistente"
CASOS = sorted(RAIZ.rglob("*.yaml"))
PERFILES = ("auxiliar", "especialista", "paciente", "visitante")
ACTORES = {"marta": "auxiliar", "rios": "especialista", "mejia": "especialista",
           "laura": "paciente", "tomas": "paciente", "jorge": "paciente", "diego": "paciente", "visita": "visitante"}
CATEGORIAS = ("agenda", "pendientes", "pacientes", "indicadores", "accion", "horario", "negocio",
              "fuera_de_alcance", "seguridad", "clinico", "privacidad")
CLAVES = {"id", "perfil", "actor", "categoria", "pregunta", "intencion", "herramientas", "contexto", "respuesta", "notas", "idioma"}
EN_VIVO = os.environ.get("ASISTENTE_EN_VIVO") == "1"
INFORME = Path(__file__).resolve().parent.parent / ".logs" / "golden-asistente" / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
# Documentos y celulares completos del mundo: ninguna salida de herramienta ni respuesta los trae (P5).
SENSIBLES = [d for (_, _, d, c, _) in PACIENTES.values() for d in (d, c)]


def _cargar(p: Path) -> dict:
    try:
        caso = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:  # un « : » sin comillas dentro de un texto es el error típico
        raise ValueError(f"{p.relative_to(RAIZ)} no es YAML válido: {e}") from None
    caso["_archivo"] = str(p.relative_to(RAIZ))
    return caso


def _id(p: Path) -> str:
    return str(p.relative_to(RAIZ).with_suffix(""))


def normal(t: str) -> str:
    """Minúsculas y sin tildes, para comparar sin depender de la redacción exacta."""
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def _contiene(texto: str, aguja: str) -> bool:
    return normal(aguja) in normal(texto)


def _herramientas(caso: dict) -> dict:
    h = caso.get("herramientas") or {}
    return {"esperadas": h.get("esperadas") or [], "una_de": h.get("una_de") or [], "aceptables": h.get("aceptables") or [],
            "prohibidas": h.get("prohibidas") or [], "ninguna": bool(h.get("ninguna"))}


def _turnos(caso: dict) -> list[str]:
    return caso["pregunta"] if isinstance(caso["pregunta"], list) else [caso["pregunta"]]


# ------------------------------------------------------------------ sin modelo

@pytest.mark.parametrize("ruta", CASOS, ids=_id)
def test_estructura(ruta):
    caso = _cargar(ruta)
    sobran = set(caso) - CLAVES - {"_archivo"}
    assert not sobran, f"Claves desconocidas: {sobran}"
    for clave in ("id", "perfil", "actor", "categoria", "pregunta", "intencion"):
        assert caso.get(clave), f"Falta `{clave}`"
    assert caso["id"] == ruta.stem, "El id del caso es el nombre del archivo"
    assert ruta.parent.name == caso["perfil"], "El caso va en la carpeta de su perfil"
    assert ACTORES.get(caso["actor"]) == caso["perfil"], f"El actor {caso['actor']} no es un {caso['perfil']}"
    assert caso["categoria"] in CATEGORIAS, f"Categoría desconocida: {caso['categoria']}"
    assert all(isinstance(t, str) and t.strip() for t in _turnos(caso))

    h = _herramientas(caso)
    propias = {x.nombre for x in herramientas_de(caso["perfil"])}
    usables = set(h["esperadas"]) | {x for g in h["una_de"] for x in g} | set(h["aceptables"])
    assert usables <= propias, f"Herramientas que el perfil {caso['perfil']} no tiene: {usables - propias}"
    assert set(h["prohibidas"]) <= set(CATALOGO), f"Herramientas inexistentes: {set(h['prohibidas']) - set(CATALOGO)}"
    assert not usables & set(h["prohibidas"]), "Una herramienta no puede ser esperada y prohibida a la vez"
    assert all(isinstance(g, list) and len(g) >= 2 for g in h["una_de"]), "`una_de` es una lista de grupos de 2 o más"
    if h["ninguna"]:
        assert not usables, "`ninguna: true` no lleva herramientas esperadas"
    else:
        assert h["esperadas"] or h["una_de"], "Un caso que usa herramientas dice cuáles (o `ninguna: true`)"

    for llamada in caso.get("contexto") or []:
        assert set(llamada) <= {"llamada", "args", "incluye", "excluye", "error"}, llamada
        assert llamada["llamada"] in usables, f"La llamada canónica {llamada['llamada']} no está entre las esperadas"
    r = caso.get("respuesta") or {}
    assert set(r) <= {"incluye", "incluye_alguno", "excluye", "propuestas"}, r
    tipos = {"agendar", "cambiar_fecha", "cancelar", "confirmar", "confirmar_telefono", "desenlace", "bloqueo", "contacto",
             "eliminar_bloqueo", "crear_paciente", "segmentos", "gestion_seguimiento", "gestionar_mensaje", "gestionar_contacto",
             "vincular_contacto", "revertir", "registro", "solicitud", "no_contactar", "quitar_no_contactar"}
    assert set(r.get("propuestas") or []) <= tipos, r.get("propuestas")


def test_ids_unicos():
    ids = [_cargar(p)["id"] for p in CASOS]
    assert len(ids) == len(set(ids))


def _tiene_contexto(p: Path) -> bool:
    try:
        return bool(_cargar(p).get("contexto"))
    except ValueError:
        return False  # su `test_estructura` ya falla y dice por qué; no se tumba toda la colección


CON_CONTEXTO = [p for p in CASOS if _tiene_contexto(p)]


@pytest.fixture(scope="module")
def mundo_compartido():
    """Un solo mundo para todas las llamadas canónicas: las herramientas corren en solo lectura (solo dejan filas de
    auditoría), así que no hace falta reconstruirlo por caso."""
    vaciar()
    c = db.connect(URL)
    catalog.load(c)
    c.commit()
    try:
        yield construir(c)
    finally:
        c.close()
        clock.freeze(None)


@pytest.mark.parametrize("ruta", CON_CONTEXTO, ids=_id)
def test_contexto(ruta, mundo_compartido):
    """Las llamadas canónicas devuelven lo que la respuesta necesita: es lo que el modelo tendrá en la mano."""
    caso = _cargar(ruta)
    w = mundo_compartido
    clock.freeze(AHORA)
    actor = w.actores[caso["actor"]]
    for llamada in caso["contexto"]:
        salida = ejecutar(actor, llamada["llamada"], w.resolver(llamada.get("args") or {}), conexion=URL)
        texto = json.dumps(salida, ensure_ascii=False)
        donde = f"{llamada['llamada']}({llamada.get('args') or {}})"
        if "error" in llamada:
            assert salida.get("error", {}).get("codigo") == llamada["error"], f"{donde} debía fallar con {llamada['error']}: {texto[:400]}"
        else:
            assert "error" not in salida, f"{donde} falló: {salida['error']}"
        for x in llamada.get("incluye") or []:
            assert _contiene(texto, w.resolver(x)), f"{donde} no trae «{x}». Salida: {texto[:1500]}"
        for x in llamada.get("excluye") or []:
            assert not _contiene(texto, w.resolver(x)), f"{donde} trae «{x}», que no debe salir"
        for s in SENSIBLES:
            assert s not in texto, f"{donde} deja salir un documento o celular completo"


def test_cobertura_cada_herramienta_tiene_al_menos_un_caso_que_la_espera():
    casos = [_cargar(p) for p in CASOS]
    faltan = []
    for perfil in PERFILES:
        usadas = set()
        for c in (c for c in casos if c["perfil"] == perfil):
            h = _herramientas(c)
            usadas |= set(h["esperadas"]) | {x for g in h["una_de"] for x in g}
        faltan += [f"{perfil}:{x.nombre}" for x in herramientas_de(perfil) if x.nombre not in usadas]
    assert not faltan, f"Herramientas sin ningún caso: {faltan}"


def test_cobertura_cada_perfil_tiene_casos_fuera_de_alcance_y_de_seguridad():
    casos = [_cargar(p) for p in CASOS]
    for perfil in PERFILES:
        cats = {c["categoria"] for c in casos if c["perfil"] == perfil}
        assert "fuera_de_alcance" in cats, perfil
        assert "seguridad" in cats or "privacidad" in cats, perfil


# ------------------------------------------------------------------ con el modelo real

class Grabadora:
    """Envuelve el cliente real y anota cada herramienta que el modelo pidió, con sus argumentos, y los tokens gastados."""

    def __init__(self, cliente):
        self._cliente, self.llamadas, self.uso = cliente, [], {}
        self.beta = type("B", (), {"messages": type("M", (), {"create": self._crear})()})()

    def _crear(self, **kw):
        r = self._cliente.beta.messages.create(**kw)
        self.llamadas += [{"nombre": b.name, "args": b.input} for b in r.content if getattr(b, "type", "") == "tool_use"]
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            self.uso[k] = self.uso.get(k, 0) + (getattr(r.usage, k, 0) or 0)
        return r


def _cliente_real():
    import anthropic
    if settings.en_bedrock():  # el mismo cliente que la aplicación, con las credenciales de AWS
        from estudia.asistente.conversacion import cliente_de_la_api
        return cliente_de_la_api()
    clave = os.environ.get("ASISTENTE_EVAL_KEY")
    if not clave:
        pytest.skip("Falta ASISTENTE_EVAL_KEY (la clave de la API para evaluar)")
    return anthropic.Anthropic(api_key=clave, base_url=os.environ.get("ASISTENTE_EVAL_BASE_URL") or "https://api.anthropic.com",
                               max_retries=2)


@pytest.fixture
def modelo_real(monkeypatch):
    if os.environ.get("ASISTENTE_EVAL_PROVEEDOR") == "bedrock":  # conftest fija `anthropic`; la evaluación lo cambia aquí
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            pytest.skip("Falta AWS_REGION para evaluar en Bedrock")
        monkeypatch.setattr(settings, "ASISTENTE_PROVEEDOR", "bedrock")
        monkeypatch.setattr(settings, "AWS_REGION", region)
    else:
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "evaluacion")
    if os.environ.get("ASISTENTE_EVAL_MODELO"):
        monkeypatch.setattr(settings, "ASISTENTE_MODELO", os.environ["ASISTENTE_EVAL_MODELO"])
        monkeypatch.setattr(settings, "ASISTENTE_MODELO_PACIENTE", os.environ["ASISTENTE_EVAL_MODELO"])
        monkeypatch.setattr(settings, "ASISTENTE_MODELO_VISITANTE", os.environ["ASISTENTE_EVAL_MODELO"])
    return _cliente_real()


def _conversar(actor, turnos: list[str], cliente, idioma=None) -> dict:
    g = Grabadora(cliente)
    conv, respuestas, propuestas = None, [], []
    for t in turnos:
        r = conversar(actor, t, conv, cliente=g, idioma=idioma)
        conv = r["conversacion_id"]
        respuestas.append(r["respuesta"])
        propuestas += r["propuestas"]
    return {"respuestas": respuestas, "respuesta": respuestas[-1], "llamadas": g.llamadas, "propuestas": propuestas,
            "uso": g.uso}


def calificar(caso: dict, r: dict, w) -> list[str]:
    """Lo que el modelo hizo mal en este caso. Lista vacía: aprobado."""
    fallos = []
    # Lo precargado cuenta como consultado: el modelo ya lo tiene en el mensaje (la agenda y mi_dia, solo de hoy).
    llamadas = [x["nombre"] for x in r["llamadas"]]
    usadas = llamadas + herramientas_precargadas(ACTORES[caso["actor"]])
    h = _herramientas(caso)
    if h["ninguna"] and llamadas:
        fallos.append(f"No debía usar herramientas y usó {llamadas}")
    for x in h["esperadas"]:
        if x not in usadas:
            fallos.append(f"No usó {x}")
    for g in h["una_de"]:
        if not set(g) & set(usadas):
            fallos.append(f"No usó ninguna de {g}")
    for x in h["prohibidas"]:
        if x in llamadas:
            fallos.append(f"Usó {x}, que no debía")
    esp = caso.get("respuesta") or {}
    texto = " ".join(r["respuestas"])
    for x in esp.get("incluye") or []:
        if not _contiene(texto, w.resolver(x)):
            fallos.append(f"La respuesta no menciona «{x}»")
    if esp.get("incluye_alguno") and not any(_contiene(texto, w.resolver(x)) for x in esp["incluye_alguno"]):
        fallos.append(f"La respuesta no menciona ninguno de {esp['incluye_alguno']}")
    for x in esp.get("excluye") or []:
        if _contiene(texto, w.resolver(x)):
            fallos.append(f"La respuesta menciona «{x}», que no debía")
    if "propuestas" in esp:
        tipos = sorted(p["tipo"] for p in r["propuestas"])
        if tipos != sorted(esp["propuestas"]):
            fallos.append(f"Propuestas {tipos}, se esperaban {sorted(esp['propuestas'])}")
    for s in SENSIBLES:
        if s in texto:
            fallos.append("La respuesta trae un documento o celular completo")
    return fallos


def test_calificar_con_un_modelo_falso(conn, monkeypatch):
    """La calificación en vivo, probada sin la API: un guion que acierta aprueba y uno que se equivoca reprueba."""
    from .test_asistente_conversacion import Falso, llama, responde, usar
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "clave-falsa-de-prueba")
    caso = _cargar(RAIZ / "especialista" / "quien-sigue.yaml")
    w = construir(conn)
    rios = w.actores["rios"]
    bien = _conversar(rios, _turnos(caso), Falso(llama(usar("mi_agenda", {"desde": "2026-11-17"})),
                                                 responde("Sigue Tomás a las 11:00, control de ortodoncia.")))
    assert bien["llamadas"] == [{"nombre": "mi_agenda", "args": {"desde": "2026-11-17"}}]
    assert calificar(caso, bien, w) == []
    mal = _conversar(rios, _turnos(caso), Falso(responde("Sigue Lucía a la 1:30.")))
    assert calificar(caso, mal, w) == ["La respuesta no menciona «Tomás»",
                                       "La respuesta no menciona ninguno de ['11:00', '11 a', '11am', 'once']",
                                       "La respuesta menciona «Lucía», que no debía"]


@pytest.mark.skipif(not EN_VIVO, reason="Solo con ASISTENTE_EN_VIVO=1 (llama al modelo real)")
@pytest.mark.parametrize("ruta", CASOS, ids=_id)
def test_en_vivo(ruta, conn, modelo_real):
    caso = _cargar(ruta)
    w = construir(conn)
    r = _conversar(w.actores[caso["actor"]], _turnos(caso), modelo_real, caso.get("idioma"))
    fallos = calificar(caso, r, w)
    extra = sorted({x["nombre"] for x in r["llamadas"]} - set(_herramientas(caso)["esperadas"])
                   - {x for g in _herramientas(caso)["una_de"] for x in g} - set(_herramientas(caso)["aceptables"]))
    INFORME.parent.mkdir(parents=True, exist_ok=True)
    with INFORME.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": caso["id"], "perfil": caso["perfil"], "categoria": caso["categoria"], "aprobado": not fallos,
                            "fallos": fallos, "herramientas_de_mas": extra, "pregunta": caso["pregunta"], **r},
                           ensure_ascii=False, default=str) + "\n")
    assert not fallos, "\n".join(fallos) + f"\nRespuesta: {r['respuesta']}\nHerramientas: {r['llamadas']}"


@pytest.mark.skipif(not os.environ.get("ASISTENTE_PREGUNTA"), reason="Solo con ASISTENTE_PREGUNTA (charla libre)")
def test_charla(conn, modelo_real):
    """Una pregunta libre (varias separadas por « || ») como `ASISTENTE_ACTOR` (marta por defecto). Correr con `-s`."""
    w = construir(conn)
    actor = os.environ.get("ASISTENTE_ACTOR", "marta")
    turnos = [t.strip() for t in os.environ["ASISTENTE_PREGUNTA"].split("||") if t.strip()]
    r = _conversar(w.actores[actor], turnos, modelo_real)
    print("\n" + json.dumps({"actor": actor, "perfil": ACTORES[actor], "turnos": turnos, **r}, ensure_ascii=False, indent=2,
                            default=str))
