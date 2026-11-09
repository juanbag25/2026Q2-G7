import type { Modelo } from "../api/tipos";
import { numero, porcentaje } from "../utilidades/formato";
import { leerNumero } from "../utilidades/metricas";

export const MINIMO_JUNTA = 2;
export const MAXIMO_JUNTA = 5; // los mismos límites que el backend (dominio/consulta.py)

/** La métrica con la que el modelo pesa en el consenso: AUC si se midió, si no accuracy. */
export function pesoVisible(m: Modelo): string | null {
  if (m.estado_evaluacion !== "ok") return null;
  const auc = leerNumero(m.metricas, "auc");
  if (auc !== null) return `AUC ${numero(auc, 3)}`;
  return m.accuracy !== null ? `Accuracy ${porcentaje(m.accuracy)}` : null;
}

interface Props {
  /** Los modelos publicados del tipo de estudio elegido. */
  modelos: Modelo[];
  elegidos: string[];
  deshabilitado?: boolean;
  onCambiar: (elegidos: string[]) => void;
}

/** Elegir de 2 a 5 modelos evaluados. Los que no tienen evaluación verificada no entran a la junta. */
export default function SelectorJunta({ modelos, elegidos, deshabilitado = false, onCambiar }: Props) {
  const lleno = elegidos.length >= MAXIMO_JUNTA;

  const alternar = (id: string) => {
    onCambiar(elegidos.includes(id) ? elegidos.filter((e) => e !== id) : [...elegidos, id]);
  };

  return (
    <fieldset className="selector-junta" disabled={deshabilitado}>
      <legend className="sr-solo">Modelos de la junta</legend>
      <ul>
        {modelos.map((m) => {
          const peso = pesoVisible(m);
          const marcado = elegidos.includes(m.id);
          const bloqueado = peso === null || (lleno && !marcado);
          return (
            <li key={m.id}>
              <label className={`opcion-junta${marcado ? " marcada" : ""}${bloqueado ? " bloqueada" : ""}`}>
                <input type="checkbox" checked={marcado} disabled={bloqueado} onChange={() => alternar(m.id)} />
                <span className="opcion-nombre">
                  {m.nombre_visible ?? m.nombre} <span className="version">v{m.version}</span>
                </span>
                <span className="opcion-peso">
                  {peso ?? (m.estado_evaluacion === "error" ? "La evaluación falló" : "Esperando la evaluación")}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      <p className="ayuda">
        {elegidos.length} de {MAXIMO_JUNTA} como máximo · hacen falta al menos {MINIMO_JUNTA}. Cada modelo pesa en el
        consenso según su métrica verificada.
      </p>
    </fieldset>
  );
}
