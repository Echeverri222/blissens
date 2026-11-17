-- Multi-negocio, pasos 5-6: rol de aplicación, políticas por fila (RLS), funciones entre negocios.
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'estudia_app') then create role estudia_app login; end if;
end $$;
revoke all on schema public from public;
grant usage on schema public to estudia_app;

create function negocio_activo() returns bigint language sql stable as
    $f$ select nullif(current_setting('app.negocio_id', true), '')::bigint $f$;
create function usuario_activo() returns bigint language sql stable as
    $f$ select nullif(current_setting('app.usuario_id', true), '')::bigint $f$;
grant execute on function negocio_activo(), usuario_activo() to estudia_app;

create function otros_accesos(p_usuario bigint, p_negocio bigint) returns int language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select count(*)::int from acceso where usuario_id = p_usuario and negocio_id <> p_negocio and activo $f$;

alter table paciente alter column negocio_id set default negocio_activo();
alter table paciente enable row level security;
alter table paciente force row level security;
create policy aislamiento on paciente using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on paciente to estudia_app;
alter table profesional alter column negocio_id set default negocio_activo();
alter table profesional enable row level security;
alter table profesional force row level security;
create policy aislamiento on profesional using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on profesional to estudia_app;
alter table servicio alter column negocio_id set default negocio_activo();
alter table servicio enable row level security;
alter table servicio force row level security;
create policy aislamiento on servicio using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on servicio to estudia_app;
alter table horario_atencion alter column negocio_id set default negocio_activo();
alter table horario_atencion enable row level security;
alter table horario_atencion force row level security;
create policy aislamiento on horario_atencion using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on horario_atencion to estudia_app;
alter table bloqueo alter column negocio_id set default negocio_activo();
alter table bloqueo enable row level security;
alter table bloqueo force row level security;
create policy aislamiento on bloqueo using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on bloqueo to estudia_app;
alter table tratamiento alter column negocio_id set default negocio_activo();
alter table tratamiento enable row level security;
alter table tratamiento force row level security;
create policy aislamiento on tratamiento using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on tratamiento to estudia_app;
alter table cita alter column negocio_id set default negocio_activo();
alter table cita enable row level security;
alter table cita force row level security;
create policy aislamiento on cita using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on cita to estudia_app;
alter table historial_estado alter column negocio_id set default negocio_activo();
alter table historial_estado enable row level security;
alter table historial_estado force row level security;
create policy aislamiento on historial_estado using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on historial_estado to estudia_app;
alter table motivo_cancelacion alter column negocio_id set default negocio_activo();
alter table motivo_cancelacion enable row level security;
alter table motivo_cancelacion force row level security;
create policy aislamiento on motivo_cancelacion using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on motivo_cancelacion to estudia_app;
alter table cancelacion alter column negocio_id set default negocio_activo();
alter table cancelacion enable row level security;
alter table cancelacion force row level security;
create policy aislamiento on cancelacion using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on cancelacion to estudia_app;
alter table caso_seguimiento alter column negocio_id set default negocio_activo();
alter table caso_seguimiento enable row level security;
alter table caso_seguimiento force row level security;
create policy aislamiento on caso_seguimiento using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on caso_seguimiento to estudia_app;
alter table intento alter column negocio_id set default negocio_activo();
alter table intento enable row level security;
alter table intento force row level security;
create policy aislamiento on intento using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on intento to estudia_app;
alter table cupo_liberado alter column negocio_id set default negocio_activo();
alter table cupo_liberado enable row level security;
alter table cupo_liberado force row level security;
create policy aislamiento on cupo_liberado using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on cupo_liberado to estudia_app;
alter table oferta_adelanto alter column negocio_id set default negocio_activo();
alter table oferta_adelanto enable row level security;
alter table oferta_adelanto force row level security;
create policy aislamiento on oferta_adelanto using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on oferta_adelanto to estudia_app;
alter table plantilla alter column negocio_id set default negocio_activo();
alter table plantilla enable row level security;
alter table plantilla force row level security;
create policy aislamiento on plantilla using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on plantilla to estudia_app;
alter table mensaje alter column negocio_id set default negocio_activo();
alter table mensaje enable row level security;
alter table mensaje force row level security;
create policy aislamiento on mensaje using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on mensaje to estudia_app;
alter table tarea_programada alter column negocio_id set default negocio_activo();
alter table tarea_programada enable row level security;
alter table tarea_programada force row level security;
create policy aislamiento on tarea_programada using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on tarea_programada to estudia_app;
alter table configuracion alter column negocio_id set default negocio_activo();
alter table configuracion enable row level security;
alter table configuracion force row level security;
create policy aislamiento on configuracion using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on configuracion to estudia_app;
alter table solicitud_contacto alter column negocio_id set default negocio_activo();
alter table solicitud_contacto enable row level security;
alter table solicitud_contacto force row level security;
create policy aislamiento on solicitud_contacto using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on solicitud_contacto to estudia_app;
alter table hecho_diario alter column negocio_id set default negocio_activo();
alter table hecho_diario enable row level security;
alter table hecho_diario force row level security;
create policy aislamiento on hecho_diario using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on hecho_diario to estudia_app;
alter table hecho_diario_profesional alter column negocio_id set default negocio_activo();
alter table hecho_diario_profesional enable row level security;
alter table hecho_diario_profesional force row level security;
create policy aislamiento on hecho_diario_profesional using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on hecho_diario_profesional to estudia_app;
alter table canal_negocio alter column negocio_id set default negocio_activo();
alter table canal_negocio enable row level security;
alter table canal_negocio force row level security;
create policy aislamiento on canal_negocio using (negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
grant select, insert, update, delete on canal_negocio to estudia_app;
alter table auditoria_acceso alter column negocio_id set default negocio_activo();
alter table auditoria_acceso enable row level security;
alter table auditoria_acceso force row level security;
create policy leer on auditoria_acceso for select using (negocio_id = (select negocio_activo()));
create policy insertar on auditoria_acceso for insert with check (negocio_id = (select negocio_activo()));
grant select, insert on auditoria_acceso to estudia_app;

-- Identidad
alter table acceso alter column negocio_id set default negocio_activo();
alter table usuario alter column rol drop not null;
alter table usuario enable row level security;  alter table usuario force row level security;
alter table sesion enable row level security;   alter table sesion force row level security;
alter table acceso enable row level security;   alter table acceso force row level security;
alter table negocio enable row level security;  alter table negocio force row level security;
alter table migracion enable row level security; alter table migracion force row level security;

create policy propio_o_del_negocio on acceso
    using (usuario_id = (select usuario_activo()) or negocio_id = (select negocio_activo()))
    with check (negocio_id = (select negocio_activo()));
create policy visible on usuario for select using (
    id = (select usuario_activo())
    or exists (select 1 from acceso a where a.usuario_id = usuario.id and a.negocio_id = (select negocio_activo())));
create policy modificable on usuario for update using (
    id = (select usuario_activo())
    or (exists (select 1 from acceso a where a.usuario_id = usuario.id and a.negocio_id = (select negocio_activo()))
        and otros_accesos(usuario.id, (select negocio_activo())) = 0));
create policy propia on sesion using (usuario_id = (select usuario_activo()))
    with check (usuario_id = (select usuario_activo()));
create policy visible on negocio for select using (
    id = (select negocio_activo())
    or id in (select a.negocio_id from acceso a where a.usuario_id = (select usuario_activo())));

grant select, update on usuario to estudia_app;
grant select, insert, update, delete on sesion, acceso to estudia_app;
grant select on negocio to estudia_app;
grant usage, select on all sequences in schema public to estudia_app;

-- Las únicas formas de cruzar negocios (security definer, ruta de búsqueda fija, devuelven lo mínimo).
create function ingreso_usuario(p_nombre text) returns setof usuario language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select * from usuario where lower(nombre_usuario) = lower(p_nombre) $f$;
create function sesion_de_huella(p_huella text, p_ahora timestamptz)
    returns table(usuario_id bigint, negocio_id bigint) language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select s.usuario_id, s.negocio_id from sesion s join usuario u on u.id = s.usuario_id
        where s.huella = p_huella and s.vence_en > p_ahora and u.activo $f$;
create function negocio_de_nombre(p_nombre text) returns setof negocio language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select * from negocio where nombre_corto = lower(p_nombre) $f$;
create function negocios_activos() returns setof negocio language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select * from negocio where activo order by id $f$;
create function negocio_de_canal(p_tipo text, p_id_externo text) returns bigint language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select c.negocio_id from canal_negocio c join negocio n on n.id = c.negocio_id
        where c.tipo = p_tipo and c.id_externo = p_id_externo and c.activo and n.activo $f$;
create function crear_usuario(p_nombre_usuario text, p_nombre text, p_clave_hash text) returns bigint
    language sql volatile security definer set search_path = public, pg_temp as
    $f$ insert into usuario(nombre_usuario, nombre, clave_hash) values (p_nombre_usuario, p_nombre, p_clave_hash)
        returning id $f$;
create function existe_usuario(p_nombre text) returns boolean language sql stable security definer
    set search_path = public, pg_temp as
    $f$ select exists (select 1 from usuario where lower(nombre_usuario) = lower(p_nombre)) $f$;
revoke all on function otros_accesos(bigint, bigint), ingreso_usuario(text), sesion_de_huella(text, timestamptz),
    negocio_de_nombre(text), negocios_activos(), negocio_de_canal(text, text), crear_usuario(text, text, text),
    existe_usuario(text) from public;
grant execute on function otros_accesos(bigint, bigint), ingreso_usuario(text), sesion_de_huella(text, timestamptz),
    negocio_de_nombre(text), negocios_activos(), negocio_de_canal(text, text), crear_usuario(text, text, text),
    existe_usuario(text) to estudia_app;
