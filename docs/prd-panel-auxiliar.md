# PRD: A calmer panel for the auxiliar's morning

> Audience: an implementing agent or a reviewer. Self-contained: read this, `CLAUDE.md`, `README.md` and `GLOSSARY.md`.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: two role-play reviews on 2026-11-25 of `/panel/agenda?vista=semana`, logged in as the demo user `auxiliar`
> (fictional seed data). One reviewer was a rushed receptionist at 7:50 a.m. The other was a careful 58-year-old auxiliar
> used to paper and Excel. Finding IDs (P-) are listed in §2. Both reviewers found P-01 to P-04 on their own.

## 1. Goal

When the auxiliar opens the panel, the first screen answers three questions without extra clicks:
- who is coming today, across all professionals;
- what needs a call or a click right now;
- after a phone call, how do I record what the patient said, in one click.

Success = starting from `/panel`, the auxiliar can do all of this in under 30 seconds and with at most 2 clicks each:
- see today's appointments for all professionals;
- see how many appointments today and tomorrow have no confirmation;
- open the call list;
- mark a patient as confirmed after a phone call.

## 2. Findings that motivate this PRD

| ID | Finding | Severity |
|---|---|---|
| P-01 | There is no way to record a confirmation given by phone. The appointment sheet (`HojaCita.tsx`) only offers "Cambiar fecha", "Cancelar cita" and the outcome. `permisos.acciones_cita` only returns `desenlace`, `cancelar` and `cambiar_fecha`. After the call, the patient stays in "No confirmadas" and gets called again. | High |
| P-02 | The week view always filters to one professional (`Agenda.tsx`: `proFiltro` falls back to `activos[0]`). It has no "Todos" option, so half the clinic is invisible and nothing says so. | High |
| P-03 | "Qué hacer hoy" (132) and the sidebar badge (154) mix real calls with paperwork. 82 of the items are old "Citas por cerrar" going back about 10 days. The badge counts every inbox, including the informational ones, so the two numbers don't match. | High |
| P-04 | Past appointments look the same as future ones. At 19:20, the 07:30 appointments still look "Programada". There is no line for the current time and nothing is greyed out. | Medium |
| P-05 | "Qué hacer hoy" rows say "Llama a X" but don't show the phone number. The "No confirmadas" tab does show it. | Medium |
| P-06 | Tomorrow's appointments still in `programada` (reminder sent, no reply yet) appear in no list. "No confirmadas" only lists `no_confirmada`. The careful auxiliar couldn't build tomorrow's call list. | Medium |
| P-07 | The inbox tab strip scrolls off to the right at 1366 px. "Mensajes por responder", "Contactos y solicitudes" and "Dados de baja" are hidden. | Medium |
| P-08 | Week-view cards are cut off ("08:30 Luis Chaparr…"), use 11–12 px text, and short appointments show only a colour stripe. Colours have no legend. | Medium |
| P-09 | Jargon and copy bugs: "Bandejas", "Escalado", "Reversibles", "Cupos ocupados por oferta", "en oferta · cancelacion" (missing accent). The words "tratamiento a medias" and "ESCALADO" are run together with no space. | Low |
| P-10 | The phone number in the appointment sheet is only a `tel:` link. There is no WhatsApp shortcut. | Low |
| P-11 | Polish: the browser tab title is "Estud-IA · Panel"; it should name the business. Seed data has "Dra. Jorge Rodríguez", a man with a female title. | Low |

What already works and **must not regress**:
- the appointment sheet (status pill, `tel:` link, history with plain reasons);
- "Cambiar fecha" with slots as buttons grouped by day;
- "No confirmadas" sorted by the nearest appointment, with phone and "Abrir cita";
- the Seguimientos outcome buttons;
- in Pacientes: "Con cita hoy y mañana" and "En riesgo";
- the day view with professionals side by side and lunch greyed out;
- "Citas canceladas" collapsed by default.

## 3. Concepts

- **Confirmación por teléfono**: the auxiliar records that the patient confirmed in a call. It is the same state transition
  as a WhatsApp confirmation (`programada|no_confirmada → confirmada`) with actor `auxiliar`. The history shows
  "Confirmada por teléfono".
