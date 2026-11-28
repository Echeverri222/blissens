# PRD: Adjustments from the clinic's answers (Nov 2026)

> Audience: an implementing agent or a reviewer. Self-contained: read this, `CLAUDE.md`, `README.md`, `GLOSSARY.md`, `requirements.md` and the PRDs it cites.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: the clinic's written answers to our question list (received 2026-11-28, kept outside the repo). **The repo is public: never copy real figures, patient data or excerpts of the Excel files into code, tests, issues or commits.** Staff names below already appear on the public site (`estudia/web/copia.py`).

## 1. Goal

The clinic confirmed most of what we built and corrected several assumptions. This PRD turns every answer into a decision: confirmed (no change), adjust, or build.

Their definition of success, in their words: **more patients rebooked, more plan payments (abonos), fewer gaps in the agenda.**

- **Daily user:** recepción (one person, handles WhatsApp Web, calls and messages during clinic hours).
- **Reviewer:** gerencia, through Indicadores.
- **Root cause they named:** weak follow-up after the valoración and no systematic reminders about the next payment. Patients leave with a plan and nobody reminds them of the next step. R13 and R14 address this directly.

## 2. Answer → decision map

| # | What the clinic said | Today in the code | Decision |
|---|---|---|---|
| 1 | Software is Dentalink; agenda exported in Excel by range; future appointments can be exported too | `data.importar` reads two Excel files (agenda + estados) | Our system **replaces Dentalink for the agenda** (§3, R24). The Excel import becomes the migration and the bridge during the overlap; verify future appointments in R1 |
| 2 | Past appointments still "Confirmado" were never closed: treat them as **no-shows pending cleanup**, not as attended | Imported as `confirmada`; count in `sin_desenlace` but not in no-show rate | **R1** |
| 3 | "Cambio de fecha" = old appointment moved; "Anulado" = cancelled by the clinic; "Anulado por pte. vía WhatsApp" = cancelled by the patient | All map to `cancelada`/`reprogramada`; key spelled `pcte.` | **R1** |
| 4 | "No Aplica" in *Antigüedad paciente* = new patient; "RO" = Revisión Odontológica | Not read | **R1** |
| 5 | Almost every appointment shows as booked by Dr. Olarte's user (main agenda user), not because he attends them | Professional taken from *Nombre Profesional* | **R1** (verify the column) |
| 6 | High-value patients are recognised by the appointment comment ("Deportista"); they could use *Tipo Paciente* | Segments read only from *Tipo Paciente* | **R1** |
| 7 | Some records have no mobile: they contact the guardian/relative, or the patient is already in a WhatsApp chat | Familia model (`responsable`) exists | **R8** |
| 8 | Valoración lasts 45 min; other durations depend on procedure and the specialist decides | Valoración = 30 min; no per-appointment override | **R2** |
| 9 | Agenda per specialist; when Dr. Olarte travels, they offer Dra. Sara López | No substitute concept | **R4** |
| 10 | Hours Mon–Fri 8:00–12:00 and 13:00–17:00, lunch 12–13 | `default_hours` = 07:30–12:00 / 13:00–17:30 | **R3** |
| 11 | Dra. Laura Vélez no longer works there; replaced by Dr. Juan Esteban | Site lists Laura Vélez | **R22** |
| 12 | WhatsApp Business (app) via WhatsApp Web, one person, **no Meta API, no chatbot** | Channel port: simulated / test / WhatsApp API; the automatic flow (reminders, buttons, follow-up, offers) already runs on it | **R16**: propose the official API, keep the current automatic flow |
| 13 | Cancellation reason not recorded; want quick buttons with the 4–5 most frequent | 8 reasons, WhatsApp list | **R11** |
| 14 | Write at **3, 7 and 15 days** after cancellation or no-show; **3 attempts** is acceptable | Cadence `[0, 3, 7, 15]` (4 sends) | **R7** |
| 15 | Always confirm 24 h before by WhatsApp or call | Reminders at 48 h and 24 h | Confirmed. No change |
| 16 | No deposits (anticipo 20–30 %) for now | Not built | Non-goal |
| 17 | Personalised plans, no packages; plan payments dropped; want **gentle balance reminders at 3 and 7 days**, accompanying, not collecting | Nothing about plans or payments | **R14** |
| 18 | Follow-up works better **with the doctor's name** | Recovery templates have no professional | **R10** |
| 19 | New patients come by word of mouth and athlete ambassadors; profile: local, 25–55, valoración/limpieza/ortodoncia/rehab | Not tracked | **R20** |
| 20 | "Lost" = 60 days without coming and without rebooking; red = cancelled or no-show and not rebooked; flag 3+ date changes | `dias_riesgo = 30`, treatment-based; no per-patient colour | **R5** |
| 21 | Recall: cleaning every 6 months; ortho/aligner control every month | Not built | **R13** |
| 22 | Never contact: finished treatment, active complaint, debt in collection, deceased | Only `acepta_mensajes` (opt-out) | **R6** |
| 23 | Automatic send failed for patients with mistyped numbers or no WhatsApp: **validate before sending** | `normalize_phone` only in the importer | **R8** |
| 24 | A freed slot can be offered 24 h ahead; same-day bookings OK | `antelacion_minima_cupo_horas = 2` | Confirmed. No change (2 h minimum already allows same-day) |
| 25 | Mark patients who **want to move their appointment earlier** | Offers go to any candidate | **R15** |
| 26 | Good occupancy = **85 %+**; Mondays and Wednesdays are hardest to fill | Occupancy shown, no default target | **R18** |
| 27 | Internationals stay 1–2 weeks, book before arriving, write in Spanish or English | Virtual assessment exists; messages only in Spanish | **R21** |
| 28 | Consent: given when registering the number; no signed consent for automatic messages; **want a clear consent format** | `texto_consentimiento`, `consentimiento_en` | **R17** + deliverable |
| 29 | Phone handled by recepción in clinic hours; outside hours they answer next business day | Messages outside hours wait silently | **R12** |
| 30 | **Usted** on first contact and formal messages; adapt if the patient uses tú; recovery: warm *usted* | Everything uses *tú* | **R9** |
| 31 | Value per appointment by procedure type, or plan value; don't use the tariff average ($0 and filler prices) | `servicio.valor` exists | Confirmed + **R19** |
| 32 | Love "Tu futura sonrisa" (main tagline) and "Volver a empezar" (recovery) | Tagline already on the site | Confirmed + **R10** |
| 33 | No brand manual; logo available in PNG/original | Logo PNG in `static/sitio` | No change. Ask for the vector file (§6) |
| 34 | Podcast is part of their content, not the brand's core | — | No change |
| 35 | Site: fix noindex, link Instagram/Facebook, real text for Experiencias | Our site is already `index, follow`; `REDES` without URLs | **R22** |
| 36 | Few web form requests; most come by WhatsApp; recepción registers web ones and replies by WhatsApp | Solicitudes + Bandejas exist | **R22** |
| 37 | Public demo: anonymised data (e.g. "Paciente001, mujer, 32 años, limpieza, No asistió"), 100 % local, no clinical notes | Fictional seed; importer for real data | **R23** |
| 38 | Want the commercial guidelines document | — | Deliverable (§5) |

