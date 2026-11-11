import { useState } from "react";
import type { Modelo } from "../api/tipos";
import { Enlace, rutaDeJunta } from "../enrutador";
import { nombreTipo } from "../utilidades/metricas";
import { useInferencia } from "../hooks/useInferencia";
import { useSesion } from "../hooks/useSesion";
import CargadorImagen from "./CargadorImagen";
import EstadoTrabajo from "./EstadoTrabajo";
import { Flecha } from "./Navegacion";
import PideIngreso from "./PideIngreso";
import ResultadoInferencia from "./ResultadoInferencia";

/** Subir un estudio y analizarlo con este modelo. Vive en la columna de la ficha. */
export default function AnalizarEstudio({ modelo }: { modelo: Modelo }) {
  const { sesion, conLogin } = useSesion();
  const inferencia = useInferencia();
  const [archivo, setArchivo] = useState<File | null>(null);

  const cabecera = (
    <header className="panel-cabecera">
      <h2>Analizar un estudio</h2>
      <p className="suave">Modelo: {modelo.nombre_visible ?? modelo.nombre} · v{modelo.version}</p>
    </header>
  );

  if (conLogin && sesion === null) {
    return (
      <aside className="panel panel-analizar">
        {cabecera}
        <PideIngreso compacto texto="Ingresá con tu cuenta de institución para analizar estudios con este modelo." />
      </aside>
    );
  }

  if (modelo.estado_evaluacion === "error") {
    return (
      <aside className="panel panel-analizar">
        {cabecera}
        <p className="suave">Este modelo no se puede usar: su evaluación no terminó.</p>
      </aside>
    );
  }

  const terminado = inferencia.etapa === "ok" || inferencia.etapa === "error";
  const puedeAnalizar = archivo !== null && !inferencia.enCurso;

  const elegir = (nuevo: File | null) => {
    setArchivo(nuevo);
    inferencia.reiniciar();
  };

  return (
    <aside className="panel panel-analizar">
      {cabecera}

      {modelo.estado_evaluacion !== "ok" && (
        <p className="nota-suave">
          Todavía no tiene accuracy medida: la predicción va a llegar sin ese contexto.
        </p>
      )}

      <CargadorImagen
        archivo={archivo}
        tipoEstudio={modelo.tipo_estudio}
        deshabilitado={inferencia.enCurso}
        onSeleccionar={elegir}
        onQuitar={() => elegir(null)}
      />

      {!terminado && (
        <button
          type="button"
          className="pildora pildora-oscura ancha"
          disabled={!puedeAnalizar}
          onClick={() => archivo && void inferencia.ejecutar(archivo, modelo)}
        >
          {inferencia.enCurso ? "Analizando…" : "Analizar"} {!inferencia.enCurso && <Flecha />}
        </button>
      )}

      <EstadoTrabajo etapa={inferencia.etapa} trabajo={inferencia.trabajo} />

      {inferencia.etapa === "error" && inferencia.error && inferencia.trabajo?.estado !== "error" && (
        <div className="caja-error" role="alert">
          {inferencia.error}
        </div>
      )}

      {inferencia.trabajo && terminado && (
        <div>
          <p className="suave">Resultado de {modelo.nombre_visible ?? modelo.nombre} · v{modelo.version}</p>
          <ResultadoInferencia trabajo={inferencia.trabajo} />
        </div>
      )}

      {terminado && (
        <button type="button" className="pildora pildora-borde ancha" onClick={() => elegir(null)}>
          Analizar otro estudio
        </button>
      )}

      {modelo.estado_evaluacion === "ok" && (
        <p className="ayuda">
          ¿Querés más de una opinión?{" "}
          <Enlace a={rutaDeJunta({ con: modelo.id })}>Consultá a una junta</Enlace> con este y otros modelos de{" "}
          {nombreTipo(modelo.tipo_estudio)}: cada uno analiza la imagen y el informe marca si coinciden.
        </p>
      )}

      <p className="letra-chica">
        Orientativo. No reemplaza el criterio clínico. El estudio se borra a los 7 días.
      </p>
    </aside>
  );
}
