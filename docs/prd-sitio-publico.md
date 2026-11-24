# PRD: Public Blissens site + scheduling + staff panel under one domain

> Audience: an implementing agent (Sonnet-class). Self-contained: read this, `CLAUDE.md`, `README.md`, `GLOSSARY.md`, then work through the work packages in order.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention). English copy exists only for the public site (`/en`).
> Evidence: three role-play reviews (patient, receptionist/auxiliar, specialist) run against the working prototype. Finding IDs (P-, A-, E-) refer to those reviews and are summarised in Appendix A.

## 1. Goal and pitch

Show the clinic one product on **one domain**: the public marketing site (a faithful, better-behaved copy of https://blissens.com/), the **appointment scheduler** replacing the site's dead "Schedule an Appointment" page, and the **staff panel** at `/panel` for the auxiliar and specialists. The clinic can adopt it under the domain they already own (see §8).

Success = a patient can go from the landing to a confirmed appointment in under a minute on a phone, in Spanish or English, and the auxiliar and specialist see that appointment and the site's leads correctly in the panel, with no wrong data on screen (no wrong doctors, services, hours or address).

## 2. Current state (already built, uncommitted in the working tree)

- `GET /` (ES) and `GET /en` (EN): landing with all sections of the real site, built in `estudia/web/templates/sitio.html`, copy in `estudia/web/copia.py`, assets and `sitio.css`/`sitio.js` in `estudia/web/static/sitio/` (self-hosted fonts and images, no third-party requests; a test enforces it).
- `#agendar` section embeds step 1 of the existing flow (`/agendar/identificar`, HTMX). Patient pages (`base.html` + identificar/elegir/mis_citas/cancelar/contacto/baja_correo) share the site shell.
- `POST /sitio/solicitud`: virtual-assessment, Experiences and contact forms insert a row into `solicitud_contacto` (details packed into `nota`).
- `/panel` (React) and the JSON API are unchanged except `Bandejas.tsx` + `panel/src/lib/solicitudes.ts`, which now render web leads (tab "Contactos y solicitudes", "Solicitud web" badge, Llamar/WhatsApp/correo links parsed from `nota`) instead of the false identity-conflict text. WP4 replaces this interim parsing with a real tray. The landing footer has an "Acceso equipo" link to `/panel`; interior patient pages use a minimal footer without it.
- Hardening already in place: per-IP in-memory rate limit on `POST /sitio/solicitud` (`estudia/web/limite.py`; uses the socket IP only, so behind a reverse proxy all visitors share one bucket until trusted proxies are configured), landing renders without a DB connection, phone/email validation on the sanitised values, canonical + hreflang + absolute `og:image` on the landing.
- Tests: `tests/test_sitio.py` (6). One pre-existing failure (`test_migraciones_subir_bajar_y_comparar_esquema`) needs PostgreSQL 16; it fails only on the private PG14 dev cluster.

## 3. Dev environment notes

- Docker Desktop was broken on the dev machine. A private PG14 cluster runs on `127.0.0.1:5433` (user/password `estudia`, DBs `estudia`, `estudia_test`); data dir lives in the session scratchpad and may be gone. Preferred: `make setup && make dev` with Docker (PG16). Never touch whatever listens on port 5432.
- Demo logins: `auxiliar`, `especialista1`, `especialista2`, password `demo-blissens`. `make seed` resets fictitious data (also clears test data left by the reviews).
- **Repo is public. Never commit real patient/professional data from the Excel files, `.env`, or numbers derived from them.** Seed data is fictitious; keep it that way.
- Regenerate `docs/openapi.json` with `make api-esquema` if the API changes. `make test` must stay green except the PG16-only test on PG14. Run `uv run ruff check .`.

## 4. Work packages (priority order)

Each package lists the finding IDs it closes and acceptance criteria. Do P0 first; P1 next; P2 only if time remains. Open questions (§7) must not block P0: where unknown, make the content configurable and note the assumption.

### P0 — Trust and correctness (the demo currently shows wrong things)

**WP1. One source of truth for professionals, services, hours, address** (P-01, P-06, E-03, A-07, A-13)
- The scheduler shows seed professionals/services that do not match the site ("Dra." used for a man's name; "Limpieza/Urgencia/Control de ortodoncia" vs the site's services; no specialty shown). Make the demo data and the public site tell the same story: the `negocio` configuration (hours, address, phone, email, professionals with title/specialty/photo, public services) is the single source used by the landing (`copia.py` should read from it, not duplicate it), the scheduler, and the outgoing messages/emails.
- Seed (`estudia/data.py`, fictitious) must include professionals and services that match what blissens.com advertises (oral rehabilitation / smile design team of three, services such as smile design, diagnosis/"prelude" consult, virtual assessment). Use neutral fictitious names for seed professionals unless the owner supplies the real ones as configuration, not as committed seed data.
- Add the professional's title (Dr./Dra.) as data, never inferred. Show "Name — Specialty" in the specialist picker. With "cualquier especialista", show who was assigned before confirming where possible.
- Working hours: the site footer, the scheduler slots (currently 7:30–17:00, no Saturday) and the panel (Saturday greyed out) must agree. Hours come from configuration. Saturday 8–12 bookable if the configured professionals work it.
- Replace the placeholder "Calle 00 # 00-00, Bogotá" in WhatsApp/email templates with the configured address (Medellín, El Tesoro). Fix "p. m.." double period.
- AC: no screen, message or email shows an address, hour range, title or service that contradicts the configuration; a test asserts landing footer hours == slot generator hours for the demo business.

**WP2. Booking confirmation that actually reassures** (P-07, A-06, P-14)
- After booking/rescheduling/cancelling, show a confirmation card: service, specialist (with title), full date/time in `America/Bogota`, address with a map link, "what to bring"/arrival note (configurable text), duration if known, "Add to calendar" (.ics download), buttons to change/cancel, and a WhatsApp/phone help link.
- The message must state the channel truthfully (email vs WhatsApp according to consent). Reschedule messages say "Cambiamos tu cita del X al Y" (not "quedó agendada"), and include the new date.
- Label the steps ("1 Tus datos · 2 Tu cita · 3 Confirmación") or drop "Paso 1 de 3". Don't show "Volver a mis citas" to patients with none.
- AC: tests on the message templates (golden cases already exist in `tests/test_golden.py`; update them deliberately).

**WP3. Language carried through the whole flow** (P-02)
- A patient who starts in `/en#agendar` must stay in English through registration, consent text, slot picker, confirmation, "Mis citas", cancel/change, error messages and emails/WhatsApp (store `idioma` per patient or in the signed link/session). ES remains the default. The ES/EN toggle must keep the visitor on the equivalent page/section, not reset to the landing top.
- Legal consent text in English must be reviewed by the owner (open question Q4); ship it as configurable copy.
- AC: crawling the EN flow yields no Spanish user-visible strings except proper nouns; a test covers it.

**WP4. Public-site lead handling in the panel** (A-03, P-09, P-11)
- Today web forms land in the "Validar por teléfono" tray (meant for identity conflicts) as a pipe-joined `nota` string. Create a proper **"Solicitudes web"** tray for the auxiliar: columns = type (Virtual assessment / Experience + package / Contact), country, language, name, email, phone, message, received time, status; row actions = **Llamar** (`tel:`), **WhatsApp** (`https://wa.me/<digits>`), **Responder por correo** (`mailto:`), status Nueva → Contactada → Agendada / Descartada, with an internal note. "Gestionada" must keep an audit record (who/when/outcome).
- Prefer structured columns over `nota` (this needs a migration with `.down.sql`, following `estudia/migrate.py` conventions; keep `solicitud_contacto` compatible for the existing identity-validation use, e.g. add `origen`, `tipo`, `paquete`, `pais`, `idioma`, `correo`, `estado`). Update the "Qué hacer hoy" copy ("El documento — intentó agendar desde otro celular ()" must never render for web leads).
- Experiences/virtual assessment success copy must not promise an email unless one is sent. Either send a real acknowledgement email through the existing `correo` module (respecting consent) or change the copy to "te escribiremos en menos de 24 h hábiles" (configurable SLA).
- Returning patient with a new/mistyped phone (P-11): replace the dead end with a message explaining the likely cause plus WhatsApp/call buttons and an option to leave a callback request that lands in the new tray.
- AC: submitting each public form produces a correctly typed row visible in the new tray with working Llamar/WhatsApp/correo actions; tests cover the three forms and the status flow; panel types regenerated (`make panel`).

**WP5. Panel search and phone confirmation (front-desk basics)** (A-01, A-02, A-05)
- Patient search (`estudia/bandejas.py` ~L101): accent- and case-insensitive (use `unaccent` extension via a migration, or normalise in Python/SQL consistently), match on full name word by word ("jesus sanchez", "sanchez" must find "Jesús Sánchez Correa"), strip non-digits for phone/document ("300 123 4567", "1.234.567"), and tolerate small typos (e.g. `pg_trgm` similarity). Keep the access-log rule: do not store the search text (`auditoria_acceso`).
- Duplicate guard: creating a patient with an existing phone or document warns "¿Es este paciente?" with the existing record; allow explicit override.
- Add a **"Confirmó por teléfono"** action (tray row "No confirmadas" and the appointment detail) that records a confirmation with the actor and channel in the history; add an "ya confirmó" option when staff book by phone. Extend `permisos.acciones_cita` accordingly.
- AC: unit tests for search variants; confirm action appears in the history with the staff user; no regression in confirmation chains/offers.

### P1 — Quality and delight

**WP6. Panel: clinical context and "my day" for the specialist** (E-01, E-06, E-09)
- Appointment detail for the specialist gets a "Paciente" section: first visit vs control, visit count, last/next appointment, treatment-in-progress marker, reception note, alert flags (e.g. allergy/anticoagulant as free-text alerts entered by staff). Read-only access to a minimal patient card for the specialist's **own** patients only (keep the existing RLS/permission model; verify another specialist's patient still returns 404/403).
- "Próximo paciente" card at the top of Mi agenda; past appointments without outcome show a "Falta desenlace" badge, a counter, and inline ✓/✗ buttons.
- Outcome toast gets **Deshacer**; revert/history copy loses internal wording ("compensa con un movimiento nuevo", "Reversión del movimiento 750", "Datos ficticios" note shown to users).
- Show the cancellation **reason and note** in history (A-09). Outcome note field optional.

