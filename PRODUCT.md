# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Pacientes locales (ES):** personas buscando odontología estética y cuidado dental en Blissens (Medellín / Colombia) que quieren conocer el enfoque de la clínica, ver casos reales y agendar, cambiar o cancelar citas para sí mismas o su hogar desde el celular en pocos toques.
- **Pacientes internacionales / turismo dental (EN):** visitantes en el exterior que llegan a `/en` para solicitar evaluación virtual o experiencias de viaje dental.
- **Auxiliar de recepción:** opera el panel diario (`/panel`) para gestionar agenda de todos los especialistas, confirmar citas por teléfono, atender bandejas de pendientes y solicitudes web, y registrar pacientes.
- **Especialistas clínicos:** revisan su agenda, horario y bloqueos desde escritorio o celular en el panel.
- **Gerencia / administración:** revisa indicadores de asistencia, cancelaciones, ingresos perdidos, metas y gestiona usuarios y negocios.

## Product Purpose

Unificar en un solo sistema web la presencia pública de **Blissens** con su motor real de agendamiento, seguimiento automatizado y operación clínica diaria (**Estud-IA**). El éxito significa que un paciente pueda pasar desde la landing hasta confirmar su cita sin fricción ni saltos visuales, y que el equipo opere la clínica desde el panel con claridad, velocidad y cero pérdida de citas.

## Positioning

A diferencia de sitios de clínica desconectados de un calendario externo genérico, Blissens integra en un mismo origen FastAPI su sitio editorial bilingüe, un agendamiento de un toque con gestión familiar/hogar, automatización de recordatorios y recuperación de cupos, y un panel operativo multi-negocio con aislamiento estricto por filas (RLS).

## Operating Context

- **Superficies activas:** Landing pública (`/` en ES, `/en` en EN), flujo de agendamiento y citas del hogar (`/agendar`, `/p/{token}*`), panel operativo SPA (`/panel/*`), y simulador local de WhatsApp/correo (`/simulador`, desactivado en producción).
- **Flujo actual de identificación del paciente:** formulario por documento y celular (`/agendar`) que otorga acceso al enlace del paciente (`/p/{token}`) sin requerir contraseña.
- **Flujo futuro (fuera del alcance de este rediseño):** unificación de credenciales en un solo inicio de sesión con detección automática de rol (paciente / auxiliar / especialista / administrador) planificada como iniciativa posterior.

## Capabilities and Constraints

- **Cero recursos de terceros en sitio público y paciente:** `tests/test_sitio.py` y `tests/test_web.py` exigen que fuentes, scripts (`htmx.min.js`, `sitio.js`) e imágenes se sirvan 100 % auto-hospedados desde `/static/`.
- **Landing sin conexión a base de datos:** `GET /` y `GET /en` no pueden invocar `db.connect` (`tests/test_sitio.py`).
- **Alcance SEO y enlaces de equipo:** `canonical`/`hreflang` y `href="/panel"` pertenecen a `/` y `/en` y no deben inyectarse en `/agendar` (`tests/test_sitio.py`).
- **Idiomas:** Landing bilingüe ES (`/`) y EN (`/en`); agendamiento (`/agendar`, `/p/*`) y panel (`/panel/*`) operan en español.
- **Privacidad estricta:** el repositorio es público; nunca se versionan datos reales de pacientes ni se persisten datos sensibles en el navegador (`panel/src/main.tsx`).
- **Multi-negocio con RLS:** cada petición autenticada en backend opera bajo `estudia_app` con `app.negocio_id` fijado por sesión o ruta.

## Brand Commitments

- **Marca principal:** Blissens (odontología estética de precisión y calidez humana), sobre la plataforma operativa Estud-IA.
- **Activos oficiales auto-hospedados:** logotipo `estudia/web/static/sitio/logo-1024x110.png`, textura iridiscente `Bg-1.png`, tipografías locales `inter-var.woff2` y `cardo-400.woff2`, fotografía real del equipo y servicios en `estudia/web/static/sitio/`.
- **Voz:** editorial, serena, precisa y cercana en el sitio público (ES/EN); directa y sin tecnicismos en el flujo del paciente; operativa, concisa y accionable en el panel.
- **Compromiso de fidelidad:** cualquier rediseño debe conservar fielmente la identidad y paleta de Blissens, evitando estéticas genéricas.

## Evidence on Hand

- Activos de marca y fotografía en `estudia/web/static/sitio/` (`logo-1024x110.png`, `Bg-1.png`, `New-Team.jpg`, `BLISSENSE-1.png`, `Services.png`, `Primium-460x460.png`, `Standerd-460x460.png`, `Basic-460x460.png`, `image-8.png`, `image-9.png`, `image-10.png`).
- Copy editorial ES/EN en `estudia/web/copia.py`.
- PRDs de referencia en `docs/prd-sitio-publico.md`, `docs/prd-panel-auxiliar.md`, `docs/prd-familia.md`, `docs/prd-indicadores.md` y `docs/prd-indicadores-fase2.md`.
- Glosario de dominio en `GLOSSARY.md`.
- **Ausencias confirmadas (no fabricar):** las imágenes `caso-{1,2,3}-{antes,despues}.svg` son placeholders temporales hasta contar con fotografías clínicas autorizadas; no inventar testimonios, premios ni cifras clínicas no respaldadas por el código.

## Product Principles

1. **Continuidad de marca sin saltos:** pasar de la landing al agendamiento y al panel debe sentirse parte del mismo estudio clínico, adaptando densidad (editorial en landing, precisión en operación) sin romper la identidad.
2. **Celular primero para el paciente, velocidad de escaneo para el equipo:** el paciente resuelve su cita en pocos toques desde el móvil; la auxiliar y los especialistas ven lo urgente primero sin ruido visual.
3. **Autosuficiencia técnica:** sin CDNs externos, sin fuentes remotas y manteniendo la landing libre de consultas a base de datos.
4. **Privacidad y claridad por defecto:** textos honestos, consentimientos explícitos y cero exposición de datos personales innecesarios.
