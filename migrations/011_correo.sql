-- Correo (PRD 5): consentimiento propio del paciente, asunto del correo y estado «fallido» del envío.
alter table paciente add column acepta_correo boolean not null default false;
alter table paciente add column consentimiento_correo_en timestamptz;
alter table mensaje add column asunto text;
alter table mensaje drop constraint mensaje_estado_entrega_check;
alter table mensaje add constraint mensaje_estado_entrega_check
    check (estado_entrega in ('entregado','diferido','omitido','fallido'));
