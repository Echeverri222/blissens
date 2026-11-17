import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Activity, CalendarDays, ClipboardList, ExternalLink, KeyRound, LogOut, Menu, Settings, ShieldBan, Users, X } from "lucide-react";
import { api } from "@/api/cliente";
import { useAccion, useConteoBandejas } from "@/api/consultas";
import type { Rol } from "@/api/tipos";
import { cn } from "@/lib/utils";
import { fechaHora } from "@/lib/tiempo";
import { useSesion } from "@/sesion/Sesion";
import { Aviso } from "@/ui/vistas";
import { Boton, Entrada } from "@/ui/controles";
import { ApiError } from "@/api/cliente";
import { Distintivo } from "./Marca";
import { useMediaQuery } from "@/lib/useMediaQuery";

interface Seccion { a: string; texto: string; icono: typeof Menu; conteo?: boolean }
export const SECCIONES: Record<Rol, Seccion[]> = {
  especialista: [
    { a: "/agenda", texto: "Mi agenda", icono: CalendarDays },
    { a: "/horario", texto: "Mi horario", icono: ShieldBan },
  ],
  auxiliar: [
    { a: "/agenda", texto: "Agenda", icono: CalendarDays },
    { a: "/bandejas", texto: "Bandejas", icono: ClipboardList, conteo: true },
    { a: "/pacientes", texto: "Pacientes", icono: Users },
    { a: "/indicadores", texto: "Indicadores", icono: Activity },
    { a: "/sistema", texto: "Sistema", icono: Settings },
  ],
};

function Enlaces({ rol, alNavegar, vertical }: { rol: Rol; alNavegar?: () => void; vertical?: boolean }) {
  const q = useConteoBandejas(rol === "auxiliar");
  const total = q.data ? Object.values(q.data).reduce((a, b) => a + b, 0) : 0;
  return (
    <>
      {SECCIONES[rol].map(({ a, texto, icono: Icono, conteo }) => (
        <NavLink key={a} to={a} onClick={alNavegar}
          className={({ isActive }) => cn("relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
            vertical ? "flex-col gap-0.5 text-xs" : "", isActive ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white")}>
          {({ isActive }) => (<>
            {isActive && !vertical && <span className="acento-activo absolute inset-y-1.5 left-0 w-1 rounded-full" aria-hidden />}
            <Icono className="size-5" aria-hidden />
            <span>{texto}</span>
            {conteo && total > 0 && <span aria-label={`${total} pendientes`} className="ml-auto rounded-full bg-white px-1.5 text-xs font-semibold text-marca">{total}</span>}
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

export function Layout(): ReactNode {
  const { sesion, ahora } = useSesion();
  const [menu, setMenu] = useState(false);
  const movil = useMediaQuery("(max-width: 767px)");
  const esp = sesion.rol === "especialista";
  return (
    <div className="flex min-h-dvh">
      <aside className="hidden w-60 shrink-0 flex-col bg-marca p-3 text-white md:flex">
        <div className="px-3 py-4"><Distintivo /></div>
        <nav aria-label="Secciones" className="mt-4 flex flex-col gap-1"><Enlaces rol={sesion.rol} /></nav>
        {sesion.modo_demo && sesion.rol === "auxiliar" && (
          <a href="/simulador" target="_blank" rel="noopener" className="mt-auto flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-white/5 hover:text-white">
            <ExternalLink className="size-4" aria-hidden /> Simulador de WhatsApp</a>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-linea bg-papel/95 px-4 py-2 backdrop-blur">
          {!esp && movil && <button aria-label="Abrir menú" onClick={() => setMenu(true)} className="rounded-md p-1.5 hover:bg-zinc-100 md:hidden"><Menu className="size-5" /></button>}
          <div className="md:hidden"><Distintivo /></div>
          <div className="ml-auto flex items-center gap-3">
            <p className="text-right text-xs text-tinta-suave" aria-label="Hora del sistema">
              <span className="block">Hora del sistema</span><b className="text-sm text-tinta">{fechaHora(ahora)}</b></p>
            {sesion.modo_demo && <span className="rounded-full bg-amber-200 px-2.5 py-1 text-xs font-semibold text-amber-950">Modo demo</span>}
            <MenuCuenta />
          </div>
        </header>
        <main className={cn("flex-1 p-4 md:p-6", esp && "pb-24 md:pb-6")}><Outlet /></main>
      </div>
      {esp && (
        <nav aria-label="Secciones" className="fixed inset-x-0 bottom-0 z-30 flex justify-around bg-marca px-2 py-1.5 md:hidden"><Enlaces rol="especialista" vertical /></nav>
      )}
      {!esp && (
        <Dialog.Root open={menu && movil} onOpenChange={setMenu}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
            <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-marca p-3 text-white">
              <Dialog.Title className="sr-only">Menú</Dialog.Title>
              <Dialog.Description className="sr-only">Secciones del panel</Dialog.Description>
              <div className="flex items-center justify-between px-3 py-3"><Distintivo /><Dialog.Close aria-label="Cerrar menú"><X className="size-5" /></Dialog.Close></div>
              <nav aria-label="Secciones" className="mt-2 flex flex-col gap-1"><Enlaces rol="auxiliar" alNavegar={() => setMenu(false)} /></nav>
              {sesion.modo_demo && <a href="/simulador" target="_blank" rel="noopener" className="mt-auto flex items-center gap-2 px-3 py-2 text-sm text-zinc-300"><ExternalLink className="size-4" aria-hidden /> Simulador de WhatsApp</a>}
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </div>
  );
}
