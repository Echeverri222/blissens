import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { api, ApiError } from "@/api/cliente";
import { useAccion, useProfesionales, useServicios } from "@/api/consultas";
import type { Metas, Servicio, UsuarioAdmin } from "@/api/tipos";
import { pesos } from "@/lib/dinero";
import { fechaHora } from "@/lib/tiempo";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Casilla, Confirmar, Entrada, Seleccion, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta } from "@/ui/vistas";

/** Contraseña temporal: se muestra una sola vez, para entregársela a la persona. */
function ClaveEmitida({ usuario, clave, alCerrar }: { usuario: string; clave: string | null; alCerrar: () => void }) {
  return (
    <Dialog.Root open onOpenChange={(o) => !o && alCerrar()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-papel p-5 shadow-2xl">
          <Dialog.Title className="text-base font-semibold">Contraseña temporal de {usuario}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-tinta-suave">Anótala ahora: no se vuelve a mostrar. Deberá cambiarla al ingresar.</Dialog.Description>
          <p className="my-4 select-all rounded-lg bg-zinc-100 px-3 py-2 text-center font-mono text-lg" aria-label="Contraseña temporal">{clave}</p>
          <div className="flex justify-end"><Boton pequeno onClick={alCerrar}>Listo</Boton></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function NuevoUsuarioForm({ alEmitir }: { alEmitir: (usuario: string, clave: string | null) => void }) {
  const pros = useProfesionales();
  const [usuario, setUsuario] = useState("");
  const [nombre, setNombre] = useState("");
  const [rol, setRol] = useState<"auxiliar" | "especialista">("auxiliar");
  const [profesional, setProfesional] = useState("");
  const [administrador, setAdministrador] = useState(false);
  const m = useAccion(api.admin.crearUsuario, {
    ok: "Usuario creado",
    alExito: (d) => { alEmitir(d.usuario.nombre_usuario, d.clave_temporal ?? null); setUsuario(""); setNombre(""); setProfesional(""); setAdministrador(false); },
  });
  function enviar(e: FormEvent) {
    e.preventDefault();
    m.mutate({ usuario: usuario.trim(), nombre: nombre.trim(), rol, administrador, profesional_id: rol === "especialista" && profesional ? Number(profesional) : null });
  }
  return (
    <Tarjeta className="p-4">
      <form onSubmit={enviar} aria-label="Nuevo usuario" className="grid gap-3 sm:grid-cols-2">
        <h2 className="text-sm font-semibold sm:col-span-2">Nuevo usuario</h2>
        {m.error instanceof ApiError && <div className="sm:col-span-2"><Aviso>{m.error.mensaje}</Aviso></div>}
        <Entrada etiqueta="Usuario" autoCapitalize="none" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        <Entrada etiqueta="Nombre visible" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
        <Seleccion etiqueta="Rol" value={rol} onChange={(e) => setRol(e.target.value as "auxiliar" | "especialista")}>
          <option value="auxiliar">Recepción</option><option value="especialista">Especialista</option>
        </Seleccion>
        {rol === "especialista" && (
          <Seleccion etiqueta="Profesional" value={profesional} onChange={(e) => setProfesional(e.target.value)} required>
            <option value="">Elige…</option>
            {pros.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </Seleccion>
        )}
        <div className="sm:col-span-2"><Casilla etiqueta="Administra el negocio" checked={administrador} onChange={(e) => setAdministrador(e.target.checked)} /></div>
        <div className="sm:col-span-2"><Boton type="submit" disabled={m.isPending}>Crear con contraseña temporal</Boton></div>
      </form>
    </Tarjeta>
  );
}

function Fila({ u, yo, alEmitir }: { u: UsuarioAdmin; yo: string; alEmitir: (usuario: string, clave: string | null) => void }) {
  const desactivar = useAccion(() => api.admin.desactivar(u.acceso_id), { ok: "Acceso quitado" });
  const activar = useAccion(() => api.admin.activar(u.acceso_id), { ok: "Acceso devuelto" });
  const clave = useAccion(() => api.admin.claveTemporal(u.acceso_id), { alExito: (d) => alEmitir(u.nombre_usuario, d.clave_temporal ?? null) });
  const admin = useAccion(() => api.admin.cambiarAcceso(u.acceso_id, { rol: u.rol, profesional_id: u.profesional_id, administrador: !u.administrador }),
    { ok: u.administrador ? "Ya no administra" : "Ahora administra" });
  const esYo = u.nombre_usuario === yo;
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <p className="font-medium">{u.nombre} <span className="font-normal text-tinta-suave">({u.nombre_usuario})</span></p>
        <p className="text-xs text-tinta-suave">
          {u.rol === "auxiliar" ? "Recepción" : "Especialista"}{u.administrador ? " · Administra" : ""}{!u.activo ? " · Sin acceso" : ""}{u.bloqueado ? " · Bloqueado" : ""}
          {" · "}{u.ultimo_acceso ? `Último ingreso ${fechaHora(u.ultimo_acceso)}` : "Nunca ha ingresado"}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {u.activo && <Confirmar pequeno etiqueta="Contraseña temporal" pregunta={`Se cerrarán las sesiones de ${u.nombre} y se generará una contraseña temporal.`} alConfirmar={() => clave.mutate(undefined)} />}
        {u.activo && !esYo && <Confirmar pequeno etiqueta={u.administrador ? "Quitar administración" : "Hacer administrador"} pregunta={`¿Cambiar los permisos de ${u.nombre}?`} alConfirmar={() => admin.mutate(undefined)} />}
        {u.activo
          ? !esYo && <Confirmar pequeno variante="peligro" etiqueta="Quitar acceso" pregunta={`${u.nombre} perderá el acceso a este negocio de inmediato.`} alConfirmar={() => desactivar.mutate(undefined)} />
          : <Confirmar pequeno etiqueta="Devolver acceso" pregunta={`${u.nombre} podrá volver a entrar a este negocio.`} alConfirmar={() => activar.mutate(undefined)} />}
      </div>
    </li>
  );
}

/** Valor promedio de un servicio, en pesos. Se guarda por fila; vacío lo quita. */
function FilaValor({ s }: { s: Servicio }) {
  const [valor, setValor] = useState(s.valor === null ? "" : String(s.valor));
  const m = useAccion((v: number | null) => api.admin.valorServicio(s.id, v), { ok: "Valor guardado" });
  const nuevo = valor.trim() === "" ? null : Math.round(Number(valor));
  const cambio = nuevo !== s.valor && (nuevo === null || (Number.isFinite(nuevo) && nuevo >= 0));
  function enviar(e: FormEvent) { e.preventDefault(); if (cambio) m.mutate(nuevo); }
  return (
    <li className="px-4 py-2.5">
      {/* Una fila compacta: nombre a la izquierda, valor en pesos a la derecha; "Guardar" solo se activa si cambió. */}
      <form onSubmit={enviar} aria-label={`Valor de ${s.nombre}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <label htmlFor={`valor-${s.id}`} className="min-w-0 flex-1 text-sm font-medium">{s.nombre}
          <span className="block text-xs font-normal text-tinta-suave">{s.valor === null ? "Sin valor configurado" : `Guardado: ${pesos(s.valor)}`}</span></label>
        <div className="flex items-center gap-2">
          <div className="relative w-36">
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-tinta-suave" aria-hidden>$</span>
            <input id={`valor-${s.id}`} aria-label={s.nombre} type="number" inputMode="numeric" min={0} step={1000} placeholder="Sin valor" value={valor} onChange={(e) => setValor(e.target.value)}
              className="w-full rounded-[var(--radius-control)] border border-zinc-300 bg-papel py-1.5 pl-6 pr-2 text-right text-sm tabular-nums text-tinta placeholder:text-zinc-500" />
          </div>
          <Boton type="submit" pequeno variante={cambio ? "primario" : "secundario"} disabled={!cambio || m.isPending}>Guardar</Boton>
        </div>
      </form>
    </li>
  );
}

function ValorServicios() {
  const q = useServicios();
  return (
    <section aria-label="Valor de los servicios" className="space-y-2">
      <h2 className="text-sm font-semibold">Valor de los servicios</h2>
      <p className="text-sm text-tinta-suave">Se usa para estimar el dinero perdido por inasistencias y cancelaciones tardías. Es un valor promedio, no una factura.</p>
      <Consulta q={q}>{(ss) => <Tarjeta><ul className="divide-y divide-linea">{ss.map((s) => <FilaValor key={`${s.id}-${s.valor}`} s={s} />)}</ul></Tarjeta>}</Consulta>
    </section>
  );
}

// Tasas: se escriben como porcentaje entero (15 = 0.15); el dinero, en pesos. Vacío quita la meta.
const METAS_CAMPOS = [
  { clave: "inasistencia", limite: "max", etiqueta: "Inasistencia máxima (%)", tasa: true },
  { clave: "asistencia", limite: "min", etiqueta: "Asistencia mínima (%)", tasa: true },
  { clave: "confirmacion", limite: "min", etiqueta: "Confirmación mínima (%)", tasa: true },
  { clave: "dinero_perdido", limite: "max", etiqueta: "Dinero perdido máximo ($)", tasa: false },
] as const;

function MetasForm({ actuales }: { actuales: Record<string, Record<string, number>> }) {
  const inicial = (c: (typeof METAS_CAMPOS)[number]) => { const v = actuales[c.clave]?.[c.limite]; return v === undefined ? "" : String(c.tasa ? Math.round(v * 1000) / 10 : v); };
  const [campos, setCampos] = useState<Record<string, string>>(() => Object.fromEntries(METAS_CAMPOS.map((c) => [c.clave, inicial(c)])));
  const m = useAccion(api.admin.fijarMetas, { ok: "Metas guardadas" });
  function enviar(e: FormEvent) {
    e.preventDefault();
    const metas: Record<string, Record<string, number>> = {};
    for (const c of METAS_CAMPOS) {
      const v = campos[c.clave].trim();
      if (v !== "") metas[c.clave] = { [c.limite]: c.tasa ? Number(v) / 100 : Math.round(Number(v)) };
    }
    m.mutate(metas as Metas);
  }
  return (
    <Tarjeta className="p-4">
      <form onSubmit={enviar} aria-label="Metas de indicadores" className="grid gap-3 sm:grid-cols-2">
        {m.error instanceof ApiError && <div className="sm:col-span-2"><Aviso>{m.error.mensaje}</Aviso></div>}
        {METAS_CAMPOS.map((c) => (
          <Entrada key={c.clave} etiqueta={c.etiqueta} type="number" inputMode="decimal" min={0} max={c.tasa ? 100 : undefined} step={c.tasa ? "any" : 1000}
            placeholder="Sin meta" value={campos[c.clave]} onChange={(e) => setCampos({ ...campos, [c.clave]: e.target.value })} />))}
        <div className="sm:col-span-2"><Boton type="submit" disabled={m.isPending}>Guardar metas</Boton></div>
      </form>
    </Tarjeta>
  );
}

function MetasSeccion() {
  const q = useQuery({ queryKey: ["admin", "metas"], queryFn: api.admin.metas });
  return (
    <section aria-label="Metas de indicadores" className="space-y-2">
      <h2 className="text-sm font-semibold">Metas de indicadores</h2>
      <p className="text-sm text-tinta-suave">Cada meta aparece en su tarjeta de Indicadores con “Cumple” o “No cumple”. Déjala vacía para no tener meta.</p>
      <Consulta q={q}>{(a) => <MetasForm actuales={a} />}</Consulta>
    </section>
  );
}

export function Administracion() {
  const { sesion } = useSesion();
  const q = useQuery({ queryKey: ["admin", "usuarios"], queryFn: api.admin.usuarios });
  const [emitida, setEmitida] = useState<{ usuario: string; clave: string | null } | null>(null);
  const emitir = (usuario: string, clave: string | null) => setEmitida({ usuario, clave });
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold">Administración</h1>
      <p className="text-sm text-tinta-suave">Personas con acceso a {sesion.negocio?.nombre}. Solo ves y gestionas las de este negocio.</p>
      <NuevoUsuarioForm alEmitir={emitir} />
      <Consulta q={q}>
        {(us) => (
          <Tarjeta><ul aria-label="Usuarios" className="divide-y divide-linea">{us.map((u) => <Fila key={u.acceso_id} u={u} yo={sesion.usuario} alEmitir={emitir} />)}</ul></Tarjeta>
        )}
      </Consulta>
      <ValorServicios />
      <MetasSeccion />
      {emitida && <ClaveEmitida usuario={emitida.usuario} clave={emitida.clave} alCerrar={() => setEmitida(null)} />}
    </div>
  );
}
