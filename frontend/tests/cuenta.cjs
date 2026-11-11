// El tipo de cuenta del lado del sitio: con qué cliente de Cognito entra «Ingresar» según
// config.json, y cómo se leen los avisos de la API.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("typescript");

function cargar(relativa) {
  const archivo = path.resolve(__dirname, "..", relativa);
  const compilado = ts.transpileModule(fs.readFileSync(archivo, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const modulo = new Module(archivo, module);
  modulo._compile(compilado, archivo);
  return modulo.exports;
}

const { cargarConfiguracion, clienteDeIngreso, configuracion } = cargar("src/api/configuracion.ts");
const { oracion } = cargar("src/utilidades/formato.ts");
const { antesDePreguntar } = cargar("src/utilidades/roles.ts");

/** Lo que contesta el bucket web a GET /config.json. */
function servir(cuerpo) {
  globalThis.fetch = async () => ({
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => cuerpo,
  });
}

function config(clientes) {
  return {
    api: "https://abc123.execute-api.us-east-1.amazonaws.com/",
    cognito: {
      dominio: "https://ateneo-x.auth.us-east-1.amazoncognito.com",
      callback: "https://abc123.execute-api.us-east-1.amazonaws.com/callback",
      logout: "https://abc123.execute-api.us-east-1.amazonaws.com/logout",
      clientes,
    },
  };
}

test("con el tercer cliente, «Ingresar» entra por el suyo, que no da grupo", async () => {
  servir(config({ ingreso: "id-ingreso", institucion: "id-institucion", publicador: "id-publicador" }));
  await cargarConfiguracion();
  const { api, cognito } = configuracion();
  assert.equal(api, "https://abc123.execute-api.us-east-1.amazonaws.com");
  assert.equal(clienteDeIngreso(cognito), "ingreso");
  assert.equal(cognito.clientes.ingreso, "id-ingreso");
});

test("un config.json anterior, sin cliente de ingreso, sigue entrando por el de publicador", async () => {
  servir(config({ institucion: "id-institucion", publicador: "id-publicador" }));
  await cargarConfiguracion();
  assert.notEqual(configuracion().cognito, null);
  assert.equal(clienteDeIngreso(configuracion().cognito), "publicador");
});

test("un cliente de ingreso que no es texto no se usa: el sitio queda sin login", async () => {
  servir(config({ ingreso: 42, institucion: "id-institucion", publicador: "id-publicador" }));
  await cargarConfiguracion();
  assert.equal(configuracion().cognito, null);
});

test("los avisos de la API se leen como oraciones", () => {
  assert.equal(
    oracion("tu cuenta ya es de institución: el tipo se elige una sola vez"),
    "Tu cuenta ya es de institución: el tipo se elige una sola vez.",
  );
  assert.equal(oracion("Tu sesión venció. Ingresá de nuevo para seguir."), "Tu sesión venció. Ingresá de nuevo para seguir.");
  assert.equal(oracion("  "), "");
});

test("antes de preguntar: sin grupos en Cognito pregunta; con grupos, trae un token nuevo una sola vez", () => {
  // Recién registrada: no eligió en ningún lado.
  assert.equal(antesDePreguntar([], false), "preguntar");
  assert.equal(antesDePreguntar([], true), "preguntar");
  // Eligió en otro navegador, o cerró este antes de volver del login: el token es viejo.
  assert.equal(antesDePreguntar(["admin_institucion"], false), "refrescar");
  assert.equal(antesDePreguntar(["medico"], false), "refrescar");
  // Ya volvió de ese pedido y el token sigue sin el grupo: avisa en vez de dar vueltas.
  assert.equal(antesDePreguntar(["admin_institucion"], true), "avisar");
});
