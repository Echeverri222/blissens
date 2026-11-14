# Requirements — Estud-IA: Gestión inteligente de citas (Blissens Odontología / Eme y Eme Group)

> Estado: **borrador v0.1** · Fuente: `contexto/.../Estud-IA Reto.md` (ideas del equipo + contexto del reto).
> Pendiente de incorporar: los Excel (agenda, estados, aranceles, guiones) y los PDF de proceso actual.

---

## 1. Resumen del problema

Menos de la mitad de las citas programadas (ago–nov) termina en atención efectiva. Hay cancelaciones tardías, inasistencias y abandono de tratamientos, sin que el sistema lo detecte ni actúe. El proceso es manual de punta a punta (WhatsApp/llamada → auxiliar → software → Excel a fin de mes).

**Enfoque elegido (idea 1):** diseñar desde el **paciente**. Una mala gestión de agenda genera deserción, muchas veces sin que el paciente lo decida de forma consciente. Si le facilitamos agendar, cambiar y retomar, la ocupación de la clínica mejora como consecuencia.

## 2. Objetivo y resultado esperado

**Objetivo:** mejorar el sistema de gestión de citas para lograr ocupación constante de agenda y reducir significativamente la interrupción de tratamientos.

| Resultado | Cómo se vería |
|---|---|
| Paciente | Agenda, cambia o cancela en segundos, sin depender de la auxiliar; recibe propuestas útiles en vez de mensajes genéricos |
| Especialista | Menos cupos vacíos, agenda estable |
| Administrativo/auxiliar | Deja de reprogramar y perseguir a mano; ve alertas y reportes sin armar Excel |

## 3. Actores

| Actor | Rol en el sistema |
|---|---|
| Paciente | Agenda, confirma, cancela, reprograma, responde ofertas de adelanto |
| Auxiliar / recepción | Supervisa, interviene en casos excepcionales, gestiona pacientes en riesgo |
| Especialista | Define disponibilidad, consulta su agenda |
| Administrador / gerencia | Consulta indicadores, configura reglas |
| Sistema (automatizaciones) | Recordatorios, lista de espera, seguimiento, recuperación |

## 4. Requerimientos funcionales

Prioridad: **M** = Must (MVP), **S** = Should, **C** = Could. Origen entre paréntesis (idea del equipo o evidencia del reto).

### 4.1 Agendamiento autoservicio *(idea 2)*

| ID | Requerimiento | Prio |
|---|---|---|
| RF-01 | El paciente ve los espacios disponibles por especialista/tratamiento y selecciona uno (tipo Calendly) | M |
| RF-02 | Los espacios mostrados respetan duración del procedimiento, disponibilidad del especialista y reglas de la clínica | M |
| RF-03 | El paciente puede indicar preferencias de horario (franjas, días) para que el sistema filtre o sugiera | S |
| RF-04 | Acceso al agendamiento por enlace enviado a WhatsApp, sin crear cuenta (identificación por teléfono/documento) | M |
| RF-05 | La cita creada se escribe en el software/base de datos de la clínica sin intervención manual | M |
| RF-06 | Las citas por llamada o WhatsApp siguen siendo posibles; la auxiliar las registra en el mismo sistema | M |
| RF-07 | Para pacientes en tratamiento, el sistema propone la siguiente cita según el plan (frecuencia entre sesiones) | S |

### 4.2 Confirmación y recordatorios

| ID | Requerimiento | Prio |
|---|---|---|
| RF-08 | Recordatorios automáticos a 48 h y 24 h (ya existen; se mantienen y se integran) | M |
| RF-09 | La confirmación es **explícita** (sí / no / reprogramar). Sin respuesta ≠ asistencia: se marca como "no confirmada" | M |
| RF-10 | Las citas no confirmadas generan alerta a la auxiliar y un segundo intento automático | M |
| RF-11 | El mensaje usa guiones personalizados por tratamiento (ver `Guiones_Blissens_.xlsx`) | S |

### 4.3 Cancelación y reasignación *(ideas 2 y 4)*

