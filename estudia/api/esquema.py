"""Genera el archivo versionado del esquema OpenAPI (`make api-esquema`). Una prueba falla si la API cambia sin regenerarlo."""
import json

from .. import settings

ARCHIVO = settings.ROOT / "docs" / "openapi.json"


def esquema() -> dict:
    from ..web.app import app
    return json.loads(json.dumps(app.openapi()))


def main() -> None:
    ARCHIVO.write_text(json.dumps(esquema(), indent=2, ensure_ascii=False) + "\n")
    print(f"Esquema OpenAPI escrito en {ARCHIVO.relative_to(settings.ROOT)}")


if __name__ == "__main__":
    main()
