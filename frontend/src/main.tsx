import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { cargarConfiguracion } from "./api/configuracion";
import { recibirDelCallback, tomarVuelta } from "./api/sesion";
import "./estilos.css";

const raiz = document.getElementById("root");
if (raiz === null) throw new Error("No existe el elemento #root en index.html");
const contenedor = raiz;

// Antes de pintar: dónde está la API y si venimos del login con los tokens en la URL (y, si esa
// vuelta la pidió el sitio para traer un token nuevo, con qué avisar).
async function arrancar(): Promise<void> {
  await cargarConfiguracion();
  const errorIngreso = recibirDelCallback();
  const vuelta = tomarVuelta();
  createRoot(contenedor).render(
    <StrictMode>
      <App avisoInicial={errorIngreso ?? vuelta.aviso} trasRefrescar={vuelta.refresco} />
    </StrictMode>,
  );
}

void arrancar();