| ID | Requerimiento | Prio |
|---|---|---|
| RF-12 | El paciente cancela o reprograma desde el mismo enlace | M |
| RF-13 | Al cancelar, se pide el **motivo** (lista corta de opciones + "otro") con un solo toque | M |
| RF-14 | Tras cancelar, el sistema ofrece de inmediato nuevos espacios para reprogramar | M |
| RF-15 | Se registra cada intento de reasignación y su resultado (aceptó, rechazó, sin respuesta) | M |
| RF-16 | Si el paciente no reprograma, se programan recordatorios de seguimiento sobre esa reasignación pendiente (cadencia configurable) | M |
| RF-17 | Se registra si la cancelación fue tardía (umbral configurable, p. ej. < 24 h) | M |

### 4.4 Lista de espera y llenado de cupos *(idea 4)*

| ID | Requerimiento | Prio |
|---|---|---|
| RF-18 | Cuando un cupo queda libre, el sistema identifica candidatos: pacientes con cita futura del mismo tratamiento/especialista que podrían adelantarse | M |
| RF-19 | Envía mensaje automático con respuesta simple: *"Tu cita podría adelantarse de [fecha/hora] a [fecha/hora]. ¿Quieres hacerlo? Sí / No"* | M |
| RF-20 | Si responde **Sí**, el sistema mueve la cita y libera el espacio anterior (que a su vez dispara RF-18 en cadena) | M |
| RF-21 | Reglas de priorización de candidatos (urgencia clínica, tratamiento a medias, valor del paciente, antigüedad en espera) | S |
| RF-22 | Control de concurrencia: un cupo se ofrece a un candidato a la vez (o con expiración) para evitar doble asignación | M |
| RF-23 | Tiempo máximo de espera de respuesta antes de pasar al siguiente candidato (configurable) | M |
| RF-24 | El paciente puede inscribirse voluntariamente en lista de espera para horarios más tempranos | C |

### 4.5 Detección y recuperación de pacientes

| ID | Requerimiento | Prio |
|---|---|---|
| RF-25 | Detección automática (no a fin de mes) de pacientes con tratamiento a medias sin cita futura agendada | M |
| RF-26 | Segmentación por tratamiento pendiente y por valor (internacional, deportista, alto valor) | S |
| RF-27 | Mensajes de recuperación personalizados según el tratamiento que dejó pendiente | S |
| RF-28 | Escalamiento a la auxiliar para pacientes de alto valor o sin respuesta tras N intentos | S |
| RF-29 | Registro del resultado de cada gestión de recuperación | M |

### 4.6 Inteligencia de negocios *(idea 3)*

Hoy **no se miden**: inasistencias de pacientes agendados, tasa de recuperación, motivo de cancelación, tiempo promedio entre citas.

| ID | Requerimiento | Prio |
|---|---|---|
| RF-30 | Cálculo automático de inasistencia (no-show) por periodo, especialista y tratamiento | M |
| RF-31 | Tasa de recuperación (cancelaciones reprogramadas / total de cancelaciones) | M |
| RF-32 | Distribución de motivos de cancelación | M |
| RF-33 | Tiempo promedio entre citas por tratamiento y por paciente | M |
| RF-34 | Ocupación de agenda, cupos vacíos y cupos recuperados por lista de espera | M |
| RF-35 | Tasa de abandono de tratamiento y de recuperación de abandonados | S |
| RF-36 | Ingresos recuperados / perdidos estimados (cruce con aranceles) | S |
| RF-37 | Proceso de cierre (diario/semanal/mensual) que consolida estas variables y las deja listas en un tablero | M |
| RF-38 | Exportación a Excel/PDF mientras dure la transición | C |

### 4.7 Administración y configuración

| ID | Requerimiento | Prio |
|---|---|---|
| RF-39 | Configuración de reglas: umbral de cancelación tardía, cadencia de recordatorios, tiempo de espera de ofertas, intentos máximos | S |
| RF-40 | Gestión de plantillas de mensajes y listas de motivos | S |
| RF-41 | Vista para la auxiliar: citas no confirmadas, cancelaciones sin resolver, pacientes en riesgo, cupos libres | M |
| RF-42 | Bitácora de todos los mensajes enviados y respuestas por paciente | M |

## 5. Requerimientos de datos *(SCAMPER: Excel → base de datos)*

