-- Prospectos (docs/adr/0010-prospectos-sin-documento.md): quien escribe desde el sitio, sobre todo desde el exterior, queda como una
-- ficha ligera de `paciente` sin documento (nombre, correo o WhatsApp, país y su autorización). La recepción le pone el
-- documento cuando llega a la clínica y pasa a paciente. `documento`, `celular` y `correo` ya admitían nulo.
alter table paciente add column etapa text not null default 'paciente' check (etapa in ('prospecto','paciente'));
-- Un prospecto se puede contactar por algo y todavía no tiene documento.
alter table paciente add constraint paciente_prospecto_contacto
    check (etapa <> 'prospecto' or (documento is null and (correo is not null or celular is not null)));
-- El registro desde el sitio web (no solo en inglés) marca el segmento internacional.
alter table paciente drop constraint paciente_segmento_origen_check;
alter table paciente add constraint paciente_segmento_origen_check
    check (segmento_origen in ('recepcion','importacion','sitio_en','sitio_web'));

-- De-duplicación: por correo (sin importar mayúsculas) y por los dígitos del WhatsApp.
create index paciente_correo_idx on paciente(negocio_id, lower(correo)) where correo is not null;
create index paciente_celular_digitos_idx on paciente(negocio_id, (regexp_replace(celular, '\D', '', 'g')))
    where celular is not null;

-- Las solicitudes del sitio que aún no tienen paciente y dejaron correo: se vinculan al paciente que ya tiene ese correo
-- o, si no hay, a un prospecto nuevo por correo. Las que solo dejaron WhatsApp se quedan sueltas (la recepción las vincula).
update solicitud_contacto s set paciente_id = (
        select min(p.id) from paciente p where p.negocio_id = s.negocio_id and lower(p.correo) = lower(s.correo))
    where s.origen = 'sitio' and s.paciente_id is null and s.correo is not null;

with grupos as (
    select negocio_id, lower(correo) as correo,
           (array_agg(nombre order by id desc) filter (where nombre is not null))[1] as nombre,
           (array_agg(nullif(celular, '') order by id desc) filter (where nullif(celular, '') is not null))[1] as celular,
           min(momento) as primera
    from solicitud_contacto
    where origen = 'sitio' and paciente_id is null and correo is not null
    group by negocio_id, lower(correo)
), nuevos as (
    insert into paciente(negocio_id, nombres, correo, celular, etapa, internacional, segmento_origen, segmento_marcado_en,
                         consentimiento_en, creado_en)
    select negocio_id, coalesce(nombre, correo), correo, celular, 'prospecto', true, 'sitio_web', primera, primera, primera
    from grupos
    returning id, negocio_id, correo
)
update solicitud_contacto s set paciente_id = n.id
    from nuevos n
    where s.negocio_id = n.negocio_id and lower(s.correo) = n.correo and s.origen = 'sitio' and s.paciente_id is null;
