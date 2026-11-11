// La sesión de Cognito del lado del navegador: los pasos 2, 5 y 6 del login.
//
//   2. ingresar() (o crearCuenta()) manda al Hosted UI con un `state` al azar,
//      que empieza con el cliente (ingreso, institucion o publicador): la Lambda
//      lo usa para saber con qué cliente de Cognito canjear el código.
//   3-4. Cognito vuelve a GET /callback de API Gateway; la Lambda canjea el
//        código y redirige acá con los tokens en el fragmento (#access_token=…).
//   5. recibirDelCallback() los lee, comprueba el `state`, los guarda en
//      localStorage y borra el fragmento de la barra y del historial.
//   6. tokenDeAcceso() es lo que cliente.ts manda en cada pedido.
//
// Sin refresh token: cuando el access token vence (una hora), la sesión se
// cierra y el botón «Ingresar» vuelve a pasar por Cognito, que todavía recuerda
// al usuario y no pide la contraseña. Lo mismo después de elegir el tipo de
// cuenta: el token que hay es de antes, y otra vuelta trae uno con el grupo.

import { clienteDeIngreso, configuracion } from "./configuracion";
import type { ClienteCognito, TipoCuenta } from "./configuracion";

export interface Sesion {
  accessToken: string;
  idToken: string;
  /** Epoch en ms. Con 30 s de margen respecto del vencimiento real. */
  expira: number;
  email: string | null;
  /** Los grupos de Cognito: medico, admin_institucion, publicador, admin_plataforma. */
  grupos: string[];
}

const CLAVE_SESION = "ateneo:sesion";
const CLAVE_ESTADO = "ateneo:login-estado"; // sessionStorage: solo esta pestaña
const CLAVE_VOLVER = "ateneo:login-volver";
const CLAVE_AVISO = "ateneo:login-aviso"; // un aviso que sobrevive a la vuelta por Cognito

const oyentes = new Set<() => void>();
let sesion: Sesion | null = leerGuardada();

function leerGuardada(): Sesion | null {
  try {
    const valor = JSON.parse(window.localStorage.getItem(CLAVE_SESION) ?? "null") as Sesion | null;
    if (valor && typeof valor.accessToken === "string" && valor.expira > Date.now()) {
      return { ...valor, grupos: Array.isArray(valor.grupos) ? valor.grupos : [] };
    }
  } catch {
    // Almacenamiento bloqueado o valor roto: sin sesión.
  }
  return null;
}

function cambiar(nueva: Sesion | null): void {
  sesion = nueva;
  try {
    if (nueva) window.localStorage.setItem(CLAVE_SESION, JSON.stringify(nueva));
    else window.localStorage.removeItem(CLAVE_SESION);
  } catch {
    // Modo privado: la sesión vale mientras la pestaña esté abierta.
  }
  for (const oyente of oyentes) oyente();
}

export function suscribirSesion(oyente: () => void): () => void {
  oyentes.add(oyente);
  return () => oyentes.delete(oyente);
}

/** La sesión tal como está; no la vence (sirve de snapshot para React). */
export function sesionActual(): Sesion | null {
  return sesion;
}

/** El access token vigente, o null. Si venció, cierra la sesión. */
export function tokenDeAcceso(): string | null {
  if (sesion && sesion.expira <= Date.now()) cambiar(null);
  return sesion?.accessToken ?? null;
}

/** La API contestó 401: el token ya no sirve (vencido, revocado o de otro pool). */
export function descartarSesion(): void {
  if (sesion) cambiar(null);
}

/** El sitio no es HTTPS: no hay crypto.randomUUID, pero getRandomValues sí. */
function alAzar(): string {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Paso 2: al Hosted UI de Cognito, por la puerta `cliente`. Vuelve a la ruta actual después de
 * ingresar. El state empieza con el mismo cliente con el que se pide el código.
 */
function alHostedUI(pagina: "oauth2/authorize" | "signup", cliente: ClienteCognito): void {
  const cognito = configuracion().cognito;
  const clienteId = cognito?.clientes[cliente];
  if (!cognito || !clienteId) return;
  const estado = `${cliente}.${alAzar()}`;
  try {
    window.sessionStorage.setItem(CLAVE_ESTADO, estado);
    window.sessionStorage.setItem(CLAVE_VOLVER, window.location.pathname);
  } catch {
    // Sin sessionStorage no se puede comprobar el state: el ingreso va a fallar con un aviso.
  }
  const url = new URL(`${cognito.dominio}/${pagina}`);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: clienteId,
    redirect_uri: cognito.callback,
    scope: "openid email profile",
    state: estado,
  }).toString();
  window.location.assign(url.toString());
}

