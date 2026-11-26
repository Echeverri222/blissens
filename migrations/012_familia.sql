-- Familia (docs/prd-familia.md): un paciente responsable gestiona las citas de sus familiares desde su enlace.
alter table paciente add column responsable_id bigint references paciente(id) on delete set null;
alter table paciente add column parentesco text check (parentesco in ('hijo','pareja','padre','otro'));
alter table paciente add column consentimiento_por bigint references paciente(id) on delete set null;
alter table paciente add constraint paciente_responsable_no_propio check (responsable_id <> id);
create index paciente_responsable on paciente(negocio_id, responsable_id) where responsable_id is not null;
