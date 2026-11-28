-- H-11: las referencias familiares de paciente deben validar pertenencia al mismo negocio (ADR-0001).
alter table paciente drop constraint if exists paciente_responsable_id_fkey;
alter table paciente drop constraint if exists paciente_consentimiento_por_fkey;
alter table paciente add constraint paciente_responsable_id_neg_fkey
    foreign key (negocio_id, responsable_id) references paciente(negocio_id, id) on delete set null (responsable_id);
alter table paciente add constraint paciente_consentimiento_por_neg_fkey
    foreign key (negocio_id, consentimiento_por) references paciente(negocio_id, id) on delete set null (consentimiento_por);
