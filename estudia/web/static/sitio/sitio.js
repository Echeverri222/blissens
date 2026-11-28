/* Interacciones del sitio público de Blissens. JavaScript sin dependencias; todo funciona (sin animaciones) si no carga. */
(function () {
  "use strict";
  var d = document, raiz = d.documentElement;
  var reducido = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  raiz.classList.add("js");

  /* Cabecera que se condensa al desplazarse. */
  var cab = d.getElementById("cab");
  function alDesplazar() {
    if (cab) cab.classList.toggle("cab--chica", window.scrollY > 24);
    var barra = d.getElementById("barra"), hero = d.getElementById("inicio");
    if (barra && hero) barra.classList.toggle("barra--visible", window.scrollY > hero.offsetHeight * 0.6 && !enSeccion("agendar"));
  }
  function enSeccion(id) {
    var el = d.getElementById(id); if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.top < window.innerHeight * 0.5 && r.bottom > window.innerHeight * 0.3;
  }
  var tick = false;
  window.addEventListener("scroll", function () {
    if (tick) return; tick = true;
    requestAnimationFrame(function () { alDesplazar(); tick = false; });
  }, { passive: true });
  alDesplazar();

  /* Menú móvil accesible: botón con aria-expanded, Escape cierra, el foco queda dentro y vuelve al botón. */
  var menu = d.getElementById("menu"), abrir = d.querySelector("[data-abrir-menu]"), cerrar = d.querySelector("[data-cerrar-menu]");
  function abrirMenu() {
    if (!menu) return;
    menu.hidden = false; abrir.setAttribute("aria-expanded", "true"); d.body.classList.add("menu-abierto");
    (cerrar || menu).focus();
  }
  function cerrarMenu(devolverFoco) {
    if (!menu || menu.hidden) return;
    menu.hidden = true; abrir.setAttribute("aria-expanded", "false"); d.body.classList.remove("menu-abierto");
    if (devolverFoco) abrir.focus();
  }
  if (abrir) abrir.addEventListener("click", function () { menu.hidden ? abrirMenu() : cerrarMenu(true); });
  if (cerrar) cerrar.addEventListener("click", function () { cerrarMenu(true); });
  if (menu) {
    menu.addEventListener("click", function (e) {
      if (e.target === menu) { cerrarMenu(true); return; }
      if (e.target.closest("a")) cerrarMenu(false);
    });
    menu.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { cerrarMenu(true); return; }
      if (e.key !== "Tab") return;
      var f = menu.querySelectorAll("a[href], button"); if (!f.length) return;
      var a = f[0], z = f[f.length - 1];
      if (e.shiftKey && d.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && d.activeElement === z) { e.preventDefault(); a.focus(); }
    });
  }
  window.matchMedia("(min-width: 1240px)").addEventListener("change", function (m) { if (m.matches) cerrarMenu(false); });

  /* Revelado al entrar en pantalla (se omite con movimiento reducido o sin IntersectionObserver). */
  var revs = d.querySelectorAll(".rev");
  if (reducido || !("IntersectionObserver" in window)) {
    revs.forEach(function (el) { el.classList.add("rev--ok"); });
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("rev--ok"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    revs.forEach(function (el, i) { el.style.transitionDelay = (i % 3) * 70 + "ms"; io.observe(el); });
  }

  /* Enlace activo en la navegación según la sección visible. */
  var enlaces = d.querySelectorAll(".cab__nav a");
  if (enlaces.length && "IntersectionObserver" in window) {
    var mapa = {};
    enlaces.forEach(function (a) { var h = a.getAttribute("href"), i = h.indexOf("#"); if (i > -1) mapa[h.slice(i + 1)] = a; });
    var so = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var a = mapa[e.target.id]; if (!a || !e.isIntersecting) return;
        enlaces.forEach(function (x) { x.removeAttribute("aria-current"); });
        a.setAttribute("aria-current", "true");
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    Object.keys(mapa).forEach(function (id) { var s = d.getElementById(id); if (s) so.observe(s); });
  }

  /* Comparador antes/después: el control es un <input type="range"> (teclado, lectores de pantalla y arrastre nativos). */
  d.querySelectorAll(".ba").forEach(function (ba) {
    var r = ba.querySelector(".ba__rango");
    function poner() { ba.style.setProperty("--pos", r.value + "%"); r.setAttribute("aria-valuetext", r.value + "%"); }
    r.addEventListener("input", poner); poner();
  });

  /* Experiencias: elegir un paquete lo deja seleccionado en el formulario y lleva hasta él. */
  d.querySelectorAll("[data-paquete]").forEach(function (b) {
    b.addEventListener("click", function () {
      var sel = d.getElementById("paquete-experiencia"), form = d.getElementById("reservar");
      if (sel) sel.value = b.getAttribute("data-paquete");
      if (form) { form.scrollIntoView({ behavior: reducido ? "auto" : "smooth", block: "center" }); }
      if (sel) setTimeout(function () { sel.focus({ preventScroll: true }); }, reducido ? 0 : 450);
    });
  });

  /* El 429 del límite de solicitudes trae el formulario con su mensaje: HTMX no cambia nada con errores 4xx por defecto. */
  d.body.addEventListener("htmx:beforeSwap", function (e) {
    if (e.detail.xhr && e.detail.xhr.status === 429) { e.detail.shouldSwap = true; e.detail.isError = false; }
  });

  /* Tras un cambio de HTMX (incluyendo hx-swap="outerHTML"), el foco pasa al mensaje o al primer campo con error. */
  /* Confirmación de formularios (data-confirmar), sin JavaScript en línea: la CSP no permite 'unsafe-inline'. */
  d.addEventListener("submit", function (e) {
    var f = e.target, msg = f && f.getAttribute && f.getAttribute("data-confirmar");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* Asistente del paciente, sin JavaScript en línea (la CSP lo bloquea):
     - data-limpiar-al-enviar: tras enviar con éxito, vacía el cuadro de texto;
     - data-descartar: quita la propuesta;
     - data-alternativa: la propuesta lleva a otra página en vez de cambiar el chat. */
  d.body.addEventListener("htmx:afterRequest", function (e) {
    var f = e.detail && e.detail.elt;
    if (!f || !f.hasAttribute || !f.hasAttribute("data-limpiar-al-enviar") || !e.detail.successful) return;
    var t = f.querySelector("textarea"); if (t) t.value = "";
  });
  d.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-descartar]");
    if (!b) return;
    var pr = b.closest(".propuesta"); if (pr) pr.remove();
  });
  d.body.addEventListener("htmx:beforeSwap", function (e) {
    var f = e.detail && e.detail.elt, a = f && f.getAttribute && f.getAttribute("data-alternativa");
    if (a) { e.preventDefault(); window.location.href = a; }
  });

  /* En pantallas anchas la información se muestra abierta; en el celular queda plegada para no empujar el formulario. */
  if (window.matchMedia && matchMedia("(min-width: 900px)").matches) {
    d.querySelectorAll("[data-abrir-en-escritorio]").forEach(function (el) { el.open = true; });
  }

  /* Asistente del sitio: abierto en escritorio; en el celular queda plegado como una barra pequeña junto a la barra fija. */
  var asist = d.querySelector(".asist__caja");
  if (asist && window.matchMedia && !matchMedia("(min-width: 900px)").matches) asist.open = false;

  d.body.addEventListener("htmx:afterSettle", function (e) {
    var t = (e.detail && e.detail.target) || (e.detail && e.detail.elt) || e.target;
    if (!t || !t.querySelector) return;
    if (!d.body.contains(t) && t.id) t = d.getElementById(t.id);
    if (!t) return;
    var el = t.querySelector("[role=alert], [role=status]") || t.querySelector("input:not([readonly]):not([type=hidden]):not([type=checkbox])");
    if (el) {
      if (!el.hasAttribute("tabindex") && !/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    }
  });
})();
