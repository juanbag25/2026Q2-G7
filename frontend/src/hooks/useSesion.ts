import { useSyncExternalStore } from "react";
import { configuracion } from "../api/configuracion";
import { sesionActual, suscribirSesion } from "../api/sesion";
import type { Sesion } from "../api/sesion";
import { CONSULTAN, PUBLICAN, tieneAlguno } from "../utilidades/roles";

export interface EstadoSesion {
  sesion: Sesion | null;
  /** false en local, donde no hay Cognito. */
  conLogin: boolean;
  /** Sin login (local) se puede todo; con login, lo dicen los grupos. Sin sesión, false. */
  puedePublicar: boolean;
  puedeConsultar: boolean;
  /**
   * Los enlaces a «Publicar»: para quien publica y para quien todavía no ingresó (la puerta
   * para registrarse como publicador). No para quien ingresó con otra cuenta.
   */
  ofrecerPublicar: boolean;
}

/**
 * La sesión de Cognito y lo que su cuenta puede hacer; se re-renderiza al ingresar, salir o
 * cuando la API rechaza el token. La interfaz solo esconde: decide la API (403).
 */
export function useSesion(): EstadoSesion {
  const sesion = useSyncExternalStore(suscribirSesion, sesionActual, () => null);
  const conLogin = configuracion().cognito !== null;
  const grupos = sesion?.grupos ?? [];
  const puedePublicar = !conLogin || tieneAlguno(grupos, PUBLICAN);
  return {
    sesion,
    conLogin,
    puedePublicar,
    puedeConsultar: !conLogin || tieneAlguno(grupos, CONSULTAN),
    ofrecerPublicar: sesion === null || puedePublicar,
  };
}
