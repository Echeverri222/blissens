# PRD: Booking for the whole family

> Audience: an implementing agent or a reviewer. Self-contained: read this, `CLAUDE.md`, `README.md` and `GLOSSARY.md`.
> Language: this PRD is in English; all user-facing copy and domain code stay in Spanish (repo convention).
> Evidence: a role-play review on 2026-11-25 in which a parent booked appointments for themselves, their partner and their child
> on one shared phone. Finding IDs (F-) are listed in §2.

## 1. Goal

A parent (or anyone who looks after relatives) can book, see, change and cancel appointments for everyone in their household
from **one personal link**, without retyping their phone and consent for each person, and with a valid legal basis for
processing a minor's data.

Success = a parent with two dependents books three back-to-back appointments starting from "Mis citas" in under two minutes,
sees all three on one screen, and the clinic's panel shows who is responsible for each dependent.

## 2. Findings that motivate this PRD

| ID | Finding | Severity |
|---|---|---|
| F-01 | "Mis citas" has no way to book for another person. The parent goes back to `/agendar` and repeats document, phone, name and consent for every family member (≈4 screens × N people). | High |
| F-02 | Each person's link shows only their own appointments. A parent has to keep one link per child to see or change anything. | High |
| F-03 | Shared phone: incoming WhatsApp replies from a phone with several patients are dropped as `ambiguo` (`estudia/web/app.py`, webhook). | High, **deferred** (§7) |
| F-04 | A minor registers through a consent text written in the first person ("tratar **mis** datos"). Law 1581 of 2012 requires the legal representative to authorize processing of a minor's data; the system records no guardian. | High (legal) |
| F-05 | No help to line up consecutive appointments: the parent picks each slot by hand and a slot can be taken between bookings. | Medium |
| F-06 | The panel shows no relation between patients: reception cannot see that a child's appointments are managed by a parent. | Medium |

## 3. Concepts (added to `GLOSSARY.md`)

- **Responsable**: a patient who manages the appointments of other patients from their own personal link. A responsable cannot
  themselves be managed by someone else (one level only; no chains).
- **Familiar** (dependent): a patient with `responsable_id` set. It keeps its own record, document, history and personal link;
  its phone is the responsable's phone, so the household's messages go to one place.
- **Parentesco**: relation of the familiar to the responsable: `hijo` (hijo/a), `pareja`, `padre` (madre/padre), `otro`.
- **Consentimiento por**: who authorized the processing of the patient's data. Null = the patient themselves; otherwise the
  responsable's id (as legal representative of a minor, or with the adult's permission).

## 4. Scope

### In scope

**R1. Add a family member from "Mis citas"** (F-01, F-04)
- "Mis citas" gets a **"Mi familia"** section with an **"Agregar a alguien de mi familia"** button.
- Form: documento, nombres, apellidos, fecha de nacimiento, parentesco, and one consent checkbox:
  *"Autorizo a {negocio} a tratar los datos personales de esta persona para gestionar sus citas. Si es menor de edad, declaro
  que soy su madre, padre o representante legal; si es mayor de edad, que me autorizó a agendar por ella."*
- No phone field: the familiar inherits the responsable's phone. The new patient stores `responsable_id`, `parentesco`,
  `fecha_nacimiento`, `consentimiento_en`, `consentimiento_version` and `consentimiento_por = responsable`.
