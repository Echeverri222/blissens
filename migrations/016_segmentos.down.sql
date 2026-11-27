alter table paciente add column tipo text check (tipo in ('local','internacional','deportista'));
update paciente set tipo = case when internacional then 'internacional' when deportista then 'deportista' else 'local' end;
alter table paciente drop column segmento_marcado_por;
alter table paciente drop column segmento_marcado_en;
alter table paciente drop column segmento_origen;
alter table paciente drop column deportista;
alter table paciente drop column internacional;
