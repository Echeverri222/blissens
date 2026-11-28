"""Migración 021: la valoración de 45 min y el horario de 8 a 17 solo reemplazan lo que seguía en el valor anterior."""
from estudia import db, migrate

from .conftest import ADMIN

VIEJO = (("07:30", "12:00"), ("13:00", "17:30"))
NUEVO = (("08:00", "12:00"), ("13:00", "17:00"))


def _horario(c, pid):
    return sorted((r["dia_semana"], r["desde"].strftime("%H:%M"), r["hasta"].strftime("%H:%M"))
                  for r in c.execute("select * from horario_atencion where profesional_id=%s", (pid,)))


def _semana(franjas):
    return sorted((d, a, b) for d in range(5) for a, b in franjas)


def test_la_migracion_021_cambia_solo_lo_que_sigue_en_el_valor_anterior():
    a = db.connect_admin(ADMIN.rsplit("/", 1)[0] + "/postgres")
    a.autocommit = True
    a.execute("drop database if exists estudia_mig_021")
    a.execute("create database estudia_mig_021")
    url = ADMIN.rsplit("/", 1)[0] + "/estudia_mig_021"
    try:
        migrate.run(url, hasta="020")
        c = db.connect_admin(url)
        c.execute("insert into servicio(negocio_id, nombre, duracion_min) values (1,'Valoración o revisión',30),(1,'Limpieza',30)")
        pro = {}
        for nombre in ("por_defecto", "editado"):
            pro[nombre] = c.execute("insert into profesional(negocio_id, nombre, especialidad) values (1,%s,'G') returning id",
                                    (nombre,)).fetchone()["id"]
        for dia in range(5):
            for desde, hasta in VIEJO:
                c.execute("insert into horario_atencion(negocio_id, profesional_id, dia_semana, desde, hasta) values (1,%s,%s,%s,%s)",
                          (pro["por_defecto"], dia, desde, hasta))
        for dia in range(5):  # el viernes cierra media hora antes: está editado
            for desde, hasta in VIEJO:
                c.execute("insert into horario_atencion(negocio_id, profesional_id, dia_semana, desde, hasta) values (1,%s,%s,%s,%s)",
                          (pro["editado"], dia, desde, "17:00" if (dia == 4 and hasta == "17:30") else hasta))
        editado_antes = _horario(c, pro["editado"])
        c.commit()
        assert migrate.run(url) == ["021_duraciones_y_horario.sql"]
        dur = {r["nombre"]: r["duracion_min"] for r in c.execute("select nombre, duracion_min from servicio")}
        assert dur == {"Valoración o revisión": 45, "Limpieza": 30}
        assert _horario(c, pro["por_defecto"]) == _semana(NUEVO)
        assert _horario(c, pro["editado"]) == editado_antes
        c.close()
        migrate.bajar(url, 1)
        c = db.connect_admin(url)
        assert c.execute("select duracion_min from servicio where nombre='Valoración o revisión'").fetchone()["duracion_min"] == 30
        assert _horario(c, pro["por_defecto"]) == _semana(VIEJO)
        c.close()
    finally:
        a.execute("drop database if exists estudia_mig_021")
