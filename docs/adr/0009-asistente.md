# 9. Asistente: un catálogo cerrado de herramientas y dos adaptadores

**Estado:** aceptada (`docs/prd-asistente.md`).

El asistente responde con un **catálogo cerrado de herramientas** (`estudia/asistente/`). Qué herramientas recibe cada quien lo decide su **perfil** (`visitante`, `paciente`, `especialista`, `auxiliar`, `operador`), nunca el modelo. Una sola función, `ejecutar(actor, nombre, args)`, corre cualquier herramienta: comprueba el perfil y el alcance, abre una conexión por llamada como `estudia_app` con el negocio fijado (ADR 0002) y deja el registro de accesos (ADR 0008).

Dos adaptadores comparten ese despachador: el **servidor MCP** por stdio (sesión local de quien desarrolla, perfil `operador`, solo en `local`) y el **ciclo dentro de la aplicación**, que llama a la API de Claude y ejecuta las herramientas en el mismo proceso.

**El asistente no escribe.** Una herramienta de acción devuelve una **propuesta**; la persona la confirma y el cliente la ejecuta por la ruta que ya existía, con sus comprobaciones. La identidad (negocio, usuario, paciente) sale de la sesión o del enlace firmado, nunca de un argumento.

**Descartado:** que el ciclo de la aplicación hable con las herramientas por el protocolo MCP (habría que emitir y verificar un testigo por actor y defender una ruta MCP pública, sin ganar nada); una herramienta de SQL libre fuera de `local` (la RLS aísla negocios, no pacientes ni profesionales); dejar que el modelo ejecute cambios.

**Desviaciones de decisiones anteriores:**
- El README decía que el sistema no hace peticiones a terceros. El asistente hace una, desde el servidor, y está **apagado por defecto**: sin `ANTHROPIC_API_KEY` sus rutas no se registran (ADR 0005) y cada negocio lo enciende por separado para el equipo y para los pacientes.
- ADR 0008 deja la retención apagada por defecto. Las conversaciones del asistente se conservan 30 días (`retencion_asistente_dias`).
- Sigue vigente ADR 0007: el plan gratuito es solo para datos ficticios. El asistente de pacientes no se enciende en `produccion` hasta que la empresa y su asesor confirmen el tratamiento por un tercero (Ley 1581 de 2012). No es asesoría legal.

**Perfil `visitante` (página pública).** Atiende a una persona anónima en la landing. Su actor lleva un id aleatorio en una cookie firmada, no un usuario ni un paciente, y el catálogo que recibe es mínimo: servicios, horarios libres, datos del negocio, el texto fijo del sitio y dos propuestas que son formularios ya existentes. Tiene riesgo legal menor que el de pacientes: **no se envían datos personales al tercero**. El texto se redacta (correos y cifras de 7 o más dígitos) antes de llegar al modelo y a la base, el modelo nunca pide documento, celular ni correo, y no conoce a ninguna persona. Aun así queda apagado por defecto (`asistente_visitantes`), con tope por visitante y día, presupuesto de tokens propio y retención de 7 días. Los botones de la capa 1 no usan modelo y funcionan sin la clave.