**WP7. Panel: blocks and vacations** (E-04, E-05, E-11)
- "Varios días" + hours creates one block per day (with preview "5 bloqueos de 09:00 a 11:00"), plus "repetir semanalmente".
- If a block conflicts with appointments, offer "Bloquear y enviar las N citas a recepción" feeding a reception tray instead of two contradictory messages; remove jargon "citas vivas"; clear the error when inputs change.
- Defaults: date = viewed day; "Hasta" ≥ "Desde"; 24-hour times; Spanish native validation messages (`lang="es"`, custom messages); delete dialog names the block; list blocks beyond 6 weeks.

**WP8. Panel layout and responsiveness** (E-07, E-08, A-04, A-15, A-16, E-12)
- Day view: always show service + status (dot/tint) for 30-min appointments, add a colour legend, dim past appointments, make "cupo en oferta" boxes clickable. Offer the list view (best at 390px) on all widths.
- Collapse the sidebar to icons ≤ 1100px; week view must fit 1024px (hide empty days); fix 390px header wrap and horizontal scroll; tray tabs scrollable.
- Rebrand the panel to match the site: tab title "Blissens · Panel" (not "Estud-IA"), BLISSENS wordmark/colours (black/white, Inter + Cardo accents), nicer login. Add skip link, accessible name on the avatar menu, session-expiry message, shorter idle timeout for shared tablets (configurable).
- Two staff on one browser: the session cookie is per origin; document it and show "Sesión de X" prominently (do not change the auth model in this PRD).

