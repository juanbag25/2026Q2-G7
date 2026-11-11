import { Enlace } from "../enrutador";

interface Props {
  /** Qué es esto y para qué cuentas: «Publicar es para cuentas de publicador». */
  titulo: string;
  /** Qué cuenta tiene y qué puede hacer en cambio. */
  texto: string;
  /** Dentro de otro panel (la ficha): sin encabezado de página. */
  compacto?: boolean;
}

/**
 * Lo que ve quien ingresó con una cuenta que no hace esto (una institución en Publicar, un
 * publicador en la ficha). La interfaz solo esconde: la API contesta 403 igual.
 */
export default function AvisoCuenta({ titulo, texto, compacto = false }: Props) {
  if (compacto) {
    return (
      <div className="ingreso-compacto" role="note">
        <p>
          <strong>{titulo}.</strong> {texto}
        </p>
      </div>
    );
  }

  return (
    <div className="marco angosto pagina">
      <header className="cabecera-pagina centrada">
        <h1>{titulo}</h1>
        <p className="bajada">{texto}</p>
      </header>
      <p className="opcion-catalogo">
        <Enlace a="/modelos">Ver los modelos disponibles</Enlace>
      </p>
    </div>
  );
}