### Prospects (merged in PR #35, after this PRD was drafted)
A **prospecto** is a `paciente` row with `etapa = 'prospecto'`: no document, internacional, no automatic-message consent, can't book in person (ADR 0010). New migrations in this PRD start at **021**. Rules for prospects:
- R5 colours, R7 follow-up, R13 check-ups, R14 plans and R15: do not apply (no appointments). R5 shows "Prospecto" instead of a colour.
- R6 "No contactar" applies to them too.
- R8: use the same digit rule as the prospect de-duplication (`regexp_replace(celular, '\D', '', 'g')`); the new normaliser must not break it.
- R17: prospects already have no automatic-message consent; they stay in the assisted fallback.
- R20: prospects get `origen = 'web'` by default. R21: a prospect from `/en` gets `idioma = 'en'`.
- R26/R25: Bliss never confirms or denies that a prospect exists (same rule as for patients).

## 3. Requirements

Priorities: **M** must (before the final demo), **S** should, **C** could.

### Phase A — Data the clinic can trust

#### R1. Import semantics from Dentalink (M)
- **State mapping (`ESTADOS` in `estudia/data.py`).** Normalise keys before lookup: lowercase, strip accents and punctuation, collapse spaces. Then "anulado por pte. vía whatsapp", "anulado por pcte via whatsapp" and similar all match.
  - "Anulado" → `cancelada` with `cancelacion.canal = 'clinica'` and no reason. It is a cancellation by the clinic: exclude it from patient-cancellation figures and from follow-up cases.
  - "Anulado por pte. vía WhatsApp" → `cancelada`, `canal = 'whatsapp'`, `motivo_id` null.
  - "Cambio de fecha" → `reprogramada` (unchanged).
  - Store the original text in `datos_origen.estado_origen` for audit.
- **Unclosed past appointments.** An imported appointment whose day is before today and whose state is alive (`programada`, `confirmada`, `no_confirmada`) stays alive and keeps showing in "citas por cerrar" so recepción can clean it up.
  - Indicators: add `inasistencia_por_depurar` (count) to `/indicadores/resumen`. Add `inasistencia_con_pendientes` = `(no_asistio + por_depurar) ÷ (atendidas + no_asistio + por_depurar)`. The key card shows the official rate and, below it, "Si las N citas sin cerrar fueron inasistencias: X %".
  - Never count these as attended.
- **Antigüedad paciente.** If the column exists and says "No Aplica", set `datos_origen.paciente_nuevo = true` on that appointment. Indicators may later split new and returning patients; for now only store it.
- **Especialidad "RO".** Map to "Valoración o revisión" when the comment gives no other service.
- **Professional vs. agenda user.** Before changing code, check locally (headers and distinct counts only, **never print names**) whether *Nombre Profesional* carries the attending professional or the agenda user.
  - If it carries the agenda user, take the professional from the column that names who attends. If none exists, import with the agenda user and record the limitation in the importer's `stats` as `profesional_incierto`.
  - Write the finding in §6.
- **Segments from the comment.** `segmentos_de` also reads the agenda's *Comentario* column (same word-boundary rule). The comment is read in memory and never stored (it may hold clinical notes).
- **Future appointments.** Confirm that the importer accepts a file with future dates. They become alive appointments with `origen = 'importacion'`, with no messages sent and no cases opened (current behaviour).
- **Tests (`tests/test_import.py`):** synthetic rows only. Cover the accent/punctuation variants, a past "Confirmado" counted in `por_depurar`, a clinic-cancelled row that opens no case, "RO" mapping, and "Deportista" in the comment.

#### R2. Durations (M)
- `catalog.SERVICIOS`: "Valoración o revisión" → 45 min. `catalog.load` never overwrites edited rows, so add a data migration that updates only rows still at the old default (30).
- **Per-appointment duration.** In `Agendar.tsx`, recepción can change the duration (steps of `paso_min`, between 15 and 240 min). The default is the service duration. The API validates the range and the no-overlap rule (already enforced by the DB).

