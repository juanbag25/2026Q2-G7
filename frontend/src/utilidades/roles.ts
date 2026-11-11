// Qué hace cada grupo de Cognito: espejo de backend/app/dominio/usuario.py. La interfaz solo
// esconde lo que no corresponde; la que decide es la API, que contesta 403 si igual llega el pedido.

/** /api/modelos/*: subir, publicar y seguir modelos. */
export const PUBLICAN: readonly string[] = ["publicador", "admin_plataforma"];
/** /api/estudios, /api/inferencias, /api/trabajos: analizar estudios. */
export const CONSULTAN: readonly string[] = ["medico", "admin_institucion", "admin_plataforma"];

const NOMBRES: Record<string, string> = {
  medico: "médico",
  admin_institucion: "institución",
  publicador: "publicador",
  admin_plataforma: "administración de Ateneo",
};

export function tieneAlguno(grupos: readonly string[], requeridos: readonly string[]): boolean {
  return grupos.some((g) => requeridos.includes(g));
}

/**
 * Qué hacer cuando el token dice que la cuenta no tiene grupos, según los que tiene en Cognito
 * ahora (GET /api/cuenta/tipo). Si ya tiene alguno, el token es de antes de elegir: se trae uno
 * nuevo. Si esta carga ya es la vuelta de ese pedido, se avisa en vez de volver al login, que
 * daría vueltas sin fin.
 */
export function antesDePreguntar(
  gruposReales: readonly string[],
  trasRefrescar: boolean,
): "preguntar" | "refrescar" | "avisar" {
  if (gruposReales.length === 0) return "preguntar";
  return trasRefrescar ? "avisar" : "refrescar";
}

/** «Tu cuenta es de …»: para explicarle a alguien por qué no ve una sección. */
export function tuCuenta(grupos: readonly string[]): string {
  if (grupos.length === 0) return "Tu cuenta todavía no tiene un rol: elegí si es de una institución o de un publicador.";
  return `Tu cuenta es de ${grupos.map((g) => NOMBRES[g] ?? g).join(" y ")}.`;
}
