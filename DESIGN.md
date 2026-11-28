---
name: Blissens
description: Atelier clínico editorial monocromático negro/blanco con tipografía Cardo + Inter y destello iridiscente contenido.
colors:
  obsidian-ink: "#000000"
  studio-charcoal: "#0a0a0a"
  charcoal-elevated: "#111113"
  graphite-surface: "#1c1c1e"
  pure-canvas: "#ffffff"
  gallery-paper: "#f6f6f7"
  hairline-silver: "#e4e4e7"
  slate-muted: "#5f5f64"
  panel-ink: "#18181b"
  panel-muted: "#52525b"
  mist-gray: "#bdbdc2"
  iridescent-aqua: "#3fbfb0"
  iridescent-azure: "#3b9fe0"
  iridescent-lilac: "#b07cf0"
  focus-sky: "#7aa7ff"
  error-bg: "#fff1f2"
  error-ink: "#9f1239"
  error-border: "#fecdd3"
  success-bg: "#ecfdf5"
  success-ink: "#065f46"
  success-border: "#a7f3d0"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(2.6rem, 8.5vw, 7rem)"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "0.01em"
  headline:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(1.7rem, 3.6vw + 0.5rem, 3.1rem)"
    fontWeight: 600
    lineHeight: 1.12
    letterSpacing: "0.03em"
  editorial:
    fontFamily: "Cardo, Georgia, 'Times New Roman', serif"
    fontSize: "clamp(1.15rem, 1.1vw + 0.9rem, 1.55rem)"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0.02em"
  title:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "0em"
  label:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.14em"
rounded:
  control: "10px"
  card: "14px"
  panel: "16px"
  pill: "9999px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  section: "clamp(4rem, 9vw, 8rem)"
components:
  button-primary:
    backgroundColor: "{colors.obsidian-ink}"
    textColor: "{colors.pure-canvas}"
    rounded: "{rounded.pill}"
    padding: "11px 26px"
  button-primary-inverse:
    backgroundColor: "{colors.pure-canvas}"
    textColor: "{colors.obsidian-ink}"
    rounded: "{rounded.pill}"
    padding: "11px 26px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.studio-charcoal}"
    rounded: "{rounded.pill}"
    padding: "11px 26px"
  card-surface:
    backgroundColor: "{colors.pure-canvas}"
    textColor: "{colors.panel-ink}"
    rounded: "{rounded.panel}"
    padding: "20px"
  input-field:
    backgroundColor: "{colors.pure-canvas}"
    textColor: "{colors.studio-charcoal}"
    rounded: "{rounded.control}"
    padding: "11px 14px"
---

# Design System: Blissens

## Overview

**Creative North Star: "Atelier Clínico Editorial"**

Blissens proyecta serenidad clínica y lujo silencioso: alterna superficies monocromáticas de alto contraste —negro absoluto y blanco puro— para que la fotografía real, la tipografía y las acciones prioritarias respiren sin artificio. El diseño se comporta como un atelier editorial en la landing pública y como una cabina de precisión limpia en el agendamiento y el panel operativo, manteniendo el mismo lenguaje visual en todo el recorrido.

El espectro iridiscente propio de la marca (textura `Bg-1.png` en la landing y el degradado agua–azul–lila en el panel) actúa exclusivamente como firma lumínica de precisión: aparece en el acento del titular principal, en marcadores numéricos y en el estado activo o distintivo, nunca como relleno masivo que compita con el contenido clínico.

**Key Characteristics:**
- Contraste monocromático firme (`obsidian-ink` y `pure-canvas`) amortiguado por superficies neutras frías (`gallery-paper` y `hairline-silver`).
- Dúo tipográfico auto-hospedado: `Cardo` para la voz editorial y la calma de marca; `Inter` variable para la arquitectura, titulares en mayúsculas y datos operativos con dígitos tabulares.
- Destello iridiscente estrictamente contenido (menos del 10 % del área visible) como señal de identidad y foco activo.
- Cero dependencias de fuentes o activos remotos; todo se sirve localmente desde `/static/`.

## Colors