#### R3. Clinic hours (M)
- `catalog.default_hours` → Mon–Fri 08:00–12:00 and 13:00–17:00.
- Data migration for Blissens: replace `horario_atencion` rows that still equal the old default for each professional. Leave customised rows alone.
- The demo seed uses the new hours.
- `datos_del_negocio` (assistants) and the site show "Lunes a viernes, 8:00–12:00 y 13:00–17:00".

#### R4. Substitute professional (S)
- New nullable column `profesional.suplente_id` (same business, not itself). It is editable in Administración.
- **When it applies.** When the slots search for a reschedule, an offer or a recovery link finds no slot with the original professional within `horizonte_dias` because of a block, it adds the substitute's slots.
- Each substitute slot carries `suplente: true`. The patient sees "con la Dra. Sara López (reemplaza al Dr. Olarte)", and recepción sees a "Suplente" badge.
- Seed: Sara López as substitute for Juan Manuel Olarte.

### Phase B — Who to contact, and who not

#### R5. Patient status colours (semáforo) (M)
Computed per patient by a single function `pacientes.semaforo(conn, ids)` in SQL. It is never stored.

| Colour | Rule (first match wins) |
|---|---|
| `perdido` (grey) | No alive future appointment **and** last attended appointment > `dias_perdido` (60) days ago (or none, with a cancelled/no-show appointment > 60 days ago) |
| `rojo` | Last appointment ended `cancelada` (by the patient) or `no_asistio`, or is an unclosed past one (R1), **and** no alive future appointment |
| `amarillo` | ≥ 3 appointments `reprogramada` in the last 12 months (`umbral_cambios_fecha` = 3), **or** an alive future appointment still `no_confirmada` within 48 h |
| `verde` | Everything else |

- Config: `dias_perdido: 60` and `umbral_cambios_fecha: 3` in `DEFAULTS`. `dias_riesgo` (30, treatment-based early warning) stays as is.
- **Where it shows:**
  - a coloured dot plus label in Pacientes, the ficha and the Llamar list;
  - a filter in Pacientes by colour;
  - the assistant's `ficha_paciente` and `buscar_pacientes` return it.
- **Accessibility:** colour is never the only signal; always show the word.
- **Patients with `no_contactar` (R6)** show their reason instead of a colour.

#### R6. Do not contact (M)
- **Migration:** `paciente.no_contactar text check (no_contactar in ('queja','cobro','fallecido','otro'))`, plus `no_contactar_en timestamptz`, `no_contactar_por bigint references usuario(id)` and `no_contactar_nota text` (short, no clinical data).
- **Panel:** in the ficha, "No contactar" with the 4 reasons and a confirmation step. Recepción can remove it. Both actions go to the audit trail.
- **Effects.** Enforce these in the domain layer, not only in the UI:
  - `messaging.send` with `direct=False` → `omitido` (as with opt-out). Direct replies to something the patient just did still go out, except for `fallecido`, which blocks everything.
  - Excluded from: follow-up cases (no new case; open ones are closed as `anulado`), early-appointment offers, recall (R13), plan follow-up (R14), Pendientes/Llamar lists, and at-risk lists.
  - `fallecido` also hides the patient from booking and assistant searches (the ficha remains reachable from Pacientes with a filter).
- **Finished treatment.** "Tratamiento terminado" is not a flag: `tratamiento.estado = 'finalizado'` already excludes it from recovery. It does **not** stop periodic recall (R13) unless the clinic says otherwise (§6, Q2).

#### R7. Follow-up cadence: 3, 7, 15 days, 3 attempts (M)
- `cadencia_seguimiento_dias` default → `[3, 7, 15]`. `followup.open_case` must handle a cadence whose first entry is not 0: schedule every attempt, and send none at opening.
- **Cancellations.** The immediate `cancelacion_recibida` reply stays: it answers the patient's own action and does **not** count as an attempt. Implement it as a direct send outside the case cadence.
- **No-shows.** No message on day 0. The first attempt is on day 3.
- `agotar_caso` = last attempt + `dias_hasta_agotar` (unchanged).
- Manual attempts by recepción (calls) count toward the 3. When 3 attempts are recorded, the remaining automatic ones are cancelled.
- Update `tests/test_followup.py` for the new default.

#### R8. Valid mobile before sending (M)
- **Validation on entry.** Use one function `pacientes.normalizar_celular(raw, pais='CO')`, which replaces `data.normalize_phone` everywhere:
  - Colombian mobiles → `+573XXXXXXXXX`;
  - numbers starting with `+` → E.164 (8–15 digits);
  - everything else → invalid.
- Use it in the panel (create/edit patient), `/agendar`, web forms and the importer. The panel shows "Celular no válido" inline.
- **Status.** Migration: `paciente.celular_estado text not null default 'sin_verificar' check (celular_estado in ('sin_verificar','valido','invalido','sin_whatsapp'))`.
  - Set `invalido` when normalisation fails (the raw value is not kept).
  - Set `sin_whatsapp` when the channel reports "not a WhatsApp user" or the recepción marks it from R16.
  - Set `valido` after any delivered or answered message.
- **Before sending:** `messaging.send` with an `invalido`/`sin_whatsapp`/null mobile → `estado_entrega = 'omitido'`, `detalle = 'celular'`. It does not count as a follow-up attempt.
- **New tray in Pendientes → Llamadas: "Celulares por revisar"**, listing patients with a future appointment or an open case whose mobile is unusable.
  - If the patient has a `responsable` with a usable mobile, show "Contactar a <responsable> (<parentesco>)".
  - Actions: edit the mobile, or "Ya está en un chat de WhatsApp" (marks `valido`).
- **Import report:** count of rows with invalid mobiles (number only).

### Phase C — Messages that sound like the clinic

