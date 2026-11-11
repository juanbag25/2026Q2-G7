import { useEffect, useState } from "react";
import AvisoCuenta from "./components/AvisoCuenta";
import ElegirTipoCuenta from "./components/ElegirTipoCuenta";
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
  /**
   * Lo que hay que avisar al arrancar: el login volvió con un error (cancelado, código vencido,
   * state ajeno), o la cuenta ya tenía otro tipo cuando se eligió uno (409).
   */
  avisoInicial: string | null;
  /** Esta carga es la vuelta de un ingreso que pidió el sitio para traer un token nuevo. */
  trasRefrescar: boolean;
}

/**
 * Marco del sitio: barra, la vista de la ruta actual y pie. El catálogo y las fichas
 * son públicos; publicar pide una cuenta de publicador, y analizar un estudio, dentro de la
 * ficha, una de institución o de médico. Una cuenta recién registrada desde «Ingresar» no tiene
 * ninguna de las dos: hasta que elija, en cualquier ruta se ve solo esa pregunta.
 */
export default function App({ avisoInicial, trasRefrescar }: Props) {
  const ruta = useRuta();
  const { salud, consultado } = useSalud();
  const { tema, alternar } = useTema();
  const { sesion, conLogin, pideTipo, puedePublicar, puedeConsultar } = useSesion();
  const [aviso, setAviso] = useState(avisoInicial);
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
  // Sin la portada debajo, la barra no puede ir blanca sobre la imagen.
  const enPortada = ruta.vista === "inicio" && !pideTipo;

  useEffect(() => {
    if (pideTipo) document.title = "Tipo de cuenta · Ateneo";
    else if (ruta.vista !== "modelo") document.title = titulo(ruta);
  }, [ruta, pideTipo]);

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
        {pideTipo ? (
          <ElegirTipoCuenta email={sesion?.email ?? null} trasRefrescar={trasRefrescar} />
        ) : (
          <>
            {ruta.vista === "inicio" && <Inicio />}
            {ruta.vista === "modelos" && <Modelos />}
            {ruta.vista === "modelo" && <FichaModelo key={ruta.id} id={ruta.id} />}
            {ruta.vista === "junta" && junta}
            {ruta.vista === "publicar" && publicar}
          </>
        )}
      </main>

      <PieSitio salud={salud} consultado={consultado} />
    </div>
  );
}
