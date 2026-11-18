-- Usuarios, sesiones y trazabilidad de quién hizo cada cambio (PRD #2).

create table usuario (
    id bigserial primary key,
    nombre_usuario text not null,
    nombre text not null,
    clave_hash text not null,
    rol text not null check (rol in ('auxiliar','especialista')),
    profesional_id bigint references profesional(id),
    activo boolean not null default true,
    intentos_fallidos int not null default 0,
    bloqueado_hasta timestamptz,
    creado_en timestamptz not null default now(),
    ultimo_acceso timestamptz,
    -- Un especialista siempre está ligado a un profesional; una auxiliar nunca.
    check ((rol = 'especialista') = (profesional_id is not null))
);
create unique index usuario_nombre_unico on usuario (lower(nombre_usuario));
create unique index usuario_profesional_unico on usuario (profesional_id) where profesional_id is not null;

create table sesion (
    huella text primary key,            -- sha256 del identificador de la cookie; el valor nunca se guarda
    usuario_id bigint not null references usuario(id) on delete cascade,
    creada_en timestamptz not null default now(),
    vence_en timestamptz not null
);
create index sesion_usuario_idx on sesion(usuario_id);

alter table historial_estado drop constraint historial_estado_actor_check;
alter table historial_estado add constraint historial_estado_actor_check
    check (actor in ('paciente','auxiliar','especialista','sistema'));
alter table historial_estado add column usuario_id bigint references usuario(id) on delete set null;

alter table bloqueo add column creado_por bigint references usuario(id) on delete set null;
alter table bloqueo add column creado_en timestamptz not null default now();
create index bloqueo_profesional_idx on bloqueo using gist (profesional_id, rango);
