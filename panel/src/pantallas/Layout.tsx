import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Activity, ArrowLeftRight, CalendarDays, ClipboardList, ExternalLink, KeyRound, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Settings, ShieldBan, UserCog, Users, X } from "lucide-react";
import { api } from "@/api/cliente";
import { useAccion, useConteoBandejas } from "@/api/consultas";
import type { Rol } from "@/api/tipos";
import { totalLlamadas } from "@/lib/pendientes";
import { cn } from "@/lib/utils";
import { fechaHora, horaDe } from "@/lib/tiempo";
import { rolDe, useSesion } from "@/sesion/Sesion";
import { Aviso } from "@/ui/vistas";
import { Boton, Entrada } from "@/ui/controles";
import { ApiError } from "@/api/cliente";
import { Distintivo } from "./Marca";
import { ANCHO_ASISTENTE, Asistente } from "./Asistente";
import { useMediaQuery } from "@/lib/useMediaQuery";

interface Seccion { a: string; texto: string; icono: typeof Menu; conteo?: boolean }
export const SECCIONES: Record<Rol, Seccion[]> = {
  especialista: [
    { a: "/agenda", texto: "Mi agenda", icono: CalendarDays },
    { a: "/horario", texto: "Mi horario", icono: ShieldBan },
  ],
  auxiliar: [
    { a: "/agenda", texto: "Agenda", icono: CalendarDays },
    { a: "/bandejas", texto: "Pendientes", icono: ClipboardList, conteo: true },
    { a: "/pacientes", texto: "Pacientes", icono: Users },
    { a: "/indicadores", texto: "Indicadores", icono: Activity },
    { a: "/sistema", texto: "Sistema", icono: Settings },
  ],
};

const ADMINISTRACION: Seccion = { a: "/administracion", texto: "Administración", icono: UserCog };

