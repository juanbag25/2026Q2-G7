import { useMemo, useState } from "react";
import Paginacion from "../components/Paginacion";
import TarjetaModelo from "../components/TarjetaModelo";
import { Enlace, rutaDeJunta } from "../enrutador";
import { useModelos } from "../hooks/useModelos";
import { lideres, nombreTipo } from "../utilidades/metricas";

const POR_PAGINA = 9;

type Orden = "accuracy" | "recientes";

/** El catálogo: tarjetas filtrables por tipo de estudio, de a nueve por página. */
export default function Modelos() {
  const { publicados, cargando, error, refrescar } = useModelos();
  const [busqueda, setBusqueda] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [orden, setOrden] = useState<Orden>("accuracy");
  const [pagina, setPagina] = useState(1);

  const tipos = useMemo(() => [...new Set(publicados.map((m) => m.tipo_estudio))].sort(), [publicados]);
  const mejores = useMemo(() => lideres(publicados), [publicados]);

  const filtrados = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    const lista = publicados.filter(
      (m) =>
        (tipo === null || m.tipo_estudio === tipo) &&
        (texto === "" || `${m.nombre} ${m.nombre_visible ?? ""} ${m.tipo_estudio} ${m.etiquetas.join(" ")}`.toLowerCase().includes(texto)),
    );
    if (orden === "accuracy") {
      // Los evaluados primero, del mejor al peor; el resto conserva el orden de la API (más nuevo primero).
      return [...lista].sort((a, b) => (b.accuracy ?? -1) - (a.accuracy ?? -1));
    }
    return lista;
  }, [publicados, busqueda, tipo, orden]);

  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
  const actual = Math.min(pagina, paginas);
  const visibles = filtrados.slice((actual - 1) * POR_PAGINA, actual * POR_PAGINA);

  const cambiarPagina = (n: number) => {
    setPagina(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="marco pagina">
      <header className="cabecera-pagina">
        <div>
          <h1>Modelos</h1>
          <p className="bajada">Elegí un modelo disponible, revisá su evaluación y subí una imagen desde su ficha. Si querés, también podés publicar uno propio.</p>
        </div>
        <div className="fila-accion">
          <Enlace a={rutaDeJunta({ tipo })} className="pildora">
            Consultar en junta
          </Enlace>
          <Enlace a="/publicar" className="pildora pildora-borde">
            Publicar uno propio
          </Enlace>
        </div>
      </header>

      <div className="herramientas">
        <input
          type="search"
          className="buscador"
          placeholder="Buscar por nombre, tipo o etiqueta"
          aria-label="Buscar modelos"
          value={busqueda}
          onChange={(e) => {
            setBusqueda(e.target.value);
            setPagina(1);
          }}
        />
        <div className="filtros" role="group" aria-label="Tipo de estudio">
          {[null, ...tipos].map((t) => (
            <button
              key={t ?? "todos"}
              type="button"
              className={t === tipo ? "filtro activo" : "filtro"}
              aria-pressed={t === tipo}
              onClick={() => {
                setTipo(t);
                setPagina(1);
              }}
            >
              {t === null ? "Todos" : nombreTipo(t)}
            </button>
          ))}
        </div>
        <label className="orden">
          <span className="sr-solo">Ordenar</span>
          <select value={orden} onChange={(e) => setOrden(e.target.value as Orden)}>
            <option value="accuracy">Mejor accuracy</option>
            <option value="recientes">Más recientes</option>
          </select>
        </label>
      </div>

      {error && (
        <div className="caja-error" role="alert">
          No se pudo cargar el catálogo: {error}{" "}
          <button type="button" className="enlace" onClick={() => void refrescar()}>
            Reintentar
          </button>
        </div>
      )}

      {cargando && publicados.length === 0 ? (
        <div className="grilla-modelos" aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="tarjeta-modelo esqueleto" />
          ))}
        </div>
      ) : visibles.length === 0 ? (
        <div className="vacio">
          {publicados.length === 0 ? (
            <>
              <p>Todavía no hay modelos publicados.</p>
              <Enlace a="/publicar" className="pildora pildora-oscura">
                Publicar el primero
              </Enlace>
            </>
          ) : (
            <p>Ningún modelo coincide con la búsqueda.</p>
          )}
        </div>
      ) : (
        <>
          <p className="conteo">
            {filtrados.length} {filtrados.length === 1 ? "modelo" : "modelos"}
          </p>
          <div className="grilla-modelos">
            {visibles.map((m) => (
              <TarjetaModelo key={m.id} modelo={m} mejor={mejores.has(m.id)} />
            ))}
          </div>
          <Paginacion pagina={actual} paginas={paginas} onCambiar={cambiarPagina} />
        </>
      )}
    </div>
  );
}