**WP9. Public site polish** (P-03, P-04, P-05, P-10, P-12, P-13, P-15, P-17, P-18)
- Fix the HTMX focus/scroll handler in `sitio.js` (`htmx:afterSwap` with `outerHTML`): after submit, scroll to and focus the new message/error element by id. Success and error messages must be visible without scrolling.
- Back-button after booking: send `Cache-Control: no-store` on `/p/*`, reload on `pageshow` with `persisted`; never leave "Confirmar cita" stuck.
- Cancel flow: show which appointment is being cancelled, require a confirm step after choosing a reason, offer "Cambiar fecha" first.
- Footer: Instagram/Facebook real URLs (Q3), data-processing policy as a real page `/politica-de-datos` (text supplied by the owner, Q2) linked from every consent label (Ley 1581). Link "Mis citas" access ("Ya tengo cita" → identify by document) in header/footer. Friendly branded 404/410 and expired-link pages instead of raw JSON (HTML requests only; JSON API keeps JSON).
- Floating/visible WhatsApp button (configurable number) and `tel:` links; enlarge tap targets ≥ 44px (toggle, checkboxes, footer links); fix h1 spacing ("Sonríe y mira al futuro"); move `?aviso=` messages out of the URL (flash via cookie or HX trigger).
- Visually bridge landing → booking: booking pages use the dark/editorial header and typographic treatment of the landing instead of a plain white card.
- Add `sitemap.xml`, `robots.txt` (booking/patient pages `noindex`), canonical + hreflang ES/EN, JSON-LD `Dentist` (LocalBusiness) with hours/address.

### P2 — Content depth and growth

