-- En Supabase, los roles de su API de datos (anon, authenticated, service_role) reciben permisos por defecto sobre todo lo
-- que se crea en `public`. La aplicación no usa esa API: se les retira todo, y a lo futuro también. Donde esos roles no
-- existen (PostgreSQL común) no hace nada.
do $m$
declare r text;
begin
    foreach r in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on all tables in schema public from %I', r);
            execute format('revoke all on all sequences in schema public from %I', r);
            execute format('revoke all on all functions in schema public from %I', r);
            execute format('alter default privileges in schema public revoke all on tables from %I', r);
            execute format('alter default privileges in schema public revoke all on sequences from %I', r);
            execute format('alter default privileges in schema public revoke all on functions from %I', r);
        end if;
    end loop;
end
$m$;
