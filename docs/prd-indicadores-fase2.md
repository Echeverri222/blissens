# PRD: Indicators phase 2 — money, targets and team follow-through

> Audience: an implementing agent or a reviewer. Self-contained: read this, `docs/prd-indicadores.md` (phase 1, already shipped in PR #20), `CLAUDE.md`, `README.md` and `GLOSSARY.md`.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: the three manager reviews of 2026-11-25 (see phase 1 §2). These items needed data the system did not store yet.

## 1. Goal

Answer the three questions phase 1 could not:

| Who | Question |
|---|---|
| Patricia (owner) | "How much money did we lose this period, and where?" |
| Valentina (operations) | "Are we hitting our targets? Is the team closing its pending items, and how fast? How long until a cancelled patient books again?" |
| Dr. Andrés (clinical) | (Benefits from the targets and the rebooking time.) |

## 2. Requirements

### R1. A value for each service (needed by R2)
- **Database.** New migration `migrations/013_valor_servicio.sql`, plus a `.down.sql`, following the pattern of the existing migrations. It adds `servicio.valor` as a nullable `numeric(12,0)` in pesos, with `check (valor is null or valor >= 0)`.
- **API.** Add `valor: int | null` to the service schema returned by the catalogue endpoint.
- **Admin endpoint.** New `PUT /admin/servicios/{id}` with body `{ "valor": int | null }`. It is restricted to administrators: use the existing `administrador` dependency in `estudia/api/admin.py`.
- **UI.** A new section in `Administracion.tsx` titled "Valor de los servicios":
  - one row per service, showing the name and a peso input;
  - each value is saved per row with "Guardar", using `useAccion` with a success toast;
  - the screen explains: "Se usa para estimar el dinero perdido por inasistencias y cancelaciones tardías. Es un valor promedio, no una factura."
  - amounts are formatted with `Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 })`. Put the helper in `panel/src/lib/`.
- **Demo seed (`estudia/data.py`, demo data only).** Set round, clearly fictional values for each demo service, for example 80 000, 150 000 or 400 000. **Never use figures from the real Excel files: the repo is public.**

### R2. Money lost
- **Definition.** Money lost in a period is the sum of `servicio.valor` over the period's appointments (`cita.dia` within the range, matching the filters) that:
  - ended as `no_asistio`, or
  - were cancelled late (`cancelacion.tardia`) and not rebooked. "Not rebooked" means the appointment is not `reprogramada`, and the same patient has no appointment with the same service created after the cancellation and within 30 days.
- **Missing values.** Appointments whose service has no value are not counted. They are reported in `citas_sin_valor`.
- **API.**
  - Add `valor_perdido`, `valor_perdido_inasistencia`, `valor_perdido_tardias` and `citas_sin_valor` to `/indicadores/resumen`, including the `anterior` block when `comparar=true`.
  - Compute them from `cita` directly; `hecho_diario` has no per-appointment value. Do not change the daily close.
- **Tables.** Add `valor_perdido` to each row (`FilaDimension`) of `/indicadores/por-profesional` and `/por-servicio`.
- **Key cards.** Add a 4th key card, "Dinero perdido", placed first:
  - the amount in COP;
  - the comparison with the previous period. The colour follows the meaning: less money lost is better;
  - the help text: "Inasistencias + cancelaciones tardías que no se reagendaron, al valor promedio de cada servicio."
  - the breakdown: "$X por inasistencias · $Y por cancelaciones tardías".
- **When values are missing.**
  - If every service lacks a value, the card shows "Sin valores" and the text "Configura el valor de cada servicio en Administración", with a link. The link appears only if the user is an administrator; otherwise the text reads "Pide a quien administra que configure…".
  - If only some appointments lack a value, show the muted line "N citas sin valor configurado no se cuentan".
- **Layout.** The key strip becomes 4 cards: 2×2 on mobile and 4 across on `lg`. Remove the phase 1 rule that makes the last card span the full width on mobile.
- **Tables.** Add a "Perdido" column to the tables by professional and by service, visible on mobile as well. The tables stay sorted by % inasistencia. Add a small control to sort by "Perdido" instead: a toggle in the table header or a `<select>`.

### R3. Targets for each indicator
- **Storage.** New config key `metas_indicadores` in `estudia/config.py` `DEFAULTS`, defaulting to `{}`. Its shape is `{ "inasistencia": {"max": 0.15}, "asistencia": {"min": 0.8}, "confirmacion": {"min": 0.6}, "dinero_perdido": {"max": 2000000} }`, and every key is optional.
- **Admin endpoint.** `PUT /admin/metas`, for administrators only, validates the shape:
  - rates are between 0 and 1;
  - money is an integer of at least 0;
  - only `min` for "higher is better" indicators, and only `max` for the others.
- **API.** `/indicadores/resumen` returns `metas`, the current targets, so the screen needs no extra call.
- **UI in `Administracion.tsx`.** A section "Metas de indicadores" with optional inputs:
  - percentages are entered as whole numbers (15 means 0.15);
  - money is entered in pesos;
  - an empty field removes the target.
- **UI on each key card that has a target.**
  - Show a line "Meta ≤ 15 %" or "Meta ≥ 80 %", followed by a pill: "Cumple" (green) or "No cumple" (red).
  - When the value is null, show no pill.

### R4. Record who resolves pending items, and when
- **Database.** New migration `migrations/014_resolucion_pendientes.sql`, plus `.down.sql`, adding:
  - `mensaje.gestionado_en timestamptz` and `mensaje.gestionado_por bigint references usuario(id)`;
  - `caso_seguimiento.cerrado_por bigint references usuario(id)`, filled only when a person closes the case by hand. Automatic closes leave it null.
- **Writes.**
  - `bandejas` "marcar gestionado" sets `gestionado_en` (from `clock.now`) and `gestionado_por`, the current user.
  - `followup.register_manual` and any manual close set `cerrado_por`. Thread the user id from the API layer.
- **Check the appointment history.** Every panel action that changes an appointment's state must write `historial_estado.usuario_id`: outcome, confirming by phone, cancelling, rescheduling, and the "Sin respuesta" and "Gestionada" actions. Today it is filled in only 2 of 867 demo rows. Find the call sites in `estudia/api/` and `lifecycle.py`, and pass the user through.
- **Demo seed.** No backfill is needed. Optionally, give a few demo rows realistic values so R5 shows something.

### R5. Team follow-through metric
- **Endpoint.** New `GET /indicadores/pendientes`, using the same date filter as the other indicator endpoints. The professional and service filters apply where they make sense.
- **Response.** For each of three kinds:
  - `cierre_citas`: the outcome was registered by a person. Time = `historial_estado.momento − upper(cita.rango)`, using only the first outcome entry, by a person and not reverted.
  - `mensajes`: time = `gestionado_en − mensaje.creado_en`. Check the column name in the migration.
  - `seguimientos`: cases closed by hand; time = `cerrado_en − abierto_en`.

  Each kind returns `{ resueltos, mediana_horas, p90_horas, abiertos_hoy, vencidos }`. `vencidos` counts items still open after more than 48 h for appointments and messages, and more than 7 days for follow-ups. Put these thresholds in constants.
- **By person.** `por_usuario`: `[{ usuario, resueltos, mediana_horas }]`, taken from the user columns above. Show "Sin registrar" for null users.
- **UI.** A card "¿El equipo cierra sus pendientes?", placed after the reminders card:
  - a 3-row table: kind, resolved, median time ("3 h" or "2 días"), and overdue now;
  - a small list by person below it;
  - a footnote: "Antes del <fecha de la migración> no se registraba quién resolvía; esas filas aparecen como Sin registrar."

### R6. Time from cancellation to a new appointment
- **Endpoint.** New `GET /indicadores/reagendamiento`, with the same filters. Consider cancellations whose `cancelacion.momento` falls in the range. The rebooking is the first appointment for the same patient created after `momento` (`cita.creada_en`), with the same professional or the same service, within 60 days.
- **Response.**
  - `mediana_dias`, `total`;
  - `buckets`: `mismo_dia`, `1_3`, `4_14`, `15_60` and `no_reagendo`.
- **UI.** Inside "Más indicadores", next to the cancellations card: a horizontal stacked bar or 5 small counters, with the line "La mitad reagenda en N días".

## 3. Non-goals
- Real billing or payments, and taxes.
- Reminder delivery status from the provider: the channel is simulated.
- Before/after experiment markers.
- Editing the other system settings from the UI.

## 4. Testing

The developer's laptop is slow. **Do not run full suites.** Run only:
- `uv run pytest tests/test_indicators.py -q` and any new test file you create, by path. The migrations run in the test fixtures; check `tests/conftest.py`.
- `uv run pytest tests/test_admin.py -q`, if you touch the admin endpoints.
- `uv run pytest tests/test_recovery_tasks.py tests/test_followup.py -q`, if you touch the follow-up code.
- The single `tests/test_api.py` test that covers indicators, `-k indicators`, if the response shape changes. In phase 1 it compared the full dictionary.
- `cd panel && npx vitest run src/indicadores.test.tsx src/flujos.test.tsx`.
- `cd panel && npx tsc --noEmit` and `npx eslint <changed files>` once at the end. CI runs lint, and phase 1 failed on unused variables.

Add tests for:
- **R1:** the endpoint, including that it is admin-only.
- **R2:** money lost, covering a no-show, a late cancellation that was rebooked, one that was not, and a service with no value.
- **R3:** target validation, and `metas` returned in the summary.
- **R4:** `gestionado_por` and `gestionado_en` are set, and `historial_estado.usuario_id` is set for at least the outcome and confirm actions.
- **R5:** median and overdue counts.
- **R6:** the buckets.
- **UI:**
  - the money card with and without values;
  - the target pill;
  - the "Valor de los servicios" save flow in Administración.

After API changes:
- run `make api-esquema`;
- run `cd panel && npm run tipos`.

A dev server (`make dev`) may already be running. Do not start or stop it. Run the migrations against the dev DB using the repo's migrate command (see the `Makefile`), so the developer can see the result.
