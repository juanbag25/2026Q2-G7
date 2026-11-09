// Ruteo del lado del cliente, sin librerías.
//
// El backend (sitio.py) y el bucket web (error_document) devuelven index.html para
// cualquier ruta fuera de /api, así que History API alcanza. Si algún día entra
// react-router, lo único que cambia es este archivo y el componente Enlace.

import { useSyncExternalStore } from "react";
import type { MouseEvent, ReactNode } from "react";

export type Ruta =
  | { vista: "inicio" }
  | { vista: "modelos" }
  | { vista: "modelo"; id: string }
  | { vista: "junta" }
  | { vista: "publicar" };

const FICHA = /^\/modelos\/([^/]+)$/;

/** Cualquier ruta desconocida cae en el inicio. /consulta quedó de la versión anterior. */
export function leerRuta(pathname: string): Ruta {
  const limpia = pathname.replace(/\/+$/, "") || "/";
  if (limpia === "/modelos" || limpia === "/consulta") return { vista: "modelos" };
  if (limpia === "/publicar") return { vista: "publicar" };
  if (limpia === "/junta") return { vista: "junta" };
  const ficha = FICHA.exec(limpia);
  if (ficha) return { vista: "modelo", id: decodeURIComponent(ficha[1]) };
  return { vista: "inicio" };
}

export function rutaDeModelo(id: string): string {
  return `/modelos/${encodeURIComponent(id)}`;
}

/** La junta, con un modelo ya elegido (desde su ficha) o un tipo de estudio (desde el catálogo). */
export function rutaDeJunta(desde: { con?: string; tipo?: string | null } = {}): string {
  const q = new URLSearchParams();
  if (desde.con) q.set("con", desde.con);
  if (desde.tipo) q.set("tipo", desde.tipo);
  const texto = q.toString();
  return texto ? `/junta?${texto}` : "/junta";
}

const oyentes = new Set<() => void>();

function avisar(): void {
  for (const oyente of oyentes) oyente();
}

function suscribir(oyente: () => void): () => void {
  oyentes.add(oyente);
  window.addEventListener("popstate", avisar);
  return () => {
    oyentes.delete(oyente);
    if (oyentes.size === 0) window.removeEventListener("popstate", avisar);
  };
}

const leer = (): string => window.location.pathname;

/** El pathname actual; se re-renderiza al navegar o al usar atrás/adelante. */
export function useCamino(): string {
  return useSyncExternalStore(suscribir, leer, () => "/");
}

export function useRuta(): Ruta {
  return leerRuta(useCamino());
}

export function navegar(camino: string): void {
  if (window.location.pathname === camino) return;
  window.history.pushState({}, "", camino);
  window.scrollTo({ top: 0 });
  avisar();
}

interface PropsEnlace {
  a: string;
  className?: string;
  /** Marca el enlace como actual también en las rutas que cuelgan de él (/modelos/…). */
  prefijo?: boolean;
  children: ReactNode;
}

/** <a> real (se puede abrir en otra pestaña) que navega sin recargar. */
export function Enlace({ a, className, prefijo = false, children }: PropsEnlace) {
  const actual = useCamino();
  const esActual = actual === a || (prefijo && actual.startsWith(`${a}/`));

  const alHacerClic = (e: MouseEvent<HTMLAnchorElement>) => {
    // Ctrl/Cmd/Shift o botón del medio: que lo maneje el navegador.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return;
    }
    e.preventDefault();
    navegar(a);
  };

  return (
    <a href={a} className={className} aria-current={esActual ? "page" : undefined} onClick={alHacerClic}>
      {children}
    </a>
  );
}
