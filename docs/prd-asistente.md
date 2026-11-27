# PRD: An assistant with a closed tool catalogue for auxiliar, especialista and paciente

> Audience: an implementing agent or a reviewer. Self-contained: read this, `CLAUDE.md`, `README.md`, `GLOSSARY.md` and ADRs 0001, 0002, 0003, 0005, 0007 and 0008.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: the feasibility spike of 2026-11-25. It showed that an MCP server (Python SDK 2.3) mounts inside the existing FastAPI app, and that a tool reading through `db.connect()` sees the active negocio's rows and zero rows without one.

## 1. Goal

Staff and patients can ask questions in plain Spanish and get answers taken from the database, through a **closed catalogue of tools**. What each person can reach is decided by their role, never by the model.

| Who | What they get |
|---|---|
| Auxiliar | "¿Quién no ha confirmado para mañana?", "¿Cuánto perdimos este mes por inasistencias?", and prepared actions she confirms with one click. |
| Especialista | "¿Qué tengo el jueves?", "Bloquea mi viernes en la tarde": only their own agenda. |
| Paciente | "¿Cuándo es mi cita?", "Quiero cambiarla": only their household's appointments, inside a narrow guided chat. It is not a general chatbot. |
| Developer | The same catalogue as an MCP server in a local Claude Code session. |

Success = the access matrix in §5 is enforced by tests, a patient cannot obtain anything the "Mis citas" page does not already show, and no tool call can change the database.

## 2. Principles (each one is a test in §10)

- **P1. Parity.** A perfil's tools are a subset of what that role can already do in the panel or in the personal link. The assistant never grants new access.
- **P2. The assistant never writes.** Action tools return a **propuesta**. The person confirms it, and the client runs it through the endpoint that already exists, with that endpoint's own checks.
- **P3. Identity never comes from the model.** No tool takes `negocio_id`, `usuario_id` or the caller's `paciente_id`. They come from the session or the signed link.
- **P4. Three independent gates.** (1) The model is only sent its perfil's tools. (2) The dispatcher re-checks the perfil and the row scope on every call. (3) The connection runs as `estudia_app` with the negocio fixed, so RLS applies.
- **P5. Minimum data.** A tool returns only the fields it needs. No tool returns a document number, phone, email or birth date in full.
- **P6. Off by default.** With no API key the routes are not registered. With a key, each negocio turns the assistant on, for staff and for patients separately.

## 3. Concepts (add to `GLOSSARY.md`)

- **Asistente**: the conversational feature. It answers using herramientas and prepares propuestas.
- **Herramienta**: one named, typed operation in the catalogue (`estudia/asistente/`). It is either `lectura` or `propuesta`.
- **Actor**: who is asking: a usuario with their acceso, or a paciente identified by their personal link. Built by the server, never by the model.
- **Perfil**: the set of herramientas an actor gets: `paciente`, `especialista`, `auxiliar` or `operador`.
- **Propuesta**: an action the assistant prepared but did not run: a kind, its parameters and a one-line summary. The person confirms or discards it.
- **Operador (perfil)**: the developer's local MCP session. It exists only when `ENTORNO=local`.

## 4. Architecture

### D1. One catalogue, two adapters
- **Catalogue.** New package `estudia/asistente/`. Each herramienta declares: name, Spanish description, a Pydantic input model, the perfiles that may use it, its kind, its audit action, and a handler `(conn, actor, args) -> dict`.
- **Dispatcher.** One function, `ejecutar(actor, nombre, args)`, is the only way to run a herramienta. It checks the perfil, validates the input, opens the connection, runs the handler, writes the audit row and trims the output.
- **Adapter 1: MCP server** (`python -m estudia.asistente.mcp`, stdio). It lists and runs the catalogue for one actor. Used by the developer's Claude Code session.
- **Adapter 2: in-app loop.** The web app calls the Claude API with the actor's herramientas and runs each tool call through `ejecutar`, in the same process.
- **Why the in-app loop does not go through the MCP protocol.** The actor is known inside the request. Passing it over a second network hop would add a token to mint and verify, and a public MCP endpoint to defend, for no gain. Both adapters share the dispatcher, so the rules are identical.
- **Record this as ADR 0009.**

### D2. Connections
- The dispatcher opens one connection **per tool call** with `db.connect(negocio=actor.negocio_id, usuario_id=actor.usuario_id)` and closes it before returning.
- No connection is held while waiting for the model. There is no pool, and the Supabase session-mode pooler has few slots.

