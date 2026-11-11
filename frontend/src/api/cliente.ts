import { configuracion } from "./configuracion";
import { descartarSesion, tokenDeAcceso } from "./sesion";
import type { CuerpoError } from "./tipos";

/** En AWS, API Gateway (otro origen, HTTPS); en local, el mismo origen del sitio. */
function base(): string {
  return `${configuracion().api}/api`;
}

/**
 * Error de la API. `status` es el HTTP, `error` el código que manda el backend
 * y `detalle` el texto legible para mostrar en pantalla.
 */
export class ErrorApi extends Error {
  readonly status: number;
  readonly error: string;
  readonly detalle: string;

  constructor(status: number, error: string, detalle: string) {
    super(detalle);
    this.name = "ErrorApi";
    this.status = status;
    this.error = error;
    this.detalle = detalle;
  }
}

function esCuerpoError(valor: unknown): valor is CuerpoError {
  if (typeof valor !== "object" || valor === null) return false;
  const v = valor as Record<string, unknown>;
  return typeof v.error === "string" && typeof v.detalle === "string";
}

async function leerError(respuesta: Response): Promise<ErrorApi> {
  let cuerpo: unknown = null;
  try {
    cuerpo = await respuesta.json();
  } catch {
    // Sin cuerpo JSON (p. ej. un 502 del balanceador): usamos el status.
  }
  if (esCuerpoError(cuerpo)) {
    return new ErrorApi(respuesta.status, cuerpo.error, cuerpo.detalle);
  }
  return new ErrorApi(
    respuesta.status,
    `http_${respuesta.status}`,
    `La API respondió ${respuesta.status} ${respuesta.statusText}`.trim(),
  );
}

async function pedir<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  // Paso 6 del login: el access token de Cognito en cada pedido. API Gateway lo
  // valida antes de reenviar al backend, y el backend lo vuelve a validar.
  const headers = new Headers(init.headers);
  const token = tokenDeAcceso();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let respuesta: Response;
  try {
    respuesta = await fetch(base() + ruta, { ...init, headers });
  } catch (e) {
    const motivo = e instanceof Error ? e.message : String(e);
    throw new ErrorApi(0, "red", `No se pudo conectar con la API (${motivo})`);
  }
  if (respuesta.status === 401) {
    // Vencido o inválido: la pantalla vuelve a pedir el ingreso.
    descartarSesion();
    throw new ErrorApi(401, "no_autenticado", "Tu sesión venció. Ingresá de nuevo para seguir.");
  }
  if (respuesta.status === 403) {
    // La cuenta no tiene el rol de esta acción. No es la sesión: no se descarta. El backend ya
    // dice qué cuenta hace falta y cuál es la tuya; un 403 sin ese cuerpo (el WAF) lleva uno propio.
    const error = await leerError(respuesta);
    throw error.error === "sin_permiso"
      ? error
      : new ErrorApi(403, "prohibido", "La API rechazó el pedido (403). Si sigue pasando, avisale a la administración de Ateneo.");
  }
  if (!respuesta.ok) throw await leerError(respuesta);
  // 204 sin cuerpo: devolvemos undefined tipado como T.
  if (respuesta.status === 204) return undefined as unknown as T;
  return (await respuesta.json()) as T;
}

export function get<T>(ruta: string): Promise<T> {
  return pedir<T>(ruta, { headers: { Accept: "application/json" } });
}

export function post<T>(ruta: string, cuerpo: unknown): Promise<T> {
  return pedir<T>(ruta, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(cuerpo),
  });
}

/** Convierte cualquier excepción en un texto para mostrar. */
export function mensajeDeError(e: unknown): string {
  if (e instanceof ErrorApi) return e.detalle;
  if (e instanceof Error) return e.message;
  return String(e);
}
