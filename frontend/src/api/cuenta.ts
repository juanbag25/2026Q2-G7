import { post } from "./cliente";
import type { TipoCuenta } from "./configuracion";

export interface TipoCuentaElegido {
  tipo: TipoCuenta;
  /** El grupo de Cognito en el que quedó: admin_institucion o publicador. */
  grupo: string;
}

/**
 * POST /api/cuenta/tipo, una sola vez por cuenta. 409 si ya tiene otro tipo (en Cognito, o
 * elegido en otra pestaña). El token no cambia: para usar el grupo hay que volver a ingresar.
 */
export function elegirTipoCuenta(tipo: TipoCuenta): Promise<TipoCuentaElegido> {
  return post<TipoCuentaElegido>("/cuenta/tipo", { tipo });
}
