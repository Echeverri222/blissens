# PRD: Assistant phase 2 — a support assistant on the public site, and a fuller especialista assistant

> Audience: an implementing agent or a reviewer. Read `docs/prd-asistente.md` (phase 1) and ADR 0009 first: this PRD only states what changes. Also `docs/prd-sitio-publico.md` for the landing page.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention). The public site is also served in English at `/en`.
> Status: not started. Phase 1 is on branch `MCP` (draft PR #22) and has never been run against the real model API. Nothing here should start before phase 1 has answered one real request.
> Assumption: "support on `http://localhost:8000/`" means a help chat for **visitors of the public landing page** (`/` and `/en`), not help for staff on how to use the panel.

## 1. Goal

Two follow-ups to phase 1, independent of each other:

- **Part A. Asistente del sitio.** An anonymous visitor of the landing page can ask about services, opening hours, location, how to book, the virtual assessment and the Experiences, and can be handed to the existing contact form. It knows nothing about any patient and never will.
- **Part B. Especialista.** The especialista perfil already exists in phase 1 and already opens from the panel drawer. It is thin (seven tools) and its UI text was written for the auxiliar. Part B makes it useful for a specialist's day without giving it anything the panel does not already give.

Success: a visitor gets a correct answer taken from text the clinic already published, or reaches the contact form, without the clinic's cost being open-ended; a specialist can ask "¿quién sigue?" and close yesterday's appointments from the drawer.

## 2. Principles

P1–P6 of phase 1 hold unchanged. Part A adds three, each one a test in §8:

- **P7. A visitor has no identity and gets no patient data.** The `visitante` perfil has no tool that reads `paciente`, `cita`, `mensaje`, `solicitud_contacto` or any table with personal data. It cannot confirm or deny that someone is a patient.
- **P8. Personal data does not go through the model.** Name, phone, email and document are typed by the visitor into the existing form, never into the chat. Text that looks like a phone, a document or an email is stopped before the model call.
- **P9. Public traffic has its own budget.** The site assistant has its own switch, its own daily message and token budgets and its own concurrency cap. Exhausting them never affects the staff or patient assistants, and the landing page keeps working with the chat gone.

## 3. Concepts (add to `GLOSSARY.md`)

| Term | Meaning |
|---|---|
| **Visitante** | Someone on the public site who has not identified themselves. An actor with a negocio and nothing else. |
| **Asistente del sitio** | The assistant a visitante talks to on the landing page. Perfil `visitante`. |

Record the decision in a new ADR (`docs/adr/0010-asistente-del-sitio.md`): phase 1 says an actor is "a user with their access, or a patient identified by their link"; this adds an actor with no identity.

## 4. Part A — Asistente del sitio

### A1. What it may talk about

- **Scope.** Six subjects: services (name and duration), opening hours and address, how to book, the virtual assessment, the Experiences and their packages, and reaching a person. Anything else gets one fixed sentence: "Solo puedo ayudarte con información de {negocio}." / "I can only help with information about {negocio}."
- **Only published text.** Every fact comes from a herramienta backed by `estudia/web/copia.py` or by the service catalogue. If the copy does not state a price, the assistant does not state one: it offers the contact form.
- **No clinical content.** No symptoms, diagnoses, treatment advice or suitability ("¿me sirve X?"). Fixed answer plus the contact card. For pain or an emergency: "Si es una urgencia, llama a la clínica" with the phone from `copia.TELEFONO`.
- **Existing patients.** "Ya tengo una cita", "quiero cambiar mi cita" → it does not look anything up. It points to `#agendar`, where identifying with document and phone leads to the personal link, which has the patient assistant of phase 1.
- **Language.** The page's language (`es` at `/`, `en` at `/en`), unless the visitor writes in the other one.

### A2. Tools (perfil `visitante`)

| Herramienta | Clase | Backed by | Notes |
|---|---|---|---|
| `servicios` | L | catalogue of active services | Existing tool. Name and duration; never `servicio.valor`. |
| `datos_del_negocio` | L | `configuracion.direccion`, `horario_atencion` | Existing tool. |
| `informacion_del_sitio` | L | `copia.COPIA[idioma]` | New. Input `tema`, a closed enum: `como_agendar`, `evaluacion_virtual`, `experiencias`, `equipo`, `contacto`. Returns that section's published text, plain, at most 4 000 characters. A small table in the catalogue maps each `tema` to keys of `copia.COPIA`; a test fails if a key disappears. |
| `ir_a_seccion` | P | an anchor of the landing page | New. Input `seccion`, a closed enum: `agendar`, `evaluacion_virtual`, `experiencias`, `contacto`. The card is a button that scrolls to that section. |
| `proponer_solicitud` | P | `POST /sitio/solicitud` | New. Inputs `interes` (the keys of `copia.INTERESES`) and `mensaje` (at most 300 characters, the visitor's question in their words). The card is the **existing** form with `interes` chosen and `mensaje` filled in and editable. The visitor types name, phone and email, ticks the consent and submits it themselves. |

Not available, and why:

- **`espacios_libres`.** Today free times are shown only after identifying. Showing them to anonymous visitors would be new access (P1) and would let anyone scrape how full the agenda is. See Q3.
- **`mis_citas`, every other `proponer_*`, `pedir_contacto`.** They need an identity.

The site copy goes through a tool rather than into the system prompt so the prompt stays small and fixed, and so the catalogue stays the one place that says what the model can read.

### A3. Limits

| Limit | Value | Where |
|---|---|---|
| Characters per message | 300 | `AJUSTES["visitante"]` |
| Tool calls per message | 3 | `AJUSTES["visitante"]` |
| Messages per conversation | 8 | `AJUSTES["visitante"]` |
| `max_tokens` / effort | 2 048 / `low` | same reasons as the paciente perfil |
| Time budget per message | 20 s | a visitor will not wait the 45 s the staff get |
| Messages per visitante per day | `asistente_sitio_mensajes_visitante`, default 10 | counted in the database |
| Messages per negocio per day | `asistente_sitio_mensajes_dia`, default 300 | counted in the database |
| Tokens per negocio per day | `asistente_sitio_tokens_dia`, default 500 000 | counted in the database, `fallo` rows included |
| Simultaneous model calls | 4 per process | a semaphore; the app is synchronous and a flood of chats must not use up the worker threads the rest of the site needs |
| Requests per IP | `LimiteVentana(10, 600)` | second line only (see the caveat below) |

- Past any limit the reply is fixed, never an error page: "Por ahora no puedo responder más. Déjanos tus datos y te contactamos." plus the contact card. Past the negocio's daily budget the entry button is not rendered at all.
- **Caveat on the per-IP limit.** `_ip_cliente` uses the socket address. Behind Render's proxy every visitor shares one bucket until trusted proxies are configured (already noted in `docs/prd-sitio-publico.md`). So the database budgets are the real stop, and the per-IP limit must not be tuned to be it.
- **Worst-case cost** is the token budget times the model's output price. With the default budget and the prices in phase 1's Q2, that is under US$10 a day on the most expensive model, and far less on a cheaper one.
- **Model.** New setting `ASISTENTE_MODELO_SITIO`; when unset it falls back to `ASISTENTE_MODELO_PACIENTE`, then `ASISTENTE_MODELO`. See Q2.

### A4. Identity, switches and the personal-data filter

- **Switch.** New `asistente_sitio` in `configuracion`, default off. With no API key the routes are not registered (P6). With the switch off they answer 404.
- **Who the visitante is.** Opening the chat sets a cookie `visitante`: a random 128-bit id signed with `itsdangerous`, `HttpOnly`, `SameSite=Lax`, `Secure` outside `local`, one day. The database stores its SHA-256, never the IP. A message with no valid cookie gets a new conversation, so clearing cookies only resets the per-visitante limit, not the negocio's.
- **Actor.** `Actor(perfil="visitante", negocio_id=…, visitante=<hash>)` built by the route from `conn_publica`. No `usuario_id`, no `paciente_id`.
- **Notice, not consent.** There is no personal data to consent to, but the chat opens with a fixed line before the first message can be sent: "Este asistente usa un servicio de inteligencia artificial de un tercero. No escribas datos personales ni de salud." / the English equivalent. See Q1.
- **Filter (P8).** Before the model call, text with seven or more digits (ignoring spaces, dots and dashes) or with something shaped like an email address is not sent and is not stored. The reply is fixed: "Por tu seguridad no escribas datos personales aquí. Usa este formulario." plus the contact card. The attempt still counts toward the limits.
- **Honeypot.** The message form carries the same hidden `web` field as `/sitio/solicitud`; a filled one gets the normal-looking fixed reply and no model call.

### A5. Routes and UI

- `GET /sitio/asistente/entrada?idioma=` → the floating button, or 204 when the switch is off or the daily budget is spent. The landing page includes one empty placeholder with `hx-get` on load, and only when the app has a key (`app.state.asistente`), so **the landing page still renders without a database connection** and makes no extra request when there is no key. The switch may be cached in process for 60 s.
- `GET /sitio/asistente?idioma=` → the chat panel (sets the cookie). `POST /sitio/asistente` (form: `texto`, `conversacion`, `idioma`, `web`) → an HTMX fragment with the reply and its cards. Both use `conn_publica`, and close the connection before calling the model, as the patient route does.
- **Button.** Bottom right, "¿Necesitas ayuda?" / "Need help?". It must not cover the submit button of any form at 360 px wide.
- **Guided first.** The panel opens with buttons: "Servicios", "Horarios y ubicación", "Cómo agendar", "Evaluación virtual", "Experiencias", "Hablar con una persona". "Horarios y ubicación", "Cómo agendar" and "Hablar con una persona" are answered from the copy **without calling the model**. Free text is allowed below them.
- **A person is always one tap away.** "Hablar con una persona" stays visible for the whole conversation and shows the contact card plus the phone link.
- **Rendering.** Plain text through Jinja autoescape; no `linkify`, no Markdown, no HTML from the model. Cards are built by the server from validated propuestas (closed enums), never from model text.
- **Accessibility.** `role="log"` with `aria-live="polite"`, focus moves into the panel on open and back to the button on close, Escape closes, a visible "Escribiendo…" state.
- **No third-party requests.** The existing test that the landing page loads nothing from other hosts must keep passing. No CAPTCHA.
- **Without JavaScript** the button never appears and the page is exactly what it is today.

### A6. What the team sees

- A solicitud sent from a card lands in the existing "Contactos y solicitudes" tray like any web lead, with "Desde el asistente del sitio" in its note (or `origen = 'asistente_sitio'` if WP4 of the site PRD has added structured columns by then).
- The team does not see transcripts (Q4). The visitor's question travels in `mensaje`, which they saw and could edit.

### A7. Data model and privacy

New migration `016_asistente_sitio.sql` (+ `.down.sql`). **Do not edit 015**: the migrator refuses to run when an applied file has changed.

- `asistente_conversacion`: `perfil` also accepts `visitante`; new nullable `visitante text` (the cookie hash) and `idioma text`; the "exactly one actor" check becomes one of `usuario_id`, `paciente_id`, `visitante`; index on `(negocio_id, visitante, ultima_en desc)`. RLS unchanged.
- New keys in `estudia/config.py`: `asistente_sitio` (False), `asistente_sitio_mensajes_visitante` (10), `asistente_sitio_mensajes_dia` (300), `asistente_sitio_tokens_dia` (500 000), `retencion_asistente_sitio_dias` (7).
- **Retention.** Visitor conversations are purged after `retencion_asistente_sitio_dias` by the existing purge in `estudia/privacidad.py`. They are short-lived on purpose: the filter cannot catch a name or a health detail typed in free text.
- **Not linked to a patient.** A visitor who later books is not joined to their earlier chat. Visitor conversations are not part of a patient's export or anonymisation.
- `render.yaml` and `.env.example`: `ASISTENTE_MODELO_SITIO`.

## 5. Part B — Especialista

### B1. What exists today (phase 1, branch `MCP`)

With a key and `asistente_equipo` on, an especialista sees "Asistente" in the panel header, the same drawer as the auxiliar. Its tools: `servicios`, `datos_del_negocio`, `mi_agenda`, `detalle_cita` (own), `mi_horario`, `proponer_desenlace` (own), `proponer_bloqueo` (own). Limits are the staff ones.

Gaps:

1. The empty-state text says "Pregúntame por la agenda, los pendientes o los pacientes", but an especialista has no pendientes and no patient search.
2. "¿Quién sigue?" and "¿qué citas me faltan por cerrar?" work only if the model reads a whole agenda range and filters it itself.
3. Two things the panel lets a specialist do have no propuesta: removing an own block (`DELETE /bloqueos/{id}`) and reverting a movement (`POST /historial/{id}/revertir`).
4. The conversation is lost when the page reloads, which on a phone between patients is often.

### B2. Changes within today's access (no panel change needed)

| Herramienta | Clase | Backed by | Notes |
|---|---|---|---|
| `mi_dia` | L | `agenda.range_agenda`, own professional, one day | Input: optional `dia` (default today). Returns counts by estado, the next appointment (time, service, patient's first name), free gaps and blocks. A summary of what `mi_agenda` already returns. |
| `citas_sin_desenlace` | L | own past appointments whose `acciones` include `desenlace` | At most 30 days back and 50 rows. |
| `proponer_quitar_bloqueo` | P (own) | `DELETE /bloqueos/{id}` | `mi_horario` must return each block's id. An id that is not the actor's returns `no_existe`. |
| `proponer_revertir` | P (own) | `POST /historial/{id}/revertir` | `detalle_cita` must return, per history entry, its id and whether the route would accept reverting it. The tool applies the same rule as the route; it adds none. |

- The auxiliar perfil also gets `proponer_quitar_bloqueo` and `proponer_revertir`, with the scope the panel already gives it.
- **Several appointments in one message** ("cierra las de ayer como atendidas") produce one card per appointment, each confirmed on its own, at most 10 cards per reply. There is no "confirmar todas" (Q6).
- **Text by perfil.** `GET /asistente/estado` returns `perfil`. For an especialista the empty state reads "Pregúntame por tu agenda o tu horario, o pídeme cerrar una cita o bloquear un espacio." with four tappable suggestions: "¿Qué tengo hoy?", "¿Quién sigue?", "¿Qué citas me faltan por cerrar?", "Bloquea mi agenda mañana de 2 a 4".
- **Keep the conversation across a reload.** The drawer keeps the open conversation id in `sessionStorage` and restores it with the existing `GET /asistente/conversaciones/{id}`. Propuestas of restored turns are shown closed ("Ya no se puede confirmar desde aquí"), since their outcome is not stored. For both staff perfiles.
- **Prompt.** `ESPECIALISTA` in `instrucciones.py` gains the four new tools and one rule: it does not give clinical advice and does not keep clinical notes.

### B3. Gated on the panel (P1: the panel first, then the assistant)

| Wanted | Blocked on | Then |
|---|---|---|
| Patient context for an own appointment: first visit or control, number of visits, last and next appointment, reception note, alerts | WP6 of `docs/prd-sitio-publico.md` (the "Paciente" section of the appointment detail), not built | New tool `contexto_paciente` (L, own patients only) that calls the same function WP6 adds. Another specialist's patient returns `no_existe`. |
| Own indicators | Q4 of phase 1 (default No) | Only if the owner says yes and the panel shows them first. |
| Leaving a request for reception ("agendar control en 15 días") | Does not exist in the panel (Q5) | Only if the panel gets it first. |

### B4. What an especialista never gets

Patient search, the ficha, bandejas, other professionals' agendas, free-slot search, and agendar / cambiar fecha / cancelar / confirmar por teléfono. The panel API refuses all of them to this role, and so does the dispatcher.

## 6. Access matrix (changes only)

`L` = lectura, `P` = propuesta, `·` = not available. Merge into the table of phase 1 §5; the snapshot test compares the merged table with the catalogue.

| Herramienta | Visitante | Paciente | Especialista | Auxiliar | Audit action |
|---|---|---|---|---|---|
| `servicios` | L | L | L | L | · |
| `datos_del_negocio` | L | L | L | L | · |
| `informacion_del_sitio` | L | · | · | · | · |
| `ir_a_seccion` | P | · | · | · | · |
| `proponer_solicitud` | P | · | · | · | · |
| `mi_dia` | · | · | L | · | · |
| `citas_sin_desenlace` | · | · | L | · | · |
| `proponer_quitar_bloqueo` | · | · | P (own) | P | `asistente:propuesta` |
| `proponer_revertir` | · | · | P (own) | P | `asistente:propuesta` |
| `contexto_paciente` (after WP6) | · | · | L (own) | · | `ver_ficha` |

Visitante propuestas are not audited: `auditoria_acceso` records who accessed patient data, and here there is neither a who nor patient data. `operador` gets the new `L` tools of the especialista only through the auxiliar's equivalents, as today.

## 7. Out of scope

- Free times, booking, or anything about an existing appointment from the public chat.
- WhatsApp, voice, or a chat that a person from the clinic can take over live.
- Showing transcripts to the team, and an analytics screen (the tables allow counting conversations and solicitudes later).
- Help for staff about how to use the panel.
- Telling the assistant what happened to a propuesta after the person confirmed or discarded it (still open from phase 1).
- Clinical notes, dictation, or any clinical record for the especialista.
- Any new access for a role. Where a specialist needs more, the panel changes first (§B3).

## 8. Testing

Same rules as phase 1: the model is never called (a fake client is injected), `tests/conftest.py` keeps the key empty, and tests share one database, so run one pytest process at a time and only the files touched.

- **P7.** A seeded patient with a recognisable name, an appointment and a solicitud: no `visitante` tool output and no request sent to the fake client contains them. `ejecutar` with a visitante actor returns `sin_permiso` for every tool outside §A2, named directly. No visitante input schema has an id property.
- **P8.** A message with a phone, a document number or an email produces no model call and no stored text, and the reply carries the contact card. `proponer_solicitud` has no name, phone, email or document input.
- **P9.** With the site budgets spent, `/sitio/asistente/entrada` is 204 and a staff message still gets a reply; with the staff budget spent, the site still answers. A fifth simultaneous call gets the fixed "busy" reply without waiting.
- **P2.** After `proponer_solicitud` the count of `solicitud_contacto` is unchanged; it changes only when the form is posted.
- **P6.** No key: no `/sitio/asistente*` route and no placeholder in the landing HTML. Key and switch off: 404 and 204.
- **Landing page.** Still renders with no database connection; still loads nothing from another host; ES and EN both have the placeholder when a key is set.
- **Rendering.** A model reply containing `<script>` and a Markdown link comes out as inert text. A propuesta with a `seccion` or `interes` outside the enum is dropped.
- **Limits.** 301 characters, the ninth message of a conversation, the eleventh of the day for one cookie, a filled honeypot: each gets its fixed reply and no model call.
- **Migration.** 016 goes up and down; a row with two actors, or with `perfil = 'visitante'` and no `visitante`, is rejected.
- **Especialista.** `mi_dia` and `citas_sin_desenlace` return only the actor's professional. `proponer_quitar_bloqueo` and `proponer_revertir` on another professional's block or appointment return `no_existe`. An auxiliar-only tool named directly returns `sin_permiso`. Row counts are unchanged after each propuesta.
- **Panel.** Suggestions and empty-state text by perfil; `ejecutarPropuesta` maps `quitar_bloqueo` and `revertir` to their endpoints; a reload restores the conversation with its propuestas closed.

## 9. Open questions for the owner (the default applies until answered)

| # | Question | Default |
|---|---|---|
| Q1 | Is the notice in §A4 enough for an anonymous chat that uses a third-party AI provider, and does the `visitante` cookie need to be mentioned in the privacy policy? This is not legal advice; it goes with Q1 of phase 1. | Ship switched off; turn on only after the owner's answer. |
| Q2 | Which model for the public site? It answers from fixed copy with five tools, so the cheapest tier is the natural candidate, but that needs to be checked with real questions in both languages. | Same model as the paciente perfil until tested. |
| Q3 | Should a visitor see free times before identifying? | No. |
| Q4 | Should the team be able to read visitor transcripts (for quality), and for how long? | No transcripts in the panel; 7 days of retention. |
| Q5 | Should a specialist be able to leave a request for reception from the panel? | No. |
| Q6 | Should several propuestas be confirmable with one tap? | No: one confirmation per action. |
| Q7 | Do the published texts state prices for the Experiences and services? If not, every price question ends in the contact form. | The assistant states only what the copy states. |

## 10. Suggested order of work

Part B first: it is small and adds no public exposure.

1. **B-1.** `perfil` in `/asistente/estado`, text and suggestions by perfil, conversation restored after a reload.
2. **B-2.** ~~`mi_dia`, `citas_sin_desenlace`~~ (done), `proponer_quitar_bloqueo`, `proponer_revertir`, with the `mi_horario` and `detalle_cita` additions and the panel mapping.
3. **A-1.** Migration 016, the `visitante` perfil, the three new tools, config keys, ADR 0010, glossary.
4. **A-2.** Routes, cookie, filter, limits, budgets, semaphore. All of §8 for Part A except the UI.
5. **A-3.** Button and chat panel on `/` and `/en`, guided buttons, cards, accessibility.
6. **A-4.** The "Desde el asistente del sitio" marker in the tray.
7. **B-3.** `contexto_paciente`, once WP6 of the site PRD is built.

Before turning Part A on anywhere real: one real request to the model API has worked (phase 1 has not had one), trusted proxies are configured so the per-IP limit means something, and Q1 is answered.
