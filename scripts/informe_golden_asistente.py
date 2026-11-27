"""Resume el último informe de `make golden-asistente-vivo`: aprobados por perfil y categoría, y cada caso reprobado."""
import json
import sys
from collections import defaultdict
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent / ".logs" / "golden-asistente"


def main() -> int:
    informes = sorted(CARPETA.glob("*.jsonl"))
    if not informes:
        print("No hay informes en .logs/golden-asistente/")
        return 1
    filas = [json.loads(x) for x in informes[-1].read_text(encoding="utf-8").splitlines() if x.strip()]
    print(f"Informe: {informes[-1].name} ({len(filas)} casos)\n")
    for clave in ("perfil", "categoria"):
        grupos = defaultdict(lambda: [0, 0])
        for f in filas:
            grupos[f[clave]][0] += f["aprobado"]
            grupos[f[clave]][1] += 1
        print(f"Por {clave}:")
        for k, (ok, n) in sorted(grupos.items()):
            print(f"  {k:<18} {ok}/{n}")
        print()
    for f in (f for f in filas if not f["aprobado"]):
        print(f"✗ {f['perfil']}/{f['id']}: {'; '.join(f['fallos'])}")
        print(f"    herramientas: {[x['nombre'] for x in f['llamadas']]}  respuesta: {f['respuesta'][:160]!r}")
    de_mas = [f for f in filas if f.get("herramientas_de_mas")]
    if de_mas:
        print("\nHerramientas de más (no reprueban, pero cuestan):")
        for f in de_mas:
            print(f"  {f['perfil']}/{f['id']}: {f['herramientas_de_mas']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
