# Propuesta: pasar a la API oficial de WhatsApp

Documento para la gerencia de la clínica. Explica qué proponemos, cuánto cuesta (con la fórmula para calcularlo con sus cifras), los pasos para activarlo y los textos que se envían a Meta para su aprobación.

## 1. Qué proponemos

Hoy los mensajes a los pacientes se envían a mano desde WhatsApp Web, y los envía una sola persona de recepción. Proponemos pasar a la **API oficial de WhatsApp (Cloud API de Meta)**, que permite que el sistema envíe los mensajes por usted, desde el número de la clínica, sin copiar y pegar.

El flujo automático que ya funciona **se mantiene tal cual**:

- Aviso de cita agendada.
- Recordatorios 48 horas y 24 horas antes, con botones para responder con un toque («Sí, asistiré», «No podré ir», «Cambiar fecha»).
- Segundo intento si el paciente no confirma.
- Confirmación y cancelación; al cancelar, el sistema pregunta el motivo.
- Seguimiento a los 3, 7 y 15 días a quien canceló, no asistió o dejó su plan a medias.
- Ofertas de adelanto cuando se libera un espacio.
- Baja: si el paciente escribe BAJA, no recibe más mensajes automáticos.

**Qué cambia para recepción**

- Deja de copiar y enviar mensajes uno por uno. Solo atiende lo que el sistema le escala (la bandeja de Pendientes).
- Si el número actual de la clínica se pasa a la API (ver sección 3), recepción responde desde el panel del sistema y no desde WhatsApp Web. El panel tendrá una vista de conversaciones por familia, con las respuestas de los pacientes, los mensajes automáticos enviados y una caja para responder.
- Mientras la API no esté activa, o para pacientes que aún no tienen autorización registrada, el sistema deja esos mensajes en una bandeja «Por enviar», donde recepción los abre en WhatsApp con un clic y marca «Enviado». Es un puente temporal, no el producto final.

## 2. Costos

### 2.1 En una frase

**El costo mensual no tiene por qué subir mucho.** Este sistema reemplaza a Dentalink para la agenda, así que esa suscripción se recorta (o se reduce a un plan mínimo, ver sección 5) y ese ahorro paga buena parte de WhatsApp y del alojamiento (hosting). El mayor beneficio, además, no es de dinero directo: son las **horas de recepción** que dejan de gastarse en recordatorios y seguimiento.

### 2.2 Cómo cobra Meta

Meta cobra **por mensaje plantilla entregado**, según la **categoría** del mensaje y el **país** del paciente:

- **Utilidad (utility):** mensajes sobre algo que el paciente ya tiene con la clínica: recordatorios de cita, confirmaciones, seguimiento de un tratamiento existente. Es la categoría que usamos para todo.
- **Marketing:** promociones y ofertas comerciales. Cuesta más. **No la usamos**: la clínica no hace mensajes de prospección.
- **Respuestas dentro de una conversación que abrió el paciente: sin costo.** Cuando el paciente escribe o toca un botón, se abre una ventana de 24 horas en la que las respuestas son gratis.
- **Plantillas de utilidad enviadas dentro de esa ventana abierta: también sin costo.**

Las tarifas por país las publica Meta en su tarifario oficial y las cambia con el tiempo, por eso este documento no fija ningún valor: se consulta el día en que se prepara la cifra final y se anota la fecha.

### 2.3 Fórmula

```
Costo mensual de WhatsApp =
    ( citas por mes × plantillas por cita  +  mensajes de seguimiento por mes )
    × tarifa de utilidad para Colombia
```

```
Costo mensual de la propuesta  =  WhatsApp  +  hosting (Render + Supabase)  +  lo que quede de Dentalink
Costo mensual de hoy           =  suscripción actual de Dentalink  +  tiempo de recepción en mensajes
Diferencia                     =  hoy − propuesta
```

