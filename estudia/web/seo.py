"""SEO técnico del sitio público: robots.txt, sitemap.xml bilingüe, llms.txt y JSON-LD Schema.org."""
from xml.sax.saxutils import escape, quoteattr

from . import copia

_DISALLOW = (
    "/panel",
    "/api/",
    "/p/",
    "/simulador",
    "/correo/",
    "/sitio/",
    "/canales/",
    "/salud",
    "/tick",
)

_STREET_ADDRESS = (
    "Carrera 25 # 1A Sur 45, C.C. El Tesoro, Torre Médica 2, consultorios 1156 y 1157, El Poblado"
)


def _base(base_url: str) -> str:
    return base_url.rstrip("/")


def robots_txt(base_url: str) -> str:
    """Política de rastreo: permite la landing y estáticos, bloquea rutas privadas y operativas."""
    base = _base(base_url)
    lineas = [
        "User-agent: *",
        "Allow: /",
        *(f"Disallow: {ruta}" for ruta in _DISALLOW),
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return "\n".join(lineas)


def sitemap_xml(base_url: str) -> str:
    """Sitemap XML bilingüe (ES/EN) con enlaces alternativos hreflang."""
    base = _base(base_url)
    es_url = f"{base}/"
    en_url = f"{base}/en"
    alternates = (
        f'    <xhtml:link rel="alternate" hreflang="es" href={quoteattr(es_url)}/>\n'
        f'    <xhtml:link rel="alternate" hreflang="en" href={quoteattr(en_url)}/>\n'
        f'    <xhtml:link rel="alternate" hreflang="x-default" href={quoteattr(es_url)}/>'
    )
    bloques = "\n".join(
        f"  <url>\n    <loc>{escape(loc)}</loc>\n{alternates}\n  </url>"
        for loc in (es_url, en_url)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f"{bloques}\n"
        "</urlset>\n"
    )


def llms_txt(base_url: str) -> str:
    """Resumen conciso en Markdown de Blissens para agentes y LLMs usando datos oficiales de copia.py."""
    base = _base(base_url)
    servicios = "\n".join(
        f"- **{nombre}**: {detalle}" for nombre, detalle in copia.ES["servicios"]["lista"]
    )
    especialistas = "\n".join(
        f"- {nombre} — {cargo}" for nombre, cargo, *_ in copia.ES["equipo"]["personas"]
    )
    return (
        "# Blissens\n\n"
        f"> {copia.ES['meta']['descripcion']}\n\n"
        "## Sitio web\n"
        f"- Español: {base}/\n"
        f"- English: {base}/en\n\n"
        "## Ubicación y contacto\n"
        f"- Dirección: {copia.DIRECCION}\n"
        f"- Horario (ES): {copia.HORARIO['es']}\n"
        f"- Hours (EN): {copia.HORARIO['en']}\n"
        f"- Teléfono / WhatsApp: {copia.TELEFONO}\n"
        f"- Correo: {copia.CORREO}\n\n"
        "## Servicios\n"
        f"{servicios}\n\n"
        "## Especialistas\n"
        f"{especialistas}\n"
    )


def json_ld(base_url: str, lang: str) -> dict:
    """Datos estructurados Schema.org (Dentist + WebSite) coherentes con el contenido visible."""
    base = _base(base_url)
    t = copia.COPIA.get(lang, copia.ES)
    clinic_id = f"{base}/#clinic"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Dentist",
                "@id": clinic_id,
                "name": "Blissens",
                "url": f"{base}{t['home']}",
                "description": t["meta"]["descripcion"],
                "image": f"{base}/static/sitio/{copia.IMAGENES['equipo']}",
                "logo": f"{base}/static/sitio/logo-1024x110.png",
                "telephone": copia.TELEFONO_TEL,
                "email": copia.CORREO,
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": _STREET_ADDRESS,
                    "addressLocality": "Medellín",
                    "addressRegion": "Antioquia",
                    "addressCountry": "CO",
                },
                "openingHoursSpecification": [
                    {
                        "@type": "OpeningHoursSpecification",
                        "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                        "opens": "08:00",
                        "closes": "17:00",
                    },
                    {
                        "@type": "OpeningHoursSpecification",
                        "dayOfWeek": "Saturday",
                        "opens": "08:00",
                        "closes": "12:00",
                    },
                ],
                "availableLanguage": ["es", "en"],
                "medicalSpecialty": "Dentistry",
                "hasOfferCatalog": {
                    "@type": "OfferCatalog",
                    "name": t["servicios"]["kicker"],
                    "itemListElement": [
                        {
                            "@type": "Offer",
                            "itemOffered": {
                                "@type": "Service",
                                "name": nombre,
                                "description": detalle,
                            },
                        }
                        for nombre, detalle in t["servicios"]["lista"]
                    ],
                },
                "employee": [
                    {
                        "@type": "Person",
                        "name": nombre,
                        "jobTitle": cargo,
                    }
                    for nombre, cargo, *_ in t["equipo"]["personas"]
                ],
            },
            {
                "@type": "WebSite",
                "@id": f"{base}/#website",
                "name": "Blissens",
                "url": f"{base}/",
                "inLanguage": ["es-CO", "en-US"],
                "publisher": {"@id": clinic_id},
            },
        ],
    }
