import { ingresar, salir } from "../api/sesion";
import { Enlace } from "../enrutador";
import { useSesion } from "../hooks/useSesion";
import type { Tema } from "../hooks/useTema";
import Marca from "./Marca";

interface Props {
  /** En la portada la barra flota sobre la imagen, en blanco. */
  sobrePortada: boolean;
  tema: Tema;
  onAlternarTema: () => void;
}

function IconoTema({ tema }: { tema: Tema }) {
  if (tema === "oscuro") {
    // Sol: al estar en oscuro, el botón lleva a claro.
    return (
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.6v2.4M12 19v2.4M2.6 12H5M19 12h2.4M5.4 5.4l1.7 1.7M16.9 16.9l1.7 1.7M18.6 5.4l-1.7 1.7M7.1 16.9l-1.7 1.7" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M20.5 14.6A8.6 8.6 0 1 1 9.4 3.5a6.8 6.8 0 0 0 11.1 11.1Z" strokeLinejoin="round" />
    </svg>
  );
}

export function Flecha() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Barra superior: marca, las secciones en una píldora, tema y sesión. */
export default function Navegacion({ sobrePortada, tema, onAlternarTema }: Props) {
  const { sesion, conLogin, ofrecerPublicar, ofrecerConsultar } = useSesion();

  return (
    <header className={sobrePortada ? "barra barra-portada" : "barra"}>
      <div className="barra-interior">
        <Enlace a="/" className="logo">
          <Marca tamano={24} />
          <span className="logo-texto">Ateneo</span>
        </Enlace>

        <nav className="menu" aria-label="Secciones">
          <Enlace a="/">Inicio</Enlace>
          <Enlace a="/modelos" prefijo>
            Modelos
          </Enlace>
          {ofrecerConsultar && <Enlace a="/junta">Junta</Enlace>}
          {ofrecerPublicar && <Enlace a="/publicar">Publicar</Enlace>}
        </nav>

        <div className="barra-fin">
          <button
            type="button"
            className="boton-icono"
            onClick={onAlternarTema}
            aria-label={tema === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
            title={tema === "oscuro" ? "Tema claro" : "Tema oscuro"}
          >
            <IconoTema tema={tema} />
          </button>
          {conLogin &&
            (sesion ? (
              <span className="sesion">
                <span className="sesion-email" title={sesion.email ?? undefined}>
                  {sesion.email ?? "Sesión iniciada"}
                </span>
                <button type="button" className="pildora pildora-borde" onClick={salir}>
                  Salir
                </button>
              </span>
            ) : (
              <button type="button" className="pildora pildora-clara" onClick={ingresar}>
                Ingresar <Flecha />
              </button>
            ))}
        </div>
      </div>
    </header>
  );
}