Una paleta arquitectónica monocromática donde el negro y el blanco estructuran la jerarquía, los neutros fríos sostienen la operación diaria y el trío iridiscente marca la firma de marca.

### Primary
- **Obsidian Ink** (`obsidian-ink`): superficie principal de cabecera, secciones editoriales oscuras, botón primario sobre claro y estado seleccionado en selectores de fecha/hora.
- **Studio Charcoal** (`studio-charcoal`): barra lateral del panel operativo, tinta principal de texto en sitio público y controles primarios en el panel.
- **Pure Canvas** (`pure-canvas`): superficie principal de lectura, tarjetas de formularios, botón primario invertido sobre fondo negro y secciones blancas de la landing.

### Secondary
- **Iridescent Aqua** (`iridescent-aqua`), **Iridescent Azure** (`iridescent-azure`) y **Iridescent Lilac** (`iridescent-lilac`): componen el degradado de marca (`135deg`, agua → azul al 55 % → lila) y reflejan la textura `Bg-1.png`. Se usan en aros distintivos, barras de estado activo y acentos lumínicos puntuales.

### Neutral
- **Gallery Paper** (`gallery-paper`): fondo general de páginas interiores del paciente y del panel operativo, creando separación sutil detrás de tarjetas blancas.
- **Charcoal Elevated** (`charcoal-elevated`) y **Graphite Surface** (`graphite-surface`): contenedores oscuros elevados para paneles de formulario y superficies secundarias sobre negro.
- **Hairline Silver** (`hairline-silver`): bordes de 1px en tarjetas, divisores de acordeón, filas de familia y rejillas del panel.
- **Panel Ink** (`panel-ink`): texto principal de alta legibilidad en el panel operativo.
- **Slate Muted** (`slate-muted`) y **Panel Muted** (`panel-muted`): texto secundario, metadatos y etiquetas de apoyo sobre fondos claros.
- **Mist Gray** (`mist-gray`): texto secundario y kickers de apoyo sobre fondos negros.

### Semantic & Focus
- **Focus Sky** (`focus-sky`) / **Iridescent Azure** (`iridescent-azure`): anillo de foco visible de teclado (`outline` con `outline-offset`), nunca reemplazado por un simple cambio de color.
- **Error** (`error-bg`, `error-ink`, `error-border`) y **Success** (`success-bg`, `success-ink`, `success-border`): banners de validación, avisos de cita confirmada y alertas operativas con contraste AA garantizado.

### Named Rules
**The Ten-Percent Iridescence Rule.** El gradiente iridiscente y la textura `Bg-1.png` ocupan menos del 10 % de cualquier pantalla; nunca se usan como fondo de tarjetas de contenido, tablas ni botones de texto largo.

**The Monochrome First Rule.** La jerarquía primaria siempre se resuelve con contraste tonal (negro, blanco, papel y bordes de 1px) antes de recurrir al color semántico o al acento.

## Typography

**Display & UI Font:** `Inter` variable (auto-hospedada en `inter-var.woff2`, pesos 100–900; fallback `system-ui, -apple-system, "Segoe UI", sans-serif`).
**Editorial Accent Font:** `Cardo` (auto-hospedada en `cardo-400.woff2`, peso 400; fallback `Georgia, "Times New Roman", serif`).

**Character:** `Inter` aporta precisión clínica, claridad en mayúsculas con *tracking* abierto y legibilidad impecable en horarios, teléfonos y KPIs; `Cardo` introduce calidez editorial y distinción boutique en kickers, subtítulos de marca y pantallas de bienvenida.