| Dato | Qué es | Valor |
|---|---|---|
| Citas por mes | Citas agendadas en un mes típico | [citas/mes, lo da la clínica] |
| Plantillas por cita | Mensajes que el sistema inicia por cada cita (aviso de agenda, recordatorio 48 h, recordatorio 24 h, y segundo intento si no confirma). Las respuestas a botones no cuentan | [plantillas por cita, promedio estimado ___] |
| Mensajes de seguimiento por mes | Seguimientos a los 3, 7 y 15 días, continuidad de tratamiento y ofertas de adelanto en un mes típico | [mensajes/mes, estimado ___] |
| Tarifa de utilidad, Colombia | Precio por mensaje plantilla de utilidad entregado | [tarifa vigente de Meta para Colombia, consultada el ___] |
| Hosting | Plan de Render (aplicación) + plan de Supabase (base de datos) | [precio publicado de Render ___ + Supabase ___, consultado el ___] |
| Suscripción actual de Dentalink | Lo que la clínica paga hoy | [lo da la clínica; no se escribe en el repositorio] |
| Lo que quede de Dentalink | Plan mínimo solo para la historia clínica, si la clínica decide mantenerlo (sección 5) | [costo del plan reducido, o cero si se resuelve de otra forma] |
| Horas de recepción en recordatorios y seguimiento | Tiempo semanal que hoy se va en enviar mensajes a mano | [horas/semana, lo da la clínica] |

Como los recordatorios van en su mayoría fuera de una ventana abierta, para estimar con prudencia se cuentan todos como cobrados; los que caigan dentro de una ventana abierta salen gratis y bajan la cifra real.

### 2.4 Comparación

> **Hoy** (Dentalink + tiempo de recepción en mensajes) **vs. propuesta** (WhatsApp + hosting + plan reducido de historia clínica, si aplica): [una línea con las cifras reales de la clínica].

Las cifras reales de la clínica **se completan fuera del repositorio**; aquí solo queda la fórmula y los espacios.

### 2.5 Recomendación: Meta directamente

Recomendamos usar la **Cloud API de Meta directamente**, sin intermediario. Un proveedor intermedio (BSP) suma una mensualidad propia además de lo que cobra Meta, y no aporta nada que este sistema no haga ya. Con Meta directo no hay cargo de plataforma, solo el costo por mensaje.

### 2.6 El beneficio mayor

Cada recordatorio y cada seguimiento que hoy se envía a mano son minutos de recepción. Con el sistema enviándolos, esas horas quedan libres para atender llamadas, pacientes en sala y los casos que de verdad necesitan a una persona. La meta de la clínica (más pacientes que reagendan, más abonos, menos huecos en la agenda) depende de ese seguimiento constante, y es lo que mejor justifica el paso.

## 3. Pasos para activarlo

1. **Verificación de empresa en Meta (Meta Business).** La clínica crea o usa su cuenta de Meta Business y verifica la empresa con sus documentos legales. Es un trámite de la clínica; nosotros acompañamos. Puede tardar varios días.
2. **Decidir el número.**
   - **Pasar el número actual a la API (recomendado):** los pacientes ya lo conocen. Desde ese momento el número **deja de funcionar en la aplicación WhatsApp Business y en WhatsApp Web**; recepción responde desde el panel del sistema.
   - **Usar un número nuevo** solo para los mensajes automáticos: el número actual sigue como hoy, pero los pacientes verán dos números y las respuestas llegarían a uno que no es el de siempre.
   - Es una decisión de la gerencia.
3. **Enviar las plantillas a Meta para su aprobación.** Son las de la sección 4. Meta las revisa y suele tardar de horas a **pocos días**; si rechaza alguna, se ajusta el texto y se vuelve a enviar. Conviene enviarlas cuanto antes, porque este es el paso con espera.
4. **Autorización de los pacientes (opt-in, R17).** Meta exige que el paciente haya aceptado recibir mensajes, y la ley colombiana (Ley 1581 de 2012) exige su autorización para tratar sus datos. El sistema envía automáticamente **solo a pacientes con autorización registrada**; para los demás deja el mensaje en la bandeja «Por enviar», marcado «Sin autorización registrada», para que recepción la pida en la siguiente llamada o visita. La clínica recibe un formato de autorización de una página para imprimir o enviar.
5. **Encender.** Activar el canal es un **cambio de configuración**, no de programa: se registra el canal de WhatsApp de la clínica y las claves en el entorno del sistema. El simulador sigue funcionando sin Meta para pruebas y capacitación. Si algo falla, se vuelve al envío asistido desde «Por enviar» cambiando la misma configuración.

## 4. Plantillas para enviar a Meta

Una plantilla por cada mensaje que **inicia** una conversación (el paciente no ha escrito antes). Todas en categoría **utility** y en español, tratando de «usted». En el texto, `{{1}}`, `{{2}}`… son los espacios que Meta llena con los datos de cada cita. Los botones son de respuesta rápida; al tocarlos, el sistema recibe la respuesta y actúa (confirmar, cancelar, cambiar fecha, etc.).

