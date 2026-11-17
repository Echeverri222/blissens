# Estud-IA · Gestión inteligente de citas (Blissens Odontología)

Sistema de gestión de citas diseñado desde el paciente: agendamiento autoservicio, confirmación explícita,
cancelación con motivo y seguimiento, llenado de cupos por ofertas de adelanto, recuperación de tratamientos a
medias e indicadores. Todo corre **en local, sin cuentas externas y con datos ficticios**; WhatsApp se simula.

Especificación: [issue #1 (PRD)](https://github.com/Echeverri222/blissens/issues/1) · Requerimientos: `requirements.md` · Stack: `stack.md`.

## Requisitos

Docker (PostgreSQL), Python 3.12+ y [`uv`](https://docs.astral.sh/uv/). Nada más. Tras instalar dependencias el
sistema funciona sin conexión a internet (CSS y scripts se sirven desde `estudia/web/static`).

## Comandos

| Comando | Qué hace |
|---|---|
| `make setup` | Instala dependencias, crea `.env`, levanta PostgreSQL, aplica migraciones y carga datos ficticios |
| `make dev` | Arranca aplicación web, trabajador de tareas y panel |
| `make test` | Corre la suite contra una base de datos de prueba (`estudia_test`) |
| `make seed` | Recarga los datos ficticios (misma semilla, mismos datos) y crea los usuarios de demostración |
| `make usuario ARGS="..."` | Gestiona usuarios: `crear <usuario> --nombre N --rol auxiliar\|especialista [--profesional ID]`, `listar`, `desactivar <usuario>`, `activar <usuario>`, `clave <usuario>` |
| `make api-esquema` | Regenera `docs/openapi.json` (una prueba falla si la API cambia sin regenerarlo) |
| `make reset` | Borra la base local y la reconstruye desde cero |
| `make importar` | Importa los Excel reales desde `datos_reales/` (ignorada por git). No crea usuarios: con datos reales se crean con `make usuario` |
| `make cierre` | Ejecuta el cierre de indicadores a demanda |

Un clon recién hecho funciona con `make setup && make dev`.

## Direcciones locales

| Dirección | Qué es |
|---|---|
| http://localhost:8000/agendar | Entrada pública de agendamiento (paciente) |
| http://localhost:8000/p/&lt;token&gt; | "Mis citas" (enlace personal firmado; llega por el simulador) |
| http://localhost:8000/simulador | Simulador de WhatsApp y control del reloj |
| http://127.0.0.1:8501 | Panel de la auxiliar e indicadores |
| http://localhost:8000/docs | Documentación interactiva de la API. Inicia sesión desde `POST /api/v1/sesion`: la cookie queda puesta y el resto de endpoints funcionan |
| http://localhost:8000/api/v1/... | API JSON con inicio de sesión y roles (PRD #2) |

Usuarios de demostración (solo existen con datos ficticios; `make seed` los imprime): `auxiliar`,
`especialista1` y `especialista2`, todos con la contraseña `demo-blissens`.

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
7. En el panel (*Hoy*) marca citas como atendida / no asistió.
8. *Bandejas → Pacientes en riesgo*: tratamientos activos sin cita futura.
9. *Indicadores → Ejecutar cierre ahora*.
10. *Paciente*: bitácora e historial; **Revertir** un cambio.

Escribe `BAJA` en el simulador para probar la baja de mensajes automáticos.

## Arquitectura

Un solo paquete Python (`estudia/`) compartido por tres procesos y una base PostgreSQL:

```
Paciente ──► /agendar y /p/<token> ─┐
Simulador de WhatsApp ◄─► canal ────┤
                                    ├─► dominio ◄──► PostgreSQL
Panel (Streamlit) ──────────────────┤                  ▲
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
- Zona horaria `America/Bogota`. La API exige sesión; el panel de Streamlit, el simulador y `/tick` siguen sin
  autenticación (brecha conocida y temporal, el panel solo escucha en `127.0.0.1`): deben cerrarse antes de cualquier despliegue.

## Privacidad y datos reales

El repositorio es público y el reto prohíbe divulgar datos de pacientes. **Ningún dato real se versiona**:
los Excel reales van en `datos_reales/` (ignorada por git) y se cargan con `make importar`, que no dispara
mensajes ni casos de seguimiento por hechos pasados. Pruebas, capturas y demos usan solo datos ficticios.
Los mensajes contienen lo mínimo (nombre de pila, fecha, hora, profesional y dirección), nunca diagnóstico.

## Fuera de alcance

WhatsApp real, despliegue en la nube, front nuevo (siguiente PRD), pantalla de administración de usuarios, integración con el software de la clínica,
requerimientos *Should/Could* y multisede (ver PRD §8).
