-- Multi-negocio, paso 1-2 (ampliar): negocio, negocio_id en toda tabla de negocio y accesos. No quita nada.
create table negocio (
    id bigserial primary key,
    nombre_corto text not null unique check (nombre_corto ~ '^[a-z0-9][a-z0-9-]*$'),
    nombre text not null,
    zona_horaria text not null default 'America/Bogota',
    activo boolean not null default true,
    creado_en timestamptz not null default now()
);
insert into negocio(id, nombre_corto, nombre) values (1, 'blissens', 'Blissens Odontología');
select setval(pg_get_serial_sequence('negocio','id'), 1);

alter table paciente add column negocio_id bigint not null default 1 references negocio(id);
alter table profesional add column negocio_id bigint not null default 1 references negocio(id);
alter table servicio add column negocio_id bigint not null default 1 references negocio(id);
alter table horario_atencion add column negocio_id bigint not null default 1 references negocio(id);
alter table bloqueo add column negocio_id bigint not null default 1 references negocio(id);
alter table tratamiento add column negocio_id bigint not null default 1 references negocio(id);
alter table cita add column negocio_id bigint not null default 1 references negocio(id);
alter table historial_estado add column negocio_id bigint not null default 1 references negocio(id);
alter table motivo_cancelacion add column negocio_id bigint not null default 1 references negocio(id);
alter table cancelacion add column negocio_id bigint not null default 1 references negocio(id);
alter table caso_seguimiento add column negocio_id bigint not null default 1 references negocio(id);
alter table intento add column negocio_id bigint not null default 1 references negocio(id);
alter table cupo_liberado add column negocio_id bigint not null default 1 references negocio(id);
alter table oferta_adelanto add column negocio_id bigint not null default 1 references negocio(id);
alter table plantilla add column negocio_id bigint not null default 1 references negocio(id);
alter table mensaje add column negocio_id bigint not null default 1 references negocio(id);
alter table tarea_programada add column negocio_id bigint not null default 1 references negocio(id);
alter table configuracion add column negocio_id bigint not null default 1 references negocio(id);
alter table solicitud_contacto add column negocio_id bigint not null default 1 references negocio(id);
alter table hecho_diario add column negocio_id bigint not null default 1 references negocio(id);
alter table hecho_diario_profesional add column negocio_id bigint not null default 1 references negocio(id);

create table canal_negocio (
    id bigserial primary key,
    negocio_id bigint not null default 1 references negocio(id),
    tipo text not null,
    id_externo text not null,
    secreto_ref text,
    activo boolean not null default true,
    unique (tipo, id_externo)
);
create table auditoria_acceso (
    id bigserial primary key,
    negocio_id bigint not null default 1 references negocio(id),
    momento timestamptz not null default now(),
    usuario_id bigint,
    accion text not null,
    paciente_id bigint,
    cita_id bigint,
    peticion text
);
create index auditoria_acceso_idx on auditoria_acceso(negocio_id, momento);

alter table usuario add column debe_cambiar_clave boolean not null default false;
alter table servicio add column activo boolean not null default true;
alter table mensaje add column id_externo text;
alter table paciente add column consentimiento_version text;
alter table sesion add column negocio_id bigint references negocio(id);

create table acceso (
    id bigserial primary key,
    usuario_id bigint not null references usuario(id) on delete cascade,
    negocio_id bigint not null references negocio(id),
    rol text not null check (rol in ('auxiliar','especialista')),
    profesional_id bigint,
    administrador boolean not null default false,
    activo boolean not null default true,
    creado_en timestamptz not null default now(),
    unique (usuario_id, negocio_id),
    check ((rol = 'especialista') = (profesional_id is not null))
);
create unique index acceso_profesional_unico on acceso(negocio_id, profesional_id) where profesional_id is not null;
create index acceso_negocio_idx on acceso(negocio_id);

-- Relleno idempotente: un acceso a Blissens por cada usuario, con su rol y su profesional.
insert into acceso(usuario_id, negocio_id, rol, profesional_id, activo)
select id, 1, rol, profesional_id, activo from usuario
on conflict (usuario_id, negocio_id) do nothing;
