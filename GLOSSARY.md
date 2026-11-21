# Glosario

Vocabulario del dominio de Estud-IA. El código y los documentos usan estos términos con este sentido.

| Término | Significado |
|---|---|
| **Negocio** | Un cliente de Estud-IA: una empresa con sus pacientes, profesionales, mensajes y configuración. Hoy solo existe Blissens. No es una sede. |
| **Negocio activo** | El negocio al que pertenece una petición o una tarea. Se fija al abrir la conexión (`app.negocio_id`) y la base lo usa para decidir qué filas existen. El código de dominio nunca lo menciona. |
| **Acceso** | El vínculo de un usuario con un negocio: rol, profesional (si es especialista), si administra y si está activo. Un usuario puede tener varios. |
| **Usuario** | Una persona de la plataforma (nombre de usuario y contraseña). Es global; lo que puede hacer lo dice su acceso al negocio activo. |
| **Administrador** | Quien tiene `administrador` en su acceso: gestiona los usuarios de su negocio. No es un tercer rol: lo es una auxiliar o un especialista. |
| **Operador** | Quien gestiona la plataforma con el rol de administración de la base (crea negocios, migra, respalda). |
| **Entorno** | Dónde corre el sistema: `local`, `demo` o `produccion`. Decide qué herramientas de demostración existen: lo que un entorno no permite no se registra como ruta. |
| **Rol de aplicación** | `estudia_app`: el rol con el que corre la aplicación. No es dueño de las tablas ni puede saltarse RLS. |
| **Rol de administración** | Dueño del esquema; lo usan las migraciones y los comandos del operador. |
| **Puerto del canal** | La interfaz que separa «enviar y recibir mensajes» del proveedor concreto (simulado, de prueba, WhatsApp). |
| **Canal del negocio** | Fila de `canal_negocio`: tipo, identificador externo y la *referencia* (nombre de variable de entorno) del secreto. |
| **Turno** | La parte del ciclo de tareas que corresponde a un negocio: un máximo de tareas en su propio contexto. |
| **Registro de accesos** | `auditoria_acceso`: quién consultó la ficha, el detalle de una cita o el buscador de pacientes. No guarda el texto buscado. |
| **Retención** | Cuánto se conservan mensajes, tareas, registro de accesos y sesiones. Por defecto no se borra nada. |
| **Anonimizar** | Quitar lo que identifica a un paciente conservando los hechos de sus citas para los indicadores. |
| **Correo de cita** | Uno de los tres correos que el sistema envía: agendada, recordatorio de 24 h y cancelada. Complementa a WhatsApp; no pide confirmar ni lleva servicio ni datos clínicos. |
| **Consentimiento de correo** | Autorización del paciente para recibir correos (`acepta_correo`). Independiente de `acepta_mensajes`: la baja de uno no toca al otro. |
| **Cupo, oferta, caso de seguimiento, recuperación** | Ver `requirements.md` y el PRD #1. |
