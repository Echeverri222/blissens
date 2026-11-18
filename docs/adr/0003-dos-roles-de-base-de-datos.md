# 3. Rol de aplicación sin privilegios y rol de administración

**Estado:** aceptada (PRD #4, D4).

La aplicación se conecta como `estudia_app`: ni superusuario, ni dueño de las tablas, ni con `BYPASSRLS`. Migraciones y comandos del operador usan el rol de administración (`DATABASE_URL_ADMIN`). El rol de aplicación cruza negocios solo por funciones `security definer` que devuelven lo mínimo (`ingreso_usuario`, `sesion_de_huella`, `negocio_de_nombre`, `negocios_activos`, `negocio_de_canal`, `otros_accesos`, `crear_usuario`, `existe_usuario`). **Desviación del PRD:** son 8, no 5; las tres últimas (`otros_accesos`, `crear_usuario`, `existe_usuario`) las exige la gestión de usuarios de nivel plataforma. Fuera de `local` la aplicación no arranca si su rol es privilegiado o dueño de las tablas.
