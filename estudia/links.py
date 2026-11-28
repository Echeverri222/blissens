"""Enlaces personales firmados que vencen (PRD §6.11). Desde el PRD #4 llevan el negocio dentro."""
import hashlib

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import settings

NEGOCIO_ENLACES_ANTIGUOS = 1  # los enlaces emitidos antes del PRD #4 no llevan negocio: eran de Blissens


def _serializador() -> URLSafeTimedSerializer:
    # La primera clave firma; todas verifican (permite rotar SECRET_KEY sin invalidar enlaces vigentes).
    claves = [settings.SECRET_KEY] + ([settings.SECRET_KEY_ANTERIOR] if settings.SECRET_KEY_ANTERIOR else [])
    return URLSafeTimedSerializer(claves, salt="enlace-paciente")


def huella_celular(celular: str | None) -> str:
    """Huella truncada del celular: si el número cambia o se borra, los enlaces que la llevan dejan de servir."""
    base = f"huella-celular:{settings.SECRET_KEY}:{celular or ''}".encode()
    return hashlib.sha256(base).hexdigest()[:10]


def make_token(patient_id: int, negocio_id: int | None = None, conn=None, celular: str | None = None) -> str:
    if negocio_id is None:
        negocio_id = conn.execute("select negocio_activo() n").fetchone()["n"] if conn is not None \
            else NEGOCIO_ENLACES_ANTIGUOS
    if celular:
        return _serializador().dumps([negocio_id, patient_id, huella_celular(celular)])
    return _serializador().dumps([negocio_id, patient_id])


def _normalizar(v) -> tuple[int, int] | None:
    if isinstance(v, int):
        return NEGOCIO_ENLACES_ANTIGUOS, v
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v):
        return v[0], v[1]
    if isinstance(v, list) and len(v) == 3 and isinstance(v[0], int) and isinstance(v[1], int) and isinstance(v[2], str):
        return v[0], v[1]
    return None


def huella_del_token(token: str, max_age_days: int = 30) -> str | None:
    """La huella del celular que lleva el enlace, o None si no la lleva (enlaces antiguos) o no sirve."""
    try:
        v = _serializador().loads(token, max_age=max_age_days * 86400)
    except (BadSignature, SignatureExpired):
        return None
    return v[2] if isinstance(v, list) and len(v) == 3 else None


def read_token_completo(token: str, max_age_days: int = 30) -> tuple[int, int] | None:
    """(negocio_id, paciente_id) de un enlace vigente y bien firmado; None si no sirve."""
    try:
        return _normalizar(_serializador().loads(token, max_age=max_age_days * 86400))
    except (BadSignature, SignatureExpired):
        return None


def negocio_del_token(token: str) -> int | None:
    """Negocio firmado en el enlace (sin comprobar vigencia: eso lo hace la ruta con la configuración del negocio)."""
    try:
        r = _normalizar(_serializador().loads(token))
    except SignatureExpired as e:
        r = _normalizar(e.payload)
    except BadSignature:
        return None
    return r[0] if r else None


def read_token(token: str, max_age_days: int = 30) -> int | None:
    r = read_token_completo(token, max_age_days)
    return r[1] if r else None