**WP10. Content parity with the real site** (P-08, P-09, P-16)
- Separate linkable pages mirroring the real site: `/servicios`, `/nosotros`, `/experiencias` (with packages, inclusions and prices as configurable content; real prices Q1), `/evaluacion-virtual`, `/casos` (before/after), each ES + EN, sharing the shell. Keep the landing as the summary.
- Before/after: real, **consented** cases supplied by the clinic (Q5), with name-less captions; until then hide the section rather than show placeholders marked "imagen de ejemplo". Resolve the Premium card photo showing a third-party hotel sign (Q6).
- Prices/payment info on the scheduler for services that have one (configurable, optional).

**WP11. Reception extras** (A-10, A-11, A-12, A-17, E-10, E-13)
- Contact shortcuts (Llamar/WhatsApp) on every tray row that says "llámale"; edit patient data; print/export day agenda; check-in / "en sala" status; patient notes; keyboard shortcut for search.
- Indicators page: reconcile "Cupos liberados" with the tray, plain-language labels, es-CO number/date formats, no "÷" formulas for reception.
- Offer chain: expire/disable stale offers' buttons; at most one active offer per patient per cupo window.
- iCal feed per specialist (token URL); "Solicitar cambio" for the weekly schedule; highlight newly arrived changes in the agenda.

## 5. Non-goals

- No change to the auth model, multi-tenant RLS, the channel port, or the JSON API contract beyond fields needed by the work packages (regenerate `docs/openapi.json`).
- No CMS/WordPress integration, no payments, no real WhatsApp provider changes, no rewrite of the panel framework.
- No real clinic data in the repo.

## 6. Quality bar (applies to every package)

- Mobile first (390px) and 1440px; WCAG AA contrast, visible focus, keyboard operable, `prefers-reduced-motion` honoured, correct `lang`.
- No third-party runtime requests on the public site (existing test). Fonts and images self-hosted.
- Tests with each package; `uv run pytest`, `ruff`, `make test` panel checks, and `make e2e` recorridos updated where flows change. Update golden cases deliberately.
- Verify in a browser (Playwright e2e or Chrome tools) end to end: landing → `#agendar` → book → confirmation (ES and EN); web lead → panel tray → contacted; specialist outcome + undo.
- Do not commit/push unless asked; follow the repo's PR style (`mattpocock-skills:pr` if available).

## 7. Open questions for the owner (default noted, do not block)

| # | Question | Default until answered |
|---|---|---|
| Q1 | Real Experiences prices/inclusions (real site shows three packages with USD prices) and whether the virtual consultation is free or paid (real site is inconsistent) | Omit prices; say "te contactamos con la propuesta" |
| Q2 | Data-processing policy text (Ley 1581) | Placeholder page clearly marked draft, linked from consents |
| Q3 | Instagram / Facebook URLs, WhatsApp number | Hide icons until provided; use the phone in the footer for WhatsApp |
| Q4 | Approval of English consent/legal text | Ship translation flagged "pending legal review" in config |
| Q5 | Consented before/after cases | Hide section |
| Q6 | Keep the Premium card hotel photo? | Replace with a neutral Medellín image |
| Q7 | Real professionals, titles, specialties and which services each performs (there is no professional↔service mapping today: the matcher offers every professional for every service) | Add `profesional_servicio`; demo seed maps fictitious ones |
| Q8 | Saturday hours: does any specialist work Saturdays? | Follow configured professional schedules |

Open design point inside WP1/Q7: add a `profesional_servicio` table (migration) and filter `/agendar` slots and panel booking by it (`any_slots` / `assign_professional` in `estudia/agenda.py`).

## 8. Deployment under the clinic's existing domain (for the pitch)

The clinic's domain currently points to WordPress. Options to present, cheapest first:
1. **Subdomain** (`citas.blissens.com` → this app, landing + `/agendar` + `/panel`), WordPress untouched; the WordPress "Schedule an Appointment" menu item links to it. Zero risk, reversible.
2. **Path-based reverse proxy**: `blissens.com/agendar` and `/panel` proxied to this app while WordPress keeps everything else.
3. **Full replacement**: apex domain points to this app (the landing in this PRD is the copy); needs WP content parity (WP10), redirects from old WP URLs (`/about-us/`, `/services/`, `/case-study/`, `/medelline/`, `/foreigner-virtual-assessment/`, `/experiences/`, `/contact/`, `/es/`) to the new routes, and `BASE_URL`/cookies/TLS set for the domain.
Deployment recipe already exists (`render.yaml`, `docs/adr/0007-despliegue-render-supabase.md`); production requires the privacy conditions of PRD #4 (demo/free tier is fictitious data only). Implementer: add a short `docs/` note with the DNS/proxy steps and the 301 map; do not change DNS.

