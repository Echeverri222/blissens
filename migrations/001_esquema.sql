-- Esquema inicial de Estud-IA. PostgreSQL estándar, portable a Supabase.
create extension if not exists btree_gist;

create table paciente (
    id bigserial primary key,
    external_id text unique,
    nombres text not null,
    apellidos text not null default '',
    documento text unique,
    celular text,
    correo text,
    fecha_nacimiento date,
    tipo text check (tipo in ('local','internacional','deportista')),
    acepta_mensajes boolean not null default true,
    consentimiento_en timestamptz,
    creado_en timestamptz not null default now()
);

create table profesional (
    id bigserial primary key,
    nombre text not null,
    especialidad text not null default '',
    activo boolean not null default true,
    external_id text unique
);

create table servicio (
    id bigserial primary key,
    nombre text not null unique,
    duracion_min int not null check (duracion_min > 0),
    autoagendable boolean not null default false,
    admite_adelanto boolean not null default true
);

create table horario_atencion (
    id bigserial primary key,
    profesional_id bigint not null references profesional(id),
    dia_semana int not null check (dia_semana between 0 and 6), -- 0 = lunes
    desde time not null,
    hasta time not null,
    check (hasta > desde)
);

create table bloqueo (
    id bigserial primary key,
    profesional_id bigint not null references profesional(id),
    rango tstzrange not null,
    motivo text not null default ''
);

create table tratamiento (
    id bigserial primary key,
    paciente_id bigint not null references paciente(id),
    profesional_id bigint not null references profesional(id),
    tipo text not null default 'tratamiento' check (tipo in ('diagnostico','tratamiento')),
    sesiones_previstas int,
    estado text not null default 'activo' check (estado in ('activo','finalizado','abandonado')),
    generado_en date not null default current_date,
    external_id text unique
);

create table cita (
    id bigserial primary key,
    paciente_id bigint not null references paciente(id),
    profesional_id bigint not null references profesional(id),
    servicio_id bigint not null references servicio(id),
    tratamiento_id bigint references tratamiento(id),
    dia date not null,
    rango tstzrange, -- nulo en citas históricas importadas sin hora
    estado text not null check (estado in
        ('programada','confirmada','no_confirmada','cancelada','reprogramada','atendida','no_asistio')),
    origen text not null check (origen in ('paciente','auxiliar','sistema','importacion')),
    cita_anterior_id bigint references cita(id),
    datos_origen jsonb not null default '{}',
    external_id text unique,
    creada_en timestamptz not null default now(),
    -- La regla de cruce vive en la base: un profesional no puede tener dos citas vivas que se crucen.
    constraint cita_sin_cruce exclude using gist (profesional_id with =, rango with &&)
        where (estado in ('programada','confirmada','no_confirmada') and rango is not null)
);
create index cita_dia_idx on cita(dia);
create index cita_paciente_idx on cita(paciente_id);
create index cita_estado_idx on cita(estado);

create table historial_estado (
    id bigserial primary key,
    cita_id bigint not null references cita(id),
    estado_anterior text,
    estado_nuevo text not null,
    actor text not null check (actor in ('paciente','auxiliar','sistema')),
    detalle text not null default '',
    momento timestamptz not null,
    revierte_id bigint references historial_estado(id)
);
create index historial_cita_idx on historial_estado(cita_id);

create table motivo_cancelacion (
    id bigserial primary key,
    etiqueta text not null unique,
    orden int not null
);

create table cancelacion (
    id bigserial primary key,
    cita_id bigint not null references cita(id),
    motivo_id bigint references motivo_cancelacion(id),
    texto_libre text,
    canal text not null,
    antelacion_horas numeric not null,
    tardia boolean not null,
    momento timestamptz not null
);
create index cancelacion_cita_idx on cancelacion(cita_id);

create table caso_seguimiento (
    id bigserial primary key,
    tipo text not null check (tipo in ('cancelacion','inasistencia','tratamiento_a_medias')),
    paciente_id bigint not null references paciente(id),
    cita_id bigint references cita(id),
    tratamiento_id bigint references tratamiento(id),
    estado text not null default 'abierto'
        check (estado in ('abierto','reprogramado','rechazado','agotado','anulado')),
    escalado boolean not null default false,
    cita_resultante_id bigint references cita(id),
    abierto_en timestamptz not null,
    cerrado_en timestamptz
);
-- Solo un caso abierto por cita o tratamiento de origen.
create unique index caso_abierto_cita on caso_seguimiento(cita_id) where estado = 'abierto' and cita_id is not null;
create unique index caso_abierto_tratamiento on caso_seguimiento(tratamiento_id)
    where estado = 'abierto' and tratamiento_id is not null;

