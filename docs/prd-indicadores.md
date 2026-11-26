# PRD: Indicators that a manager can act on

> Audience: an implementing agent or a reviewer. Self-contained: read this, `CLAUDE.md`, `README.md` and `GLOSSARY.md`.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: three role-play reviews on 2026-11-25 of `/panel/indicadores` with fictional seed data:
> - **Patricia**, the owner, who thinks about money. She reviewed the screen in Chrome.
> - **Dr. Andrés**, the clinical director, who thinks about patients and professionals. He reviewed the code and the API.
> - **Valentina**, the operations manager, who thinks about processes and experiments. She reviewed the code, the API and read-only SQL.
>
> Finding IDs (I-) are in §2. All three reviewers found I-01, I-02, I-03 and I-05 on their own.

## 1. Goal

When a manager opens Indicadores, the top of the screen answers three questions in under a minute:
- **How are we doing compared with before?** Three key numbers, each compared with the previous period.
- **Can I trust these numbers?** A visible warning when appointments still have no outcome recorded.
- **What or who needs action?** Counters that open the list of patients or appointments behind them.

The detail comes below: tables by professional and service showing their sample size, whether reminders work, and when patients miss appointments. Maintenance controls move out of this screen.

Phase 1 (this PRD) uses only data that already exists. Phase 2 (§6) needs new data: price per service, targets, and who resolves pending items.

## 2. Findings

| ID | Finding | Raised by |
|---|---|---|
| I-01 | **Incomplete data is not flagged.** In the demo, 82 past appointments have no outcome. The last ~2 weeks show 0 attended, "Atención efectiva 0,0 %", and the weekly trend line has gaps. Nothing explains why. | All |
| I-02 | **"Atención efectiva" (33,6 %) is misleading.** It divides attended appointments by every appointment in the range, including cancelled, rescheduled and still-pending ones. | All |
| I-03 | **No numbers to compare against.** The cards don't show the previous period, a trend arrow or a target, so a manager can't tell whether 24 % is good or bad. | All |
| I-04 | **The screen shows no people.** `/bandejas/en-riesgo` has 20 active treatments with no future appointment, and none of them appear here. Dr. Andrés can't get from "orthodontics has 25 % no-shows" to who those patients are. | Andrés |
| I-05 | **Bars hide their sample size and their labels.** "Blanqueamiento 50 %" is 3 of 6 appointments. Recharts drops X-axis labels on the service and reason charts: 3 of 8 names show, and the tallest bar has no name. | All |
| I-06 | **Reminders can't be evaluated.** The no-show rate with a reminder (21 %) versus without one (24 %) is computable but not shown. Failed reminder tasks (18 in `/sistema`) are not mentioned. | Valentina |
| I-07 | **No view by weekday or hour.** In the demo, Wednesday has 28 % no-shows and the 07:00 and 16:00 slots are above 35 %. The data is in `cita.rango`. | Valentina |
| I-08 | **Several numbers ignore the filters.** | Patricia, Andrés |
| | - `time_between_patient` ignores the professional and service filters (`estudia/indicators.py`). | |
| | - `_where(..., "hp")` drops the service filter, so "Cupos liberados", "vacíos" and the capacity used for "Ocupación" don't change when you filter by service. | |
| | - With a service filter, "Ocupación" divides one service's minutes by the full schedule. | |
| I-09 | **Maintenance controls sit on a manager's screen.** "Ejecutar cierre ahora" and "Último cierre diario" are maintenance. "Último cierre" shows 2026-11-30 while today is 2026-11-25. | All |
| I-10 | **On a phone the screen is hard to use.** The 8 cards stack in one column, each with its help text. The 4 filters stack too. Tooltips need hover. There is a lot of scrolling before the first chart. | Valentina |
| I-11 | **Labels are jargon:** "Recuperación de cancelaciones", "Cupos llenados con la lista de espera · por agendamiento", "Días promedio entre citas". There is no preset for "este mes vs. mes pasado". | Patricia |

**Must not regress:**
- the current filters (dates, professional, service);
- the daily close (`hecho_diario`) as the source of the aggregates;
- the role check (auxiliar only);
- the existing API endpoints, which may gain fields but must not lose any.

## 3. Requirements (Phase 1)

