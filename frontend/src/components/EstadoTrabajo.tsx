import type { Trabajo } from "../api/tipos";
import type { EtapaInferencia } from "../hooks/useInferencia";

const MAX_INTENTOS = 3; // MAX_INTENTOS del backend

/** Lo único que mira del trabajo; la junta le pasa el avance de toda la consulta. */
type Avance = Pick<Trabajo, "estado" | "intentos">;

interface Props {
  etapa: EtapaInferencia;
  trabajo: Avance | null;
}

type EstadoPaso = "pendiente" | "activo" | "hecho" | "error";

/** Índice del paso en curso según la etapa del hook y el estado del trabajo. */
function pasoActivo(etapa: EtapaInferencia, trabajo: Avance | null): number {
  switch (etapa) {
    case "idle":
      return -1;
    case "subiendo":
      return 0;
    case "encolando":
      return 1;
    case "esperando":
      return trabajo?.estado === "en_curso" ? 2 : 1;
    case "ok":
    case "error":
      return 3;
  }
}

/** Indicador de pasos: subida → cola → procesamiento → listo / error. */
export default function EstadoTrabajo({ etapa, trabajo }: Props) {
  if (etapa === "idle") return null;

  const nombres = ["Subiendo la imagen", "En cola", "Procesando", etapa === "error" ? "Error" : "Listo"];
  const activo = pasoActivo(etapa, trabajo);
  // Si falló sin llegar a tener trabajo, el error ocurrió antes de la cola.
  const indiceError = etapa === "error" ? (trabajo ? 3 : 0) : -1;

  const estadoDe = (i: number): EstadoPaso => {
    if (etapa === "error") {
      if (i === indiceError) return "error";
      return i < indiceError ? "hecho" : "pendiente";
    }
    if (etapa === "ok") return "hecho";
    if (i < activo) return "hecho";
    if (i === activo) return "activo";
    return "pendiente";
  };

  return (
    <div className="pasos" aria-live="polite">
      <ol>
        {nombres.map((nombre, i) => {
          const estado = estadoDe(i);
          return (
            <li key={nombre} className={`paso ${estado}`}>
              <span className="paso-marca" aria-hidden="true">
                {estado === "activo" ? <span className="spinner" /> : null}
              </span>
              <span className="paso-nombre">{nombre}</span>
            </li>
          );
        })}
      </ol>
      {trabajo && trabajo.intentos > 1 && (
        <p className="suave">
          intento {trabajo.intentos} de {MAX_INTENTOS}
        </p>
      )}
    </div>
  );
}