- **Pendientes de hoy**: what needs a human action today. It splits into **Llamadas** (calls) and **Trámites** (paperwork).
  - Llamadas, ordered by urgency: escalated follow-ups, messages to answer, contact requests, unconfirmed appointments for
    today and tomorrow, appointments of opted-out patients.
  - Trámites: past appointments without an outcome (`sin_desenlace`).
  - "En riesgo" and "Cupos libres" stay informational: they are not counted as pending.

Add both terms to `GLOSSARY.md`.

## 4. Requirements

### R1 Confirmar por teléfono (P-01)
- New action `confirmar` in `permisos.acciones_cita`: auxiliar only, while the appointment is in `programada` or
  `no_confirmada` and has not started yet.
- New endpoint `POST /api/v1/citas/{id}/confirmar`, auxiliar only, audited like the other appointment actions.
  - It calls `lifecycle.transition(..., "confirmada", actor="auxiliar", detalle="Confirmada por teléfono")`.
  - It cancels nothing and sends no message to the patient.
  - It is reversible through the existing revert flow, like the other auxiliar movements. Check `REVERSIBLES` in
    `permisos.py` and include it if the policy allows.
  - Update `docs/openapi.json` and regenerate the panel types (`make panel`).
- `HojaCita.tsx`: a primary button "Confirmó" (check icon), shown before "Cambiar fecha" when the action is available.
- The rows in "No confirmadas", in "Dados de baja" and in the calls group of "Qué hacer hoy" (when the row is an appointment)
  get an inline "Confirmó" button. Clicking it confirms the appointment, removes the row and shows a toast "Cita confirmada".
- In the same rows and in the sheet, next to the phone, add a "WhatsApp" link to `https://wa.me/<digits>` (P-10). Reuse
  `digitosWhatsApp` from `lib/solicitudes.ts`.

### R2 Agenda defaults (P-02, P-04)
- `/panel` and the "Agenda" menu item already open the day view for today with all professionals. Keep that as the landing.
- The week view gets a "Todos" option, and it becomes the auxiliar's default there. With "Todos", each day column lists
  appointments from every professional, stacked in time order. Each card shows the professional's short name, and the cards
  stay readable at 1366 px. The specialist keeps seeing only their own week.
- Day view, today only:
  - a thin horizontal line at the current time, refreshed every minute;
  - on first load, scroll to about one hour before now;
  - past appointments that are still alive (`programada`, `confirmada`, `no_confirmada`) are visually muted, and get a small
    "Por cerrar" tag once they end, linking to the sheet where the outcome is recorded;
  - finished states keep their current style.

### R3 Resumen del día (P-03, P-06)
- A strip above the agenda grid, for the auxiliar only, with up to four counters. Each counter is a link.
  1. "N citas hoy": alive appointments today. Links to the day view.
  2. "N sin confirmar hoy y mañana": `programada` or `no_confirmada`, starting from now until the end of tomorrow. Links to
     the No confirmadas inbox.
  3. "N mensajes por responder": links to that inbox. Hidden when 0.
  4. "N por cerrar": links to Citas por cerrar. Muted style, since it is paperwork.
- Counts come from one new endpoint `GET /api/v1/resumen-dia`, or from an extension of the existing inbox counts. Pick
  whichever is simpler; don't add a table.
- The strip collapses into one line on mobile.

### R4 No confirmadas includes tomorrow's silent ones (P-06)
- `bandejas.no_confirmadas` also returns appointments in `programada` that start before the end of tomorrow (Bogotá time)
  and haven't started yet. They come after the `no_confirmada` ones of the same day, ordered by start time.
- Each row shows its status ("Sin confirmar" or "Sin respuesta aún"). If a reminder was sent, it also says when: use the
  `recordatorio_<h>h` marks or `recordatorio_enviado` in `datos_origen`, or "Recordatorio enviado" when only the boolean
  exists.
- The inbox help text explains this in one sentence.

### R5 Qué hacer hoy: calls first, paperwork apart (P-03, P-05)
- "Qué hacer hoy" renders two groups:
  - "Llamadas", with the count and the urgency order from §3;
  - "Trámites", collapsed by default, showing the count of `sin_desenlace` with a link to the inbox, not 82 rows.