### R1. Incomplete-data banner (I-01)
- **What:** at the top of the screen, a yellow `Aviso` reading: "Hay N citas pasadas sin desenlace en este periodo; las cifras de esos días están incompletas." It links to `/bandejas` (the "Citas por cerrar" tab, if that tab can be deep-linked).
- **When:** shown only when N > 0, where N is the number of past appointments in the selected range (and matching the filters) that are still in `programada`, `confirmada` or `no_confirmada`.
- **Weekly trend:** each point includes `sin_desenlace`. A week with appointments but no outcome is drawn as "sin datos" with a note, not as a silent gap.

### R2. Rename and redefine "Atención efectiva" (I-02)
- **Name:** "Asistencia".
- **Formula:** attended ÷ (attended + no-show + cancelled). It excludes rescheduled appointments and those with no outcome yet.
- **Help text:** state the formula in plain Spanish.
- **API:** keep the field `atencion_efectiva` for compatibility with the new formula, or add `asistencia` and deprecate the old one. Note the choice in the PR.

### R3. Comparison with the previous period (I-03)
- **Previous period:** the range of equal length that ends the day before `desde`.
- **API:** `/indicadores/resumen` accepts `comparar=true`. It then returns `anterior: {…same numeric fields…}`, or the frontend makes a second call. Prefer the backend so the definition lives in one place.
- **On each key card:** the delta in percentage points, with an arrow. Colour comes from meaning, not direction: more no-shows is red, more attendance is green. Each indicator has a "higher is better" flag.
- **Period presets** above the date inputs:
  - "Últimos 7 días"
  - "Últimos 30 días"
  - "Este mes"
  - "Mes pasado"

  The default stays at the last 60 days, or switches to "Últimos 30 días"; implementer's call, stated in the PR.

### R4. New top of the screen (I-03, I-10, I-11)
Order, from the top:
1. Title and filters. Presets sit on one row. On mobile, the professional and service selects collapse under a "Filtros" toggle that shows how many filters are active.
2. The R1 banner.
3. **Key-number strip:** 3 cards, 2 columns on mobile, 3 on desktop, each with the R3 comparison:
   - Inasistencia
   - Asistencia (R2)
   - Confirmación

   The help text moves behind an "i" button (a popover or `<details>`, since there is no hover on touch screens).
4. **Action counters (R5).**
5. **Professional and service tables (R6).**
6. **Reminders (R7)** and **day × hour (R8)**.
7. A collapsed `<details>` section, "Más indicadores", holding:
   - the weekly trend;
   - reasons (R9);
   - Ocupación;
   - Cancelaciones and Recuperación (renamed "Canceladas que se reagendaron");
   - the waitlist slot cards (renamed "Cupos liberados por cancelaciones", "…tomados por otro paciente", "…quedaron vacíos");
   - time between appointments.

