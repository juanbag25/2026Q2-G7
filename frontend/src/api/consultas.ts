import { get, post } from "./cliente";
import type { Consulta, SolicitudConsulta } from "./tipos";

/** Arma la junta: un trabajo por modelo en la cola, todos sobre el mismo estudio (202). */
export function crear(solicitud: SolicitudConsulta): Promise<Consulta> {
  return post<Consulta>("/consultas", solicitud);
}

/** Cada modelo por separado y, cuando terminaron todos, el informe de consenso. */
export function obtener(id: string): Promise<Consulta> {
  return get<Consulta>(`/consultas/${encodeURIComponent(id)}`);
}
