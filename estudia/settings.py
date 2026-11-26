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

ENTORNOS = ("local", "demo", "produccion")
ENTORNO = os.environ.get("ENTORNO", "local")
# DATABASE_URL es la del rol de aplicación (sin privilegios, sujeto a RLS); DATABASE_URL_ADMIN, la del dueño del esquema.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://estudia_app:estudia_app@127.0.0.1:5433/estudia")
DATABASE_URL_ADMIN = os.environ.get("DATABASE_URL_ADMIN", "postgresql://estudia:estudia@127.0.0.1:5433/estudia")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://estudia_app:estudia_app@127.0.0.1:5433/estudia_test")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SECRET_KEY_POR_DEFECTO = "cambia-esto-en-cualquier-despliegue"
SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY_POR_DEFECTO)
SECRET_KEY_ANTERIOR = os.environ.get("SECRET_KEY_ANTERIOR", "")
NEGOCIO_POR_DEFECTO = os.environ.get("NEGOCIO_POR_DEFECTO", "blissens")
TICK_SECRETO = os.environ.get("TICK_SECRETO", "")
# Contraseña del rol de aplicación: solo se fija sola en local; en otros entornos la pone el operador.
CLAVE_ROL_APP = os.environ.get("CLAVE_ROL_APP", "estudia_app" if ENTORNO == "local" else "")
DATOS_REALES_DIR = ROOT / os.environ.get("DATOS_REALES_DIR", "datos_reales")
# Asistente (docs/prd-asistente.md): sin clave, sus rutas no se registran. El modelo de los pacientes puede ser otro (PRD §12, Q2).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ASISTENTE_MODELO = os.environ.get("ASISTENTE_MODELO", "claude-opus-5-5")
ASISTENTE_MODELO_PACIENTE = os.environ.get("ASISTENTE_MODELO_PACIENTE", "") or ASISTENTE_MODELO
