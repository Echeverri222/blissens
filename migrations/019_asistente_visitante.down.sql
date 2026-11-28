delete from asistente_conversacion where perfil = 'visitante';  -- sus mensajes caen en cascada
drop index asistente_conversacion_visitante_idx;
alter table asistente_conversacion drop constraint asistente_conversacion_perfil_actor;
alter table asistente_conversacion add constraint asistente_conversacion_perfil_actor check ((perfil = 'paciente') = (paciente_id is not null));
alter table asistente_conversacion drop constraint asistente_conversacion_un_actor;
alter table asistente_conversacion add constraint asistente_conversacion_un_actor check ((usuario_id is null) <> (paciente_id is null));
alter table asistente_conversacion drop constraint asistente_conversacion_perfil_check;
alter table asistente_conversacion add constraint asistente_conversacion_perfil_check check (perfil in ('paciente','especialista','auxiliar'));
alter table asistente_conversacion drop column visitante;
