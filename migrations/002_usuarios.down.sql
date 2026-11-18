alter table bloqueo drop column if exists creado_por, drop column if exists creado_en;
alter table historial_estado drop column if exists usuario_id;
alter table historial_estado drop constraint if exists historial_estado_actor_check;
alter table historial_estado add constraint historial_estado_actor_check
    check (actor in ('paciente','auxiliar','sistema'));
drop table if exists sesion;
drop table if exists usuario;