/**
 * Cualquier cuenta entra por cualquiera de los clientes. «Ingresar» usa el suyo porque Cognito
 * muestra ahí el link «Sign up»: quien se registra desde ese link queda sin grupo y elige el tipo
 * dentro de la app (components/ElegirTipoCuenta.tsx), en vez de quedar en el de otro cliente.
 */
export function ingresar(): void {
  const cognito = configuracion().cognito;
  if (cognito) alHostedUI("oauth2/authorize", clienteDeIngreso(cognito));
}

/**
 * Otra vuelta por el login para traer un token nuevo, sin pedir la contraseña: la sesión de
 * Cognito dura una hora. `aviso` se muestra al volver.
 */
export function ingresarDeNuevo(aviso?: string): void {
  try {
    if (aviso) window.sessionStorage.setItem(CLAVE_AVISO, aviso);
  } catch {
    // Sin sessionStorage el aviso se pierde; el ingreso igual trae el grupo que haya.
  }
  ingresar();
}

/** El aviso que dejó ingresarDeNuevo(), una sola vez. */
export function tomarAviso(): string | null {
  try {
    const aviso = window.sessionStorage.getItem(CLAVE_AVISO);
    window.sessionStorage.removeItem(CLAVE_AVISO);
    return aviso;
  } catch {
    return null;
  }
}

/** El registro de una institución o de un publicador: cada uno por su cliente, que da el grupo. */
export function crearCuenta(tipo: TipoCuenta): void {
  alHostedUI("signup", tipo);
}

/** Borra la sesión local y la de Cognito, que vuelve al sitio por /logout. */
export function salir(): void {
  cambiar(null);
  const cognito = configuracion().cognito;
  if (!cognito) return;
  const url = new URL(`${cognito.dominio}/logout`);
  url.search = new URLSearchParams({
    client_id: cognito.clientes[clienteDeIngreso(cognito)] ?? cognito.clientes.publicador,
    logout_uri: cognito.logout,
  }).toString();
  window.location.assign(url.toString());
}

/** Los claims del id token, solo para mostrarlos: la firma la comprueba la API, no el navegador. */
function claimsDe(idToken: string): Record<string, unknown> {
  try {
    const parte = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const binario = window.atob(parte.padEnd(Math.ceil(parte.length / 4) * 4, "="));
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(binario, (c) => c.charCodeAt(0))));
  } catch {
    return {};
  }
}

/**
 * Paso 5. Se llama una vez al arrancar. Si la URL trae la vuelta del login,
 * guarda los tokens y limpia la URL. Devuelve un mensaje si el ingreso falló.
 */
export function recibirDelCallback(): string | null {
  const fragmento = new URLSearchParams(window.location.hash.slice(1));
  if (!fragmento.has("access_token") && !fragmento.has("error")) return null;

  let esperado: string | null = null;
  let volver = "/";
  try {
    esperado = window.sessionStorage.getItem(CLAVE_ESTADO);
    volver = window.sessionStorage.getItem(CLAVE_VOLVER) ?? "/";
    window.sessionStorage.removeItem(CLAVE_ESTADO);
    window.sessionStorage.removeItem(CLAVE_VOLVER);
  } catch {
    // Sin sessionStorage: esperado queda null y el ingreso se rechaza abajo.
  }
  // Los tokens no quedan en la barra, ni en el historial, ni en un enlace copiado.
  window.history.replaceState(null, "", volver);

  if (fragmento.has("error")) {
    return `No se pudo ingresar: ${fragmento.get("error_description") || fragmento.get("error")}.`;
  }
  // Un state que no pedimos es un login que no empezó en esta pestaña: se descarta.
  if (esperado === null || fragmento.get("state") !== esperado) {
    return "No se pudo ingresar: la respuesta no corresponde a un ingreso iniciado en esta pestaña. Probá de nuevo.";
  }

  const idToken = fragmento.get("id_token") ?? "";
  const claims = claimsDe(idToken);
  const grupos = claims["cognito:groups"];
  const segundos = Number(fragmento.get("expires_in") ?? "3600");
  cambiar({
    accessToken: fragmento.get("access_token") ?? "",
    idToken,
    expira: Date.now() + (Number.isFinite(segundos) ? segundos : 3600) * 1000 - 30_000,
    email: typeof claims.email === "string" ? claims.email : null,
    grupos: Array.isArray(grupos) ? grupos.filter((g): g is string => typeof g === "string") : [],
  });
  return null;
}