#### R9. Formal *usted*, warm (M)
- Rewrite every patient-facing text in *usted*: `catalog.PLANTILLAS` (all keys), email templates (`estudia/correo.py`), patient pages (`/agendar`, `/p/*`, `templates/*.html`), the public site copy (`copia.py`, ES only) and the consent text.
- **Tone:** formal but close ("Hola, Ana. Le recordamos su cita…", "Con gusto le ayudamos").
- `catalog.load` does not overwrite edited templates. Add a data migration that replaces each template only if its text equals the previous default, and bump a `version_plantillas` config key.
- **Assistants:** change the `paciente` and `visitante` instructions to "Trata de usted. Si la persona te tutea, tutéala tú también." Update `instrucciones.py` and regenerate the agent files with `scripts/agentes_asistente.py`.
  - Golden cases (`tests/golden_asistente/`): update expected phrasings where they assert *tú*. Do **not** run them against the real model (only the user does that); the fake client keeps passing.
- The panel (staff-facing) keeps its current voice.

#### R10. "Volver a empezar" and the doctor's name (M)
- `seguimiento_reasignacion`, `seguimiento_inasistencia` and `continuidad_tratamiento` gain `{profesional}` and open with the recovery line. Example: "Hola, {nombre}. Volver a empezar es más fácil acompañado: el {profesional} le guarda un espacio. Elija el que mejor le quede: {enlace}". The template text is final copy for review by the clinic.
- `followup.send_attempt` fills `profesional` from the case's appointment or treatment, using `profesional.nombre` with its title (add `profesional.titulo text` — "Dr.", "Dra." — editable in Administración, with an empty default).
- Never include the service, a diagnosis or amounts in WhatsApp text (Ley 1581, minimum data).

#### R11. Cancellation reasons: five quick options (M)
- **Default list** (until the clinic confirms, §6 Q1): "Salud", "Trabajo o estudio", "Viaje", "Motivo económico", "Otro". Keep the remaining rows but set `motivo_cancelacion.activo = false` (new column, default true). Historical data keeps its reason.
- Administración: reorder, activate or deactivate reasons. Maximum 5 active plus "Otro".
- **Panel:** cancelling an appointment shows the active reasons as **buttons** (one tap) instead of a select. "Otro" opens a short text field. The reason is required (already true for the assistant).
- **WhatsApp `pedir_motivo`:** use the active reasons (list message).
- After 30 days of data, Indicadores already shows the distribution. The clinic can then confirm the top 5.

