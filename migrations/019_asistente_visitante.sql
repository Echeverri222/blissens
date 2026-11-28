-- Asistente del sitio público (docs/prd-asistente.md, perfil visitante): una conversación puede ser de un visitante anónimo,
-- identificado solo por un id al azar que el servidor guarda en una cookie firmada. No tiene usuario ni paciente.
alter table asistente_conversacion add column visitante text;
alter table asistente_conversacion drop constraint asistente_conversacion_perfil_check;
alter table asistente_conversacion add constraint asistente_conversacion_perfil_check
    check (perfil in ('paciente','especialista','auxiliar','visitante'));
alter table asistente_conversacion drop constraint asistente_conversacion_un_actor;
alter table asistente_conversacion add constraint asistente_conversacion_un_actor
    check (num_nonnulls(usuario_id, paciente_id, visitante) = 1);
alter table asistente_conversacion drop constraint asistente_conversacion_perfil_actor;
alter table asistente_conversacion add constraint asistente_conversacion_perfil_actor
    check ((perfil = 'paciente') = (paciente_id is not null) and (perfil = 'visitante') = (visitante is not null));
create index asistente_conversacion_visitante_idx on asistente_conversacion(negocio_id, visitante, ultima_en desc);
