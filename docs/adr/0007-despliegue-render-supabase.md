# 7. Despliegue: Render y Supabase, ensayado en local

**Estado:** aceptada (PRD #4, D12); el despliegue real no se ha hecho.

Una imagen (`Dockerfile`) que arranca como `web` (migra y sirve) o `trabajador`; `render.yaml` describe el servicio. El plan gratuito no tiene procesos en segundo plano: el ciclo de tareas lo dispara `pg_cron` de Supabase llamando a `/tick` con `X-Tick-Secreto`. Conexión por el intermediario en modo sesión. El trabajo diario sigue en PostgreSQL 16 local; `make ensayo-supabase` comprueba contra la imagen de Supabase (PostgreSQL 17) las migraciones, la suite con el rol de aplicación y que su API de datos no expone ninguna tabla (la migración 009 les retira los permisos a `anon`, `authenticated` y `service_role`). El plan gratuito es **solo para datos ficticios**.