create table intento (
    id bigserial primary key,
    caso_id bigint not null references caso_seguimiento(id),
    numero int not null,
    canal text not null check (canal in ('automatico','manual')),
    resultado text check (resultado in ('acepto','rechazo','sin_respuesta')),
    momento timestamptz not null,
    detalle text not null default ''
);
create index intento_caso_idx on intento(caso_id);

create table cupo_liberado (
    id bigserial primary key,
    profesional_id bigint not null references profesional(id),
    rango tstzrange not null,
    cita_origen_id bigint references cita(id),
    causa text not null,
    estado text not null default 'abierto' check (estado in ('abierto','en_oferta','ocupado','vacio','anulado')),
    ocupado_por text check (ocupado_por in ('oferta','agendamiento')),
    creado_en timestamptz not null
);
create index cupo_estado_idx on cupo_liberado(estado);

create table oferta_adelanto (
    id bigserial primary key,
    cupo_id bigint not null references cupo_liberado(id),
    cita_id bigint not null references cita(id),
    orden int not null,
    estado text not null default 'pendiente'
        check (estado in ('pendiente','aceptada','rechazada','vencida','anulada')),
    enviada_en timestamptz not null,
    vence_en timestamptz not null,
    respondida_en timestamptz
);
-- Una oferta pendiente a la vez por cupo, garantizado por la base.
create unique index oferta_unica_pendiente on oferta_adelanto(cupo_id) where estado = 'pendiente';
create index oferta_cita_idx on oferta_adelanto(cita_id);

create table plantilla (
    clave text primary key,
    texto text not null,
    tipo text not null default 'botones' check (tipo in ('botones','lista')),
    botones jsonb not null default '[]'
);

create table mensaje (
    id bigserial primary key,
    paciente_id bigint not null references paciente(id),
    direccion text not null check (direccion in ('saliente','entrante')),
    canal text not null default 'simulado',
    plantilla text,
    texto text not null,
    tipo text not null default 'botones',
    botones jsonb not null default '[]',
    respuesta text,
    entidad_tipo text,
    entidad_id bigint,
    estado_entrega text not null default 'entregado'
        check (estado_entrega in ('entregado','diferido','omitido')),
    gestionado boolean not null default true,
    momento timestamptz not null
);
create index mensaje_paciente_idx on mensaje(paciente_id, momento);

create table tarea_programada (
    id bigserial primary key,
    tipo text not null,
    ejecutar_en timestamptz not null,
    datos jsonb not null default '{}',
    estado text not null default 'pendiente' check (estado in ('pendiente','hecha','fallida')),
    intentos int not null default 0,
    error text,
    creada_en timestamptz not null default now()
);
create index tarea_pendiente_idx on tarea_programada(ejecutar_en) where estado = 'pendiente';

create table configuracion (
    clave text primary key,
    valor jsonb not null
);

create table solicitud_contacto (
    id bigserial primary key,
    documento text not null,
    celular text not null,
    nota text not null default '',
    momento timestamptz not null,
    gestionada boolean not null default false
);

create table hecho_diario (
    fecha date not null,
    profesional_id bigint not null references profesional(id),
    servicio_id bigint not null references servicio(id),
    citas int not null default 0,
    atendidas int not null default 0,
    no_asistio int not null default 0,
    canceladas int not null default 0,
    reprogramadas int not null default 0,
    con_recordatorio int not null default 0,
    confirmadas_explicitas int not null default 0,
    minutos_atendidos int not null default 0,
    cancelaciones int not null default 0,
    cancelaciones_tardias int not null default 0,
    cancelaciones_recuperadas int not null default 0,
    motivos jsonb not null default '{}',
    primary key (fecha, profesional_id, servicio_id)
);

create table hecho_diario_profesional (
    fecha date not null,
    profesional_id bigint not null references profesional(id),
    minutos_disponibles int not null default 0,
    cupos_liberados int not null default 0,
    cupos_ocupados_oferta int not null default 0,
    cupos_ocupados_agendamiento int not null default 0,
    cupos_vacios int not null default 0,
    primary key (fecha, profesional_id)
);
