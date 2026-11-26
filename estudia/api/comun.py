"""Piezas comunes de la API: errores, autenticación y traducción de errores de dominio."""
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .. import agenda, clock, db, horario, lifecycle, pacientes, permisos, usuarios

PREFIJO = "/api/v1"
COOKIE = "estudia_sesion"
get_conn = db.request_conn


class ApiError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, extra: dict | None = None):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra or {}


# Error de dominio -> (estado HTTP, código estable)
TRADUCCION = {
    permisos.SinPermiso: (403, "sin_permiso"),
    permisos.NoExiste: (404, "no_existe"),
    horario.BlockNotFound: (404, "no_existe"),
    agenda.SlotTaken: (409, "espacio_ocupado"),
    lifecycle.InvalidTransition: (409, "transicion_invalida"),
    agenda.CannotRevert: (409, "no_reversible"),
    agenda.OutcomeTooEarly: (409, "desenlace_anticipado"),
    horario.BlockConflict: (409, "bloqueo_con_citas"),
    horario.BlockPast: (409, "bloqueo_pasado"),
    horario.BlockInvalid: (422, "bloqueo_invalido"),
    pacientes.DocumentoExistente: (409, "documento_existente"),
    pacientes.DatosInvalidos: (422, "datos_invalidos"),
    usuarios.CredencialesInvalidas: (401, "credenciales_invalidas"),
    usuarios.InicioBloqueado: (429, "inicio_bloqueado"),
    usuarios.ClaveInvalida: (422, "clave_invalida"),
    usuarios.UsuarioInvalido: (422, "usuario_invalido"),
    usuarios.NegocioDesconocido: (404, "negocio_desconocido"),
    usuarios.UltimoAdministrador: (409, "ultimo_administrador"),
    usuarios.ClaveDeOtroNegocio: (409, "clave_de_otro_negocio"),
}


def _respuesta(status: int, codigo: str, mensaje: str, extra: dict | None = None) -> JSONResponse:
    return JSONResponse({"codigo": codigo, "mensaje": mensaje, **(extra or {})}, status_code=status)


def _citas_en_conflicto(citas: list[dict]) -> list[dict]:
    return [{"id": c["id"], "estado": c["estado"], "inicio": c["rango"].lower.astimezone(clock.TZ).isoformat(),
             "fin": c["rango"].upper.astimezone(clock.TZ).isoformat(), "servicio": c["servicio"],
             "paciente_id": c["paciente_id"], "paciente": c["paciente"]} for c in citas]


def registrar_errores(app: FastAPI) -> None:
    """Todas las respuestas de error de /api/v1 tienen la misma forma: código estable y mensaje en español."""

    def en_api(request: Request) -> bool:
        return request.url.path.startswith(PREFIJO)

    @app.exception_handler(ApiError)
    async def _api(request: Request, e: ApiError):
        return _respuesta(e.status, e.codigo, e.mensaje, e.extra)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, e: RequestValidationError):
        if not en_api(request):
            from fastapi.exception_handlers import request_validation_exception_handler
            return await request_validation_exception_handler(request, e)
        campos = ", ".join(sorted({".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]) for err in e.errors()}))
        return _respuesta(422, "datos_invalidos", f"Revisa los datos enviados ({campos}).")

    for tipo, (status, codigo) in TRADUCCION.items():
        def _make(status=status, codigo=codigo):
            async def handler(request: Request, e: Exception):
                if not en_api(request):
                    raise e
                extra = {"citas": _citas_en_conflicto(e.citas)} if isinstance(e, horario.BlockConflict) else None
                mensaje = str(e) or "No se pudo completar la operación"
                if isinstance(e, horario.BlockConflict):
                    mensaje = "Ese rango tiene citas vivas. Muévelas o cancélalas y vuelve a intentarlo."
                elif isinstance(e, usuarios.InicioBloqueado):
                    mensaje = "Demasiados intentos fallidos. Intenta de nuevo en unos minutos."
                return _respuesta(status, codigo, mensaje, extra)
            return handler
        app.add_exception_handler(tipo, _make())


def solo_json(request: Request) -> None:
    """Las peticiones que modifican solo aceptan cuerpo JSON (junto con SameSite=Lax evita envíos desde otros sitios)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        tiene_cuerpo = request.headers.get("content-length", "0") not in ("", "0") or "transfer-encoding" in request.headers
        if tiene_cuerpo and not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise ApiError(422, "solo_json", "Esta operación solo acepta cuerpo JSON.")


def usuario_sin_negocio(request: Request, conn=Depends(get_conn)) -> dict:
    """Sesión válida, con o sin negocio elegido (para ver la sesión, elegir negocio y salir)."""
    token = request.cookies.get(COOKIE)
    u = usuarios.usuario_de_sesion(conn, token)
    if u is None:
        raise ApiError(401, "no_autenticado", "Inicia sesión para continuar.")
    request.state.token = token
    request.state.usuario_id, request.state.negocio_id = u["id"], u["negocio_id"]
    return u


def _con_negocio(u: dict) -> dict:
    if u["negocio_id"] is None:
        raise ApiError(409, "negocio_requerido", "Elige el negocio con el que vas a trabajar.")
    if u["debe_cambiar_clave"]:
        raise ApiError(403, "cambio_de_clave_requerido", "Debes cambiar tu contraseña temporal para continuar.")
    return u


def usuario_actual(u: dict = Depends(usuario_sin_negocio)) -> dict:
    """Sesión válida con un negocio activo, ya fijado en la conexión: de él sale todo lo que la base deja ver."""
    return _con_negocio(u)


def usuario_sin_conexion(request: Request) -> dict:
    """Lo mismo que `usuario_actual`, pero la conexión que valida la sesión se abre y se cierra aquí mismo: la ruta que la usa
    no retiene ninguna conexión mientras espera (por ejemplo, la respuesta de un modelo). No fija nada en el estado de la petición
    salvo lo que necesita el registro."""
    token = request.cookies.get(COOKIE)
    conn = db.connect(negocio=None)
    try:
        u = usuarios.usuario_de_sesion(conn, token)
        conn.commit()
    finally:
        conn.close()
    if u is None:
        raise ApiError(401, "no_autenticado", "Inicia sesión para continuar.")
    request.state.token = token
    request.state.usuario_id, request.state.negocio_id = u["id"], u["negocio_id"]
    return _con_negocio(u)


def administrador(u: dict = Depends(usuario_actual)) -> dict:
    permisos.exigir_administrador(u)
    return u


def auxiliar(u: dict = Depends(usuario_actual)) -> dict:
    permisos.exigir_auxiliar(u)
    return u


def a_bogota(d: datetime) -> datetime:
    """Una hora sin zona se interpreta como hora de Bogotá."""
    return d.replace(tzinfo=clock.TZ) if d.tzinfo is None else d.astimezone(clock.TZ)


def inicio(r: dict) -> datetime | None:
    return r["rango"].lower if r.get("rango") else None


def fin(r: dict) -> datetime | None:
    return r["rango"].upper if r.get("rango") else None


def auditar(accion: str):
    """Dependencia de ruta: deja una fila en el registro de accesos por cada consulta de datos de un paciente o una cita."""
    def dep(request: Request, conn=Depends(get_conn), u: dict = Depends(usuario_actual)) -> None:
        from .. import privacidad
        pp = request.path_params
        privacidad.registrar(conn, u["id"], accion, pp.get("paciente_id"), pp.get("cita_id"),
                             f"{request.method} {request.scope['route'].path}" if request.scope.get("route") else None)
    return Depends(dep)
