"""Recuperación: detección diaria de tratamientos a medias (RF-25)."""
from datetime import datetime

from . import clock, config, followup
from .lifecycle import ALIVE


def at_risk(conn, now: datetime | None = None, profesional_id: int | None = None, servicio_id: int | None = None) -> list[dict]:
    """Tratamientos activos, sin cita futura, con más días que el umbral desde la última cita. Primero los pacientes de
    alto valor (internacionales y deportistas), después los de más días sin cita.
    Con `servicio_id` quedan los tratamientos cuyo paciente tuvo citas de ese servicio con ese profesional."""
    now = now or clock.now(conn)
    threshold = config.get(conn, "dias_riesgo")
    return conn.execute(
        """
        select t.id as tratamiento_id, t.paciente_id, t.profesional_id, p.nombres, p.apellidos,
               max(c.dia) as ultima_cita, (%(hoy)s::date - max(c.dia)) as dias_sin_cita,
               (select cs.id from caso_seguimiento cs where cs.tratamiento_id = t.id and cs.estado = 'abierto') as caso_id,
               p.celular, p.internacional, p.deportista,
               (select s.nombre from cita u join servicio s on s.id = u.servicio_id where u.paciente_id = t.paciente_id
                  and u.profesional_id = t.profesional_id order by u.dia desc, u.id desc limit 1) as servicio
        from tratamiento t
        join paciente p on p.id = t.paciente_id
        join cita c on c.paciente_id = t.paciente_id and c.profesional_id = t.profesional_id
        where t.estado = 'activo'
          and (%(pro)s::int is null or t.profesional_id = %(pro)s)
          and (%(srv)s::int is null or exists (select 1 from cita fs where fs.paciente_id = t.paciente_id
               and fs.profesional_id = t.profesional_id and fs.servicio_id = %(srv)s))
        group by t.id, p.id
        having (%(hoy)s::date - max(c.dia)) > %(umbral)s
           and not exists (select 1 from cita f where f.paciente_id = t.paciente_id and f.profesional_id = t.profesional_id
                           and f.estado = any(%(alive)s) and f.rango is not null and lower(f.rango) > %(now)s)
        order by (p.internacional or p.deportista) desc, dias_sin_cita desc
        """,
        {"hoy": now.date(), "umbral": threshold, "alive": list(ALIVE), "now": now,
         "pro": profesional_id, "srv": servicio_id}).fetchall()


def detect(conn, now: datetime | None = None) -> int:
    """Abre un caso 'tratamiento a medias' por cada tratamiento en riesgo, sin duplicar."""
    opened = 0
    for r in at_risk(conn, now):
        if r["caso_id"] is None:
            if followup.open_case(conn, "tratamiento_a_medias", r["paciente_id"], tratamiento_id=r["tratamiento_id"]):
                opened += 1
    return opened
