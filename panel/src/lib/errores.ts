// Qué hace el panel con cada `codigo` de error de la API (PRD #3 §6.2). El `mensaje` se muestra tal cual.
export type Comportamiento =
  | "iniciar_sesion" // no_autenticado
  | "mensaje_inicio" // credenciales_invalidas, inicio_bloqueado
  | "no_disponible" // sin_permiso, no_existe
  | "recargar_espacios" // espacio_ocupado
  | "conflicto_bloqueo" // bloqueo_con_citas
  | "recargar_dato" // desenlace_anticipado, no_reversible, transicion_invalida, bloqueo_pasado
  | "mensaje_formulario" // datos_invalidos, bloqueo_invalido, clave_invalida, documento_existente
  | "generico"; // cualquier otro, o fallo de red

const TABLA: Record<string, Comportamiento> = {
  no_autenticado: "iniciar_sesion",
  credenciales_invalidas: "mensaje_inicio",
  inicio_bloqueado: "mensaje_inicio",
  sin_permiso: "no_disponible",
  no_existe: "no_disponible",
  espacio_ocupado: "recargar_espacios",
  bloqueo_con_citas: "conflicto_bloqueo",
  desenlace_anticipado: "recargar_dato",
  no_reversible: "recargar_dato",
  transicion_invalida: "recargar_dato",
  bloqueo_pasado: "recargar_dato",
  datos_invalidos: "mensaje_formulario",
  bloqueo_invalido: "mensaje_formulario",
  clave_invalida: "mensaje_formulario",
  documento_existente: "mensaje_formulario",
};

export const comportamientoDe = (codigo: string): Comportamiento => TABLA[codigo] ?? "generico";
