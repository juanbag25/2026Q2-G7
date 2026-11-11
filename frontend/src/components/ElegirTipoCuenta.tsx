import { useState } from "react";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import type { TipoCuenta } from "../api/configuracion";
import { elegirTipoCuenta } from "../api/cuenta";
import { ingresarDeNuevo } from "../api/sesion";
import { oracion } from "../utilidades/formato";
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
}

/**
 * Lo primero que ve, en cualquier ruta, quien se registró desde «Ingresar»: su cuenta todavía no
 * tiene grupo. Elige una vez; la API fija la elección y agrega el grupo en Cognito. El token del
 * navegador es de antes de elegir, así que con un 200, o con un 409 (ya tenía un tipo), se vuelve a
 * pasar por el login, que no pide la contraseña y trae el grupo que quedó.
 */
export default function ElegirTipoCuenta({ email }: Props) {
  const [enviando, setEnviando] = useState<TipoCuenta | null>(null);
  const [error, setError] = useState<string | null>(null);

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
