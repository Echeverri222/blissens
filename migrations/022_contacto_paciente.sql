-- Reglas de contacto (docs/prd-respuestas-clinica.md, R6 y R8): "No contactar" con su motivo y el estado del celular.
alter table paciente add column no_contactar text check (no_contactar in ('queja','cobro','fallecido','otro'));
alter table paciente add column no_contactar_en timestamptz;
alter table paciente add column no_contactar_por bigint references usuario(id) on delete set null;
alter table paciente add column no_contactar_nota text;

-- Estado del celular: lo fija la validación al guardarlo y lo corrigen el canal (no es WhatsApp) o la recepción.
alter table paciente add column celular_estado text not null default 'sin_verificar'
    check (celular_estado in ('sin_verificar','valido','invalido','sin_whatsapp'));
-- Lo que ya no tiene forma de celular válido (formato internacional) queda marcado desde el principio.
update paciente set celular_estado = 'invalido'
    where celular is not null and regexp_replace(celular, '[^0-9+]', '', 'g') !~ '^\+[0-9]{8,15}$';

-- Por qué un mensaje no salió ('celular': el número no sirve).
alter table mensaje add column detalle text;
