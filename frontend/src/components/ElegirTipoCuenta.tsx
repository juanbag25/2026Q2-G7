import { useEffect, useState } from "react";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import type { TipoCuenta } from "../api/configuracion";
import { elegirTipoCuenta, leerTipoCuenta } from "../api/cuenta";
import { ingresarDeNuevo } from "../api/sesion";
import { oracion } from "../utilidades/formato";
import { antesDePreguntar, tuCuenta } from "../utilidades/roles";
import { Flecha } from "./Navegacion";

const TIPOS: { tipo: TipoCuenta; nombre: string; texto: string }[] = [
  {
    tipo: "institucion",
    nombre: "Institución",
    texto: "Analizás estudios con los modelos del catálogo, de a uno o en junta.",
  },
  {
    tipo: "publicador",
    nombre: "Publicador",
    texto: "Subís tus modelos, los publicás y ves cómo rinden en la evaluación de Ateneo.",
  },
];

interface Props {
  email: string | null;
  /** Esta carga ya es la vuelta de un ingreso que pidió el sitio para traer un token nuevo. */
  trasRefrescar: boolean;
}

/**
 * Lo primero que ve, en cualquier ruta, quien se registró desde «Ingresar»: su cuenta todavía no
 * tiene grupo. Elige una vez; la API fija la elección y agrega el grupo en Cognito. El token del
 * navegador es de antes de elegir, así que con un 200, o con un 409 (ya tenía un tipo), se vuelve a
 * pasar por el login, que no pide la contraseña y trae el grupo que quedó.
 *
 * Antes de preguntar, revisa lo que la cuenta tiene en Cognito: si ya eligió (en otro navegador,
 * o cerró este antes de volver del login), el token es viejo y trae uno nuevo en vez de preguntar.
 */
export default function ElegirTipoCuenta({ email, trasRefrescar }: Props) {
  const [fase, setFase] = useState<"revisando" | "refrescando" | "preguntando">("revisando");
  const [enviando, setEnviando] = useState<TipoCuenta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    leerTipoCuenta()
      .then(({ grupos }) => {
        if (!vigente) return;
        const paso = antesDePreguntar(grupos, trasRefrescar);
        if (paso === "refrescar") {
          setFase("refrescando");
          ingresarDeNuevo();
          return;
        }
        if (paso === "avisar") {
          setError(`${tuCuenta(grupos)} Pero el ingreso volvió sin ese rol: salí y volvé a ingresar.`);
        }
        setFase("preguntando");
      })
      .catch(() => {
        // Sin poder revisar, se pregunta igual: al elegir, la API decide con lo que hay en Cognito.
        if (vigente) setFase("preguntando");
      });
    return () => {
      vigente = false;
    };
  }, [trasRefrescar]);

  const elegir = async (tipo: TipoCuenta) => {
    setEnviando(tipo);
    setError(null);
    try {
      await elegirTipoCuenta(tipo);
      ingresarDeNuevo();
    } catch (e) {
      if (e instanceof ErrorApi && e.status === 409) {
        // Ya tenía un tipo: el login nuevo trae ese, y a la vuelta se dice por qué.
        ingresarDeNuevo(oracion(e.detalle));
        return;
      }
      setError(`No se pudo guardar el tipo de cuenta. ${oracion(mensajeDeError(e))}`);
      setEnviando(null);
    }
  };

  if (fase !== "preguntando") {
    return (
      <div className="marco angosto pagina">
        <p className="revisando-cuenta" role="status">
          <span className="spinner grande" aria-hidden="true" />
          {fase === "revisando" ? "Revisando tu cuenta…" : "Tu cuenta ya tiene su tipo: actualizando la sesión…"}
        </p>
      </div>
    );
  }

  return (
    <div className="marco angosto pagina">
      <header className="cabecera-pagina centrada">
        <h1 className="titulo-pregunta">¿Tu cuenta es de una institución o de un publicador?</h1>
        <p className="bajada">
          Se elige una sola vez{email ? `, para ${email}` : ""}. Después, Ateneo te muestra lo que corresponde a tu
          cuenta.
        </p>
      </header>

      <div className="tipos-cuenta" role="group" aria-label="Tipo de cuenta">
        {TIPOS.map(({ tipo, nombre, texto }) => (
          <button
            key={tipo}
            type="button"
            className={enviando === tipo ? "tipo-cuenta elegido" : "tipo-cuenta"}
            onClick={() => void elegir(tipo)}
            disabled={enviando !== null}
            aria-busy={enviando === tipo}
          >
            <span className="tipo-cuenta-nombre">
              {nombre} <Flecha />
            </span>
            <span className="tipo-cuenta-texto">{enviando === tipo ? "Guardando…" : texto}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="caja-error tipo-cuenta-error" role="alert">
          {error}
        </div>
      )}

      <p className="suave tipo-cuenta-nota">
        Los médicos no se registran solos: los invita su institución, con el rol ya asignado.
      </p>
    </div>
  );
}