### D3. Calling the model
- Use the official `anthropic` SDK. Before writing this code, load the `claude-api` skill and follow it for the tool loop, thinking blocks, refusals and prompt caching.
- Model from `ASISTENTE_MODELO`, default `claude-opus-5-5`. `ASISTENTE_MODELO_PACIENTE` may override it for the paciente perfil (§12, Q2).
- The system prompt and the tool list are fixed per perfil, so they cache. The current date and time come from `clock.now(conn)` and travel in the user turn, not in the system prompt.
- Store each assistant turn as the raw list of content blocks and replay it unchanged. Never edit earlier turns.
- A refusal, a `max_tokens` stop, an API error or a turn longer than 45 s all produce the same fixed reply: "No pude responder eso. ¿Quieres que la clínica te contacte?" (staff: "No pude responder eso. Intenta de nuevo.").

### D4. Environment and switches
- `ANTHROPIC_API_KEY`: add to `render.yaml` with `sync: false` and to `.env.example` as a comment. Without it, the assistant routes are not registered (the ADR 0005 pattern) and the UI hides the entry point.
- New keys in `estudia/config.py` `DEFAULTS`:

| Key | Default | Meaning |
|---|---|---|
| `asistente_equipo` | `false` | The negocio's staff can use the assistant. |
| `asistente_pacientes` | `false` | The negocio's patients can use it. |
| `asistente_mensajes_dia_usuario` | `200` | Messages per staff user per day. |
| `asistente_mensajes_dia_paciente` | `20` | Messages per household per day. |
| `asistente_tokens_dia` | `2000000` | Input + output tokens per negocio per day. Past it, everyone gets the fixed "no disponible" reply. |
| `retencion_asistente_dias` | `30` | Conversations older than this are deleted by the daily purge. |

- No new startup check is needed in `arranque.py`.

## 5. Access matrix

`L` = lectura, `P` = propuesta, `·` = not available. This table is the specification: a snapshot test compares it with the catalogue.

| Herramienta | Paciente | Especialista | Auxiliar | Backed by | Audit action |
|---|---|---|---|---|---|
| `mis_citas` | L | · | · | `_appointments` over `familia.ids_del_hogar` | `asistente:mis_citas` |
| `servicios` | L | L | L | catalogue of active services | · |
| `espacios_libres` | L | · | L | `agenda.available_slots` / `any_slots`; with `cita_id`, that appointment's service and professional (even if not self-bookable, as on «Mis citas»); with «anyone», each slot names its `agenda.assign_professional` | · |
| `datos_del_negocio` | L | L | L | `configuracion.direccion`; opening hours per weekday as the merged `horario_atencion` ranges (a lunch closure shows as two), the days without service, and the active professionals with their id | · |
| `mi_agenda` | · | L | · | `agenda.range_agenda`, own professional | · |
| `agenda` | · | · | L | `agenda.range_agenda`, any professional | · |
| `detalle_cita` | · | L (own) | L | `permisos.cita_visible` | `ver_cita` |
| `mi_horario` | · | L | · | `horario.schedule`, `horario.list_blocks` | · |
| `mi_dia` | · | L | · | `agenda.range_agenda`, own professional, one day: counts, in progress, next, free gaps, blocks | · |
| `citas_sin_desenlace` | · | L | · | own started appointments still alive, last 30 days, at most 50 | · |
| `motivos_cancelacion` | · | · | L | `motivo_cancelacion` (id and label) | · |
| `buscar_pacientes` | · | · | L | `bandejas.find_patients` | `buscar_paciente` |
| `ficha_paciente` | · | · | L | `bandejas.patient_record`, trimmed | `ver_ficha` |
| `resumen_dia` | · | · | L | `bandejas.resumen_dia` | · |
| `bandeja` | · | · | L | the eight `bandejas.*` lists, chosen by an enum | · |
| `indicadores` | · | · | L | `indicators.*`, chosen by an enum | · |
| `proponer_agendar` | P | · | P | `POST /p/{token}/agendar` · `POST /citas` | `asistente:propuesta` |
| `proponer_cambiar_fecha` | P | · | P | `POST /p/{token}/cambiar/{id}` · `POST /citas/{id}/cambiar-fecha` | `asistente:propuesta` |
| `proponer_cancelar` | P | · | P | the cancel screen `/p/{token}/cancelar/{id}` · `POST /citas/{id}/cancelar` | `asistente:propuesta` |
| `proponer_confirmar` | P | · | · | new `POST /p/{token}/confirmar/{id}` (also a button on «Mis citas») | `asistente:propuesta` |
| `proponer_confirmar_telefono` | · | · | P | `POST /citas/{id}/confirmar` | `asistente:propuesta` |
| `proponer_desenlace` | · | P (own) | P | `POST /citas/{id}/desenlace` | `asistente:propuesta` |
| `proponer_bloqueo` | · | P (own) | P | `POST /bloqueos` | `asistente:propuesta` |
| `pedir_contacto` | P | · | · | new `POST /p/{token}/contacto` (§7) | `asistente:propuesta` |

