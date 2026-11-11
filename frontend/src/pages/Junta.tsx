import { useMemo, useState } from "react";
import type { Modelo } from "../api/tipos";
import CargadorImagen from "../components/CargadorImagen";
import EstadoTrabajo from "../components/EstadoTrabajo";
import { Flecha } from "../components/Navegacion";
import PideIngreso from "../components/PideIngreso";
import ResultadoJunta, { LEYENDA } from "../components/ResultadoJunta";
import SelectorJunta, { MAXIMO_JUNTA, MINIMO_JUNTA } from "../components/SelectorJunta";
import { Enlace } from "../enrutador";
import { useJunta } from "../hooks/useJunta";
import { useModelos } from "../hooks/useModelos";
import { useSesion } from "../hooks/useSesion";
import { nombreTipo } from "../utilidades/metricas";

const evaluado = (m: Modelo) => m.estado_evaluacion === "ok" && m.accuracy !== null;

/** Lo que trae el enlace: /junta?con=<modelo> desde la ficha, /junta?tipo=<tipo> desde el catálogo. */
function leerPedido(): { con: string | null; tipo: string | null } {
  const q = new URLSearchParams(window.location.search);
  return { con: q.get("con"), tipo: q.get("tipo") };
}

/**
 * La junta de modelos (spec F8): de 2 a 5 modelos evaluados del mismo tipo de estudio, la
 * imagen se sube una vez y cada modelo la analiza por separado, en paralelo. Arriba, el consenso.
 */