Notas para el envío:

- Meta no permite saltos de línea dentro de una variable. En las plantillas de familia, la lista de citas (`lista`) se arma en una sola línea separada por « · ». Tampoco admite que un texto empiece o termine con una variable: las tres plantillas de seguimiento terminan con el enlace y hay que añadirles una frase de cierre breve (por ejemplo, «Gracias.») antes de enviarlas. Este ajuste se confirma con la clínica al preparar el envío.
- Meta pide valores de ejemplo para cada variable; los prepara el equipo técnico con datos ficticios.

| Clave | Nombre en Meta | Categoría | Texto exacto | Variables | Botones |
|---|---|---|---|---|---|
| `cita_agendada` | `cita_agendada` | utility | Hola, {{1}}. Su cita quedó agendada para el {{2}} a las {{3}} con {{4}}. Le esperamos en {{5}}. Gracias por elegirnos. | {{1}} = nombre, {{2}} = fecha, {{3}} = hora, {{4}} = profesional, {{5}} = direccion | ninguno |
| `recordatorio_48h` | `recordatorio_cita_48h` | utility | Hola, {{1}}. Le recordamos su cita del {{2}} a las {{3}} con {{4}}. ¿Nos confirma su asistencia? | {{1}} = nombre, {{2}} = fecha, {{3}} = hora, {{4}} = profesional | «Sí, asistiré»; «No podré ir»; «Cambiar fecha» |
| `recordatorio_24h` | `recordatorio_cita_24h` | utility | Hola, {{1}}. Mañana es su cita: {{2}} a las {{3}} con {{4}}, en {{5}}. Le esperamos. | {{1}} = nombre, {{2}} = fecha, {{3}} = hora, {{4}} = profesional, {{5}} = direccion | ninguno |
| `segundo_intento` | `recordatorio_segundo_intento` | utility | Hola, {{1}}. Aún no hemos recibido su confirmación para la cita del {{2}} a las {{3}} con {{4}}. ¿Puede responder con un toque? | {{1}} = nombre, {{2}} = fecha, {{3}} = hora, {{4}} = profesional | «Sí, asistiré»; «No podré ir»; «Cambiar fecha» |
| `seguimiento_reasignacion` | `seguimiento_reasignacion` | utility | Hola, {{1}}. Volver a empezar es más fácil acompañado: {{2}} le guarda un espacio. Elija el que mejor le quede: {{3}} | {{1}} = nombre, {{2}} = profesional, {{3}} = enlace | «Ahora no» |
| `seguimiento_inasistencia` | `seguimiento_inasistencia` | utility | Hola, {{1}}. Volver a empezar es más fácil acompañado: {{2}} le guarda un espacio. Si desea retomar su cita del {{3}}, elija el que mejor le quede: {{4}} | {{1}} = nombre, {{2}} = profesional, {{3}} = fecha, {{4}} = enlace | «Ahora no» |
| `continuidad_tratamiento` | `continuidad_tratamiento` | utility | Hola, {{1}}. Volver a empezar es más fácil acompañado: {{2}} le guarda un espacio para continuar su plan. Elija el que mejor le quede: {{3}} | {{1}} = nombre, {{2}} = profesional, {{3}} = enlace | «Ahora no» |
| `oferta_adelanto` | `oferta_adelanto_cita` | utility | Hola, {{1}}. Su cita podría adelantarse de {{2}} a las {{3}} a {{4}} a las {{5}}. ¿Desea hacerlo? | {{1}} = nombre, {{2}} = fecha_actual, {{3}} = hora_actual, {{4}} = fecha_nueva, {{5}} = hora_nueva | «Sí, adelantarla»; «No, gracias» |
| `cita_agendada_hogar` | `cita_agendada_familia` | utility | Hola, {{1}}. Le confirmamos lo que quedó agendado:<br>{{2}}<br>Los esperamos en {{3}}. Gracias por elegirnos. | {{1}} = nombre, {{2}} = lista, {{3}} = direccion | ninguno |
| `recordatorio_48h_hogar` | `recordatorio_familia_48h` | utility | Hola, {{1}}. Le recordamos las próximas citas de su familia:<br>{{2}}<br>¿Nos confirma la asistencia? | {{1}} = nombre, {{2}} = lista | «Sí, asistiremos»; «Cambiar o cancelar» |
| `recordatorio_24h_hogar` | `recordatorio_familia_24h` | utility | Hola, {{1}}. Mañana tienen cita:<br>{{2}}<br>Los esperamos en {{3}}. | {{1}} = nombre, {{2}} = lista, {{3}} = direccion | ninguno |
| `segundo_intento_hogar` | `recordatorio_familia_segundo_intento` | utility | Hola, {{1}}. Mañana tienen cita:<br>{{2}}<br>Aún nos falta la confirmación de las que dicen «sin confirmar». ¿Puede responder con un toque? | {{1}} = nombre, {{2}} = lista | «Sí, asistiremos»; «Cambiar o cancelar» |

