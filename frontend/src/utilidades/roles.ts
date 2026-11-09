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

/** «Tu cuenta es de …»: para explicarle a alguien por qué no ve una sección. */
export function tuCuenta(grupos: readonly string[]): string {
  if (grupos.length === 0) return "Tu cuenta todavía no tiene un rol asignado: avisale a la administración de Ateneo.";
  return `Tu cuenta es de ${grupos.map((g) => NOMBRES[g] ?? g).join(" y ")}.`;
}
