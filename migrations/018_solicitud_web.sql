-- Solicitudes del sitio web con datos propios (antes iban todos en `nota`), fotos adjuntas, avisos por correo y el
-- paciente al que la recepción la vincula. Las solicitudes que vienen de un paciente (familia, asistente) no cambian.
alter table solicitud_contacto
    add column origen text not null default 'paciente' check (origen in ('paciente','sitio')),
    add column interes text check (interes in ('evaluacion_virtual','experiencia','contacto')),
    add column idioma text check (idioma in ('es','en')),
    add column nombre text,
    add column correo text,
    add column pais text,
    add column paquete text,
    add column mensaje text,
    add column paciente_id bigint,
    add column aviso_enviado_en timestamptz,   -- correo a la clínica
    add column acuse_enviado_en timestamptz,   -- correo de «recibimos tu solicitud» a quien la envió
    add constraint solicitud_contacto_paciente_neg_fkey foreign key (negocio_id, paciente_id)
        references paciente(negocio_id, id);
create index solicitud_contacto_paciente_idx on solicitud_contacto(negocio_id, paciente_id) where paciente_id is not null;
create index solicitud_contacto_correo_idx on solicitud_contacto(negocio_id, correo) where correo is not null;

-- Las que ya existen: se leen de la nota con el mismo formato que usaba el panel.
update solicitud_contacto set
    origen = 'sitio',
    interes = case when nota like 'Sitio web · Evaluación virtual%' then 'evaluacion_virtual'
                   when nota like 'Sitio web · Experiencia%' then 'experiencia' else 'contacto' end,
    idioma = coalesce((regexp_match(nota, '· idioma (es|en)'))[1], 'es'),
    nombre = (regexp_match(nota, '\| Nombre: ([^|]*?)( \||$)'))[1],
    correo = (regexp_match(nota, '\| Correo: ([^|]*?)( \||$)'))[1],
    pais = (regexp_match(nota, '\| País: ([^|]*?)( \||$)'))[1],
    paquete = case (regexp_match(nota, '^Sitio web · Experiencia · ([^·|]*?) ·'))[1]
                  when 'Premium (hotel)' then 'premium' when 'Standard (Airbnb)' then 'standard'
                  when 'Essential (transporte)' then 'essential' end,
    mensaje = (regexp_match(nota, ' \| Mensaje: (.*)$'))[1],
    aviso_enviado_en = momento, acuse_enviado_en = momento   -- no se avisa ahora de lo viejo
where documento = '—' or nota like 'Sitio web ·%';

create table solicitud_adjunto (
    id bigserial primary key,
    negocio_id bigint not null default negocio_activo() references negocio(id),
    solicitud_id bigint not null,
    nombre text not null,
    tipo text not null check (tipo in ('image/jpeg','image/png','image/webp','application/pdf')),
    tamano integer not null check (tamano > 0 and tamano <= 5242880),
    datos bytea not null,
    creado_en timestamptz not null default now(),
    constraint solicitud_adjunto_negocio_id_uq unique (negocio_id, id),
    constraint solicitud_adjunto_solicitud_neg_fkey foreign key (negocio_id, solicitud_id)
        references solicitud_contacto(negocio_id, id) on delete cascade
);
create index solicitud_adjunto_solicitud_idx on solicitud_adjunto(negocio_id, solicitud_id);
alter table solicitud_adjunto enable row level security;
alter table solicitud_adjunto force row level security;
create policy aislamiento on solicitud_adjunto using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, delete on solicitud_adjunto to estudia_app;
grant usage, select on sequence solicitud_adjunto_id_seq to estudia_app;
