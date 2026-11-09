import { useMemo } from "react";
import { Flecha } from "../components/Navegacion";
import TarjetaModelo from "../components/TarjetaModelo";
import { Enlace } from "../enrutador";
import { useModelos } from "../hooks/useModelos";
import { useSesion } from "../hooks/useSesion";
import { porcentaje } from "../utilidades/formato";
import { lideres } from "../utilidades/metricas";
import { modelosIniciales } from "../utilidades/modelos";

const PASOS = [
  {
    titulo: "Elegí un modelo",
    texto: "Explorá los modelos disponibles y compará sus métricas de evaluación. No necesitás subir uno propio.",
  },
  {
    titulo: "Subí tu estudio",
    texto: "Abrí la ficha del modelo y seleccioná una imagen compatible con su tipo de estudio.",
  },
  {
    titulo: "Consultá el resultado",
    texto: "Recibí la predicción y consultá las métricas con las que se evaluó el modelo.",
  },
];

/** Las tres miradas de la marca, en grande, detrás del título. */
function FondoPortada() {
  return (
    <svg className="portada-anillos" viewBox="0 0 600 600" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <circle cx="300" cy="215" r="150" />
        <circle cx="375" cy="350" r="150" />
        <circle cx="225" cy="350" r="150" />
        <circle cx="300" cy="305" r="240" opacity="0.35" />
        <circle cx="300" cy="305" r="290" opacity="0.18" />
      </g>
      <circle cx="300" cy="305" r="34" fill="currentColor" opacity="0.9" />
    </svg>
  );
}

export default function Inicio() {
  const { publicados, error, demo } = useModelos();
  const { ofrecerPublicar } = useSesion();

  const evaluados = publicados.filter((m) => m.estado_evaluacion === "ok" && m.accuracy !== null);
  const mejor = evaluados.reduce<number | null>((max, m) => Math.max(max ?? 0, m.accuracy ?? 0), null);
  const tipos = new Set(publicados.map((m) => m.tipo_estudio)).size;
  const mejores = useMemo(() => lideres(publicados), [publicados]);
  // El registro del servidor define cuáles se incluyen, aunque otro tenga mayor accuracy.
  const destacados = modelosIniciales(publicados, demo?.modelos);

  return (
    <div className="inicio">
      <section className="portada">
        <div className="portada-fondo" aria-hidden="true">
          <FondoPortada />
        </div>

        <h1 className="portada-titulo">
          <span>Ateneo</span>
        </h1>

        <div className="portada-vidrio">
          <div className="vidrio-texto">
            <p className="vidrio-lema">
              {evaluados.length > 0 ? "Modelos de IA clínica listos para usar." : "IA clínica para analizar tus estudios."}
            </p>
            <p className="vidrio-descripcion">
              Elegí un modelo del catálogo y subí una imagen. No necesitás publicar uno propio para empezar.
            </p>
            {evaluados.length > 0 && (
              <p className="vidrio-disponibilidad">
                {evaluados.length} {evaluados.length === 1 ? "modelo evaluado disponible" : "modelos evaluados disponibles"}
              </p>
            )}
            <div className="acciones">
              <Enlace a="/modelos" className="pildora pildora-clara">
                Elegir un modelo <Flecha />
              </Enlace>
              {ofrecerPublicar && (
                <Enlace a="/publicar" className="pildora pildora-vidrio">
                  Publicar uno propio
                </Enlace>
              )}
            </div>
          </div>

          {error === null && (
            <dl className="vidrio-datos">
              <div>
                <dt>Modelos</dt>
                <dd>{publicados.length}</dd>
              </div>
              <div>
                <dt>Listos para usar</dt>
                <dd>{evaluados.length}</dd>
              </div>
              <div>
                <dt>Tipos de estudio</dt>
                <dd>{tipos}</dd>
              </div>
              <div>
                <dt>Mejor accuracy</dt>
                <dd>{mejor !== null ? porcentaje(mejor) : "—"}</dd>
              </div>
            </dl>
          )}
        </div>
      </section>

      <section className="marco seccion">
        <header className="cabecera-seccion">
          <h2 className="titular">
            Elegí un modelo
            <br />
            y analizá tu estudio
          </h2>
        </header>

        {destacados.length > 0 ? (
          <div className="grilla-modelos">
            {destacados.map((m) => (
              <TarjetaModelo key={m.id} modelo={m} mejor={mejores.has(m.id)} />
            ))}
          </div>
        ) : (
          <div className="vacio">
            <p>Todavía no hay modelos publicados.</p>
          </div>
        )}

        <div className="centrado">
          <Enlace a="/modelos" className="pildora pildora-oscura">
            Ver todos los modelos <Flecha />
          </Enlace>
        </div>
      </section>

      <section className="marco seccion">
        <header className="cabecera-seccion">
          <h2 className="titular">Cómo funciona?</h2>
        </header>

        <ol className="pasos-inicio">
          {PASOS.map((paso, i) => (
            <li key={paso.titulo}>
              <span className="paso-numero">{String(i + 1).padStart(2, "0")}</span>
              <h3>{paso.titulo}</h3>
              <p>{paso.texto}</p>
            </li>
          ))}
        </ol>
      </section>

      {ofrecerPublicar && (
        <section className="marco seccion">
          <div className="banda">
            <div>
              <h2>¿Querés sumar tu propio modelo?</h2>
              <p>También podés publicarlo para que lo evaluemos y sumarlo al catálogo. Es opcional: podés usar los modelos disponibles sin publicar uno.</p>
            </div>
            <Enlace a="/publicar" className="pildora pildora-clara">
              Publicar uno propio <Flecha />
            </Enlace>
          </div>
        </section>
      )}
    </div>
  );
}
