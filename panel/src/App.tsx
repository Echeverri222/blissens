import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/pantallas/Layout";
import { Ingresar } from "@/pantallas/Ingresar";
import { Agenda } from "@/pantallas/Agenda";
import { MiHorario } from "@/pantallas/Horario";
import { Agendar } from "@/pantallas/Agendar";
import { Bandejas } from "@/pantallas/Bandejas";
import { Ficha, Pacientes } from "@/pantallas/Pacientes";
import { Indicadores } from "@/pantallas/Indicadores";
import { Sistema } from "@/pantallas/Sistema";
import { RutaProtegida } from "@/sesion/Sesion";
import { NoDisponible } from "@/ui/vistas";

/** Rutas por rol: escribir a mano la dirección de una sección ajena lleva al inicio del rol (la API impone el permiso). */
export function Rutas() {
  return (
    <Routes>
      <Route path="/ingresar" element={<Ingresar />} />
      <Route element={<RutaProtegida><Layout /></RutaProtegida>}>
        <Route path="/agenda" element={<Agenda />} />
        <Route path="/horario" element={<RutaProtegida roles={["especialista"]}><MiHorario /></RutaProtegida>} />
        <Route path="/agendar" element={<RutaProtegida roles={["auxiliar"]}><Agendar /></RutaProtegida>} />
        <Route path="/bandejas" element={<RutaProtegida roles={["auxiliar"]}><Bandejas /></RutaProtegida>} />
        <Route path="/pacientes" element={<RutaProtegida roles={["auxiliar"]}><Pacientes /></RutaProtegida>} />
        <Route path="/pacientes/:id" element={<RutaProtegida roles={["auxiliar"]}><Ficha /></RutaProtegida>} />
        <Route path="/indicadores" element={<RutaProtegida roles={["auxiliar"]}><Indicadores /></RutaProtegida>} />
        <Route path="/sistema" element={<RutaProtegida roles={["auxiliar"]}><Sistema /></RutaProtegida>} />
        <Route path="/no-disponible" element={<NoDisponible />} />
      </Route>
      <Route path="*" element={<Navigate to="/agenda" replace />} />
    </Routes>
  );
}