### R5. Action counters with drill-down (I-04)
Three tappable counters, each showing a number and a one-line label. Each one opens a list in a dialog or a panel on the same page (not a navigation away):
- **"Tratamientos sin próxima cita".** Reuse `recovery.at_risk` / `GET /bandejas/en-riesgo`. When a professional or service filter is set, filter by it (join through the treatment's appointments). Each row shows:
  - patient;
  - service or treatment;
  - days since the last appointment;
  - contact links (reuse `EnlacesContacto` from `Llamar.tsx`);
  - opening the patient record.
- **"Pacientes que faltaron 2+ veces".** New endpoint `GET /indicadores/faltas-repetidas`, using the same filters. It returns patients with ≥2 `no_asistio` in the range: patient id, name, count, last date, and whether they have a future appointment. Same row actions.
- **"Citas sin desenlace".** The N from R1, linking to the inbox.

### R6. Tables by professional and by service (I-05, drill-down)
- **Columns:** these replace the two bar charts. Name, Citas, Atendidas, No asistió, % inasistencia, plus Cancelaciones if it's cheap to add (otherwise skip it).
- **Sorting and display:** default sort is % inasistencia, highest first. All names are visible. Numbers are right-aligned and tabular.
- **Small samples:** when attended + no-show < 10, show "muestra pequeña" in muted text and render the % in grey.
- **Drill-down:** clicking a row opens a dialog listing the missed appointments behind it. New endpoint `GET /indicadores/citas-perdidas?…filters&profesional_id|servicio_id` returns appointments in the range with state `no_asistio` or a late cancellation. Each row has:
  - date;
  - patient;
  - professional;
  - service;
  - state;
  - reason, if cancelled;
  - whether it was rebooked (`reprogramada`, or a newer appointment exists for the same patient and service).

  Clicking a row opens the existing `HojaCita`, if that's straightforward.
- **Data source:** this endpoint queries `cita` directly. `hecho_diario` has no row-level data.

### R7. Do reminders work? (I-06)
A small card with two parts:
- **Inasistencia con recordatorio vs. sin recordatorio:** two horizontal bars or two numbers, each with its n. Computed from `cita` and `datos_origen->>'recordatorio_enviado'`, in a new endpoint `GET /indicadores/recordatorios`, with the same filters.
- **Funnel**, with counts and the % from step to step:
  1. Citas del periodo
  2. Con recordatorio enviado
  3. Confirmadas por el paciente
  4. Atendidas

  The data is in `hecho_diario`: `citas`, `con_recordatorio`, `confirmadas_explicitas`, `atendidas`.
- **Failed reminders:** if `/sistema` reports failed reminder tasks, add a muted line: "N recordatorios fallaron al enviarse" (link to `/sistema`).

### R8. No-shows by weekday × hour (I-07)
- **Endpoint:** `GET /indicadores/dia-hora`, with the same filters. Computed from `cita` where `rango is not null`, in local time. It returns cells `{dia_semana 0-6, hora, atendidas, no_asistio}`.
- **UI:** an HTML table (not a chart library), with rows for weekdays (Lun to Sáb, plus Dom only if any data) and columns for hours. Cell background intensity follows the no-show %. Cells with n < 5 stay neutral and show "·". Tapping or hovering a cell shows "X de Y". The table scrolls horizontally inside its card on mobile; the page itself must not scroll horizontally.

### R9. Readable reasons (I-05)
Replace the reasons bar chart with a list sorted by count: a horizontal bar for each reason, with the full label, the total count, and the late count. "sin especificar" and "Otro" stay visible.

### R10. Fix filters that are ignored (I-08)
- `time_between_patient` must apply the professional and service filters, the same way `time_between` does.
- `hecho_diario_profesional` has no service column. When a service filter is set:
  - **Ocupación:** show "—" with the note "No aplica al filtrar por servicio".
  - **Slot cards:** show "—" with the same note.

  Do not show numbers that silently ignore the filter.
- Add a backend test for each fix.

### R11. Move maintenance controls (I-09)
- **Move to Sistema:** "Ejecutar cierre ahora" and "Último cierre diario" go to `Sistema.tsx`, keeping the confirmation dialog.
- **"Datos al":** Indicadores shows only a muted line, "Datos al <fecha>". When the daily close is behind today − 1, the line says so.
- **Future date:** investigate why `ultimo_diario` is 2026-11-30 in the demo while today is 2026-11-25, and fix the cause. It is likely the seed or a demo clock offset. If the close legitimately covers future days, display `min(ultimo_diario, hoy)`.

## 4. Non-goals (Phase 1)

- Money: no peso amounts. There is no price per service (Phase 2).
- Targets ("meta ≤ 15 %"): Phase 2.
- Before/after experiments, reminder delivery status, and auxiliar pending-item productivity: Phase 2.
- No new chart library. Recharts stays for the trend; the tables are plain HTML.

## 5. Testing

The developer's laptop is slow. **Do not run the full test suites locally.** Run only:
- `uv run pytest tests/test_indicators.py -q`, plus any new test file you create for this work;
- `cd panel && npx vitest run src/flujos.test.tsx`, or a new targeted test file;
- `cd panel && npx tsc --noEmit` once at the end.

CI runs everything else.

Add tests for:
- R2: the formula;
- R3: the previous-period comparison;
- R5: the repeated no-shows endpoint;
- R6: the missed-appointments endpoint;
- R7: reminders;
- R8: weekday × hour;
- R10: the filter fixes;
- the UI: one test that the banner shows when there are appointments with no outcome, and one test that a table row opens the drill-down.

After any API change:
- regenerate `docs/openapi.json` with `make api-esquema`;
- regenerate the panel types with `cd panel && npm run tipos`.

## 6. Phase 2 (not in this PRD)

- **Price per service and "money lost":**
  - add `servicio.valor` and an admin form to edit it;
  - compute the money lost from no-shows plus late cancellations;
  - add a "Perdido este periodo: $X" card, plus a pesos column in the R6 tables.
- **Configurable targets per indicator,** shown on the key cards as "meta ≤ 15 %".
- **Who resolves pending items, and when:**
  - record `usuario_id` and a timestamp when inbox items are resolved;
  - add metrics for auxiliar pending items.
- **Reminder delivery status** from the channel provider, and before/after markers for template changes.
- **Time from cancellation to a new appointment** (median and distribution).
