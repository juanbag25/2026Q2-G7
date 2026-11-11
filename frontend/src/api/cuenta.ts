import { get, post } from "./cliente";
import type { TipoCuenta } from "./configuracion";

export interface TipoCuentaElegido {
  tipo: TipoCuenta;
  /** El grupo de Cognito en el que quedó: admin_institucion o publicador. */
  grupo: string;
}

export interface EstadoCuenta {
  /** null si todavía no eligió, o si es de médico o de admin. */
  tipo: TipoCuenta | null;
  /** Los grupos que tiene en Cognito ahora, que pueden no ser los del token. */
  grupos: string[];
}

/** GET /api/cuenta/tipo: lo que la cuenta ya tiene, para no preguntar algo ya respondido. */
export function leerTipoCuenta(): Promise<EstadoCuenta> {
  return get<EstadoCuenta>("/cuenta/tipo");
}

/**
 * POST /api/cuenta/tipo, una sola vez por cuenta. 409 si ya tiene otro tipo (en Cognito, o
 * elegido en otra pestaña). El token no cambia: para usar el grupo hay que volver a ingresar.
 */
export function elegirTipoCuenta(tipo: TipoCuenta): Promise<TipoCuentaElegido> {
  return post<TipoCuentaElegido>("/cuenta/tipo", { tipo });
}
