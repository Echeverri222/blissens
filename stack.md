# Stack recomendado para el MVP — Estud-IA (Blissens Odontología / Eme y Eme Group)

> Estado: **propuesta v0.1** · Complementa `requirements.md`.
> El repositorio aún no tiene código: este documento recomienda qué usar para construir el MVP.

---

## 1. Qué condiciona la elección

- **Prototipo académico de nivel intermedio:** tiene que poder construirlo y mantenerlo un equipo pequeño, en poco tiempo y gratis.
- **Datos sensibles:** el reto prohíbe divulgar datos reales y pide revisar cualquier demo pública. Los Excel traen cédula, teléfono, email y fecha de nacimiento.
- **Los datos de partida son Excel:** agenda, estados, aranceles y guiones.
- **Hay tres requisitos técnicamente difíciles:**
  - Mensajes de WhatsApp con botones (RNF-01).
  - Temporizadores: recordatorios, seguimiento y tiempo para responder una oferta (RF-08, RF-16, RF-23).
  - Que un cupo libre no se asigne a dos pacientes a la vez (RF-22).

## 2. Herramientas recomendadas (todas en Python, todas gratis)

| Para qué | Herramienta | Por qué |
|---|---|---|
| **Base de datos** | **PostgreSQL en Supabase** (plan gratis) | Reemplaza el Excel como fuente única (RD-01). Su panel parece una hoja de cálculo, así que cualquiera del equipo puede revisar los datos. Además permite que la propia base impida dos citas en el mismo cupo (RF-22) y trae `pg_cron` para tareas programadas |
| **Lógica central** | **FastAPI** | Recibe las respuestas de WhatsApp y concentra las reglas: confirmar, cancelar, ofrecer el cupo libre a otro paciente, pasar al siguiente si no responde. Es simple, rápido y documenta su API sola |
| **Página del paciente** (tipo Calendly) | **FastAPI + plantillas Jinja2 + HTMX** y un CSS ligero (Pico o Tailwind) | Páginas generadas en el servidor, pensadas para celular y sin app que instalar (RNF-02). El enlace lleva un token firmado (`itsdangerous`), así que el paciente no necesita cuenta (RF-04) |
| **WhatsApp** | **WhatsApp Cloud API de Meta con número de prueba** | Gratis y oficial. Permite botones interactivos (hasta 3: *Sí / No / Reprogramar*), justo lo que piden RF-09 y RF-19. Limitación: solo envía a 5 números verificados, que para una demo sobra |
| **Temporizadores** | **`pg_cron` de Supabase** llamando un endpoint `/tick` cada pocos minutos | Las tareas pendientes se guardan como filas en la base y no en memoria. Si el servidor se reinicia o se duerme, nada se pierde (RNF-06) |
| **Panel de la auxiliar y de los especialistas** | **React + TypeScript + Vite**, Tailwind, TanStack Query y Recharts | Aplicación de navegador servida por FastAPI en `/panel`; solo consume la API `/api/v1`. Cubre la agenda, las bandejas y pacientes en riesgo (RF-41) y los indicadores RF-30 a RF-34. Sustituye a Streamlit |
| **Cargar los Excel** | **pandas + openpyxl** | Un script lee los Excel, limpia y normaliza los estados y los inserta en Postgres. Ese mismo script sirve para el cierre periódico (RF-37) |
| **Datos de demo** | **Faker** (configurado para Colombia, `es_CO`) | Crea pacientes ficticios con la misma estructura que los reales. Los datos reales solo se usan en local y nunca se suben a GitHub ni se muestran en demos |
| **Despliegue** | **Render** (plan gratis) para FastAPI | Ojo: el servidor gratis se duerme tras 15 min sin uso. Meta reintenta los mensajes que no llegan, pero antes de una demo conviene "despertarlo" |
| **Desarrollo** | Git/GitHub, VS Code, `uv`, **ngrok**, **pytest** | ngrok expone tu máquina para que Meta te envíe mensajes mientras desarrollas. Con pytest se prueba la parte más delicada: la cadena de ofertas y los tiempos de espera |

## 3. Cómo se conectan

```
Paciente ──WhatsApp──► Meta Cloud API ──webhook──► FastAPI ◄──► Supabase (Postgres)
   └──── enlace ─────► página de agendamiento (FastAPI+HTMX)        ▲      │
                                                                    │   pg_cron → /tick
Auxiliar / especialistas ─► Panel React (/panel) ─► API ────────────┘
```

## 4. Cómo resolver lo difícil con estas herramientas

- **Que un cupo no se asigne dos veces (RF-22):** se le pide a la base que rechace dos citas del mismo especialista en horarios que se crucen. Postgres lo hace con una restricción de exclusión sobre el rango de horas. Para las ofertas, un índice único garantiza que cada cupo tenga como máximo una oferta pendiente a la vez. Así la regla la hace cumplir la base y no depende de que el código no tenga errores.
- **Tiempo para responder una oferta (RF-23):** cada oferta guarda su hora de vencimiento. En cada `/tick`, las ofertas vencidas se marcan y el cupo se ofrece al siguiente candidato.
- **Confirmación explícita (RF-09):** si el paciente no responde, la cita queda como "no confirmada". Esa marca dispara la alerta a la auxiliar y un segundo intento (RF-10).
- **Trazabilidad (RD-02, RNF-07):** una tabla guarda cada cambio de estado de una cita, quién o qué lo hizo y cuándo. Esa tabla alimenta tanto los indicadores como la opción de revertir un cambio.

## 5. Lo que no recomiendo para el núcleo

- **n8n, Make o Zapier como base del sistema:** sirven para automatizar rápido, pero la cadena de ofertas con tiempos y bloqueos se vuelve frágil y difícil de probar. Además es un reto de programación.
- **Integrarse con el software actual de la clínica:** por ahora no se sabe qué capacidad de integración tiene (pregunta abierta 1 de `requirements.md`). Para el MVP basta con importar los Excel.
- **IA:** déjala como algo opcional. Un caso útil y barato sería clasificar el texto libre de los motivos de cancelación marcados como "otro", o personalizar los mensajes de recuperación a partir de los guiones. No es necesaria para que el MVP funcione.

## 6. Alternativa si el equipo maneja mejor JavaScript

El equivalente es **Next.js + Supabase + Vercel** (con sus tareas programadas) en una sola aplicación. La arquitectura sería la misma.