### Hierarchy
- **Display** (`600`, `clamp(2.6rem, 8.5vw, 7rem)`, `line-height: 1.02`, mayúsculas): reservado exclusivamente al titular del Hero en la landing.
- **Headline** (`600`, `clamp(1.7rem, 3.6vw + 0.5rem, 3.1rem)`, `line-height: 1.12`, mayúsculas, `letter-spacing: 0.03em`): encabezados de sección en landing y encabezado principal de `/agendar` en escritorio.
- **Editorial** (`Cardo 400`, `clamp(1.15rem, 1.1vw + 0.9rem, 1.55rem)`, `line-height: 1.55`): kickers, párrafos de apertura (*lead*), títulos de bienvenida en `Ingresar` / `Negocio` y elementos de firma de marca.
- **Title** (`600`, `1.25rem`, `line-height: 1.25`, `letter-spacing: -0.01em`): encabezados de pantallas del panel, tarjetas principales y hojas de detalle.
- **Body** (`400`, `1rem`, `line-height: 1.65`, máx. `65–72ch` en lectura): cuerpo general de landing, formularios y vistas operativas.
- **Label** (`500`, `0.75rem`, `line-height: 1.3`, `letter-spacing: 0.14em`, mayúsculas): etiquetas de sección, metadatos de horarios y encabezados compactos de tabla.

### Named Rules
**The Clinical Tabular Rule.** Todas las horas de cita, conteos de bandejas, porcentajes y cifras de dinero en el panel usan `font-variant-numeric: tabular-nums` en `Inter` para alinear columnas y evitar saltos visuales.

**The Restrained Serif Rule.** En el panel operativo (`/panel/*`), `Cardo` se reserva únicamente para la portada de acceso (`Ingresar` y `ElegirNegocio`) y nunca se usa en tablas, botones, formularios ni métricas.

## Layout

- **Landing pública (`/` y `/en`, Modo Persuade):** contenedor centrado `min(100% - 2rem, 1180px)` (cabecera hasta `1320px`), ritmo vertical generoso `clamp(4rem, 9vw, 8rem)`, alternancia de bandas oscuras y claras, y grillas de 2 columnas (`>= 900px`) o 3 columnas (`>= 700–900px`). Barra fija de acción inferior solo por debajo de `1240px`.
- **Flujo del paciente (`/agendar` y `/p/*`, Modo Operate de marca):** celular primero con cabecera compacta (`3.5rem` en móvil, `4.5rem` en escritorio); vista dividida `44% / 56%` en escritorio (`>= 900px`) para el ingreso/contexto, y columna enfocada (`max-width: 34rem`) sobre `gallery-paper` para `Mis citas`, selección de espacios, familia y cancelación, sin navegación de marketing que distraiga.
- **Panel operativo (`/panel/*`, Modo Operate):** barra lateral fija oscura (`studio-charcoal`) en escritorio con área principal fluida sobre `gallery-paper`; en móvil, barra inferior para especialistas y *drawer* para auxiliar.

## Elevation & Depth

El sistema es **plano por defecto con capas tonales y bordes de 1px** (`hairline-silver` sobre claro, `rgba(255,255,255,0.14–0.18)` sobre oscuro). Las sombras se reservan estrictamente para superficies flotantes o montadas sobre bandas de contraste:

- **Header Condensed** (`0 1px 0 rgba(255,255,255,.12), 0 8px 24px rgba(0,0,0,.35)`): cabecera fija al hacer scroll.
- **Focus Card Lift** (`0 1px 2px rgba(0,0,0,.06), 0 14px 40px rgba(0,0,0,.12)`): tarjeta de formulario principal montada sobre la banda oscura de `/agendar` o pantalla de acceso.
- **Dialog / Sheet** (`0 20px 50px rgba(0,0,0,.22)`): hojas modales (`Hoja` / Radix Dialog) y menús desplegables en el panel.

### Named Rules
**The Hairline Elevation Rule.** En el panel operativo y en las tarjetas de citas, la separación visual se logra con fondo blanco sobre `gallery-paper` y borde de `1px solid hairline-silver`, nunca apilando sombras difusas en cada fila.

## Shapes

- **Botones de acción y badges de landing:** cápsula completa (`9999px`) con altura táctil mínima de `48px` (`3rem`) en flujos públicos y `40–44px` en acciones del panel.
- **Tarjetas y contenedores:** esquinas suavemente redondeadas (`14px` en panel, `16px` en tarjetas de formulario y pacientes; `12px` en fotografía editorial).
- **Controles e inputs:** esquinas funcionales y nítidas (`10px`) con borde de `1px` y foco claramente separado.

## Components

