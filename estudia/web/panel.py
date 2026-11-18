"""Sirve el panel (aplicación de una sola página) en /panel. Mismo origen que la API: la cookie de sesión funciona sin CORS."""
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from .. import settings

DIST = settings.ROOT / "panel" / "dist"
router = APIRouter(include_in_schema=False)

SIN_CONSTRUIR = """<!doctype html><html lang="es"><meta charset="utf-8"><title>Panel sin construir</title>
<body style="font-family:system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem;line-height:1.5">
<h1>El panel aún no está construido</h1>
<p>Ejecuta <code>make panel</code> (una vez) o <code>make dev</code> (reconstruye al guardar) y recarga esta página.</p>
</body></html>"""


def _pagina():
    index = DIST / "index.html"
    if not index.is_file():
        return HTMLResponse(SIN_CONSTRUIR, status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


@router.get("/panel")
@router.get("/panel/{ruta:path}")
def panel(ruta: str = ""):
    """Un archivo construido si existe; cualquier otra ruta devuelve la página principal (rutas internas del panel)."""
    if ruta:
        archivo = (DIST / ruta).resolve()
        if archivo.is_file() and DIST.resolve() in archivo.parents:
            inmutable = ruta.startswith("assets/")
            return FileResponse(archivo, headers={"Cache-Control": "public, max-age=31536000, immutable"} if inmutable
                                else {"Cache-Control": "no-cache"})
    return _pagina()