- The count on the "Qué hacer hoy" tab and the sidebar badge are the same number: the **Llamadas** count. One shared
  function computes it, used by both `Layout.tsx` and `Bandejas.tsx`. Informational inboxes and paperwork don't count.
- Every call row shows the phone number (`tel:`) and the WhatsApp link.

### R6 Inbox tabs and wording (P-07, P-09)
- The tab strip wraps onto two lines instead of scrolling. Group the tabs as:
  - "Llamar": No confirmadas, Seguimientos, Mensajes, Contactos, Dados de baja;
  - "Revisar": Citas por cerrar, Cupos libres, Pacientes en riesgo.
- Rename user-facing jargon. Code identifiers stay as they are.

  | Current text | New text |
  |---|---|
  | "Bandejas" (menu and h1) | "Pendientes" |
  | "Escalado" | "Necesita llamada" |
  | "Reversibles" | "Se pueden deshacer" |
  | "Cupos ocupados por oferta" | "Cupos llenados con la lista de espera" (or equivalent plain wording) |

- Fix the missing accent in "cancelación" and the missing space before the escalation tag.
- Update tests that assert on the old copy.

### R7 Cards and legend (P-08)
- Week-view cards show at least "HH:MM" and the patient's first name and first surname, without cutting the first name.
  - Show the full name in a `title` tooltip.
  - Card text is at least 12 px; status text is at least 12 px.
  - Short appointments show a status icon (`ESTADOS[...].icono`) next to the time, not only a colour stripe.
- A small legend button "¿Qué significan los colores?" next to the view toggle. It opens a popover listing `ESTADOS` with
  colour, icon and text.

### R8 Polish (P-11)
- The panel's document title becomes "<business name> · Panel". Use the business name from the session or configuration
  if it is available; otherwise use "Panel".
- Seed data (`estudia/data.py`): a professional's title must agree with the name. Fix the generator or the fixed names so
  that no "Dra." goes with a male first name.
- Seed data: when the seed creates future `programada` appointments marked `recordatorio_enviado`, also schedule the same
  24 h unconfirmed-check task that production schedules. This way the demo shows "Sin confirmar" the way the real system
  would. Reuse the existing scheduling function; don't duplicate it.

## 5. Out of scope
- A printable call list, a view of free slots per professional, and a "patient arrived" / waiting-room status. Write these
  down as follow-ups in §7; don't build them.
- A global search bar in the header.
- A text-size control.
- Any change to the patient-facing site or to WhatsApp templates.

## 6. Acceptance criteria
Python tests go in `tests/test_panel_auxiliar.py`, or extend the existing API and inbox tests. Panel tests go in
`panel/src/flujos.test.tsx`, with MSW handlers in `panel/src/pruebas/servidor.ts`.

1. `confirmar` is offered and works for the auxiliar on a future `programada` or `no_confirmada` appointment:
   - the state becomes `confirmada`;
   - the history row has actor `auxiliar` and detail "Confirmada por teléfono";
   - no outbound message is created.
2. `confirmar` is not offered and returns 403 or 409 in these cases: for a specialist; for a past appointment; for an
   appointment in `confirmada`, `cancelada` or a final state.
3. `bandejas.no_confirmadas` returns tomorrow's `programada` appointments. It doesn't return the ones for the day after
   tomorrow, or ones that already started.
4. The Llamadas count excludes `sin_desenlace`, `en_riesgo` and `cupos_libres`. The sidebar badge and the "Qué hacer hoy"
   tab show the same number.
5. Panel: from the sheet of a `no_confirmada` appointment, clicking "Confirmó" calls the endpoint. The sheet then shows
   "Confirmada".
6. Panel: in the week view, the auxiliar sees a "Todos" option, and it is selected by default. A specialist does not see it.
7. Panel: the day view for today renders the current-time line. A past alive appointment renders the "Por cerrar" tag.
8. Panel: the summary strip renders the four counters with the right links, and hides "mensajes" when the count is 0.
9. `make test` and `make lint` pass.

## 7. Follow-ups (not in this PRD)
- A printable or exportable call list for tomorrow, with outcome buttons ("Confirmó / No contesta / Reprogramar").
- A view of free slots per professional for the next N days, to fill gaps.
- A check-in ("Llegó") and waiting-room status for today.
- A global search by name or phone from any screen.