(`<br>` marca un salto de línea en el texto de la plantilla.)

### Respuestas dentro de la conversación (no requieren aprobación)

Estos mensajes solo se envían como respuesta a algo que el paciente acaba de hacer (tocar un botón o escribir), es decir, dentro de la ventana de 24 horas que él abrió. Van como texto libre, sin plantilla, sin aprobación de Meta y sin costo.

| Clave | Texto | Botones |
|---|---|---|
| `confirmacion_recibida` | Gracias, {{1}}. Su cita del {{2}} a las {{3}} quedó confirmada. Le esperamos en {{4}}. | ninguno |
| `pedir_motivo` | Listo, {{1}}. Cancelamos su cita del {{2}}. Para mejorar nuestro servicio, ¿nos cuenta el motivo? Elija una opción. | lista de motivos |
| `cancelacion_recibida` | Gracias, {{1}}. Su cita del {{2}} quedó cancelada. Cuando quiera retomarla, elija un nuevo espacio aquí: {{3}} | «Ahora no» |
| `adelanto_confirmado` | Listo, {{1}}. Adelantamos su cita: ahora es el {{2}} a las {{3}} con {{4}}, en {{5}}. Esta es su nueva fecha. | ninguno |
| `oferta_no_disponible` | Hola, {{1}}. Ese espacio ya no está disponible. No se preocupe: su cita original sigue igual. | ninguno |
| `baja_confirmada` | Listo, {{1}}. No le enviaremos más mensajes automáticos por WhatsApp. Los correos, si los recibe, se cancelan con el enlace que traen. Si necesita algo, escríbanos o llámenos. | ninguno |
| `respuesta_tardia` | Hola, {{1}}. Esa cita ya no está vigente. Si necesita ayuda, la clínica le acompaña con gusto. | ninguno |
| `cambiar_fecha` | Claro, {{1}}. Elija su nueva fecha aquí: {{2}}. Su cita actual se mantiene hasta que elija otra. | ninguno |
| `seguimiento_pausado` | Entendido, {{1}}. No insistiremos más sobre esto. Cuando quiera retomar, aquí estamos. | ninguno |
| `confirmacion_recibida_hogar` | Gracias, {{1}}. Quedaron confirmadas:<br>{{2}}<br>Los esperamos en {{3}}. | ninguno |
| `cambiar_hogar` | Claro, {{1}}. Desde aquí puede cambiar o cancelar cada cita: {{2}} | ninguno |

Si una de estas respuestas llegara a enviarse con la ventana ya cerrada (por ejemplo, el paciente tocó un botón de un mensaje muy antiguo), el sistema no la envía por la API y la deja en «Por enviar» para recepción.

## 5. Lo que no cubre

- **Historia clínica.** Dentalink hoy también guarda la historia clínica, que las normas colombianas obligan a la clínica a conservar. Este sistema reemplaza a Dentalink **solo para la agenda**. La clínica debe decidir cómo mantener la historia clínica: un plan reducido de Dentalink solo para eso, otra herramienta, o una fase posterior de este proyecto. El costo de lo que quede se suma en la comparación de la sección 2.
- **Plantillas de marketing.** No se usan: no hay mensajes de promoción ni de prospección a personas que no son pacientes.
- **Chatbot en WhatsApp.** El número de la clínica envía plantillas y entiende botones, pero no conversa con texto libre ni responde preguntas. Lo que el paciente escriba y el sistema no entienda llega a recepción. Los asistentes conversacionales viven en el sitio web y en los enlaces personales de los pacientes.
- **Cifras reales de la clínica.** No están en este documento; se completan por fuera del repositorio.