function Enlaces({ rol, administrador, alNavegar, vertical, compacto }: { rol: Rol; administrador?: boolean; alNavegar?: () => void; vertical?: boolean; compacto?: boolean }) {
  const q = useConteoBandejas(rol === "auxiliar");
  const total = q.data ? totalLlamadas(q.data) : 0;
  return (
    <>
      {[...SECCIONES[rol], ...(administrador ? [ADMINISTRACION] : [])].map(({ a, texto, icono: Icono, conteo }) => (
        <NavLink key={a} to={a} onClick={alNavegar} title={compacto ? texto : undefined}
          className={({ isActive }) => cn("relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
            vertical ? "flex-col gap-0.5 text-xs" : "", compacto && "justify-center px-0", isActive ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white")}>
          {({ isActive }) => (<>
            {isActive && !vertical && <span className="acento-activo absolute inset-y-1.5 left-0 w-1 rounded-full" aria-hidden />}
            <Icono className="size-5" aria-hidden />
            <span className={cn(compacto && "sr-only")}>{texto}</span>
            {conteo && total > 0 && <span aria-label={`${total} pendientes`} className={cn("rounded-full bg-white px-1.5 text-xs font-semibold text-marca",
              compacto ? "absolute -top-0.5 right-0.5 text-[10px]" : "ml-auto")}>{total}</span>}
          </>)}
        </NavLink>
      ))}
    </>
  );
}

function CambiarClave({ abierta, alCerrar }: { abierta: boolean; alCerrar: () => void }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const m = useAccion((v: { actual: string; nueva: string }) => api.sesion.cambiarClave(v.actual, v.nueva), {
    ok: "Contraseña cambiada", alExito: () => { setActual(""); setNueva(""); alCerrar(); },
  });
  return (
    <Dialog.Root open={abierta} onOpenChange={(o) => !o && alCerrar()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-papel p-5 shadow-2xl">
          <Dialog.Title className="text-base font-semibold">Cambiar contraseña</Dialog.Title>
          <Dialog.Description className="mb-3 text-sm text-tinta-suave">Cerraremos tus otras sesiones abiertas. Mínimo 8 caracteres.</Dialog.Description>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate({ actual, nueva }); }}>
            {m.error instanceof ApiError && <Aviso>{m.error.mensaje}</Aviso>}
            <Entrada etiqueta="Contraseña actual" type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} required />
            <Entrada etiqueta="Contraseña nueva" type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} required />
            <div className="flex justify-end gap-2">
              <Boton variante="secundario" pequeno onClick={alCerrar}>Cancelar</Boton>
              <Boton type="submit" pequeno disabled={m.isPending}>Guardar</Boton>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function MenuCuenta() {
  const { sesion, salir } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [clave, setClave] = useState(false);
  return (
    <div className="relative">
      <button onClick={() => setAbierto((v) => !v)} aria-expanded={abierto} aria-haspopup="menu"
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-zinc-100">
        <span className="flex size-8 items-center justify-center rounded-full bg-marca text-xs font-semibold text-white" aria-hidden>{sesion.nombre.slice(0, 1)}</span>
        <span className="hidden sm:block"><span className="block font-medium leading-tight">{sesion.nombre}</span>
          <span className="block text-xs text-tinta-suave">{sesion.rol === "auxiliar" ? "Recepción" : "Especialista"}</span></span>
      </button>
      {abierto && (
        <div role="menu" className="absolute right-0 top-full z-30 mt-1 w-56 rounded-xl border border-linea bg-papel p-1 shadow-lg">
          <div className="border-b border-linea px-3 py-2 text-sm sm:hidden"><b>{sesion.nombre}</b><br /><span className="text-tinta-suave">{sesion.rol === "auxiliar" ? "Recepción" : "Especialista"}</span></div>
          {sesion.negocios.length > 1 && (
            <Link role="menuitem" to="/negocio" onClick={() => setAbierto(false)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-zinc-100">
              <ArrowLeftRight className="size-4" aria-hidden /> Cambiar de negocio</Link>
          )}
          <button role="menuitem" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-zinc-100" onClick={() => { setAbierto(false); setClave(true); }}>
            <KeyRound className="size-4" aria-hidden /> Cambiar contraseña</button>
          <button role="menuitem" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-zinc-100" onClick={() => void salir()}>
            <LogOut className="size-4" aria-hidden /> Cerrar sesión</button>
        </div>
      )}
      <CambiarClave abierta={clave} alCerrar={() => setClave(false)} />
    </div>
  );
}

const CLAVE_MENU = "panel.menu_contraido";

export function Layout(): ReactNode {
  const { sesion, ahora } = useSesion();
  const [menu, setMenu] = useState(false);
  const movil = useMediaQuery("(max-width: 767px)");
  const rol = rolDe(sesion);
  const esp = rol === "especialista";
  const marca = sesion.negocio?.nombre ?? "Estud-IA";
  const [asistente, setAsistente] = useState(false);
  const [contraido, setContraido] = useState(() => { try { return localStorage.getItem(CLAVE_MENU) === "1"; } catch { return false; } });
  const contraer = (v: boolean) => { setContraido(v); try { localStorage.setItem(CLAVE_MENU, v ? "1" : "0"); } catch { /* sin almacenamiento: solo esta visita */ } };
  useEffect(() => { document.title = sesion.negocio ? `${sesion.negocio.nombre} · Panel` : "Panel"; }, [sesion.negocio]);
  return (
    <div className="flex min-h-dvh">
      {/* Fija a la altura de la ventana: al bajar por la página solo se mueve el contenido, no el menú. Se contrae a solo íconos. */}
      <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto bg-marca text-white md:flex", contraido ? "w-16 p-2" : "w-60 p-3")}>
        <div className={cn("py-4", contraido ? "flex justify-center" : "px-3")}><Distintivo nombre={marca} soloInicial={contraido} /></div>
        <nav aria-label="Secciones" className="mt-4 flex flex-col gap-1"><Enlaces rol={rol} administrador={sesion.administrador} compacto={contraido} /></nav>
        <div className="mt-auto flex flex-col gap-1">
          {sesion.simulador && rol === "auxiliar" && (
            <a href="/simulador" target="_blank" rel="noopener" title={contraido ? "Simulador de WhatsApp" : undefined}
              className={cn("flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-white/5 hover:text-white", contraido && "justify-center px-0")}>
              <ExternalLink className="size-4" aria-hidden /><span className={cn(contraido && "sr-only")}>Simulador de WhatsApp</span></a>
          )}
          <button onClick={() => contraer(!contraido)} aria-label={contraido ? "Expandir menú" : "Contraer menú"} title={contraido ? "Expandir menú" : "Contraer menú"}
            className={cn("flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-white/5 hover:text-white", contraido && "justify-center px-0")}>
            {contraido ? <PanelLeftOpen className="size-4" aria-hidden /> : <><PanelLeftClose className="size-4" aria-hidden /> Contraer menú</>}</button>
        </div>
      </aside>
      {/* Con el asistente acoplado abierto, el contenido se corre para no quedar debajo del panel. */}
      <div className={cn("flex min-w-0 flex-1 flex-col", asistente && !movil && ANCHO_ASISTENTE)}>
        <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-linea bg-papel/95 px-4 py-2 backdrop-blur sm:gap-3">
          {!esp && movil && <button aria-label="Abrir menú" onClick={() => setMenu(true)} className="rounded-md p-1.5 hover:bg-zinc-100 md:hidden"><Menu className="size-5" /></button>}
          <div className="min-w-0 md:hidden"><Distintivo nombre={marca} /></div>
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            {/* En el celular solo la hora: la fecha completa no cabe junto a la marca. */}
            <p className="whitespace-nowrap text-right text-xs text-tinta-suave" aria-label="Hora del sistema">
              <span className="hidden sm:block">Hora del sistema</span>
              <b className="hidden text-sm text-tinta sm:inline">{fechaHora(ahora)}</b>
              <b className="text-sm text-tinta sm:hidden">{horaDe(ahora)}</b></p>
            {sesion.modo_demo && <span className="whitespace-nowrap rounded-full bg-amber-200 px-2.5 py-1 text-xs font-semibold text-amber-950">
              <span className="hidden sm:inline">Modo demo</span><span className="sm:hidden" aria-hidden>Demo</span></span>}
            <Asistente acoplado={!movil} abierto={asistente} alCambiar={setAsistente} />
            <MenuCuenta />
          </div>
        </header>
        <main className={cn("flex-1 p-4 md:p-6", esp && "pb-24 md:pb-6")}><Outlet /></main>
      </div>
      {esp && (
        <nav aria-label="Secciones" className="fixed inset-x-0 bottom-0 z-30 flex justify-around bg-marca px-2 py-1.5 md:hidden"><Enlaces rol="especialista" administrador={sesion.administrador} vertical /></nav>
      )}
      {!esp && (
        <Dialog.Root open={menu && movil} onOpenChange={setMenu}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
            <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-marca p-3 text-white">
              <Dialog.Title className="sr-only">Menú</Dialog.Title>
              <Dialog.Description className="sr-only">Secciones del panel</Dialog.Description>
              <div className="flex items-center justify-between px-3 py-3"><Distintivo nombre={marca} /><Dialog.Close aria-label="Cerrar menú"><X className="size-5" /></Dialog.Close></div>
              <nav aria-label="Secciones" className="mt-2 flex flex-col gap-1"><Enlaces rol="auxiliar" administrador={sesion.administrador} alNavegar={() => setMenu(false)} /></nav>
              {sesion.simulador && <a href="/simulador" target="_blank" rel="noopener" className="mt-auto flex items-center gap-2 px-3 py-2 text-sm text-zinc-300"><ExternalLink className="size-4" aria-hidden /> Simulador de WhatsApp</a>}
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </div>
  );
}