| ID | Requerimiento |
|---|---|
| RD-01 | Base de datos única reemplaza Excel como fuente de verdad (pacientes, tratamientos, citas, estados, cancelaciones, mensajes) |
| RD-02 | Cada cita tiene un estado trazable (programada, confirmada, cancelada, reprogramada, no asistió, atendida) con fecha y quién/qué lo cambió |
| RD-03 | Cada cancelación guarda motivo, momento (antelación) y resultado de reasignación |
| RD-04 | El paciente tiene plan de tratamiento: procedimientos, sesiones previstas, sesiones realizadas |
| RD-05 | Atributos de segmentación del paciente: tratamiento, valor, tipo (internacional/deportista/otro) |
| RD-06 | Integración o sincronización con el software actual de la clínica (por definir: API, base de datos, import) |

## 6. Requerimientos no funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 | Canal principal **WhatsApp** (WhatsApp Business API); interacciones de máximo 1–2 toques |
| RNF-02 | Mobile-first; sin instalación ni cuenta para el paciente |
| RNF-03 | Cumplimiento de protección de datos de salud (Ley 1581 de 2012, Colombia): consentimiento, finalidad, mínimo de datos sensibles en mensajes |
| RNF-04 | Opt-out claro: el paciente puede dejar de recibir mensajes |
| RNF-05 | Tono cálido y cercano alineado con la marca (la clínica enfatiza servicio al usuario) |
| RNF-06 | Disponibilidad suficiente en horario de operación; las automatizaciones fallan de forma segura (si falla, la auxiliar lo ve) |
| RNF-07 | Auditabilidad: todo cambio automático de cita queda registrado y es reversible por la auxiliar |
| RNF-08 | Usabilidad para personal no técnico (la auxiliar debe operarlo sin soporte) |

## 7. Indicadores de éxito (KPIs)

| KPI | Línea base | Meta |
|---|---|---|
| Citas programadas que terminan en atención efectiva | < 50 % (ago–nov) | Por definir con la clínica |
| Tasa de inasistencia | No medida | Medirla primero; meta tras 1 mes de datos |
| Cupos vacíos rellenados por lista de espera | 0 % | Por definir |
| Tasa de recuperación de cancelaciones | No medida | Por definir |
| Pacientes con tratamiento abandonado recuperados | Solo mensual y genérico | Por definir |
| Horas de la auxiliar dedicadas a reprogramar/recordar | No medida | Reducción % |

## 8. Supuestos (a validar)

- Los pacientes responderán a mensajes de WhatsApp con respuestas simples (sí/no).
- El software actual de la clínica permite leer/escribir citas (API, exportación o acceso a base de datos).
- Un porcentaje relevante de cancelaciones es evitable si el paciente puede reprogramar con facilidad.
- Adelantar citas es clínicamente aceptable para la mayoría de tratamientos (hay que excluir los que dependen de etapas, cicatrización, laboratorio).

## 9. Preguntas abiertas

Corresponden al bloque "¿Qué preguntas siguen sin resolver?" del documento, que está vacío:

1. ¿Qué software usa hoy la clínica y qué capacidad de integración tiene?
2. ¿Qué tratamientos admiten adelantar cita y cuáles no? ¿Quién lo define?
3. ¿Cuál es el umbral de "cancelación tardía" para la clínica?
4. ¿Hay penalización o política de cancelación? ¿Se puede introducir?
5. ¿Cómo se define "paciente de alto valor" y "tratamiento abandonado" (cuántos días sin cita)?
6. ¿La clínica tiene sedes/especialistas múltiples con agendas distintas?
7. ¿Ya hay cuenta de WhatsApp Business y proveedor oficial?
8. ¿Qué resultado concreto necesita el paciente? (bloque vacío en el documento, conviene entrevistarlos)
9. ¿Presupuesto y plazo para el prototipo/MVP?

## 10. Alcance sugerido para el MVP

**Dentro:** RF-01, 02, 04, 05, 06, 08, 09, 10, 12–20, 22, 23, 25, 29, 30–34, 37, 41, 42 y los datos RD-01 a RD-04.
**Después:** personalización por valor del paciente, scoring, lista de espera voluntaria, estimación de ingresos, configuración avanzada.

## 11. Ideas pendientes del SCAMPER

- **Sustituir:** Excel → base de datos · recordatorios manuales → sistema automatizado.
- **Combinar:** *(sin completar en el documento)*
- Adaptar, Modificar, Poner en otro uso, Eliminar, Reorganizar: *(sin explorar aún)*
