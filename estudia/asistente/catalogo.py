"""El catálogo cerrado: qué herramientas existen y cuáles recibe cada perfil (PRD asistente, §5)."""
from . import herramientas, operador  # noqa: F401  (importarlos las registra)
from .base import CATALOGO, Herramienta


def herramientas_de(perfil: str) -> list[Herramienta]:
    """Las herramientas del perfil, en el orden del catálogo. Es lo único que se le ofrece al modelo."""
    return [h for h in CATALOGO.values() if perfil in h.perfiles]


def esquema_entrada(h: Herramienta, perfil: str) -> dict:
    """JSON Schema de la entrada de una herramienta para ese perfil (algunas piden campos distintos)."""
    esquema = h.modelo_de(perfil).model_json_schema()
    esquema.pop("title", None)
    for p in esquema.get("properties", {}).values():
        p.pop("title", None)
    esquema.setdefault("properties", {})
    return esquema


def definiciones_api(perfil: str) -> list[dict]:
    """Las herramientas del perfil como definiciones de la API de Claude: `name`, `description`, `input_schema`."""
    return [{"name": h.nombre, "description": h.descripcion, "input_schema": esquema_entrada(h, perfil)}
            for h in herramientas_de(perfil)]