### Buttons
Carácter: firmes, táctiles y de alto contraste, con desplazamiento sutil de `-1px` en hover.
- **Primary (landing/paciente):** relleno `obsidian-ink`, texto `pure-canvas`, forma cápsula (`9999px`), `padding: 11px 26px`, altura mínima `48px`.
- **Primary Inverse (sobre negro):** relleno `pure-canvas`, texto `obsidian-ink`, hover `#e8e8ea`.
- **Outline / Secondary:** fondo transparente, borde `1px` con `currentColor` (o `#c4c4c9` sobre blanco), hover con velo neutro sutil (`rgba(127,127,127,.15)`).
- **Panel Primary / Secondary:** radios funcionales (`10px`), altura mínima `40px`, transición rápida (`150ms`), con estado deshabilitado legible y sin parpadeo.

### Inputs & Selectors
Carácter: limpios, amplios y sin adornos innecesarios.
- **Campos de texto / select:** fondo `pure-canvas`, borde `1px solid #c9c9ce`, radio `10px`, altura mínima `48px` en paciente (`40px` en panel), foco con borde oscuro y halo suave o `focus-visible` de `2–3px`.
- **Chips de día y hora (`_espacios.html`):** celdas táctiles con borde `hairline-silver` (`8–10px` de radio) que invierten a `obsidian-ink` / `pure-canvas` cuando están seleccionadas (`aria-pressed="true"` / `:checked`).

### Cards & Containers
Carácter: sobrios y estructurados por espacio en blanco.
- **Tarjeta clara:** fondo `pure-canvas`, borde `1px solid hairline-silver`, radio `14–16px`, padding `20px` (hasta `32px` en formularios enfocados).
- **Tarjeta oscura (landing):** fondo `charcoal-elevated`, borde `1px solid rgba(255,255,255,.14)`, radio `16px`.

### Navigation
- **Cabecera landing:** fija en `obsidian-ink` (`4.5rem`, se condensa a `3.4rem` al desplazar), logo Blissens invertido a blanco, enlaces en `Inter` limpio, selector `ES / EN`, acceso visible secundario al sistema (`Ingresar` → `/panel`) y CTA principal cápsula blanca (`Agendar cita` → `/agendar`).
- **Cabecera enfocada paciente:** fija en `obsidian-ink` (`3.5rem` móvil / `4.5rem` escritorio), logo Blissens, teléfono opcional y botón compacto para volver; sin menú de marketing ni enlace a `/panel`.
- **Sidebar panel:** fija en `studio-charcoal`, logotipo/identidad Blissens con acento iridiscente sutil y navegación clara por rol.

### Signature Component: Iridescent Halo & Brand Wordmark
El logotipo oficial (`logo-1024x110.png`) y el anillo/degradado iridiscente (`Bg-1.png` / `--degradado`) actúan como firma reconocible de Blissens en la cabecera, el Hero, los pasos numerados y la pantalla de ingreso del panel.

## Do's and Don'ts

### Do:
- **Do** mantener 100 % de fuentes (`inter-var.woff2`, `cardo-400.woff2`), scripts e imágenes auto-hospedados en `/static/` (requisito probado por `tests/test_sitio.py` y `tests/test_web.py`).
- **Do** usar `font-variant-numeric: tabular-nums` en todas las horas, contadores y métricas del panel.
- **Do** preservar `prefers-reduced-motion: reduce` anulando animaciones de marquesina, flotación y entrada.
- **Do** garantizar objetivos táctiles de al menos `44px` en móvil en todos los botones, chips de hora y pestañas.

### Don't:
- **Don't** introducir colores de marca ajenos (azules genéricos de Tailwind, morados saturados o fondos beige cálidos) que contradigan el negro/blanco/papel frío de Blissens.
- **Don't** usar `Cardo` en controles operativos, tablas de datos o etiquetas densas del panel.
- **Don't** inyectar navegación completa de marketing ni enlaces a `/panel` dentro de `/agendar` o `/p/*`.
- **Don't** depender de Google Fonts, CDNs externos ni consultas a base de datos en `GET /` o `GET /en`.
