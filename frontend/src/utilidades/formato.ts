// Ayudas de presentación compartidas por varios componentes.

/** 0.9134 → "91,3 %" (o "91.3 %" según el locale del navegador). */
export function porcentaje(valor: number, decimales = 1): string {
  return `${(valor * 100).toLocaleString(undefined, {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })} %`;
}

/** Número con hasta `decimales` decimales, sin ceros de relleno. */
export function numero(valor: number, decimales = 3): string {
  return valor.toLocaleString(undefined, { maximumFractionDigits: decimales });
}

/** ISO (UTC) → fecha y hora en el huso horario del navegador. */
export function fechaLocal(iso: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return fecha.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "nombre · vversion · tipo_estudio", igual en el selector y en el panel de publicación. */
export function etiquetaModelo(m: { nombre: string; version: string; tipo_estudio: string }): string {
  return `${m.nombre} · v${m.version} · ${m.tipo_estudio}`;
}

/** "sha256:abcdef0123456789..." → "abcdef012345". */
export function hashCorto(hash: string, largo = 12): string {
  const sinPrefijo = hash.startsWith("sha256:") ? hash.slice("sha256:".length) : hash;
  return sinPrefijo.slice(0, largo);
}

/** Primer tramo de un UUID, para mostrar sin ocupar toda la línea. */
export function idCorto(id: string, largo = 8): string {
  return id.length > largo ? `${id.slice(0, largo)}…` : id;
}

export function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function duracion(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Un mensaje de la API como oración: mayúscula al principio y punto al final, si le faltan. */
export function oracion(texto: string): string {
  const limpio = texto.trim();
  if (!limpio) return limpio;
  const conMayuscula = limpio[0].toUpperCase() + limpio.slice(1);
  return /[.!?…]$/.test(conMayuscula) ? conMayuscula : `${conMayuscula}.`;
}