#### R12. Out-of-hours auto-reply (S)
- Inbound message outside clinic hours (derived from `horario_atencion`: the union of all professionals' hours for that weekday), when the patient has not received this reply in the last 12 h → direct send of `fuera_de_horario`: "Gracias por escribirnos. Recepción le responde el siguiente día hábil desde las 8:00."
- Holidays: not modelled (non-goal).
- The confirmation buttons (Sí / No / Cambiar) keep working 24/7; this applies only to free text that goes to "mensajes sin interpretar".

#### R13. Periodic check-up (recall) (S)
- Migration: `servicio.control_cada_dias int` (null = no recall). Defaults: Limpieza 180, Control de ortodoncia o alineadores 30. Editable in Administración.
- **New `caso_seguimiento.tipo`: `'control'`.** The daily job opens one when:
  - the patient's last `atendida` appointment of that service is older than `control_cada_dias`;
  - there is no alive future appointment of that service;
  - there is no open `control` case for that patient and service;
  - and `no_contactar` is null.
- Same cadence (R7), new template `recordar_control` in *usted*, with `{profesional}`. For example: "Hola, {nombre}. Ya es momento de su control con el {profesional}. Le dejamos los espacios disponibles: {enlace}".
- It shows in Pendientes as "Control pendiente" and in Indicadores as part of recovery.

#### R14. Plan follow-up and gentle payment reminders (M)
This addresses the clinic's main concern. **No amounts and no "deuda/cobro" wording in any message.**
- **Migration on `tratamiento`:** `plan_entregado_en timestamptz`, `valor_plan numeric(12,0)` (optional, panel-only, never in messages), `ultimo_abono_en timestamptz`.
- **Panel, ficha → treatment:**
  - "Plan entregado", with date (default today) and an optional value;
  - "Registrar abono", with date (no amount needed; optional amount stored in `datos` for gerencia).
  - Both go to the audit trail.
- **New case type `'plan'`, own cadence `cadencia_plan_dias: [3, 7]`.** Opened when "Plan entregado" is recorded (or "Registrar abono" while the plan still has sessions left). The case closes as `reprogramado` when the patient books any appointment with that professional, or as `rechazado` with "Ahora no". It is excluded when `no_contactar` is set.
  - Day 3, `plan_acompanamiento_1`: "Hola, {nombre}. El {profesional} quiere saber cómo se siente con su plan de tratamiento. Cuando quiera dar el siguiente paso, aquí puede elegir su próxima cita: {enlace}".
  - Day 7, `plan_acompanamiento_2`: "Hola, {nombre}. Seguimos pendientes de usted para continuar su plan con el {profesional}. Si tiene alguna duda sobre el siguiente paso, responda este mensaje y recepción le ayuda."
  - Final copy is reviewed by the clinic.
- **Payment cadence (after a first abono)** (S): if `ultimo_abono_en` is older than `dias_recordar_abono` (default 30) and the treatment is active, open a `plan` case again. Same templates; never mention money.
- **Pendientes → Llamadas: "Planes sin siguiente paso"**: treatments with a plan delivered more than 7 days ago, no appointment and no abono since. Sorted with high-value patients first, then by `valor_plan` descending.
- **Indicadores:** card "Planes": delivered in period, with next appointment or abono within 15 days (conversion %), and `valor_plan` of plans with no next step (when values exist; same missing-value rule as money lost).

#### R15. "Quiere adelantar su cita" (S)
- Migration: `cita.quiere_adelantar boolean not null default false`.
- **Set by:**
  - recepción (toggle in the appointment sheet);
  - the patient from `/p/{token}` ("Avísenme si se libera un espacio antes");
  - the patient assistant (`proponer_quiere_adelantar`, proposal tool);
  - replying "Sí" to an offer also implies it.
- `slots.candidates`: patients with `quiere_adelantar` first, then the current order (high value, etc.).
- Indicators: offers accepted by patients who asked versus those who did not (for the demo story).

### Phase D — WhatsApp: the official API

#### R16. Official WhatsApp API with the current automatic flow (M)
We propose that the clinic moves to the **WhatsApp Business Platform (Cloud API)**. The automatic flow we already built stays as it is: reminders at 48/24 h with one-tap buttons, confirmations, cancellation with reason, follow-up, early-appointment offers, opt-out with BAJA. Recepción stops copying messages by hand and only handles what the system escalates (Pendientes).
- **Channel.** Use the existing WhatsApp adapter behind the channel port (`estudia/canales.py`, ADR 0006). Configuration is a `canal_negocio` row plus the secret's env-var reference; no new code path. Verify that the adapter covers, and add what is missing:
  - template sends (`plantilla` key ↔ approved Meta template name and language), with buttons that map to the existing button ids (`conf:si:{cita_id}`, `oferta:si:{oferta_id}`, …);
  - free-form text only inside the 24-hour customer-service window; outside it, only approved templates;
  - delivery status webhooks → `mensaje.estado_entrega` (`entregado`, `leido`, `fallido`), and the "not a WhatsApp user" error → R8 `sin_whatsapp`;
  - signature check of the webhook (already in the port) and idempotency (migration 008).
- **Templates.** One Meta template per `plantilla` key that starts a conversation, in *usted* (R9), category **utility** (appointments, follow-up of an existing treatment). Marketing-category templates are not used: there are no prospecting messages (non-goals). Add `plantilla.nombre_meta` and `plantilla.categoria` to keep the mapping. `docs/whatsapp-api.md` lists every template with its exact text for submission.
- **Number.** The clinic's current number is registered in the WhatsApp Business app. It can move to the API (it stops working in the app and in WhatsApp Web) or the clinic uses a new number for automatic messages. Recommendation: move the current number, because patients already have it. Recepción then answers from the panel instead of WhatsApp Web; this needs a minimal inbox (see below). Decision for the clinic (§6 Q9).
- **Recepción inbox (S, needed if the current number moves).** "Mensajes sin interpretar" (exists) becomes a conversation view per household: incoming text, the automatic messages sent, and a reply box. Free text is allowed only while the 24-hour window is open; otherwise the box offers the approved templates. Out-of-hours reply: R12.
- **Fallback while the API is not live, or for patients without recorded consent (R17): assisted sending.** Messages that cannot go through the API are left as `estado_entrega = 'por_enviar'` in a "Por enviar" tray with **"Abrir en WhatsApp"** (`https://wa.me/<digits>?text=<urlencoded>`), **"Enviado"**, **"No tiene WhatsApp"** and **"Descartar"**. The appointment sheet offers quick outcomes ("Confirmó", "Cancela" + reason, "Quiere cambiar", "Quiere adelantar") because buttons don't come back from WhatsApp Web. Keep this small: it is a bridge, not the product.
- **Simulator:** `/simulador` keeps showing everything, so the demo runs fully local without Meta.

#### R16b. Cost proposal (M, deliverable)
`docs/whatsapp-api.md` includes a cost section for gerencia. It must say plainly that **the monthly cost does not have to go up much, because this system replaces Dentalink for the agenda (R24): the Dentalink subscription is cut and partly pays for WhatsApp and hosting.** Contents:
- **WhatsApp:** Meta charges per delivered template message by category and country (Colombia). Replies inside a conversation the patient opened are free, and utility templates sent inside that open window are free too. Estimate = (appointments per month × reminder templates per appointment) + (follow-up, plan and check-up messages per month), × the current Colombia utility rate. Take the rate from Meta's official rate card on the day the proposal is written, and say the date. If a provider (BSP) is used instead of Meta directly, add its monthly fee; recommend Meta's Cloud API directly, which has no extra platform fee.
- **Hosting:** current Render + Supabase plans (ADR 0007), at their published prices.
- **Saving:** the Dentalink subscription the clinic pays today (the clinic gives the figure; it never goes in the repo).
- **Result:** a one-line comparison "hoy (Dentalink + tiempo de recepción) vs. propuesta (WhatsApp + hosting)", plus the hours of recepción saved on reminders and follow-up, which is the larger benefit.
- No real clinic figures in the repo: the document has the formula and placeholders; the filled version goes to the clinic outside git.

#### R24. Replacing Dentalink for the agenda (M, scope note)
- **Cut-over:** import history and future appointments from the last Dentalink export (R1, or R23 for the demo), then run both in parallel for an agreed period (default 2 weeks) where new appointments are entered only in our panel and the Excel import keeps the two in sync. After that, Dentalink stops being used for the agenda.
- **What Dentalink also does today and we do not:** the clinical record (*historia clínica*), which Colombian rules require the clinic to keep. The proposal must say how it is covered: the clinic keeps a lighter tool or plan only for the clinical record, or that is a later phase. The cost comparison (R16b) must use the cost of whatever remains. Open question §6 Q10.
- Remove "live Dentalink integration" from the non-goals reasoning: we don't integrate, we replace.

#### R17. Consent for automatic messages (M)
- **Deliverable:** `docs/entregables/autorizacion-mensajes.md`, a one-page authorization format the clinic can print or send. It covers:
  - the purposes (appointment reminders, follow-up, check-ups, plan follow-up);
  - the channel (WhatsApp, email);
  - how to opt out (reply BAJA);
  - the data controller (the clinic);
  - the Ley 1581/2012 rights.
  - The text is Spanish, *usted* (R9), and carries a version number.
- `texto_consentimiento` default takes the short version of that text. Bump `consentimiento_version`.
- **Panel ficha:** "Autorización de mensajes", with a status (`sin registrar` / `verbal` / `escrita` / `en línea`), date and version. Migration: `paciente.consentimiento_medio text`. Patients who registered online already have `en línea`.
- **Rule:** the API channel sends automatically **only** to patients with a recorded authorization (Meta also requires opt-in). Messages for patients without it go to the "Por enviar" fallback (R16), marked "Sin autorización registrada" so recepción can ask for it. Enforce this in `messaging.send`.
- **Collecting consent for existing patients:** recepción asks at the next call or visit (one tap in the ficha); patients who confirm or book from `/agendar` or their link accept it online; the first assisted message can include the short text and "Responda SÍ para recibir recordatorios automáticos". Indicadores shows the share of patients with future appointments who have consent, so gerencia sees the switch-over progress.

### Phase E — Indicators for gerencia

#### R18. Occupancy target and hard days (S)
- `metas_indicadores` default → `{"ocupacion": {"min": 0.85}}`. Add `ocupacion` to the keys `PUT /admin/metas` accepts ("higher is better") if it is missing.
- The weekday chart in Indicadores marks the days below target. **Cupos libres** (Pendientes) shows free slots on those weekdays first.
- Slot suggestions shown to patients in recovery links list, among equal options, the slots on days below target first (no hiding of other days).

#### R19. Values that gerencia believes (S)
- Administración → "Valor de los servicios": help text "Use el valor típico de la cita de este procedimiento, no el promedio del arancel (incluye precios de relleno)."
- Money lost (exists) keeps using `servicio.valor`. R14 adds plan value as a separate figure. Never add the two together.

#### R20. Where new patients come from (C)
- Migration: `paciente.origen text check (origen in ('referido','embajador','web','redes','otro'))` and `paciente.origen_detalle text` (for example the ambassador's name, without personal data of third parties beyond a name).
- Asked in the panel when creating a patient, and in the web registration ("¿Cómo nos conoció?", optional).
- Indicadores: new patients by origin. **No outbound prospecting messages** (see non-goals).

#### R21. English for international patients (C)
- Migration: `paciente.idioma text not null default 'es' check (idioma in ('es','en'))`. Registration from `/en` sets `en`, and recepción can change it.
- `plantilla` gains an `idioma` column (key + language unique). `messaging.render` falls back to Spanish when no English version exists.
- English versions of reminders, confirmation and recovery templates.

### Phase F — Public site

#### R22. Site corrections (M)
- **Team:** remove Laura Vélez (ES and EN) and add "Dr. Juan Esteban …" once the clinic sends the full name, role and photo (§6 Q4). Until then, show only Sara López and Juan Manuel Olarte; do not invent a photo or a role. Delete `image-10.png` if nothing else uses it. Update the visitor assistant's `info_clinica` team text.
- **Social links:** fill `REDES` with the URLs the clinic confirms (§6 Q5). Links use `rel="noopener noreferrer"`. Icons without a URL stay hidden rather than showing a dead icon.
- **Experiencias:** replace the current text with the clinic's real text when it arrives (§6 Q6). Keep the "Experiencia" request flow.
- **Indexing:** our site already serves `index, follow` (covered by `tests/test_seo.py`). The fix for the clinic is to point their domain at this site. Add it to the deployment checklist in `README.md`.
- **Web channel:** on the contact section and the request confirmation page, add "Escríbanos por WhatsApp", a `wa.me` link with a prefilled text ("Hola, vengo del sitio web y quiero agendar una valoración"). The number comes from config (`whatsapp_publico`), never hard-coded. Web requests keep landing in Bandejas.

### Phase G — Demo with real shape, no real data

#### R23. Anonymised import for the public presentation (M)
- New command `make importar-anonimo` (Python: `uv run python -m estudia.data importar --anonimo`). It reads the real Excel files from the ignored folder and writes to the **local** DB only. It refuses to run if `ENTORNO` is not `local`.
  - **Patients:** `Paciente001…` in import order. Surname empty. No document. Birth date replaced by the same age band (date set to 1 July of a year that keeps the age). Mobile replaced by a fake simulator number `+57300000NNNN`. Email null.
  - **Professionals:** keep the names (they are public on the site) unless `--anonimo-profesionales`, which gives "Especialista A/B/C".
  - **Never stored:** comments, clinical notes, the raw state text.
  - Dates are shifted by a fixed random offset (kept only in memory) so that real calendar days cannot be recognised. Weekdays are preserved, so shift by whole weeks.
- **Output:** the stats dict plus a line "Datos anonimizados: no los publiques igual; son solo para la demo local."
- `tests/test_import.py`: synthetic files, and assert that no input name, document or mobile appears in any table after `--anonimo`.

### Phase H — The assistant: Bliss

#### R25. Bliss, the assistant's personality (M)
The assistant gets a name and one personality across every profile: **Bliss**, Blissens' assistant.
- **Name fixed in code.** Every assistant (auxiliar, especialista, paciente, visitante, operador) is always called Bliss: `NOMBRE` in `estudia/asistente/instrucciones.py`. It is not configurable; it still travels in `<contexto>` (`Asistente: Bliss`).
- **Shared personality block `PERSONALIDAD`** in `instrucciones.py`, added to every profile next to `COMUN`. Final wording is ours; the content:
  - Who: «Eres Bliss, la asistente de {negocio}». Female grammatical gender, which is consistent with the current visitor text («sé cálida»). It is an assistant, not a person: if asked, it says it is an automatic assistant, never a human, and never claims to be a dentist.
  - Character: warm, calm, precise and close. It speaks like the clinic's best receptionist: it welcomes, explains in one sentence, and always takes the person to the next step. It follows the clinic's spirit, «Tu futura sonrisa» and «Volver a empezar»: when someone missed or cancelled, the tone is opportunity, never reproach.
  - Register by profile:
    - `paciente` and `visitante`: *usted*, warm; if the person uses *tú*, Bliss does too (R9). English when the page or the person is in English, same personality.
    - `auxiliar` and `especialista`: *tú*, as a colleague: short, operational, no greetings after the first one.
  - Introduces itself only in the first reply of a conversation («Hola, soy Bliss, la asistente de Blissens.»), never again.
  - No emojis, no exclamation chains, no clichés («¡Excelente pregunta!»), no selling. Never mentions money, debt or collection to a patient (R14); with the doctor's name when talking about a treatment or follow-up (R10).
  - Personality never overrides a rule: the topic limits, the fixed refusal phrases, the length limits and the privacy rules of each profile stay as they are and win over tone.
- **Fixed replies** (`RESPUESTAS`) rewritten in Bliss's voice and in *usted* for patients and visitors. The off-topic refusal phrases keep their exact shape, adding the name: «Soy Bliss y solo puedo ayudarle con sus citas en X.» (EN: «I'm Bliss, and I can only help with your appointments at X.»). Update the tests that assert them.
- **UI:**
  - panel (`Asistente.tsx`): button and title «Bliss», subtitle «Asistente de {negocio}»;
  - patient page (`asistente.html`) and site widget: title «Bliss · Asistente de citas»; the first-load greeting is a fixed text (no model call): «Hola, soy Bliss. Puedo ayudarle con sus citas, horarios y la dirección de la clínica.»;
  - a small mark or avatar built from the brand's own assets (no generated faces), with `alt=""` when it is decorative.
- **Golden cases:** add a few per profile for the personality: first reply introduces itself and later ones don't; a patient who writes in *tú* gets *tú*; a patient who missed an appointment gets «volver a empezar» tone, without reproach; asked «¿eres una persona?» → says it is an automatic assistant. Use the `usuario-clinica` agent to draft them. Run them with the fake client only; live checks are for the user.
- Regenerate the subagent files with `scripts/agentes_asistente.py`.

#### R26. Every change reaches the assistant (M)
The assistant may only do what the panel and the patient link already allow (ADR 0009). So each slice is done only when the assistant knows about its change too: tool outputs, new proposal tools, the task guides in `instrucciones.py`, the agent files, and golden cases. Every new action is a **proposal** confirmed with a button, never executed by the model.

| R | Assistant change | Profiles |
|---|---|---|
| R1 | `indicadores` returns `inasistencia_por_depurar` and the rate with pending ones; the guide says to mention both when there are unclosed appointments | auxiliar |
| R2 | `espacios_libres` uses the 45-min valoración; `proponer_agendar` accepts an optional `duracion_min` (same range as the panel) | auxiliar |
| R3 | `datos_del_negocio` returns the new hours (derived from `horario_atencion`, not a fixed string) | all |
| R4 | `espacios_libres` marks `suplente: true`; guide: present it as «con la Dra. X, que reemplaza al Dr. Y» | all that book |
| R5 | `ficha_paciente` and `buscar_pacientes` return `semaforo`; `buscar_pacientes` accepts a colour filter; the «¿a quién llamo?» guide orders by it | auxiliar, especialista (own patients) |
| R6 | `ficha_paciente` returns `no_contactar` and its reason; new `proponer_no_contactar` / `proponer_quitar_no_contactar`; guides never suggest calling or writing to them; `fallecido` patients don't appear in searches | auxiliar |
| R7 | `ficha_paciente` and `bandeja seguimientos` return attempts used of 3; `proponer_gestion_seguimiento` says when it is the last one | auxiliar |
| R8 | `ficha_paciente` returns `celular_estado` (never the number); new `bandeja celulares_por_revisar`; guide suggests the responsable when there is one | auxiliar |
| R9 | `paciente` and `visitante` in *usted* (R25); suggested message texts for recepción in *usted* | all |
| R10 | When recepción asks for a message text, Bliss drafts it with «Volver a empezar» and the doctor's name, never amounts or diagnoses | auxiliar |
| R11 | `motivos_cancelacion` returns only active reasons; the patient's cancel flow offers those five | auxiliar, paciente |
| R12 | None (Bliss is not on WhatsApp) | — |
| R13 | New `bandeja controles`; `ficha_paciente` shows the next check-up due | auxiliar |
| R14 | `ficha_paciente` shows plan delivered, last payment date and next step (never `valor_plan` to patients); new `proponer_plan_entregado` and `proponer_registrar_abono`; new `bandeja planes`; `indicadores` returns the plans card. Patient profile: if asked about the plan or payments, offers contact with the doctor's name, never figures | auxiliar, paciente |
| R15 | New `proponer_quiere_adelantar` (patient: for their own household's appointments; auxiliar: any); `mis_citas` returns the flag | paciente, auxiliar |
| R16 | New `bandeja por_enviar`; Bliss can draft a reply for recepción inside the 24-hour window, but never sends it | auxiliar |
| R17 | `ficha_paciente` returns the consent status; new `proponer_registrar_autorizacion` (verbal/written) | auxiliar |
| R18 | `indicadores` returns the occupancy target and the days below it | auxiliar |
| R20 | `proponer_crear_paciente` accepts `origen` | auxiliar |
| R21 | Patient profile answers in `paciente.idioma` when the person hasn't written yet | paciente |
| R22 | `info_clinica` team text updated (no Laura Vélez; Dr. Juan Esteban when confirmed) | visitante |
| R23, R24 | None | — |

## 4. Non-goals
- Deposits or advance payments (the clinic does not take them).
- Processing payments or storing balances: we record *that* a payment happened (R14), not accounting.
- Live Dentalink integration (API or DB): we replace it for the agenda (R24); the Excel import is the migration and the bridge during the overlap.
- The clinical record (*historia clínica*) in this phase (see R24).
- A free-text chatbot on the clinic's WhatsApp number. The API channel sends templates and understands buttons; the conversational assistants live on our site and patient links.
- Marketing-category WhatsApp templates.
- Prospecting messages to people who are not patients (no consent). R20 only measures where patients come from.
- Holiday calendar.
- Brand manual. We work with the existing logo; the clinic will send the original file.

## 5. Non-code deliverables
Each goes in `docs/entregables/` (Spanish, *usted*, no real data):
1. `autorizacion-mensajes.md`: the consent format (R17).
2. `guia-recepcion.md`: a one-page daily routine for recepción. Cover "Por enviar", Llamadas, colours, no contactar, plan entregado / abono, and cerrar citas pasadas.
3. `indicaciones-comerciales.md`: the commercial guidelines document the clinic asked for. Cover tone (*usted*, "Volver a empezar"), when each message goes out (24 h, 3/7/15, plan 3/7, controls), what never goes in a message (amounts, diagnoses), the cancellation reasons, and how to use the doctor's name. Gerencia decides whether to adopt it.
4. `docs/whatsapp-api.md`: the proposal to move to the official API: steps (Meta Business verification, number, templates, opt-in), the template list for submission, and the cost section (R16, R16b).

## 6. Open questions for the clinic
Send these in one message. Until answered, the defaults above apply.
1. Which 4–5 cancellation reasons do you hear most? (Default: Salud, Trabajo o estudio, Viaje, Motivo económico, Otro.)
2. If a treatment is finished, should we still send the cleaning check-up every 6 months? (Default: yes, unless the patient is marked "No contactar".)
3. Plan reminders: do 3 and 7 days count from the day the plan is delivered? And after a first payment, is a monthly nudge acceptable? (Default: yes and 30 days.)
4. Dr. Juan Esteban: full name, specialty, photo, and whether he also substitutes for anyone.
5. Instagram and Facebook URLs, and the public WhatsApp number for the site.
6. The real text for Experiencias (ES and EN).
7. Logo in vector (SVG/AI/PDF).
8. Internal (for us): result of the *Nombre Profesional* vs. agenda-user check (R1).
9. WhatsApp API: move your current number to the API (recepción answers from the panel) or use a new number for automatic messages?
10. When the agenda leaves Dentalink, how do you want to keep the clinical record, and how much does Dentalink cost you per month today (for the cost comparison, not for publication)?

## 7. Order of work
Suggested slices. Each one is a PR that can be demoed on its own:
1. **R1, R2, R3, R23**: the data is right, and the demo can use the real shape.
2. **R6, R7, R8, R5**: contact rules, then colours (colours depend on R1 and R6).
3. **R16, R16b, R17, R24**: the official API channel with consent, the "Por enviar" fallback, the cost proposal and the cut-over plan. Meta verification and template approval take days, so submit the templates as soon as R9's copy is approved.
4. **R9, R10, R11, R12**: copy and reasons.
5. **R14, R13, R15**: plan follow-up, recall, earlier appointments.
6. **R18, R19, R22**, then **R4, R20, R21**.
7. **R25**: Bliss's personality. Do it together with or before slice 4, because both rewrite the instructions and the fixed replies.

**R26 applies to every slice:** a slice is not done until its row in the R26 table is done, with golden cases for any new tool.

Update `GLOSSARY.md` with: **Semáforo**, **No contactar**, **Control periódico**, **Plan entregado**, **Abono**, **Envío asistido**, **Quiere adelantar**, **Suplente**, **Inasistencia por depurar**, **Bliss** (the assistant's name and personality; the term **Asistente** stays for the function). Add an ADR for R16/R24 (official WhatsApp API as the production channel, with assisted sending only as a fallback; the system replaces Dentalink for the agenda) and one for R17 (automatic sending requires recorded consent).

## 8. Testing
The developer's laptop is slow. **Do not run full suites.** Run only the test files you touch, by path. For example:
- `uv run pytest tests/test_import.py tests/test_followup.py -q`
- `uv run pytest tests/test_recovery_tasks.py tests/test_indicators.py -q`
- `uv run pytest tests/test_web.py tests/test_sitio.py tests/test_seo.py -q` for site changes
- `cd panel && npx vitest run <changed test files>`, then `npx tsc --noEmit` and `npx eslint <changed files>` once at the end.

The assistants are never called against the real model in tests: use the fake client. The user runs live checks.

After API changes:
- run `make api-esquema`;
- run `cd panel && npm run tipos`.

Add tests for each R: the domain rule first (the colour rules, the do-not-contact effects in `messaging.send`, the cadence with a non-zero first day, phone normalisation, the assisted channel states, the plan case lifecycle), then one UI flow per new panel action.

A dev server (`make dev`) may already be running. Do not start or stop it. Run new migrations against the dev DB with the repo's migrate command (see the `Makefile`).
