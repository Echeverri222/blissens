# Estud-IA · Gestión inteligente de citas (Blissens Odontología)

Sistema de gestión de citas diseñado desde el paciente: agendamiento autoservicio, confirmación explícita,
cancelación con motivo y seguimiento, llenado de cupos por ofertas de adelanto, recuperación de tratamientos a
medias e indicadores. Todo corre **en local, sin cuentas externas y con datos ficticios**; WhatsApp se simula.

Especificación: [issue #1 (PRD)](https://github.com/Echeverri222/blissens/issues/1) · Requerimientos: `requirements.md` · Stack: `stack.md`.

## Requisitos

Docker (PostgreSQL), Python 3.12+, [`uv`](https://docs.astral.sh/uv/) y Node 20+ (para el panel). Nada más. Tras instalar
dependencias el sistema funciona sin conexión a internet: el panel no hace ninguna petición a terceros (la tipografía va empaquetada).

## Comandos

| Comando | Qué hace |
|---|---|
| `make setup` | Instala dependencias (Python y panel), construye el panel, crea `.env`, levanta PostgreSQL, aplica migraciones y carga datos ficticios |
| `make dev` | Arranca la aplicación web (con el panel en `/panel`), el trabajador de tareas y la reconstrucción del panel al guardar |
| `make panel` | Genera los tipos desde `docs/openapi.json` y construye el panel (`panel/dist`) |
| `make test` | Suite de Python contra una base de prueba (`estudia_test`) y, del panel, tipos, lint y pruebas |
| `make e2e` | Recorridos reales en el navegador (Playwright) contra una base propia (`estudia_e2e`) |
| `make seed` | Recarga los datos ficticios (misma semilla, mismos datos) y crea los usuarios de demostración |
| `make usuario ARGS="..."` | Gestiona usuarios: `crear <usuario> --nombre N --rol auxiliar\|especialista [--profesional ID]`, `listar`, `desactivar <usuario>`, `activar <usuario>`, `clave <usuario>` |
| `make api-esquema` | Regenera `docs/openapi.json` (una prueba falla si la API cambia sin regenerarlo) |
| `make reset` | Borra la base local y la reconstruye desde cero |
| `make importar` | Importa los Excel reales desde `datos_reales/` (ignorada por git). No crea usuarios: con datos reales se crean con `make usuario` |
| `make respaldo` / `make restaurar-ensayo` | Copia de la base en `respaldos/` (ignorada por git) y restauración en una base temporal con las verificaciones del migrador |
| `make migrar ARGS="estado\|subir\|bajar\|verificar"` | Migrador con reversa |
| `make negocio ARGS="..."` | `crear`, `listar`, `activar`, `desactivar`, `config`, `depurar`, `exportar`, `exportar-paciente`, `anonimizar-paciente` |
| `make ensayo-supabase` | Ensayo contra la imagen de PostgreSQL de Supabase (migra, suite con el rol de aplicación, API de datos cerrada) |
| `make lint` | Ruff y lint del panel |
| `make cierre` | Ejecuta el cierre de indicadores a demanda |

Un clon recién hecho funciona con `make setup && make dev`.

## Direcciones locales

| Dirección | Qué es |
|---|---|
| http://localhost:8000/agendar | Entrada pública de agendamiento (paciente) |
| http://localhost:8000/p/&lt;token&gt; | "Mis citas" (enlace personal firmado; llega por el simulador) |
| http://localhost:8000/simulador | Simulador de WhatsApp y control del reloj |
| http://localhost:8000/panel | Panel de la auxiliar y de los especialistas (inicio de sesión con usuario y contraseña) |
| http://localhost:8000/docs | Documentación interactiva de la API. Inicia sesión desde `POST /api/v1/sesion`: la cookie queda puesta y el resto de endpoints funcionan |
| http://localhost:8000/api/v1/... | API JSON con inicio de sesión y roles (PRD #2) |

Usuarios de demostración (solo existen con datos ficticios; `make seed` los imprime): `auxiliar`,
`especialista1` y `especialista2`, todos con la contraseña `demo-blissens`. El panel muestra a cada rol solo lo suyo:
el especialista, *Mi agenda* y *Mi horario*; la auxiliar, *Agenda*, *Bandejas*, *Pacientes*, *Indicadores* y *Sistema*.

### Probar la API con `curl`

```bash
curl -c cookies -H 'Content-Type: application/json' -d '{"usuario":"especialista1","clave":"demo-blissens"}' localhost:8000/api/v1/sesion
curl -b cookies "localhost:8000/api/v1/agenda?desde=2026-11-16&hasta=2026-11-22"
curl -b cookies localhost:8000/api/v1/bandejas        # 403: es de la auxiliar
```

## Recorrido de demostración

El PRD §3.4 describe diez pasos. Resumen:

1. En `/agendar` registra un paciente nuevo y agenda. El mensaje de confirmación aparece en el simulador.
2. En el simulador elige al paciente y usa **Saltar a 48 h antes**: llega el recordatorio con tres botones.
3. Con otra cita sin responder, **Saltar a 24 h antes**: pasa a *no confirmada* y sale el segundo intento.
4. Cancela desde el enlace del paciente eligiendo un motivo; se ofrecen espacios de inmediato.
5. Mira el simulador de otros pacientes con cita posterior: reciben la oferta de adelanto. Avanza el reloj para
   dejarla vencer, o acéptala: el espacio que deja dispara una oferta en cadena.
6. **+3 días**: primer seguimiento de reasignación. Agenda desde el enlace y el caso se cierra.
7. En el panel, como especialista (*Mi agenda*), abre una cita ya iniciada y márcala atendida / no asistió.
8. Como auxiliar, *Bandejas → En riesgo*: tratamientos activos sin cita futura.
9. *Indicadores → Ejecutar cierre ahora*.
10. *Pacientes*: bitácora e historial; **Revertir** un cambio.

Escribe `BAJA` en el simulador para probar la baja de mensajes automáticos.

## Arquitectura

Un solo paquete Python (`estudia/`) compartido por dos procesos y una base PostgreSQL; el panel (`panel/`, React + TypeScript) es una aplicación de navegador que FastAPI sirve en `/panel` y que solo habla con la API:

```
Paciente ──► /agendar y /p/<token> ─┐
Simulador de WhatsApp ◄─► canal ────┤
                                    ├─► dominio ◄──► PostgreSQL
Panel (/panel, React) ─► API /api/v1 ─┤                  ▲
Trabajador (ciclo de tareas) ───────┘──────────────────┘
```

| Módulo | Responsabilidad |
|---|---|
| `agenda` | Espacios disponibles, agendar, cancelar, cambiar fecha, desenlace, revertir |
| `lifecycle` | Máquina de estados e historial de cada cita |
| `messaging` | Plantillas, envío, recepción, bitácora, ventana de envío, baja (puerto de canal simulado) |
| `confirmations` | Recordatorios 48 h / 24 h y confirmación explícita |
| `followup` | Casos de seguimiento, intentos y cadencia |
| `slots` | Cupos liberados, candidatos, ofertas en cadena |
| `recovery` | Detección diaria de tratamientos a medias |
| `indicators` | Hechos diarios (cierre) y consultas del tablero |
| `tasks`, `clock`, `jobs` | Tareas programadas durables, reloj único, procesos diarios |
| `data` | Datos ficticios (Faker `es_CO`) e importación de Excel |
| `usuarios`, `permisos` | Usuarios, contraseñas (`scrypt`), sesiones por cookie y una sola función de permisos por rol |
| `horario` | Horario semanal y bloqueos (rechazan si hay citas vivas; anulan cupos y ofertas cruzados) |
| `pacientes` | Alta de pacientes con consentimiento |
| `api/` | Rutas `/api/v1` delgadas, modelos de entrada/salida y traducción de errores; el esquema OpenAPI es el contrato |

Decisiones clave:

- **Las reglas críticas las hace cumplir la base de datos**: una restricción de exclusión impide dos citas vivas
  del mismo profesional que se crucen, y un índice único permite una sola oferta pendiente por cupo.
- **Todo efecto diferido es una fila** (tarea programada o mensaje). Ningún proceso guarda temporizadores en memoria.
- **Reloj único**: ninguna regla usa la hora del sistema. En modo demo el desfase vive en la base y lo comparten los tres procesos.
- **Cambiar la fecha no edita la cita**: la cierra como `reprogramada` y crea una nueva enlazada.
- **Sesiones en la base** (solo se guarda la huella del identificador) y con **hora real**: es la única excepción
  al reloj único, para que adelantar el reloj de la demo no cierre la sesión de nadie.
- **Un bloqueo nunca cancela citas**: si el rango tiene citas vivas se rechaza (409) y se listan para que recepción las mueva.
- Zona horaria `America/Bogota`. La API y el panel exigen sesión; el simulador y `/tick` solo existen en `local`/`demo` (`/tick` exige `X-Tick-Secreto` fuera de local).
- **Un negocio hoy, N mañana (PRD #4)**: todas las tablas llevan `negocio_id` con RLS forzada; el código de dominio no lo menciona (el negocio activo es un ajuste de la conexión). La aplicación usa el rol `estudia_app` (sin privilegios) y las migraciones/CLI el rol administrador (`DATABASE_URL_ADMIN`). Migraciones propias con reversa: `make migrar ARGS="estado|subir|bajar|verificar"`. Nuevo negocio: `make negocio ARGS="crear ..."`. Fuera de `local` la aplicación se niega a arrancar con configuración insegura. Administración (`/api/v1/admin/usuarios` y sección *Administración* del panel, solo para administradores): alta con contraseña temporal que se muestra una vez y debe cambiarse al ingresar, quitar/devolver acceso, cambiar permisos y no dejar el negocio sin administrador. Canal de mensajes con puerto y webhook (`POST /canales/{tipo}/webhook`); registro de accesos a datos de pacientes, retención y anonimizado; registro JSON por petición sin datos personales. Despliegue preparado y no realizado: `Dockerfile`, `render.yaml` (Render + Supabase, solo datos ficticios) y CI en `.github/workflows/ci.yml`. Decisiones en `docs/adr/` y vocabulario en `GLOSSARY.md`.
- **El panel no calcula nada de negocio**: qué botones muestra cada cita lo decide la API (`acciones`), la hora "de ahora" es la del sistema y no la del navegador, y los mensajes de error son los de la API.

## Privacidad y datos reales

El repositorio es público y el reto prohíbe divulgar datos de pacientes. **Ningún dato real se versiona**:
los Excel reales van en `datos_reales/` (ignorada por git) y se cargan con `make importar`, que no dispara
mensajes ni casos de seguimiento por hechos pasados. Pruebas, capturas y demos usan solo datos ficticios.
Los mensajes contienen lo mínimo (nombre de pila, fecha, hora, profesional y dirección), nunca diagnóstico.

## Fuera de alcance

WhatsApp real, despliegue en la nube, integración con el software de la clínica,
requerimientos *Should/Could* y multisede (ver PRD §8).
