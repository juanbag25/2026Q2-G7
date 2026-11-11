const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const ts = require("typescript");
const path = require("node:path");

const archivo = path.resolve(__dirname, "../src/utilidades/modelos.ts"); // desde la raíz o desde frontend/
const compilado = ts.transpileModule(fs.readFileSync(archivo, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const modulo = new Module(archivo, module);
modulo._compile(compilado, archivo);
const { modelosIniciales } = modulo.exports;

test("un cuarto modelo con mayor accuracy no desplaza los incluidos de la portada", () => {
  const registro = ["original", "dense", "efficient"].map((nombre) => ({ nombre, version: "1.0.0" }));
  const incluidos = registro.map((m, i) => ({ ...m, id: String(i), accuracy: 0.7, predeterminado: true }));
  const cuarto = { nombre: "usuario", version: "1.0.0", id: "cuarto", accuracy: 1, predeterminado: false };
  assert.deepEqual(modelosIniciales([cuarto, ...incluidos].reverse(), registro), incluidos);
});

test("preparación parcial conserva la identidad y no sustituye una versión faltante", () => {
  const registro = [{ nombre: "dense", version: "1.0.0" }, { nombre: "efficient", version: "1.0.0" }];
  const listo = { ...registro[1], id: "correcto" };
  const otraVersion = { nombre: "dense", version: "2.0.0", id: "otra-version" };
  assert.deepEqual(modelosIniciales([otraVersion, listo], registro), [listo]);
});