Rules that the table does not show:

- **Administrador is not a perfil.** There are no tools for users, service values or targets. Administration stays in the panel.
- **Especialista has no patient search, no ficha, no bandejas and no indicators**, because the panel gives them none (P1).
- **`operador`** gets every `L` herramienta of the auxiliar, plus `esquema` (tables and columns) and `consulta_sql`. It never gets propuestas. See §8.

### Per-tool limits
- **`mis_citas`**: upcoming appointments of the household only. Returns first name, service, professional, date, time and state. An optional `para` (a household member's id) is checked with `familia.sujeto`.
- **`espacios_libres`**: at most 12 slots per call. For a paciente it returns free times only, never who holds the taken ones.
- **`servicios`**: name and duration. **Never `servicio.valor`** for the paciente perfil: it is an internal average, not a price.
- **`buscar_pacientes`**: at most 10 rows: id, full name, and the last 4 digits of the document.
- **`ficha_paciente`**: name, last 4 digits of the document, consent flags, the last 20 appointments, open follow-up cases, and the last 10 messages. No phone, email or birth date.
- **`bandeja`** and **`indicadores`**: at most 50 rows per call. `indicadores` takes `reporte`, `desde`, `hasta`, and optional `profesional_id` and `servicio_id`.
- **`detalle_cita`** and every tool that takes an id: an id outside the actor's scope returns `no_existe`, the same as an id that does not exist (the `permisos.NoExiste` convention).
- **Every tool**: output is capped at 8 000 characters. Past that, the tool returns the first rows and `"truncado": true`.

## 6. Staff assistant (panel)

- **Endpoints**, under `/api/v1/asistente`, using `usuario_actual`:
  - `GET /estado` → `{ disponible, perfil, mensajes_restantes }`.
  - `POST /mensajes` with `{ conversacion_id?, texto }` → `{ conversacion_id, respuesta, propuestas: [...] }`. `texto` is at most 1 000 characters.
  - `GET /conversaciones/{id}` → the actor's own conversation, to restore it after a reload.
- **Perfil.** `auxiliar` or `especialista`, from `u["rol"]`. A conversation belongs to one usuario and one negocio; changing the negocio starts a new one.
- **Loop limits.** At most 8 tool calls per message. The visible reply aims at 1 500 tokens, which the prompt enforces. `max_tokens` is 4 096, because thinking also spends it and a lower cap cuts replies off.
- **UI.** A drawer opened from the top bar ("Asistente"), available on every screen:
  - the reply is rendered as **plain text with line breaks**: no HTML, no Markdown images, no clickable links;
  - each propuesta is a card with the summary, "Confirmar" and "Descartar". "Confirmar" opens the panel's existing confirmation dialog and calls the existing endpoint with `useAccion`. The assistant is not told the outcome: if asked, it reads the current state again with its tools;
  - while waiting it shows "Escribiendo…". Text streaming is a follow-up (§11).
- **Regenerate** `docs/openapi.json` (`make api-esquema`) and the panel types (`npm run tipos`).

## 7. Patient assistant (personal link)

### Access
- Only from a valid personal link (`/p/{token}`), so only after the patient has identified themselves and accepted the base consent.
- A separate consent is required. First use shows: *"El asistente usa un servicio de inteligencia artificial de un tercero para responder sobre tus citas. Para eso se le envían tu nombre y los datos de tus citas. Puedes seguir usando esta página sin el asistente."* with "Aceptar y continuar" and "No, gracias".
- A familiar uses the responsable's consent, recorded the way `consentimiento_por` already works. A familiar who stopped sharing gives their own.
- With `asistente_pacientes` off or with no API key, "Mis citas" shows no assistant at all and its routes answer 404. With both on, "Mis citas" shows "Preguntarle al asistente"; before consent it leads to the consent screen, and no message reaches the model until the consent is given.

### A narrow chat, not an open one
- **Scope.** The system prompt allows four subjects: the household's appointments, free times, the clinic's address and hours, and asking the clinic to call. Anything else gets one fixed sentence: "Solo puedo ayudarte con tus citas en {negocio}."
- **No clinical content.** No symptoms, diagnoses, treatments or prices. For pain or an emergency: "Llama a la clínica" plus the propuesta `pedir_contacto`.
- **Guided first.** The chat opens with buttons: "¿Cuándo es mi cita?", "Agendar", "Cambiar una cita", "Cancelar una cita", "Que me llamen". Free text is allowed, up to 300 characters.
- **Hard limits.** At most 4 tool calls per message, a visible reply of about 500 tokens (`max_tokens` 2 048, for the same reason as the staff limit), 12 messages per conversation, and `asistente_mensajes_dia_paciente` per household per day. Past a limit: "Por hoy no puedo responder más. ¿Quieres que la clínica te contacte?"
- **Language.** It answers in the language the patient writes in; Spanish by default.

### Routes and UI
- `GET /p/{token}/asistente` renders the chat section; `POST /p/{token}/asistente` (form: `texto`, `conversacion`) returns an HTMX fragment with the reply bubble. Both use `conn_enlace`.
- `POST /p/{token}/asistente/consentimiento` records or withdraws the consent.
- New `POST /p/{token}/contacto` inserts a `solicitud_contacto` with the note "Pidió contacto desde el asistente", so it lands in the existing Contactos tray.
- A propuesta is a card that submits the **existing** form route (`POST /p/{token}/agendar`, `POST /p/{token}/cambiar/{id}`) with its fields filled in. The cancel card opens the existing cancel screen (`GET /p/{token}/cancelar/{id}`), which asks for the reason.
- The reply goes through Jinja autoescape. **Do not apply the `linkify` filter** to assistant text.
- Rate limit by household and negocio in the database (count today's `asistente_mensaje` rows). `LimiteVentana` is per IP and in memory, so it is only a second line.

## 8. Local MCP for the developer

- `python -m estudia.asistente.mcp` speaks stdio. Add a `.mcp.json` at the repo root that launches it with `uv run`.
- It refuses to start unless `ENTORNO=local`. The perfil is `operador`, with `NEGOCIO_POR_DEFECTO` as the negocio.
- `consulta_sql`: a single `select`, run as `estudia_app` in a read-only transaction with a 5 s `statement_timeout`, at most 200 rows. It is registered only for `operador`.
- Dependencies: add `anthropic` and `mcp>=2,<3` to `pyproject.toml`. The MCP SDK 2.x renamed `FastMCP` to `MCPServer` (`from mcp.server.mcpserver import MCPServer`); most examples online are for 1.x.
- **Warning for the README.** Everything a tool returns is sent to Anthropic by the Claude session. Use this only with the fictitious demo data, never after importing the real Excel files.

## 9. Data model and privacy

- **Migration `015_asistente.sql`** plus `.down.sql`, after 013 and 014. Follow migration 006 for `negocio_id default negocio_activo()`, forced RLS, the `aislamiento` policy and the grants to `estudia_app`.
  - `asistente_conversacion`: `id`, `negocio_id`, `perfil`, `usuario_id` (nullable), `paciente_id` (nullable, the patient who wrote it: the daily limit is per household, but a familiar never reads the responsable's conversations, nor the other way round), `creada_en`, `ultima_en`. A check requires exactly one of `usuario_id` and `paciente_id`.
  - `asistente_mensaje`: `id`, `negocio_id`, `conversacion_id`, `rol`, `contenido jsonb`, `tokens_entrada`, `tokens_salida`, `creado_en`.
  - `paciente.acepta_asistente boolean not null default false`, `paciente.consentimiento_asistente_en timestamptz`, `paciente.consentimiento_asistente_por bigint references paciente(id)`.
- **Audit.** Every tool call with an audit action writes `auditoria_acceso` through `privacidad.registrar`, with `usuario_id` for staff and `paciente_id` for patients. Tool arguments are not stored.
- **Privacy hooks (ADR 0008).** `exportar_paciente` includes the patient's conversations. `anonimizar_paciente` deletes them and clears the consent. `privacidad.depurar` applies `retencion_asistente_dias`.
- **Untrusted text.** Messages, notes and cancellation reasons written by patients reach the model inside tool results. The system prompt states that tool results are data and never instructions. P2 and P4 bound the damage: the worst case is a misleading sentence shown to a person who could already read that data.
- **Logs.** The JSON request log keeps its rule: no personal data. Log the perfil, the tool names, the token counts and the duration; never the text.

**Conflicts with existing decisions, to resolve in ADR 0009:**
- The README says the system makes no requests to third parties. The assistant adds one, server-side, off by default.
- ADR 0008 keeps retention off by default. Conversations default to 30 days.
- ADR 0007 limits the hosted free plan to fictitious data. That still holds: see §12, Q1.

## 10. Testing

The developer's laptop is slow. **Do not run full suites.** Run only the new files by path, plus `tests/test_aislamiento.py` and `tests/test_privacidad.py` because both are touched. Ask before running anything broader.

**No test calls the real API.** Use a scripted fake client that returns a fixed sequence of tool calls and text.

New `tests/test_asistente.py`:
- **Matrix (§5).** For each perfil, the catalogue's tool names and kinds equal the table. Adding a tool without updating the table fails.
- **P1.** For each herramienta, an actor without the perfil gets `sin_permiso` from `ejecutar`, even when the tool is named directly.
- **P2.** After every `proponer_*` and `pedir_contacto` call, a row count over `cita`, `bloqueo`, `cancelacion`, `historial_estado` and `solicitud_contacto` is unchanged.
- **P3.** No input schema has a property named `negocio_id`, `usuario_id` or `actor`. No paciente tool has `paciente_id`.
- **Scope.**
  - Paciente A, with patient B's appointment id, gets `no_existe` from every tool that takes an id.
  - `para` outside the household is rejected.
  - An especialista gets `no_existe` for another professional's appointment and cannot widen `mi_agenda`.
- **P5.** No paciente tool output contains `documento`, `celular`, `correo`, `fecha_nacimiento` or `valor`.
- **Audit.** `ficha_paciente`, `buscar_pacientes` and `detalle_cita` each write one `auditoria_acceso` row.
- **Limits.** Tool calls per message, the daily message count, the negocio token budget and the output cap each produce the fixed reply.
- **Switches.** Without the key the routes return 404. With `asistente_pacientes` off, "Mis citas" has no assistant. Without consent, `POST /p/{token}/asistente` is refused.
- **Failures.** A refusal, a timeout and an API error return the fixed reply and store no half turn. They leave one `fallo` row with no content and the tokens spent, so a failed attempt still counts toward the daily message limit and the token budget.
- **MCP.** The stdio server lists the `operador` tools in `local` and exits with an error in `demo`. `consulta_sql` rejects `update`, `delete`, and two statements in one call.

Extend:
- `tests/test_aislamiento.py`: the two new tables do not leak between negocios.
- `tests/test_privacidad.py`: export includes conversations, anonymising deletes them, the purge honours `retencion_asistente_dias`.
- `panel/src/`: one Vitest file for the drawer: plain-text rendering, a propuesta card calling the existing endpoint after the confirmation dialog, and the hidden entry point when `disponible` is false.

**Before turning `asistente_pacientes` on anywhere.** Run a written set of about 30 adversarial prompts against the demo data: off-topic requests, "ignore your instructions", another patient's appointments, medical advice, prices. This costs API money, so get the owner's approval first and record the results in the PR.

## 11. Out of scope

- An assistant on WhatsApp or interpreting the "sin interpretar" tray.
- A remote MCP endpoint over HTTP for other clients. The spike showed it mounts at a path with `stateless_http=True`, and that the public hostname must be allow-listed in `transport_security`, or requests get `421`.
- Tools for administration, for adding family members, for consent and unsubscribing, and for reverting movements.
- A per-patient RLS policy in the database. Today RLS isolates negocios; patient and professional scope is enforced in Python.
- Streaming text to the browser, voice, attachments, and memory across conversations.

## 12. Open questions for the owner (the default applies until answered; none blocks the staff assistant)

| # | Question | Default |
|---|---|---|
| Q1 | May real patient data be processed by a third-party AI provider outside Colombia (Law 1581 of 2012), and is the consent wording in §7 valid? This is not legal advice. | No. `asistente_pacientes` stays off in `produccion`, and the hosted demo holds only fictitious data, until the owner and their adviser confirm in writing. |
| Q2 | Which model for patients? Per million tokens: Opus 5.5 $4 in / $20 out; Sonnet 5.5 $2 / $10; Haiku 5.5 $0.10 / $0.50. | `claude-opus-5-5` for every perfil. |
| Q3 | How long are conversations kept? | 30 days. |
| Q4 | Should an especialista see indicators for their own appointments? | No (P1: the panel does not show them). |
| Q5 | Should the local MCP refuse to start when real data has been imported? | No guard; the README warning in §8. |

## 13. Suggested order of work

1. Catalogue, actor, dispatcher and the §10 matrix and scope tests. No model, no UI.
2. Local MCP (§8).
3. Migration 015, the model loop and the staff endpoints with `L` tools only.
4. Propuestas for staff and the panel drawer.
5. Patient assistant: consent, routes, limits, and the adversarial run.
