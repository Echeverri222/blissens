drop index if exists paciente_responsable;
alter table paciente drop constraint if exists paciente_responsable_no_propio;
alter table paciente drop column consentimiento_por;
alter table paciente drop column parentesco;
alter table paciente drop column responsable_id;
