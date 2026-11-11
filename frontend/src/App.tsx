import { useEffect, useState } from "react";
import AvisoCuenta from "./components/AvisoCuenta";
import Navegacion from "./components/Navegacion";
import PideIngreso from "./components/PideIngreso";
import PieSitio from "./components/PieSitio";
import { useRuta } from "./enrutador";
import type { Ruta } from "./enrutador";
import { useSalud } from "./hooks/useSalud";
import { useSesion } from "./hooks/useSesion";
import { useTema } from "./hooks/useTema";
import FichaModelo from "./pages/FichaModelo";
import Inicio from "./pages/Inicio";
import Junta from "./pages/Junta";
import Modelos from "./pages/Modelos";
import Publicar from "./pages/Publicar";
import { tuCuenta } from "./utilidades/roles";

function titulo(ruta: Ruta): string {
  switch (ruta.vista) {
    case "inicio":
      return "Ateneo · Modelos de IA clínica evaluados";
    case "modelos":
      return "Modelos · Ateneo";
    case "modelo":
      return "Modelo · Ateneo";
    case "publicar":
      return "Publicar un modelo · Ateneo";
    case "junta":
      return "Junta de modelos · Ateneo";
  }
}

interface Props {
  /** El login volvió con un error (cancelado, código vencido, state ajeno). */
  errorIngreso: string | null;
}

/**
 * Marco del sitio: barra, la vista de la ruta actual y pie. El catálogo y las fichas
 * son públicos; publicar pide una cuenta de publicador, y analizar un estudio, dentro de la
 * ficha, una de institución o de médico.
 */
export default function App({ errorIngreso }: Props) {
  const ruta = useRuta();
  const { salud, consultado } = useSalud();
  const { tema, alternar } = useTema();
  const { sesion, conLogin, puedePublicar, puedeConsultar } = useSesion();
  const [aviso, setAviso] = useState(errorIngreso);
  const pideIngreso = conLogin && sesion === null;

  // /publicar: sin sesión, la puerta a Cognito; con una cuenta que no publica, por qué no.
  const publicar = pideIngreso ? (
    <PideIngreso />
  ) : puedePublicar ? (
    <Publicar />
  ) : (
    <AvisoCuenta
      titulo="Publicar es para cuentas de publicador"
      texto={`${tuCuenta(sesion?.grupos ?? [])} Podés elegir un modelo del catálogo y analizar tus estudios desde su ficha.`}
    />
  );
  // /junta: sin sesión, la propia página pide ingresar; con una cuenta que no consulta, por qué no.
  const junta =
    pideIngreso || puedeConsultar ? (
      <Junta />
    ) : (
      <AvisoCuenta
        titulo="La junta es para cuentas de institución o de médico"
        texto={`${tuCuenta(sesion?.grupos ?? [])} Podés ver el catálogo y cómo rindió cada modelo en su evaluación.`}
      />
    );
  const enPortada = ruta.vista === "inicio";

  useEffect(() => {
    if (ruta.vista !== "modelo") document.title = titulo(ruta);
  }, [ruta]);

  return (
    <div className={enPortada ? "sitio sitio-portada" : "sitio"}>
      <Navegacion sobrePortada={enPortada} tema={tema} onAlternarTema={alternar} />

      <main className="contenido">
        {aviso && (
          <div className="marco">
            <div className="caja-error aviso-ingreso" role="alert">
              {aviso}{" "}
              <button type="button" className="enlace" onClick={() => setAviso(null)}>
                Cerrar
              </button>
            </div>
          </div>
        )}
        {ruta.vista === "inicio" && <Inicio />}
        {ruta.vista === "modelos" && <Modelos />}
        {ruta.vista === "modelo" && <FichaModelo key={ruta.id} id={ruta.id} />}
        {ruta.vista === "junta" && junta}
        {ruta.vista === "publicar" && publicar}
      </main>

      <PieSitio salud={salud} consultado={consultado} />
    </div>
  );
}
