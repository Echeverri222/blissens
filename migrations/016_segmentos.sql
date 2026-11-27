-- Segmentos de alto valor (ficha del reto, §03): pacientes internacionales y deportistas de alto nivel.
-- Dos marcas en vez de `tipo`: una persona puede ser las dos cosas. Sin marca, paciente regular.
alter table paciente add column internacional boolean not null default false;
alter table paciente add column deportista boolean not null default false;
-- De dónde salió la última marca: la recepción en el panel, la importación del Excel o el registro en el sitio en inglés.
alter table paciente add column segmento_origen text check (segmento_origen in ('recepcion','importacion','sitio_en'));
alter table paciente add column segmento_marcado_en timestamptz;
alter table paciente add column segmento_marcado_por bigint references usuario(id) on delete set null;
update paciente set internacional = coalesce(tipo = 'internacional', false), deportista = coalesce(tipo = 'deportista', false),
    segmento_origen = case when tipo in ('internacional','deportista') then 'importacion' end;
alter table paciente drop column tipo;
