# 8. Ganchos de privacidad

**Estado:** aceptada (PRD #4, §6.5). No es asesoría legal.

Registro de accesos (`auditoria_acceso`, solo insertar y leer, sin guardar el texto buscado) para la ficha, el detalle de una cita y el buscador; la agenda y las bandejas no se registran (se refrescan cada minuto). Retención por negocio en configuración, **apagada por defecto**; la depuración diaria cubre mensajes y tareas, y el operador depura el registro de accesos y las sesiones con `make negocio ARGS="depurar <negocio>"`. Por paciente: exportar todo lo suyo y anonimizarlo conservando los hechos de la cita. El borrado de un negocio se diseña y no se implementa. Sin cifrado de columnas (rompería el buscador): HTTPS, TLS hacia la base y cifrado en reposo del proveedor.
