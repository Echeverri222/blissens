-- Las funciones auxiliares de contexto eran ejecutables por PUBLIC y la API de datos de Supabase (PostgREST) las exponía
-- como /rpc/...: solo las usa el rol de aplicación (y el dueño, que siempre puede).
revoke execute on function negocio_activo(), usuario_activo() from public;
grant execute on function negocio_activo(), usuario_activo() to estudia_app;
