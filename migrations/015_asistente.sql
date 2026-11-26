-- Asistente (docs/prd-asistente.md, §9): conversaciones, mensajes y el consentimiento del paciente al asistente.
create table asistente_conversacion (
    id bigserial primary key,
    negocio_id bigint not null default negocio_activo() references negocio(id),
    perfil text not null check (perfil in ('paciente','especialista','auxiliar')),
    usuario_id bigint references usuario(id) on delete cascade,
    paciente_id bigint,                 -- quien conversa: cada paciente ve solo las suyas
    creada_en timestamptz not null default now(),
    ultima_en timestamptz not null default now(),
    constraint asistente_conversacion_un_actor check ((usuario_id is null) <> (paciente_id is null)),
    constraint asistente_conversacion_perfil_actor check ((perfil = 'paciente') = (paciente_id is not null)),
    constraint asistente_conversacion_negocio_id_uq unique (negocio_id, id),
    constraint asistente_conversacion_paciente_neg_fkey foreign key (negocio_id, paciente_id)
        references paciente(negocio_id, id) on delete cascade
);
create index asistente_conversacion_usuario_idx on asistente_conversacion(negocio_id, usuario_id, ultima_en desc);
create index asistente_conversacion_paciente_idx on asistente_conversacion(negocio_id, paciente_id, ultima_en desc);

create table asistente_mensaje (
    id bigserial primary key,
    negocio_id bigint not null default negocio_activo() references negocio(id),
    conversacion_id bigint not null,
    rol text not null check (rol in ('user','assistant','fallo')),  -- 'fallo': un intento que no dejó turno, solo sus tokens
    contenido jsonb not null,           -- el turno tal como lo devolvió el modelo (lista de bloques), sin editar
    tokens_entrada integer not null default 0,
    tokens_salida integer not null default 0,
    creado_en timestamptz not null default now(),
    constraint asistente_mensaje_conversacion_neg_fkey foreign key (negocio_id, conversacion_id)
        references asistente_conversacion(negocio_id, id) on delete cascade
);
create index asistente_mensaje_conversacion_idx on asistente_mensaje(negocio_id, conversacion_id, id);
create index asistente_mensaje_dia_idx on asistente_mensaje(negocio_id, creado_en);

alter table asistente_conversacion enable row level security;
alter table asistente_conversacion force row level security;
create policy aislamiento on asistente_conversacion using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on asistente_conversacion to estudia_app;
grant usage, select on sequence asistente_conversacion_id_seq to estudia_app;

alter table asistente_mensaje enable row level security;
alter table asistente_mensaje force row level security;
create policy aislamiento on asistente_mensaje using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on asistente_mensaje to estudia_app;
grant usage, select on sequence asistente_mensaje_id_seq to estudia_app;

alter table paciente add column acepta_asistente boolean not null default false;
alter table paciente add column consentimiento_asistente_en timestamptz;
alter table paciente add column consentimiento_asistente_por bigint references paciente(id) on delete set null;
