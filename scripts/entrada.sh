#!/bin/sh
# Arranque de la imagen: `web` migra y sirve; `trabajador` ejecuta el ciclo de tareas (mismo ciclo que /tick).
set -eu
case "${1:-web}" in
  web)
    python -m estudia.migrate subir
    exec uvicorn estudia.web.app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="${TRUSTED_PROXIES:-127.0.0.1}"
    ;;
  trabajador)
    exec python -m estudia.worker
    ;;
  *)
    exec "$@"
    ;;
esac
