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
| **Responsable** | Paciente que gestiona las citas de sus familiares desde su propio enlace (agendar, ver, cambiar, cancelar). No puede ser a su vez familiar de nadie: un solo nivel. Ver `docs/prd-familia.md`. |
| **Familiar** | Paciente con `responsable_id`. Conserva su ficha, su documento y su enlace; usa el celular del responsable, así los mensajes del hogar llegan a un solo teléfono. Si es mayor de edad puede *dejar de compartir*. |
| **Hogar** | El responsable y sus familiares (un paciente sin familia es un hogar de uno). Comparten celular, así que sus avisos automáticos salen agrupados: un mensaje por evento, dirigido al responsable, con una línea por cita. |
| **Parentesco** | Relación del familiar con su responsable: `hijo`, `pareja`, `padre` (madre o padre) u `otro`. |
| **Consentimiento por** | Quién autorizó tratar los datos del paciente: vacío si fue él mismo; el responsable si lo agregó (como representante legal de un menor, o con permiso del adulto). |
| **Asistente** | La función conversacional: responde preguntas con herramientas y prepara propuestas. No es un chat abierto ni escribe en la base. Ver `docs/prd-asistente.md` y ADR 0009. |
| **Herramienta** | Una operación con nombre y entradas tipadas del catálogo del asistente (`estudia/asistente/`). Es de `lectura` o de `propuesta`. |
| **Actor** | Quién le habla al asistente: un usuario con su acceso, o un paciente identificado por su enlace personal. Lo arma el servidor, nunca el modelo. |
| **Perfil** | El conjunto de herramientas que recibe un actor: `paciente`, `especialista`, `auxiliar` u `operador`. No da más de lo que el panel o el enlace ya permiten. |
| **Propuesta** | Una acción que el asistente preparó y no ejecutó: tipo, parámetros y un resumen. La persona la confirma o la descarta; al confirmar corre por la ruta que ya existía. |
| **Operador (perfil)** | La sesión local de quien desarrolla, por el servidor MCP. Solo existe en el entorno `local`. |
| **Cupo, oferta, caso de seguimiento, recuperación** | Ver `requirements.md` y el PRD #1. |
| **Confirmación por teléfono** | Confirmar una cita futura (`programada` o `no_confirmada`) porque el paciente lo dijo en una llamada: la registra la auxiliar con «Confirmó». Pasa la cita a `confirmada` con detalle «Confirmada por teléfono», no envía mensajes y se puede deshacer. |
| **Pendientes de hoy** | La pestaña «Qué hacer hoy» de Pendientes: lo que recepción resuelve hoy, en dos grupos. **Llamadas**: seguimientos, contactos, mensajes sin interpretar, citas sin confirmar (hoy y mañana) y dados de baja; su total es el contador del menú. **Trámites**: lo que se cierra en pantalla (citas por cerrar), sin llamar. |
| **Paciente de alto valor** | Lo que la clínica llama «VIP»: un paciente internacional o un deportista de alto nivel (puede ser los dos). Son dos marcas del paciente, no un tipo. Las pone la recepción en la ficha, la importación del software de la clínica («Tipo Paciente») o el registro en el sitio en inglés (internacional); lo que decide la recepción manda. Salen primero en seguimientos y en pacientes en riesgo. |
