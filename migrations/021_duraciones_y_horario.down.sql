-- Devuelve los valores anteriores solo donde siguen en el valor nuevo por defecto.
update servicio set duracion_min = 30 where nombre = 'Valoración o revisión' and duracion_min = 45;

with nuevo(dia, desde, hasta) as (
    select d, h.desde::time, h.hasta::time from generate_series(0, 4) d, (values ('08:00', '12:00'), ('13:00', '17:00')) h(desde, hasta)
), por_defecto as (
    select p.id from profesional p
    where (select count(*) from horario_atencion h where h.profesional_id = p.id) = 10
      and not exists (select 1 from horario_atencion h where h.profesional_id = p.id
                      and not exists (select 1 from nuevo v where v.dia = h.dia_semana and v.desde = h.desde and v.hasta = h.hasta))
      and (select count(distinct (h.dia_semana, h.desde, h.hasta)) from horario_atencion h where h.profesional_id = p.id) = 10
), borradas as (
    delete from horario_atencion where profesional_id in (select id from por_defecto) returning profesional_id
)
insert into horario_atencion(profesional_id, dia_semana, desde, hasta, negocio_id)
select p.id, d, h.desde::time, h.hasta::time, p.negocio_id
from (select distinct profesional_id as id from borradas) b join profesional p on p.id = b.id,
     generate_series(0, 4) d, (values ('07:30', '12:00'), ('13:00', '17:30')) h(desde, hasta);
