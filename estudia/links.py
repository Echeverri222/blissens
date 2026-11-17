"""Enlaces personales firmados que vencen (PRD §6.11)."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import settings

_ser = URLSafeTimedSerializer(settings.SECRET_KEY, salt="enlace-paciente")


def make_token(patient_id: int) -> str:
    return _ser.dumps(patient_id)


def read_token(token: str, max_age_days: int = 30) -> int | None:
    try:
        return _ser.loads(token, max_age=max_age_days * 86400)
    except (BadSignature, SignatureExpired):
        return None
