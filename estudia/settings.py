"""Variables de entorno (lee .env si existe, sin dependencias extra)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://estudia:estudia@localhost:5433/estudia")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://estudia:estudia@localhost:5433/estudia_test")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esto-en-cualquier-despliegue")
DATOS_REALES_DIR = ROOT / os.environ.get("DATOS_REALES_DIR", "datos_reales")
