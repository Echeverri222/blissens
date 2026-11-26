"""Ganchos de privacidad (PRD #4, §6.5): registro de accesos, retención, exportar y anonimizar un paciente.

No es asesoría legal; deja listo el terreno para lo que la empresa y su asesor validen (habeas data, Ley 1581 de 2012).
"""
import json
from datetime import timedelta

from . import bandejas, clock, config, permisos

ANONIMO = "Paciente anonimizado"


def registrar(conn, usuario_id: int | None, accion: str, paciente_id: int | None = None, cita_id: int | None = None,
              peticion: str | None = None) -> None:
    """Una fila por consulta de datos de un paciente. El texto buscado NO se guarda."""
    conn.execute("insert into auditoria_acceso(usuario_id, accion, paciente_id, cita_id, peticion) values (%s,%s,%s,%s,%s)",
                 (usuario_id, accion, paciente_id, cita_id, peticion))


def exportar_paciente(conn, paciente_id: int) -> dict:
    """Todo lo que el sistema guarda de un paciente, en una estructura lista para entregarle."""
    if not conn.execute("select 1 from paciente where id=%s", (paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    r = bandejas.patient_record(conn, paciente_id)
    extra = {
        "ofertas": conn.execute("select o.* from oferta_adelanto o join cita c on c.id=o.cita_id where c.paciente_id=%s order by o.id",
                             (paciente_id,)).fetchall(),
        "accesos": conn.execute("select momento, accion, usuario_id, peticion from auditoria_acceso where paciente_id=%s "
                                "order by id", (paciente_id,)).fetchall(),
    }
    return json.loads(json.dumps({**r, **extra}, default=str))


def anonimizar_paciente(conn, paciente_id: int) -> None:
    """Borra lo que identifica a la persona y conserva los hechos de sus citas para los indicadores."""
    if not conn.execute("select 1 from paciente where id=%s", (paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    conn.execute(
        "update paciente set nombres=%s, apellidos='', documento=null, celular=null, correo=null, fecha_nacimiento=null, "
        "external_id=null, acepta_mensajes=false, acepta_correo=false, consentimiento_correo_en=null where id=%s", (ANONIMO, paciente_id))
    conn.execute("update mensaje set texto='[eliminado]', botones='[]'::jsonb, respuesta=null where paciente_id=%s", (paciente_id,))
    # La familia se deshace: el anonimizado deja de gestionar y de ser gestionado (docs/prd-familia.md, R8).
    conn.execute("update paciente set responsable_id=null, parentesco=null where id=%s or responsable_id=%s",
                 (paciente_id, paciente_id))


def _antes_de(conn, dias):
    return clock.now(conn) - timedelta(days=dias)


def depurar(conn) -> dict:
    """Retención del negocio activo, según su configuración. Por defecto no borra nada."""
    out = {}
    d = config.get(conn, "retencion_mensajes_dias")
    if d:
        out["mensajes"] = conn.execute("delete from mensaje where momento < %s and estado_entrega<>'diferido'",
                                       (_antes_de(conn, d),)).rowcount
    d = config.get(conn, "retencion_tareas_dias")
    if d:
        out["tareas"] = conn.execute("delete from tarea_programada where estado in ('hecha','fallida') and ejecutar_en < %s",
                                     (_antes_de(conn, d),)).rowcount
    return out


def depurar_admin(admin) -> dict:
    """Lo que el rol de aplicación no puede borrar (el registro de accesos solo admite insertar y leer; las sesiones son
    del usuario): lo ejecuta el operador con el rol de administración y el negocio ya fijado."""
    out = depurar(admin)
    d = config.get(admin, "retencion_auditoria_dias")
    if d:
        out["auditoria"] = admin.execute("delete from auditoria_acceso where momento < %s", (_antes_de(admin, d),)).rowcount
    d = config.get(admin, "retencion_sesiones_dias")
    if d:
        out["sesiones"] = admin.execute(
            "delete from sesion where negocio_id=negocio_activo() and vence_en < now() - make_interval(days => %s)", (d,)).rowcount
    return out
