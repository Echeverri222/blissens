alter table paciente drop constraint if exists paciente_responsable_id_neg_fkey;
alter table paciente drop constraint if exists paciente_consentimiento_por_neg_fkey;
alter table paciente add constraint paciente_responsable_id_fkey
    foreign key (responsable_id) references paciente(id) on delete set null;
alter table paciente add constraint paciente_consentimiento_por_fkey
    foreign key (consentimiento_por) references paciente(id) on delete set null;