## Appendix A — Review findings (source of truth for the packages above)

Scores (1–10) from the reviews: paciente — ease 6, beauty 7, trust 4, mobile 7, a11y 6; auxiliar — ease 6, beauty 6, terms 5, speed 8, a11y 7; especialista — ease 7, beauty 7, clinical usefulness 3, speed 9, a11y 6.

What works and must not regress: fast pages (~15 ms), no account needed, double-click on "Confirmar cita" creates no duplicate, rescheduling in 3 clicks, server-side validation and consent enforcement, "Qué hacer hoy" list, deep-linkable appointment drawer, in-app dialogs, outcome in 2 clicks with audit/revert, blocks immediately remove public slots, conflict messages list clashing appointments, strict per-specialist data isolation (API 403/404 verified), no console errors, mobile list view of the agenda, mobile menu and sticky CTA, keyboard-accessible before/after slider.

| ID | Sev | Finding | Pkg |
|---|---|---|---|
| P-01 | blocker | Scheduler shows professionals/services not on the site; wrong "Dra." | WP1 |
| P-02 | major | EN visitors fall into a Spanish flow; toggle loses place | WP3 |
| P-03 | major | Success/error messages land off-screen; focus falls to body (`sitio.js` afterSwap + outerHTML) | WP9 |
| P-04 | major | Back button after booking leaves a stuck "Confirmar cita" and a stale free slot | WP9 |
| P-05 | major | Cancel doesn't say which appointment; one tap cancels | WP9 |
| P-06 | major | Footer hours ≠ slots (7:30–17:00, no Saturday) | WP1 |
| P-07 | major | Confirmation lacks address/map/what-to-bring/calendar; says WhatsApp when email chosen; reschedule msg omits new date | WP2 |
| P-08 | major | Before/after are placeholders | WP10 |
| P-09 | major | Experiences lack prices/inclusions; success copy over-promises | WP4/WP10 |
| P-10 | major | Policy and consents not links; social icons not links | WP9 |
| P-11 | major | Returning patient with new phone hits a dead end | WP4 |
| P-12–P-18 | minor/polish | "Mis citas" unreachable; raw-JSON 404; unlabeled steps; no WhatsApp link; no cost info; landing↔booking visual jump; h1 spacing, `?aviso=` in URL, small tap targets | WP9/WP10 |
| A-01 | blocker | Search ignores accents/full names/spaced phones | WP5 |
| A-02 | major | Duplicate patients accepted silently | WP5 |
| A-03 | blocker | Web leads land in "Validar por teléfono" as a raw pipe string, no contact actions/status | WP4 |
| A-05 | blocker | No way to record "confirmó por teléfono" | WP5 |
| A-04 | major | Day view hides status/service for 30-min appts; no legend | WP8 |
| A-06 | major | Reschedule message reads like a new booking | WP2 |
| A-07 | major | Placeholder address "Calle 00 # 00-00, Bogotá"; "p. m.." | WP1 |
| A-08 | major | One-click outcome/gestionada actions with no undo; list shifts | WP6 |
| A-09 | major | Cancellation reason/note saved but never shown | WP6 |
| A-10, A-11 | major | No Llamar/WhatsApp shortcuts; no check-in, notes, edit patient, print | WP11 |
| A-12–A-18 | minor/polish | Indicators contradict trays and use jargon; raw terms; panel brand mismatch ("Estud-IA"); 390/1024px layout; agenda details; stale offers; English native validation | WP6/WP8/WP11 |
| E-01 | major | Specialist sees no clinical context; can't open patient card | WP6 |
| E-02 | major | Booking ignores specialty (no professional↔service mapping) | WP1 |
| E-03 | major | Site team ≠ bookable professionals; Saturday mismatch | WP1 |
| E-04 | major | "Varios días" block is one continuous block incl. nights; no recurring blocks | WP7 |
| E-05 | major | Block conflicts: contradictory messages, no hand-off to reception | WP7 |
| E-06 | major | Past appointments without outcome not flagged | WP6 |
| E-07–E-13 | minor/polish | Truncated day/week cards; 1024px week overflow; limited outcomes & buried undo; no change highlighting/iCal; form defaults and English validation; branding/a11y; read-only schedule | WP6–WP8/WP11 |

Full review transcripts were written to the session scratchpad (`findings/paciente.md`, `auxiliar.md`, `especialista.md`) and may no longer exist; this appendix is the durable summary.
