"""Consentimiento del paciente para el asistente (docs/prd-asistente.md, §7 y §9).

Es un consentimiento aparte del base: el asistente usa un servicio de inteligencia artificial de un tercero. Se guarda en
`paciente.acepta_asistente`, `consentimiento_asistente_en` y `consentimiento_asistente_por` (quien lo dio por esa persona,
como `consentimiento_por`: vacío = lo dio ella misma).

Quién consiente por quién:
- Un paciente sin responsable (el responsable de un hogar o alguien sin familia) consiente por sí mismo. Si tiene familiares,
  su consentimiento cubre también a los suyos: a cada uno se le anota `consentimiento_asistente_por = responsable`.
- Un familiar que aún comparte sus citas usa el consentimiento de su responsable (se lee de él, así cubre también a los que
  se agreguen después) y no puede darlo ni retirarlo desde su enlace.
- Un familiar que dejó de compartir (ya sin responsable) solo cuenta con el consentimiento que dio él mismo: el que le anotó
  su responsable no sirve.
"""
from .. import clock, familia, privacidad

TEXTO = ("El asistente usa un servicio de inteligencia artificial de un tercero para responder sobre sus citas. Para eso se le "
         "envían su nombre y los datos de sus citas. Puede seguir usando esta página sin el asistente.")


def estado(conn, paciente: dict) -> dict:
    """`{acepta, por_responsable, responsable}`: si puede usar el asistente y quién lo decide.

    `por_responsable`: la decisión es de su responsable (el familiar no la puede dar ni retirar). `responsable`: ese paciente.
    """
    responsable = familia.responsable_de(conn, paciente)
    if responsable is not None:
        return {"acepta": bool(responsable["acepta_asistente"]), "por_responsable": True, "responsable": responsable}
    # Sin responsable, solo vale lo que la persona dio por sí misma.
    propio = bool(paciente["acepta_asistente"]) and paciente["consentimiento_asistente_por"] is None
    return {"acepta": propio, "por_responsable": False, "responsable": None}


def aceptar(conn, paciente: dict) -> bool:
    """Registra el consentimiento de quien abrió su enlace (y de sus familiares). Falso si le toca a su responsable."""
    if paciente.get("responsable_id"):
        return False
    ahora = clock.now(conn)
    conn.execute("update paciente set acepta_asistente=true, consentimiento_asistente_en=%s, consentimiento_asistente_por=null "
                 "where id=%s", (ahora, paciente["id"]))
    conn.execute("update paciente set acepta_asistente=true, consentimiento_asistente_en=%s, consentimiento_asistente_por=%s "
                 "where responsable_id=%s", (ahora, paciente["id"], paciente["id"]))
    privacidad.registrar(conn, None, "asistente:consentimiento", paciente_id=paciente["id"])
    return True


def retirar(conn, paciente: dict) -> bool:
    """Retira el consentimiento (también el que dio por sus familiares). Falso si le toca a su responsable."""
    if paciente.get("responsable_id"):
        return False
    conn.execute("update paciente set acepta_asistente=false, consentimiento_asistente_en=null, consentimiento_asistente_por=null "
                 "where id=%s or consentimiento_asistente_por=%s", (paciente["id"], paciente["id"]))
    privacidad.registrar(conn, None, "asistente:retiro", paciente_id=paciente["id"])
    return True
