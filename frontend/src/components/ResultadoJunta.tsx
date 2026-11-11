import type { Consenso, Consulta, InferenciaJunta } from "../api/tipos";
import { numero, porcentaje } from "../utilidades/formato";
import ResultadoInferencia from "./ResultadoInferencia";

export const LEYENDA = "Herramienta de soporte a la decisión clínica. No reemplaza el criterio médico.";

function Barras({ probabilidades, destacada }: { probabilidades: Record<string, number>; destacada: string }) {
  const barras = Object.entries(probabilidades).sort(([, a], [, b]) => b - a);
  return (
    <ul className="barras">
      {barras.map(([etiqueta, p]) => (
        <li key={etiqueta} className={etiqueta === destacada ? "destacada" : undefined}>
          <span className="barra-etiqueta">{etiqueta}</span>
          <span className="barra-pista">
            <span className="barra-relleno" style={{ width: `${Math.max(0, Math.min(100, p * 100))}%` }} />
          </span>
          <span className="barra-valor">{porcentaje(p)}</span>
        </li>
      ))}
    </ul>
  );
}

/** El informe de consenso (spec §6.5): va arriba de todo, con la revisión prioritaria destacada. */
function InformeConsenso({ consenso, inferencias }: { consenso: Consenso; inferencias: InferenciaJunta[] }) {
  const coinciden = inferencias.filter((i) => i.coincide === true).length;
  const revisar = consenso.revision_prioritaria;
  return (
    <section className={`consenso${revisar ? " consenso-revisar" : ""}`} aria-live="polite">
      <header className="consenso-cabecera">
        <h3>Informe de consenso</h3>
        <span className={`pastilla ${revisar ? "estado-error" : "estado-ok"}`}>
          <span className="punto" />
          {revisar ? "Revisión prioritaria" : "Los modelos coinciden"}
        </span>
      </header>

      <div className="prediccion">
        <span className="prediccion-nombre">Consenso de {consenso.votos} modelos</span>
        <span className="prediccion-valor">{consenso.prediccion}</span>
      </div>

      <div className="acuerdo">
        <div className="acuerdo-cifras">
          <span className="acuerdo-valor">{porcentaje(consenso.acuerdo)}</span>
          <span className="suave">
            de acuerdo · {coinciden} de {consenso.votos} modelos coinciden con el consenso
          </span>
        </div>
        <span className="barra-pista acuerdo-pista">
          <span className="barra-relleno" style={{ width: `${Math.min(100, consenso.acuerdo * 100)}%` }} />
          <span className="acuerdo-umbral" style={{ left: `${consenso.umbral_acuerdo * 100}%` }} />
        </span>
      </div>

      {revisar && (
        <p className="nota-revisar">
          Los modelos no coinciden lo suficiente: el acuerdo ponderado está por debajo del{" "}
          {porcentaje(consenso.umbral_acuerdo, 0)}. Conviene revisar este estudio antes que otros.
        </p>
      )}

      <Barras probabilidades={consenso.probabilidades} destacada={consenso.prediccion} />

      <p className="letra-chica">
        Promedio de las probabilidades de cada modelo, ponderado por su métrica verificada contra el conjunto
        reservado. El acuerdo es la parte de ese peso que suman los modelos que coinciden con el consenso.
      </p>
    </section>
  );
}

function SinConsenso({ consulta }: { consulta: Consulta }) {
  const total = consulta.inferencias.length;
  const listas = consulta.inferencias.filter((i) => i.estado === "ok" || i.estado === "error").length;
  if (consulta.estado === "en_cola" || consulta.estado === "procesando") {
    return (
      <div className="consenso consenso-espera">
        <span className="spinner grande" aria-hidden="true" />
        <div>
          <h3>Esperando a la junta</h3>
          <p className="suave">
            {listas} de {total} modelos terminaron. El consenso sale cuando terminen todos.
          </p>
        </div>
      </div>
    );
  }
  const ok = consulta.inferencias.filter((i) => i.estado === "ok").length;
  return (
    <div className="consenso consenso-espera">
      <div>
        <h3>Sin consenso</h3>
        <p className="suave">
          {ok === 0
            ? "Ningún modelo pudo analizar la imagen."
            : "Solo un modelo con evaluación verificada terminó bien: hacen falta al menos dos para consensuar. Su resultado está abajo."}
        </p>
      </div>
    </div>
  );
}

function TarjetaInferencia({ inferencia: i }: { inferencia: InferenciaJunta }) {
  const marca =
    i.coincide === true ? (
      <span className="pastilla estado-ok">Coincide</span>
    ) : i.coincide === false ? (
      <span className="pastilla estado-error">Discrepa</span>
    ) : null;
  return (
    <li className={`inferencia-junta${i.coincide === false ? " discrepa" : ""}`}>
      <header className="inferencia-cabecera">
        <div>
          <h4>
            {i.modelo.nombre_visible ?? i.modelo.nombre} <span className="version">v{i.modelo.version}</span>
          </h4>
          <p className="suave">
            {i.peso
              ? `Pesa con ${i.peso.metrica === "auc" ? "AUC" : "accuracy"} ${numero(i.peso.valor, 3)}`
              : "Sin métrica verificada: no pesa en el consenso"}
          </p>
        </div>
        {marca}
      </header>
      {i.estado === "pendiente" || i.estado === "en_curso" ? (
        <p className="inferencia-espera suave">
          <span className="spinner" aria-hidden="true" /> {i.estado === "pendiente" ? "En cola" : "Procesando"}
          {i.intentos > 1 && ` · intento ${i.intentos}`}
        </p>
      ) : (
        <ResultadoInferencia trabajo={i} />
      )}
    </li>
  );
}

/** El resultado de la junta: arriba el consenso; debajo, cada modelo por separado; al final, la leyenda. */
export default function ResultadoJunta({ consulta }: { consulta: Consulta }) {
  return (
    <div className="resultado-junta">
      {consulta.consenso ? (
        <InformeConsenso consenso={consulta.consenso} inferencias={consulta.inferencias} />
      ) : (
        <SinConsenso consulta={consulta} />
      )}

      <section aria-labelledby="titulo-cada-modelo">
        <h3 id="titulo-cada-modelo" className="titulo-cada-modelo">
          Cada modelo
        </h3>
        <ul className="grilla-junta">
          {consulta.inferencias.map((i) => (
            <TarjetaInferencia key={i.id} inferencia={i} />
          ))}
        </ul>
      </section>

      <p className="leyenda-clinica" role="note">
        {LEYENDA}
      </p>
    </div>
  );
}
