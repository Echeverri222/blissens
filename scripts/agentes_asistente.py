"""Genera `.claude/agents/asistente-{auxiliar,paciente}.md`: un subagente de Claude Code que hace de asistente con el mismo
texto de sistema (`estudia/asistente/instrucciones.py`) y solo las herramientas MCP de ese perfil.

    uv run python scripts/agentes_asistente.py          # escribe los archivos
    uv run python scripts/agentes_asistente.py --check  # falla si no están al día (lo usa la prueba)
"""
import sys
from pathlib import Path

from estudia.asistente.catalogo import herramientas_de
from estudia.asistente.instrucciones import INSTRUCCIONES

RAIZ = Path(__file__).resolve().parent.parent
PERFILES = {"auxiliar": "la recepción (perfil auxiliar)", "paciente": "un paciente desde su enlace (perfil paciente)"}


def ruta(perfil: str) -> Path:
    return RAIZ / ".claude" / "agents" / f"asistente-{perfil}.md"


def contenido(perfil: str) -> str:
    servidor = f"estudia-{perfil}"
    herramientas = ", ".join(f"mcp__{servidor}__{h.nombre}" for h in herramientas_de(perfil))
    return f"""---
name: asistente-{perfil}
description: Hace de asistente de Blissens para {PERFILES[perfil]} con el mismo texto de sistema y solo las herramientas MCP de ese perfil ({servidor}). Para iterar herramientas, instrucciones y golden cases sin gastar en Bedrock. El prompt abre con el bloque <contexto> (`uv run python -m estudia.asistente.mcp --perfil {perfil} --contexto`) seguido de la pregunta. Archivo generado por scripts/agentes_asistente.py.
tools: {herramientas}
---

<!-- Generado por scripts/agentes_asistente.py desde estudia/asistente/instrucciones.py. No lo edites a mano. -->

{INSTRUCCIONES[perfil].rstrip()}

Las herramientas proponer_* (y pedir_contacto) no escriben nada: devuelven la tarjeta que la persona confirmaría con un botón.

Habla en el idioma que piden las instrucciones de arriba, igual que el asistente de la aplicación: la recepción siempre
en español; el paciente en el idioma en que escribe (español o inglés).

Al terminar, después de tu respuesta, agrega una línea `HERRAMIENTAS:` con las herramientas que llamaste, en orden y con
sus argumentos, para que quien te evalúa compare con el golden case.
"""


def main() -> int:
    revisar = "--check" in sys.argv
    viejos = []
    for p in PERFILES:
        nuevo = contenido(p)
        if revisar:
            if not ruta(p).exists() or ruta(p).read_text() != nuevo:
                viejos.append(str(ruta(p).relative_to(RAIZ)))
        else:
            ruta(p).write_text(nuevo)
            print(f"escrito {ruta(p).relative_to(RAIZ)}")
    if viejos:
        print("Desactualizados (corre `uv run python scripts/agentes_asistente.py`): " + ", ".join(viejos), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
