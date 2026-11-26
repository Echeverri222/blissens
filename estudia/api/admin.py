"""Administración del negocio activo: usuarios y accesos. Solo administradores (y nunca de otro negocio)."""
from fastapi import APIRouter, Depends

from .. import config, permisos, usuarios
from . import schemas as sc
from .comun import administrador, get_conn, solo_json

router = APIRouter(prefix="/admin", dependencies=[Depends(solo_json)])


def _fila(conn, acceso_id: int) -> sc.UsuarioAdmin:
    return next(_a_salida(r) for r in usuarios.listar(conn) if r["acceso_id"] == acceso_id)


def _a_salida(r: dict) -> sc.UsuarioAdmin:
    bloqueado = r["bloqueado_hasta"] is not None and r["bloqueado_hasta"] > usuarios._ahora()
    return sc.UsuarioAdmin(**{k: r[k] for k in ("acceso_id", "id", "nombre_usuario", "nombre", "rol", "activo",
                                                 "administrador", "profesional_id", "ultimo_acceso")}, bloqueado=bloqueado)


@router.get("/usuarios", tags=["Administración"], summary="Usuarios con acceso a este negocio",
            response_model=list[sc.UsuarioAdmin])
def listar(conn=Depends(get_conn), u=Depends(administrador)):
    return [_a_salida(r) for r in usuarios.listar(conn)]


@router.post("/usuarios", tags=["Administración"], summary="Crear un usuario con contraseña temporal",
             response_model=sc.UsuarioConClave, status_code=201,
             description="La contraseña temporal solo se devuelve aquí; al ingresar, la persona debe cambiarla.")
def crear(datos: sc.NuevoUsuario, conn=Depends(get_conn), u=Depends(administrador)):
    clave = usuarios.clave_temporal()
    uid = usuarios.crear(conn, datos.usuario, datos.nombre, clave, datos.rol, datos.profesional_id, datos.administrador)
    usuarios.marcar_clave_temporal(conn, uid)
    acceso = conn.execute("select id from acceso where usuario_id=%s", (uid,)).fetchone()["id"]
    return sc.UsuarioConClave(usuario=_fila(conn, acceso), clave_temporal=clave)


@router.put("/usuarios/{acceso_id}", tags=["Administración"], summary="Cambiar rol, profesional o administración",
            response_model=sc.UsuarioAdmin)
def cambiar(acceso_id: int, datos: sc.CambioAcceso, conn=Depends(get_conn), u=Depends(administrador)):
    usuarios.actualizar_acceso(conn, acceso_id, datos.rol, datos.profesional_id, datos.administrador)
    return _fila(conn, acceso_id)


@router.post("/usuarios/{acceso_id}/desactivar", tags=["Administración"], summary="Quitar el acceso a este negocio",
             response_model=sc.UsuarioAdmin, description="Pierde el acceso de inmediato; no se puede desactivar al último administrador.")
def desactivar(acceso_id: int, conn=Depends(get_conn), u=Depends(administrador)):
    usuarios.desactivar(conn, usuarios.nombre_de_acceso(conn, acceso_id))
    return _fila(conn, acceso_id)


@router.post("/usuarios/{acceso_id}/activar", tags=["Administración"], summary="Devolver el acceso y desbloquear",
             response_model=sc.UsuarioAdmin)
def activar(acceso_id: int, conn=Depends(get_conn), u=Depends(administrador)):
    usuarios.activar(conn, usuarios.nombre_de_acceso(conn, acceso_id))
    return _fila(conn, acceso_id)


@router.post("/usuarios/{acceso_id}/clave-temporal", tags=["Administración"],
             summary="Restablecer con una contraseña temporal", response_model=sc.UsuarioConClave,
             description="Cierra sus sesiones. Si la persona tiene acceso a otro negocio, responde 409.")
def clave_temporal(acceso_id: int, conn=Depends(get_conn), u=Depends(administrador)):
    clave = usuarios.clave_temporal()
    usuarios.restablecer_clave(conn, usuarios.nombre_de_acceso(conn, acceso_id), clave, temporal=True)
    return sc.UsuarioConClave(usuario=_fila(conn, acceso_id), clave_temporal=clave)


@router.put("/servicios/{servicio_id}", tags=["Administración"], summary="Fijar el valor promedio de un servicio",
            response_model=sc.ServicioOut,
            description="Pesos; `null` lo quita. Sirve para estimar el dinero perdido en los indicadores, no es una factura.")
def valor_servicio(servicio_id: int, datos: sc.ValorServicio, conn=Depends(get_conn), u=Depends(administrador)):
    s = conn.execute("update servicio set valor=%s where id=%s returning id, nombre, duracion_min, autoagendable, "
                     "valor::bigint as valor", (datos.valor, servicio_id)).fetchone()
    if s is None:
        raise permisos.NoExiste("No existe ese servicio")
    return s


@router.get("/metas", tags=["Administración"], summary="Metas vigentes de los indicadores",
            response_model=dict[str, dict[str, float]])
def ver_metas(conn=Depends(get_conn), u=Depends(administrador)):
    return config.get(conn, "metas_indicadores")


@router.put("/metas", tags=["Administración"], summary="Fijar las metas de los indicadores",
            response_model=dict[str, dict[str, float]],
            description="Reemplaza todas las metas. Cada una es opcional; un indicador sin meta no se evalúa.")
def metas(datos: sc.Metas, conn=Depends(get_conn), u=Depends(administrador)):
    vigentes = datos.model_dump(exclude_none=True)
    config.set_(conn, "metas_indicadores", vigentes)
    return vigentes