export default function Junta() {
  const { sesion, conLogin } = useSesion();
  const { publicados, cargando, error, refrescar } = useModelos();
  const junta = useJunta();
  const [pedido] = useState(leerPedido);
  const [tipoElegido, setTipoElegido] = useState<string | null>(pedido.tipo);
  // null = el usuario todavía no tocó la selección: van todos los evaluados del tipo, hasta cinco.
  const [elegidosAMano, setElegidosAMano] = useState<string[] | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);

  const tipos = useMemo(() => [...new Set(publicados.map((m) => m.tipo_estudio))].sort(), [publicados]);
  const delPedido = publicados.find((m) => m.id === pedido.con);
  const tipo =
    tipoElegido ??
    delPedido?.tipo_estudio ??
    tipos.find((t) => publicados.filter((m) => m.tipo_estudio === t && evaluado(m)).length >= MINIMO_JUNTA) ??
    tipos[0] ??
    null;

  const delTipo = useMemo(
    () =>
      publicados
        .filter((m) => m.tipo_estudio === tipo)
        // Los evaluados primero, del de más accuracy al de menos: son los que pueden entrar.
        .sort((a, b) => (b.accuracy ?? -1) - (a.accuracy ?? -1)),
    [publicados, tipo],
  );
  const evaluados = delTipo.filter(evaluado);
  const porDefecto = [
    ...(delPedido && evaluado(delPedido) && delPedido.tipo_estudio === tipo ? [delPedido.id] : []),
    ...evaluados.map((m) => m.id).filter((id) => id !== delPedido?.id),
  ].slice(0, MAXIMO_JUNTA);
  const elegidos = (elegidosAMano ?? porDefecto).filter((id) => evaluados.some((m) => m.id === id));
  const modelosElegidos = elegidos.flatMap((id) => evaluados.filter((m) => m.id === id));

  const terminado = junta.etapa === "ok" || junta.etapa === "error";
  const alcanza = elegidos.length >= MINIMO_JUNTA && elegidos.length <= MAXIMO_JUNTA;
  const puedeConsultar = archivo !== null && alcanza && !junta.enCurso;

  const cambiarTipo = (t: string) => {
    setTipoElegido(t);
    setElegidosAMano(null);
    setArchivo(null);
    junta.reiniciar();
  };
  const cambiarElegidos = (ids: string[]) => {
    setElegidosAMano(ids);
    junta.reiniciar();
  };
  const elegirArchivo = (nuevo: File | null) => {
    setArchivo(nuevo);
    junta.reiniciar();
  };

  const avance = junta.consulta
    ? { estado: junta.consulta.estado === "en_cola" ? ("pendiente" as const) : ("en_curso" as const), intentos: 1 }
    : null;

  let formulario;
  if (conLogin && sesion === null) {
    formulario = <PideIngreso compacto texto="Ingresá con tu cuenta de institución para consultar a una junta de modelos." />;
  } else if (cargando && publicados.length === 0) {
    formulario = <div className="ficha-esqueleto" aria-busy="true" />;
  } else if (tipo === null) {
    formulario = (
      <div className="vacio chico">
        <p>Todavía no hay modelos publicados.</p>
      </div>
    );
  } else {
    formulario = (
      <>
        <div className="campo">
          <span className="campo-etiqueta">Tipo de estudio</span>
          <div className="filtros" role="group" aria-label="Tipo de estudio">
            {tipos.map((t) => (
              <button
                key={t}
                type="button"
                className={t === tipo ? "filtro activo" : "filtro"}
                aria-pressed={t === tipo}
                disabled={junta.enCurso}
                onClick={() => cambiarTipo(t)}
              >
                {nombreTipo(t)}
              </button>
            ))}
          </div>
        </div>

        <div className="campo">
          <span className="campo-etiqueta">Los modelos</span>
          <SelectorJunta
            modelos={delTipo}
            elegidos={elegidos}
            deshabilitado={junta.enCurso}
            onCambiar={cambiarElegidos}
          />
          {evaluados.length < MINIMO_JUNTA && (
            <p className="nota-suave">
              {nombreTipo(tipo)} tiene {evaluados.length} {evaluados.length === 1 ? "modelo evaluado" : "modelos evaluados"}
              : una junta necesita al menos {MINIMO_JUNTA}.
            </p>
          )}
        </div>

        <div className="campo">
          <span className="campo-etiqueta">El estudio</span>
          <CargadorImagen
            archivo={archivo}
            tipoEstudio={tipo}
            deshabilitado={junta.enCurso}
            onSeleccionar={elegirArchivo}
            onQuitar={() => elegirArchivo(null)}
          />
        </div>

        {!terminado && (
          <button
            type="button"
            className="pildora pildora-oscura ancha"
            disabled={!puedeConsultar}
            onClick={() => archivo && void junta.ejecutar(archivo, modelosElegidos)}
          >
            {junta.enCurso ? "Consultando a la junta…" : `Consultar a la junta · ${elegidos.length} modelos`}{" "}
            {!junta.enCurso && <Flecha />}
          </button>
        )}

        <EstadoTrabajo etapa={junta.etapa} trabajo={avance} />

        {junta.etapa === "error" && junta.error && junta.consulta === null && (
          <div className="caja-error" role="alert">
            {junta.error}
          </div>
        )}

        {terminado && (
          <button type="button" className="pildora pildora-borde ancha" onClick={() => elegirArchivo(null)}>
            Consultar otro estudio
          </button>
        )}

        <p className="letra-chica">{LEYENDA} El estudio se borra a los 7 días.</p>
      </>
    );
  }

  return (
    <div className="marco pagina">
      <header className="cabecera-pagina">
        <div>
          <h1>Junta de modelos</h1>
          <p className="bajada">
            Elegí de {MINIMO_JUNTA} a {MAXIMO_JUNTA} modelos evaluados del mismo tipo de estudio y subí la imagen una
            vez: cada modelo la analiza por separado y, arriba, el informe de consenso marca si coinciden o si el
            estudio pide revisión prioritaria.
          </p>
        </div>
        <Enlace a="/modelos" className="pildora pildora-borde">
          Ver el catálogo
        </Enlace>
      </header>

      {error && (
        <div className="caja-error" role="alert">
          No se pudo cargar el catálogo: {error}{" "}
          <button type="button" className="enlace" onClick={() => void refrescar()}>
            Reintentar
          </button>
        </div>
      )}

      <div className="junta-cuerpo">
        <section className="panel panel-junta" aria-labelledby="titulo-armar">
          <header className="panel-cabecera">
            <h2 id="titulo-armar">Armá la junta</h2>
          </header>
          {formulario}
        </section>

        <section className="panel" aria-labelledby="titulo-informe">
          <header className="panel-cabecera">
            <h2 id="titulo-informe">El informe</h2>
          </header>
          {junta.consulta ? (
            <ResultadoJunta consulta={junta.consulta} />
          ) : (
            <div className="como-funciona">
              <p>Cuando la junta termine, acá vas a ver:</p>
              <ul>
                <li>
                  <strong>El consenso</strong>: el promedio de las probabilidades de cada modelo, ponderado por su
                  métrica verificada contra el conjunto reservado (AUC si se midió, si no accuracy).
                </li>
                <li>
                  <strong>El acuerdo</strong>: qué parte de ese peso suman los modelos que coinciden con el consenso.
                  Por debajo del 70 %, el estudio se marca para <strong>revisión prioritaria</strong>.
                </li>
                <li>
                  <strong>Cada modelo por separado</strong>, con su predicción y si coincide o discrepa.
                </li>
              </ul>
              <p className="letra-chica">{LEYENDA}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
