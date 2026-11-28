-- Los prospectos no tienen citas: se desvinculan sus solicitudes y se borran con la ficha.
update solicitud_contacto set paciente_id = null where paciente_id in (select id from paciente where etapa = 'prospecto');
delete from paciente where etapa = 'prospecto';
drop index if exists paciente_celular_digitos_idx;
drop index if exists paciente_correo_idx;
update paciente set segmento_origen = 'sitio_en' where segmento_origen = 'sitio_web';
alter table paciente drop constraint paciente_segmento_origen_check;
alter table paciente add constraint paciente_segmento_origen_check
    check (segmento_origen in ('recepcion','importacion','sitio_en'));
alter table paciente drop constraint paciente_prospecto_contacto;
alter table paciente drop column etapa;
