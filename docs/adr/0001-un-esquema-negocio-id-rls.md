# 1. Una base, un esquema, `negocio_id` y RLS forzada

**Estado:** aceptada (PRD #4, D1).

Todas las tablas llevan `negocio_id` y PostgreSQL aplica la política por filas (RLS **activada y forzada**, también en las tablas globales). Una migración sirve a todos los negocios, el ciclo de tareas atiende a todos con una conexión y hay una sola copia de seguridad.

**Descartado:** un esquema por negocio (cada migración se aplicaría N veces y podría quedar a medias) y una base por negocio (aislamiento máximo pero multiplica proyectos, conexiones, copias y migraciones). `negocios exportar` es el primer paso si algún cliente exige base propia.