- Linking a person who is already a patient:
  - same document **and** same phone as the responsable, not managed by anyone and not a responsable themselves → linked (the
    responsable could already open that person's link with document + phone, so nothing new is exposed);
  - already in this family → friendly message, nothing changes;
  - anything else (different phone, managed by someone else, has their own familiares) → nothing is revealed; the same
    "the clinic will contact you" outcome as `/agendar`, and a `solicitud_contacto` row for reception.
- A familiar cannot add people ("Tu familia la gestiona {nombre}"). Maximum 10 familiares per responsable.
- Validation: names and document required, birth date required and not in the future, parentesco from the list, consent
  required.

**R2. One view for the household** (F-02)
- "Mis citas" lists the responsable's and every familiar's upcoming appointments, each labelled with the person's first name,
  ordered by date. "Cambiar fecha" and "Cancelar" work for every appointment in the household; any appointment outside the
  household is a 404, exactly as today.
- "Mi familia" lists the familiares with parentesco and a "menor de edad" tag when applicable.

**R3. "¿Para quién es la cita?"** (F-01)
- When the responsable has familiares, the slot picker shows a **"¿Para quién es la cita?"** selector (default: the responsable,
  or the person chosen from "Mi familia"). The appointment is booked on the chosen familiar's record; messages are sent to
  that record (so they greet the familiar by name) and land on the shared phone.
- The success notice names the person: *"La cita de Mateo quedó agendada…"*.

**R4. Back-to-back booking** (F-05)
- After booking, the notice offers one button per other household member: **"Agendar a {nombre} justo después"**. It opens the
  picker for that person on the same day and service, on the hour page where the first slot at or after the end of the
  previous appointment is, with that slot preselected. One click on "Confirmar cita" books it.

**R5. A familiar's own link** (privacy)
- A familiar who opens their own link sees only their own appointments and the note *"{responsable} también ve y gestiona
  tus citas."*. An adult familiar has **"Dejar de compartir"**, which clears `responsable_id` (with confirmation). A minor
  does not get this button (their representative manages them; reception can unlink in the panel later, see §5).

**R6. Guidance on the public entry** (F-04)
- `/agendar` (ES and EN) shows: *"¿Vas a agendar para tus hijos u otros familiares? Regístrate tú primero y agrégalos desde
  Mis citas."*

**R7. Panel: family in the patient record** (F-06)
- `GET /api/v1/pacientes/{id}` returns `familia`: the responsable (id, name, parentesco of this patient) and the familiares
  (id, name, parentesco, menor). The patient page shows it under the name, with links to each person's record.
- `docs/openapi.json` and the panel types are regenerated.

**R8. Privacy hooks**
- Anonymizing a patient unlinks it from its responsable and unlinks its familiares (they keep their records).
- Exporting a patient includes `responsable_id`, `parentesco` and `consentimiento_por` (they are columns of `paciente`).

**R9. One notification per event for the household phone**

A household shares one phone, so per-appointment messages would multiply: three back-to-back appointments meant three
booking confirmations, three 48 h reminders and three 24 h reminders. Household = the responsable and their familiares
(`familia.hogar`). A patient without family is a household of one and keeps the existing messages unchanged.
- **Booking confirmation.** A household booking does not send a message right away. It marks the appointment
  `aviso_pendiente` and schedules (or pushes back) one `avisar_agendadas` task `agrupar_avisos_min` minutes later (default 5).
  When the task runs, one message `cita_agendada_hogar` goes to the responsable, with one line per appointment ("• Mateo:
  martes 19 de noviembre a las 9:30 a. m., con Dra. X"). If it is only the responsable's own appointment, the usual
  `cita_agendada` is sent. Rescheduling goes through the same path. Emails keep going one per appointment to each
  person's own address.
- **Reminders.** The first reminder task of the day that fires gathers all live household appointments that day that have
  not had that reminder. It sends one message and marks each appointment (`datos_origen.recordatorio_<h>h` = its start
  time), so the other tasks skip. At 48 h: `recordatorio_48h_hogar` lists the appointments still `programada`. At 24 h:
  `recordatorio_24h_hogar`, or `segundo_intento_hogar` with the unconfirmed ones flagged "(sin confirmar)".
- **Household buttons.** "Sí, asistiremos" (`confh:si:<ids>`) confirms every listed appointment still in the household.
  "Cambiar o cancelar" (`confh:cambiar:<ids>`) replies with the responsable's link. There is no one-tap cancel for
  several appointments: cancellation is per appointment from the link. Ids outside the household are ignored.
- **Follow-up.** At most one follow-up message (`cancelacion_recibida`, `seguimiento_*`, `continuidad_tratamiento`) per
  household every 20 h. An attempt held back this way is not counted as an attempt: it is removed and rescheduled for the
  end of the 20 h wait (or the next send window), so the household gets them one at a time.
- **Advance offers.** At most one pending offer per household, and the weekly cap counts the household, not the person.
- **Replies and opt-out.** A phone shared by a single household resolves to the responsable in the webhook, so household
  buttons work. If the number ended up in two households (an adult stopped sharing and kept it), the reply goes to the
  household that got the latest message in the last 7 days; with none, it stays `ambiguo`. A button reply is recorded on
  the member who received the original message. "BAJA" from the household phone opts out every member.
- **Timing of "no confirmada".** A grouped 24 h reminder lists all the day's appointments, but each one becomes
  `no_confirmada` only at its own 24 h mark, without another message.
- **Leaving during the wait.** If someone stops sharing before the grouped booking notice goes out, their appointment gets
  its own `cita_agendada`.
- New templates fall back to the product catalog when a business's `plantilla` table predates them.

### Out of scope

- Free-text replies from a shared phone and phones shared by unrelated patients (F-03): wait for the real WhatsApp
  channel PRD (§7).
- Staff creating or editing family links in the panel (read-only for now).
- English copy on the interior patient pages ("Mis citas", picker): tracked by WP3 of `docs/prd-sitio-publico.md`.
- Booking several people in a single submit (R4 is the deliberate simpler version).

## 5. Data model

Migration `012_familia.sql` (with `.down.sql`):

```sql
alter table paciente add column responsable_id bigint references paciente(id) on delete set null;
alter table paciente add column parentesco text check (parentesco in ('hijo','pareja','padre','otro'));
alter table paciente add column consentimiento_por bigint references paciente(id) on delete set null;
alter table paciente add constraint paciente_responsable_no_propio check (responsable_id <> id);
create index paciente_responsable on paciente(negocio_id, responsable_id) where responsable_id is not null;
```

Isolation between businesses is unchanged: `paciente` already has forced RLS by `negocio_id`, so a lookup of a responsable or
familiar can only see rows of the active business.

## 6. Acceptance criteria (each one is a test in `tests/test_familia.py` or an updated existing test)

1. A responsable adds a minor familiar: the new patient has the responsable's phone, `responsable_id`, `parentesco`,
   birth date, consent timestamp/version and `consentimiento_por`; missing consent, missing birth date, future birth date or
   invalid parentesco are rejected with a clear message and nothing is created.
2. "Mis citas" of the responsable shows appointments of the whole household with the person's name; another patient's
   appointment never appears.
3. Booking with `para=<familiar>` creates the appointment on the familiar's record, and the grouped confirmation reaches the
   responsable with the familiar's name a few minutes later; `para=<someone outside the household>` returns 404 and books nothing.
4. Change and cancel of a familiar's appointment work from the responsable's link; the same routes with an appointment outside
   the household return 404.
5. Linking an existing patient with the same phone works; with a different phone nothing is revealed and a
   `solicitud_contacto` row is created; a familiar cannot add people; an adult familiar can stop sharing; a minor cannot.
6. The back-to-back link preselects the first free slot at or after the end of the previous appointment.
7. The panel API record returns `familia` for both sides of the relation; anonymizing unlinks.
8. R9 (`tests/test_avisos_hogar.py`): back-to-back household appointments produce one 48 h reminder, one 24 h reminder and
   one booking confirmation; one tap confirms all of them and never touches another household's appointment; "Cambiar o
   cancelar" cancels nothing; at most one follow-up per household per day; one pending offer per household; a patient
   without family gets the usual immediate messages.
9. Migrations go up, down and up again (`tests/test_aislamiento.py`); `make test` green; `ruff` clean; panel typecheck, lint and
   tests green.

## 7. Deferred: shared phone and WhatsApp (F-03)

With families the shared phone becomes normal. R9 already covers the common case: a phone shared by one household resolves
to its responsable, and automatic messages for that household are grouped and addressed to them. What remains is free-text
replies and phones shared by unrelated patients, which stay `ambiguo`. Expected direction for that PRD: resolve a reply by the outgoing message it answers (button payloads carry the
appointment id, or the provider's context id), and when a free-text reply is still ambiguous, ask "¿Para quién?" with one
button per household member. Until then the simulator (one chat per patient) does not show the problem, and reception keeps
the "No confirmadas" tray as the fallback.
