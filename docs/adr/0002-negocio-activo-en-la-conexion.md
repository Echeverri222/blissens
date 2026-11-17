# 2. El negocio activo vive en la conexión, no en el código

**Estado:** aceptada (PRD #4, D2 y D3).

El dominio no recibe ni menciona `negocio_id`: la conexión fija `app.negocio_id` (y `app.usuario_id`), las políticas lo evalúan una vez por consulta y la columna usa `negocio_activo()` como valor por defecto. **Falla cerrado**: sin contexto no se ve ninguna fila. El ajuste es de sesión (no de transacción) porque el código confirma a mitad de una petición; por eso `db.fijar` confirma justo después de fijarlo y, con Supabase, la conexión va por el modo sesión (5432), nunca el modo transacción (6543).

**Descartado:** pasar `negocio_id` a cada función y consulta: es la disciplina que se quiere evitar (unas 260 consultas).
