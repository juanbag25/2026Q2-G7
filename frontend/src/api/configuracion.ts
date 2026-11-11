/**
 * Lo que el sitio sabe de la infraestructura. En AWS lo escribe Terraform en
 * /config.json, al lado del index.html del bucket web (terraform/config.tf):
 * así el mismo build sirve para cualquier cuenta y no hay que recompilar
 * cuando cambia la dirección de API Gateway.
 *
 * Sin ese archivo (docker compose, `npm run dev`) la API es relativa, del mismo
 * origen, y no hay login.
 */

/** Quien se registra solo elige qué es; médicos e integrantes llegan por invitación. */
export type TipoCuenta = "publicador" | "institucion";

/** Las puertas al Hosted UI: «Ingresar» y crear cuenta de cada tipo. */
export type ClienteCognito = TipoCuenta | "ingreso";

export interface ConfigCognito {
  /** https://<prefijo>.auth.<región>.amazoncognito.com */
  dominio: string;
  /**
   * Un cliente de Cognito por puerta. Los de cada tipo dan su grupo al registrarse: la Lambda
   * de post-confirmación ve por cuál entró el usuario. El de «Ingresar» no da ninguno: quien se
   * registra desde ahí elige el tipo dentro de la app. Un config.json anterior al tercer
   * cliente no trae `ingreso`.
   */
  clientes: Record<TipoCuenta, string> & { ingreso?: string };
  /** GET /callback de API Gateway: el redirect_uri que canjea la Lambda. */
  callback: string;
  /** GET /logout de API Gateway: rebota al sitio. */
  logout: string;
}

export interface Configuracion {
  /** Origen de la API, sin barra final. "" = el mismo del sitio. */
  api: string;
  /** null = sin login: todos los pedidos van sin token. */
  cognito: ConfigCognito | null;
}

let actual: Configuracion = { api: "", cognito: null };

function esCognito(valor: unknown): valor is ConfigCognito {
  if (typeof valor !== "object" || valor === null) return false;
  const v = valor as Record<string, unknown>;
  const clientes = v.clientes as Record<string, unknown> | null | undefined;
  return (
    ["dominio", "callback", "logout"].every((k) => typeof v[k] === "string") &&
    typeof clientes === "object" &&
    clientes !== null &&
    typeof clientes.publicador === "string" &&
    typeof clientes.institucion === "string" &&
    (clientes.ingreso === undefined || typeof clientes.ingreso === "string")
  );
}

/**
 * El cliente del botón «Ingresar»: el suyo, cuyo «Sign up» no da grupo. Con un config.json
 * anterior al tercer cliente, el de publicador, como antes.
 */
export function clienteDeIngreso(cognito: ConfigCognito): ClienteCognito {
  return cognito.clientes.ingreso ? "ingreso" : "publicador";
}

/** Se llama una vez, antes de pintar. Si falla, queda la configuración local. */
export async function cargarConfiguracion(): Promise<void> {
  try {
    const respuesta = await fetch("/config.json", { cache: "no-store" });
    // En local el backend (o Vite) contesta index.html para lo que no existe: no es JSON.
    if (!respuesta.ok || !(respuesta.headers.get("content-type") ?? "").includes("json")) return;
    const cuerpo = (await respuesta.json()) as Record<string, unknown>;
    actual = {
      api: typeof cuerpo.api === "string" ? cuerpo.api.replace(/\/+$/, "") : "",
      cognito: esCognito(cuerpo.cognito) ? cuerpo.cognito : null,
    };
  } catch {
    // Sin red o JSON roto: seguimos como en local.
  }
}

export function configuracion(): Configuracion {
  return actual;
}
