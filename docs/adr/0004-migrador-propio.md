# 4. Migrador propio con reversa

**Estado:** aceptada (PRD #4, D5).

SQL plano en `migrations/` con `estudia/migrate.py`: archivo `.down.sql`, huella de cada archivo aplicado (falla si cambió), bloqueo consultivo para que dos despliegues no migren a la vez, una transacción por migración, tiempo máximo de espera por bloqueos y marcas de primera línea `-- sin-transaccion` y `-- irreversible`. Subcomandos `estado`, `subir`, `bajar`, `verificar`. Regla: ampliar antes de contraer; la 007 (que retira lo viejo) es irreversible. **Deuda declarada:** los índices se crean sin `concurrently` (la base es pequeña).
