delete from mensaje where estado_entrega = 'fallido';
alter table mensaje drop constraint mensaje_estado_entrega_check;
alter table mensaje add constraint mensaje_estado_entrega_check
    check (estado_entrega in ('entregado','diferido','omitido'));
alter table mensaje drop column asunto;
alter table paciente drop column consentimiento_correo_en;
alter table paciente drop column acepta_correo;
