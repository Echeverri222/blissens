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
        "asistente": _conversaciones_del_asistente(conn, paciente_id),
    }
    return json.loads(json.dumps({**r, **extra}, default=str))


def _conversaciones_del_asistente(conn, paciente_id: int) -> list[dict]:
    """Las conversaciones que este paciente tuvo con el asistente, con cada turno tal como se guardó."""
    out = []
    for c in conn.execute("select id, perfil, creada_en, ultima_en from asistente_conversacion where paciente_id=%s order by id",
                          (paciente_id,)).fetchall():
        c["mensajes"] = conn.execute("select rol, contenido, tokens_entrada, tokens_salida, creado_en from asistente_mensaje "
                                     "where conversacion_id=%s order by id", (c["id"],)).fetchall()
        out.append(c)
    return out


def anonimizar_paciente(conn, paciente_id: int) -> None:
    """Borra lo que identifica a la persona y conserva los hechos de sus citas para los indicadores."""
    previo = conn.execute("select documento, celular, responsable_id from paciente where id=%s", (paciente_id,)).fetchone()
    if not previo:
        raise permisos.NoExiste("No existe ese paciente")
    documento, celular = previo["documento"], previo["celular"]
    # Solicitudes de contacto: por su documento; por su celular solo si ningún otro paciente (p. ej. su hogar) lo comparte.
    if documento:
        conn.execute("delete from solicitud_contacto where documento=%s", (documento,))
        # familia.agregar deja el documento de quien lo pidió en la nota de la solicitud de otra persona
        conn.execute("delete from solicitud_contacto where nota like %s", (f"%(documento {documento})%",))
    if celular and not conn.execute("select 1 from paciente where celular=%s and id<>%s limit 1", (celular, paciente_id)).fetchone():
        conn.execute("delete from solicitud_contacto where celular=%s", (celular,))
    conn.execute("update cancelacion set texto_libre=null where cita_id in (select id from cita where paciente_id=%s)",
                 (paciente_id,))
    conn.execute("update intento set detalle='' where caso_id in (select id from caso_seguimiento where paciente_id=%s)",
                 (paciente_id,))
    conn.execute("update paciente set consentimiento_por=null where consentimiento_por=%s", (paciente_id,))
    conn.execute(
        "update paciente set nombres=%s, apellidos='', documento=null, celular=null, correo=null, fecha_nacimiento=null, "
        "external_id=null, acepta_mensajes=false, acepta_correo=false, consentimiento_correo_en=null, internacional=false, "
        "deportista=false, segmento_origen=null, segmento_marcado_en=null, segmento_marcado_por=null where id=%s", (ANONIMO, paciente_id))
    conn.execute("update mensaje set texto='[eliminado]', botones='[]'::jsonb, respuesta=null where paciente_id=%s", (paciente_id,))
    # El asistente: sus conversaciones se borran (con sus mensajes) y el consentimiento se retira, también el que dio por otros.
    conn.execute("delete from asistente_conversacion where paciente_id=%s", (paciente_id,))
    conn.execute("update paciente set acepta_asistente=false, consentimiento_asistente_en=null, consentimiento_asistente_por=null "
                 "where id=%s or consentimiento_asistente_por=%s", (paciente_id, paciente_id))
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
    d = config.get(conn, "retencion_asistente_dias")
    if d:
        borradas = conn.execute("delete from asistente_conversacion where ultima_en < %s", (_antes_de(conn, d),)).rowcount
        if borradas:
            out["asistente"] = borradas
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
