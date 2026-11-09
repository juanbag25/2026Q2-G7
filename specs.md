# Ateneo · Especificación del pre-MVP

> Estado: borrador 4 · 2026-11-09 · el código de este repo implementa lo que dice acá
> Alcance: el paso anterior al MVP. Una portada, el catálogo, la ficha de cada modelo y la página
> para publicar, que demuestran los dos caminos de la arquitectura —inferencia (api → cola
> `inferencias` → worker → cola `resultados` → procesador) y evaluación (cola `evaluaciones` →
> evaluador en la subred aislada → conjunto reservado → métricas agregadas)— con cinco modelos
> ONNX bajados de internet y un conjunto público por tipo de estudio que hace de "conjunto reservado".

> **Entrega 3.** Lo que cambió es el transporte, no el producto: la tabla `trabajo` dejó de ser
> la cola y los pedidos viajan por SQS; worker y evaluador no escriben en la base ni se los llama
> por HTTP, y un procesador aplica los resultados. Hay login con Cognito. La §2.2 dice qué
> reemplazó a cada decisión de la Entrega 2.

Documentos relacionados: [architecture.md](architecture.md) (diseño de la aplicación) ·
[terraform/README.md](terraform/README.md) (la infraestructura y cómo desplegarla) ·
[arquitectura-aws.drawio](arquitectura-aws.drawio) (el diagrama de la infraestructura) ·
[models_specs.md](models_specs.md) (los cinco modelos y sus conjuntos).

---

## 1. Objetivo

Probar de punta a punta, con código real y mínimo, que la infraestructura (desde la Entrega 3, la
de `terraform/`) soporta el producto:

1. **Publicar un modelo.** El publicador sube el ONNX y su contrato desde la pantalla: el modelo
   entra al catálogo y el evaluador, en la subred aislada, lo mide contra el conjunto reservado.
   Al terminar, la fila del modelo tiene su accuracy.
2. **Inferir una imagen.** Un usuario sube una imagen médica desde el navegador, la api encola un
   trabajo, un worker lo procesa y la pantalla muestra la predicción.

**No es un MVP.** Hay login con Cognito, pero no permisos por rol, ni juntas de varios modelos, ni
facturación. Lo que sí hay, de punta a punta, es el camino del publicador —subir el ONNX y su
contrato desde la pantalla— y el del usuario clínico. El resto queda en §14 como evolución.

## 2. Decisiones tomadas

Resueltas el 2026-09-07, para la Entrega 2. Quedan como registro: la §2.2 dice qué reemplazó a
las que cambiaron con la Entrega 3.

| # | Tema | Decisión |
|---|------|----------|
| D1 | Cómo entra un modelo | **Lo sube el publicador desde la pantalla.** El `.onnx` va del navegador directo al bucket con un `presigned POST` (igual que la imagen del estudio, D8: un modelo pesa decenas de MB y no tiene por qué atravesar la API) y el contrato viaja en el pedido de alta: la API lo valida, confirma que el archivo llegó, escribe el `modelo.json` al lado y deja la fila en `estado_evaluacion = pendiente` para que `eval-1` la tome. Un modelo que ya esté en el bucket —subido a mano por el operador— se publica igual, sin contrato en el pedido. |
| D2 | Modelo | **ONNX listo para bajar**, sin entrenar nada: `mediscan_pneumonia.onnx` de [Rhishamah/mediscan-pneumonia](https://huggingface.co/Rhishamah/mediscan-pneumonia). 16 MB, radiografía de tórax, binario (NORMAL / PNEUMONIA). **Un modelo evalúa una sola cosa**: este es de `torax-rx`. Un modelo de cerebro sería otro `tipo_estudio` (`cerebro-mri`) con su propio conjunto reservado, sin tocar nada del código. Contrato verificado, ver §7. |
| D3 | Dataset | **Chest X-Ray Images (Pneumonia)**, el mismo de Kaggle pero servido por Hugging Face como [`hf-vision/chest-xray-pneumonia`](https://huggingface.co/datasets/hf-vision/chest-xray-pneumonia): se baja por API pública, **sin cuenta de Kaggle**. Del split de test (624 imágenes) se toman **100 por clase = 200 casos**. Tipo de estudio: `torax-rx`. |
| D4 | Cómo dispara el botón a `eval-1` | Nadie puede iniciar conexiones hacia `eval-1`, así que **polling a la base**: el evaluador toma modelos en `pendiente` con `FOR UPDATE SKIP LOCKED` cada 10 s. `eval-1` tiene que estar encendida durante la demo. |
| D5 | Inferencia | **Asíncrona.** `POST /api/inferencias` inserta el trabajo en `pendiente` y responde `202`. Un **despachador** dentro del backend toma pendientes, llama al ALB interno y escribe el resultado. La UI hace polling. Es exactamente el "despacho + barrido" de la §12 de la guía. **No requiere ningún cambio de infraestructura**: la tabla y el ALB interno ya existen; lo que cambia es que la respuesta HTTP no espera al worker. |
| D6 | Quién escribe el resultado de la inferencia | El **backend** (el despachador). El worker recibe referencias a S3, devuelve el resultado por HTTP y no toca la base. Ver la nota en §2.1. |
| D7 | Frontend | **Sin CloudFront** (el lab no lo concede). El backend sirve el sitio estático en `/` desde `/opt/ateneo/web`, sincronizado del bucket web al arrancar; `/api/*` es la API. Un solo origen, `http://<alb>`, sin CORS entre sitio y API. |
| D8 | Subida de la imagen | **URL prefirmada** directo a S3, con CORS del bucket de estudios abierto al origen del ALB (§10 de la guía). El archivo **se borra solo a los 7 días** por la regla de ciclo de vida; la fila `trabajo` y su resultado quedan. La UI nunca vuelve a leer la imagen de S3: la vista previa sale del archivo local. |
| D9 | Formato de imagen | PNG / JPG. DICOM después, como un decodificador más. |
| D10 | Autenticación | Ninguna. Queda el punto de extensión. |
| D11 | Stack | FastAPI + psycopg 3 (SQL explícito, sin ORM) + React / Vite / TypeScript. |

### 2.1 Notas de la Entrega 2

- **Sobre D6.** La guía sugiere que el worker escriba el resultado con `insert … on conflict`.
  Elegí que no lo haga porque con el despachador en el backend el worker queda sin estado y sin
  dependencia de la base. Si prefieren seguir la guía al pie, es cambiar un adaptador (§13 de
  architecture.md); la infraestructura ya lo permite (`sg-data` acepta 5432 desde `sg-worker`).
- **Una versión no se pisa.** `POST /api/modelos/subidas` responde `409` si el prefijo
  `modelos/<nombre>/<version>/` ya tiene algo. Es la misma regla que rige los conjuntos (§4): lo
  que se midió una vez no cambia de contenido a espaldas de su accuracy. Para corregir un modelo
  se sube otra versión.
- **Volver a publicar el mismo modelo.** El botón sobre un modelo ya evaluado lo vuelve a poner en
  `pendiente` y se re-evalúa, sin volver a subir el archivo (útil para repetir la demo). Si está
  `pendiente` o `en_curso`, el botón responde `409`.
- **Inferir con un modelo sin evaluar.** Se permite: la demo de inferencia no depende de que
  `eval-1` esté encendida. La tarjeta muestra "Sin evaluar" en lugar de la accuracy.
- **Placeholders de la guía.** La autoprueba de `eval-1` (§9.2) ya mira `torax-rx/v1/`, que es
  justo donde va el conjunto real: los dos archivos de mentira se reemplazan por el conjunto y las
  cinco comprobaciones siguen sirviendo tal cual.
- **Agregar un segundo modelo** (de otro tipo de estudio, o del mismo) es subirlo desde la
  pantalla con su contrato. Nada de código cambia. Con dos modelos del mismo `tipo_estudio` se ve
  la comparación de accuracy contra el mismo conjunto, que es la tesis del producto.

### 2.2 Qué reemplazó a cada decisión en la Entrega 3

| # | En la Entrega 2 | Desde la Entrega 3 |
|---|-----------------|--------------------|
| D2 | Un modelo, `mediscan_pneumonia.onnx` | Cinco, de dos tipos de estudio (`torax-rx` y `cerebro-rm`), registrados en `models/catalogo.json` ([models_specs.md](models_specs.md)) |
| D3 | Un conjunto de 200 casos de Rx de tórax | Uno de 200 casos por tipo de estudio, definidos en `models/conjuntos.json` |
| D4 | `eval-1`, encendida a mano, hace polling a la base con `SKIP LOCKED` | La api encola en `evaluaciones`; el servicio `evaluador` pasa de 0 a 1 tarea cuando hay mensajes y publica el resultado en `resultados` |
| D5 | Un despachador dentro del backend llama al worker por el ALB interno | La api encola en `inferencias` y el worker la lee: no hay ALB hacia los workers ni puertos de entrada |
| D6 | El despachador escribe el resultado | El procesador es el único que escribe resultados: lee la cola `resultados` |
| D7 | El backend sirve el sitio por el ALB, un solo origen | El sitio lo sirve S3 (corrección de la E2); la API está detrás de API Gateway, por HTTPS, con CORS hacia el sitio |
| D10 | Sin autenticación | Cognito: Hosted UI, un cliente por tipo de cuenta y cuatro grupos; API Gateway y el backend validan el access token |

## 3. Actores

- **Operador** (nosotros): despliega con Terraform. Con `datos_demo` (el valor por defecto) el
  despliegue prepara solo los cinco modelos y los conjuntos reservados, y el procesador los
  publica; a mano queda el camino para sembrar el bucket sin navegador (§5.1).
- **Publicador**: con su cuenta de Cognito, sube un modelo con su contrato en `/publicar` y mira
  su evaluación.
- **Usuario clínico**: con su cuenta de Cognito, elige un modelo en el catálogo (`/modelos`) y
  consulta un estudio desde la ficha del modelo (`/modelos/<id>`).
- **Visitante**: sin cuenta, ve la portada, el catálogo y las fichas.
- **Sistemas**: cuatro servicios de ECS —api y procesador (capa de aplicación), worker (capa de
  inferencia) y evaluador (capa de evaluación, aislada)— y tres colas de SQS.

## 4. Dominio

| Concepto | Qué es | Dónde vive |
|----------|--------|------------|
| **Modelo** | Un artefacto ONNX versionado con su contrato (`modelo.json`) y, una vez evaluado, sus métricas. Una fila por versión. | `s3://ateneo-modelos-<sufijo>/modelos/<nombre>/<version>/` + tabla `modelo` |
| **Estudio** | Una imagen subida por un usuario, de un tipo de estudio (`torax-rx`, `cerebro-rm`). Expira a los 7 días. | `s3://ateneo-estudios-<sufijo>/estudios/<uuid>.<ext>` + tabla `estudio` |
| **Trabajo** | Una inferencia de un modelo sobre un estudio, con estado, intentos y resultado. La cola es SQS; la tabla guarda el estado. | tabla `trabajo` + un mensaje en `inferencias` |
| **Conjunto de evaluación** | Casos reservados de un tipo de estudio, congelados en una versión, con manifiesto y verdad. | `s3://ateneo-evaluacion-<sufijo>/<tipo>/<version>/` |

Reglas:

- Un modelo solo se infiere sobre estudios de su mismo `tipo_estudio`, y se evalúa contra el
  conjunto de su mismo `tipo_estudio`, en la versión más reciente que exista en el bucket.
- Un conjunto en una versión es inmutable. Agregar casos crea otra versión.
- El evaluador y el worker usan **exactamente el mismo** código de preprocesamiento e inferencia
  (`ateneo_ml`): si no, la accuracy publicada no mide lo que el usuario recibe.
- La accuracy en la fila del modelo siempre dice contra qué se midió: `conjunto`, `conjunto_version`
  y el `hash` del manifiesto.

## 5. Flujos

### 5.1 Preparación

Con `datos_demo = true` (el valor por defecto) esto lo hace solo el despliegue:
`tools/demo_assets.py` baja y verifica los cinco modelos de `models/catalogo.json` y prepara un
conjunto por tipo de estudio (`models/conjuntos.json`). En AWS lo corre el constructor y en local
el servicio `demo-init`; después el procesador publica los modelos y encola su evaluación. A mano,
para un modelo o un conjunto propios:

1. `tools/descargar_modelo.py --solo-descargar`: baja el ONNX y escribe el `modelo.json` de §7 al
   lado, en `./tmp/modelo`. **Esos son los dos archivos que el publicador sube desde `/publicar`.**
   Sin `--solo-descargar` la herramienta además los sube a
   `s3://ateneo-modelos/modelos/torax-rx-neumonia/1.0.0/`: es el atajo para sembrar el bucket sin
   pasar por el navegador, no el camino del producto.
2. `tools/verificar_modelo.py`: carga el ONNX con el contrato (los tensores tienen que existir con
   esas formas) y lo corre sobre casos etiquetados para ver la accuracy. Sirve para no descubrir
   un contrato mal escrito recién en la evaluación.
3. `tools/preparar_conjunto.py --hf hf-vision/chest-xray-pneumonia --split test --por-clase 100
   --salida ./tmp/torax-rx/v1`: baja 100 por clase, convierte a PNG, renombra a UUID, escribe
   `verdad.jsonl` y `manifiesto.json` con el hash del contenido.
4. Subida por la consola de S3 a `ateneo-evaluacion-<sufijo>/torax-rx/v1/`, o
   `tools/subir_conjunto.py` para conjuntos chicos y para el desarrollo local. El evaluador no
   hay que prenderlo: arranca solo cuando llega una evaluación.

### 5.2 Subir un modelo, publicarlo y evaluarlo

```
navegador ─ POST /api/modelos/subidas ─────► api: reserva modelos/<nombre>/<version>/ (409 si existe), firma la subida
navegador ─ POST prefirmado (modelo.onnx) ─► S3 modelos
navegador ─ POST /api/modelos/publicar ────► api: valida el contrato, confirma que llegó el ONNX, escribe modelo.json,
                                                  fila `pendiente` en Postgres, mensaje a `evaluaciones` ─► 202
evaluaciones ──► evaluador (pasa de 0 a 1 tarea, subred aislada)
                   ├─ baja modelo.onnx y modelo.json de S3 modelos
                   ├─ lee manifiesto, verdad y casos de S3 evaluación, solo por el endpoint de la VPC
                   ├─ infiere los 200 casos con ateneo_ml y calcula las métricas
                   └─ publica en `resultados`: `en_curso`, después `ok` con el agregado (o `error`)
resultados ────► procesador: actualiza la fila del modelo (el único que escribe resultados)
navegador ─ GET /api/publico/modelos/{id} cada 3 s ─► api ─► la fila: estado, accuracy, métricas
```

1. El publicador elige el `.onnx` y su contrato (o lo escribe en la pantalla, que trae una
   plantilla). `POST /api/modelos/subidas` reserva `modelos/<nombre>/<version>/` —`409` si ese
   prefijo ya tiene algo: una versión publicada no se pisa— y devuelve el `presigned POST`. El
   navegador manda el archivo directo a S3.
2. **Subir y publicar** termina con `POST /api/modelos/publicar` llevando el contrato. El backend
   lo valida (§7), confirma con `head_object` que el ONNX llegó, escribe el `modelo.json` al lado
   e inserta o actualiza la fila con `estado_evaluacion = pendiente`, borrando métricas anteriores.
   Deja el pedido en la cola `evaluaciones` y responde `202`. Sobre un modelo que ya está en el
   bucket, el mismo pedido sin `contrato` lo vuelve a encolar leyendo el `modelo.json` que ya existe.
3. El evaluador toma el mensaje (si no había ninguna tarea corriendo, el servicio pasa de 0 a 1 y
   tarda uno o dos minutos), baja el modelo, lee manifiesto, verdad y casos de la versión más
   reciente de `<tipo_estudio>/` por el endpoint de la VPC, infiere cada caso con `ateneo_ml`,
   calcula métricas y publica solo el agregado en `resultados`. El procesador actualiza la fila:
   `estado_evaluacion = ok`, `accuracy`, `metricas`, `conjunto`, `conjunto_version`, `manifiesto`,
   `evaluador_id` (la tarea de ECS), `evaluado_en`. Si algo falla: `error` con el mensaje.
4. La UI hace polling y la tarjeta del modelo pasa de "Evaluando…" a la accuracy con el resto de
   las métricas. **Los casos nunca salen de la subred; lo que sale es un número.**

### 5.3 Inferir una imagen (asíncrono)

```
navegador ─ POST /api/estudios ─────► api: fila `estudio` + POST prefirmado
navegador ─ POST prefirmado ────────► S3 estudios (la imagen no pasa por la api)
navegador ─ POST /api/inferencias ──► api: confirma la subida, verifica el tipo de estudio,
                                           fila `trabajo` en `pendiente`, mensaje a `inferencias` ─► 202
inferencias ──► worker (sin puertos de entrada, sin base, sin internet)
                  ├─ publica `en_curso` en `resultados`
                  ├─ baja el modelo (caché en EFS) y el estudio (S3, por el endpoint)
                  ├─ infiere con ateneo_ml
                  └─ publica `ok` con la predicción (o `error`) y recién ahí borra el mensaje
resultados ───► procesador: actualiza la fila del trabajo
navegador ─ GET /api/trabajos/{id} cada 1,5 s ─► api ─► la fila: estado, resultado, worker, duración
```

1. El usuario abre la ficha de un modelo publicado y arrastra una imagen.
2. `POST /api/estudios` valida MIME y tamaño (≤ 20 MB) y devuelve un `presigned POST` con
   `content-length-range`. El navegador sube directo a S3.
3. `POST /api/inferencias {estudio_id, modelo_id}`: la api confirma la subida con `head_object`,
   verifica que el tipo de estudio coincide, inserta `trabajo` en `pendiente`, deja el pedido en
   la cola `inferencias` y responde `202`. Si SQS no contesta, el trabajo queda `pendiente` y el
   reenviador del procesador lo vuelve a mandar a los 10 minutos.
4. El **worker** toma el mensaje, publica `en_curso` en `resultados`, infiere y publica el
   resultado; recién entonces borra el mensaje. Un error definitivo (imagen ilegible, modelo
   incompatible, objeto inexistente) se publica y el mensaje se borra. Uno transitorio devuelve el
   mensaje a la cola en 10 s; al tercer intento se publica el error y SQS pasa el mensaje a la cola
   de fallidos, que dispara la alarma por SNS. Si el worker muere a mitad, el mensaje reaparece al
   vencer la visibilidad (2 min). El **procesador** aplica cada resultado solo si el trabajo sigue
   `pendiente` o `en_curso`: una entrega repetida de SQS no cambia nada.
5. La UI hace polling de `GET /api/trabajos/{id}` y muestra la etiqueta predicha, las
   probabilidades por clase, el worker que atendió (el hostname de la tarea), la duración y la
   cantidad de intentos.

## 6. API del backend

Prefijo `/api`. JSON en UTF-8. Errores con `{ "error": "codigo", "detalle": "texto" }`.

En AWS todo entra por API Gateway, que exige un access token de Cognito válido en todo `/api/*`
salvo `/api/health` y `/api/publico/*`; el backend lo vuelve a validar y responde `401
no_autenticado` si falta o no sirve. En local no hay Cognito y todos son anónimos; ahí la api
también sirve el sitio: lo que no es `/api/*` ni `/health` es el sitio estático, y un `404` fuera
de `/api` devuelve `index.html` (rutas del lado del cliente).

| Método y ruta | Token | Cuerpo | Respuesta | Errores |
|---------------|-------|--------|-----------|---------|
| `GET /health` | — | — | `{"ok": true}` (sin base; lo usa el ALB, no pasa por API Gateway) | — |
| `GET /api/health` | no | — | `{"ok": true, "instancia": "<hostname de la tarea>"}` | — |
| `GET /api/publico/modelos` | no | — | `[Modelo]` publicados, orden `creado desc` | — |
| `GET /api/publico/modelos/{id}` | no | — | `Modelo` | `404` |
| `GET /api/publico/demo` | no | — | estado de la preparación de la demo: global, cantidades y estado de cada modelo inicial | — |
| `GET /api/modelos/disponibles` | sí | — | `[{nombre, version, tipo_estudio, publicado: bool, modelo_id?}]` (lista prefijos `modelos/*/*/modelo.json` en S3) | — |
| `POST /api/modelos/subidas` | sí | `{nombre, version, tamano_bytes}` | `201 {prefix, subida: {url, campos}}` | `409` ese prefijo ya tiene algo · `422` tamaño fuera de rango (máx. 512 MB) |
| `POST /api/modelos/publicar` | sí | `{nombre, version, contrato?}` | `202 Modelo` (estado `pendiente`) | `404` no llegó el `modelo.onnx` (o no hay `modelo.json` en S3, sin `contrato`) · `422` contrato inválido · `409` ya está `pendiente` o `en_curso` |
| `POST /api/estudios` | sí | `{tipo_estudio, nombre_archivo, content_type, tamano_bytes}` | `201 {estudio_id, subida: {url, campos}}` | `422` MIME o tamaño no permitido |
| `POST /api/inferencias` | sí | `{estudio_id, modelo_id}` | `202 Trabajo` (estado `pendiente`) | `404` · `409` estudio no subido · `422` tipo de estudio distinto |
| `GET /api/trabajos/{id}` | sí | — | `Trabajo` | `404` |

El catálogo vive bajo `/api/publico/` porque es el único prefijo que API Gateway deja pasar sin
token: nada que cuelgue de ahí pide identidad ni depende de quién pregunta.

Esquemas:

```jsonc
// Modelo
{ "id": "uuid", "nombre": "torax-rx-efficientnet-b0", "version": "1.0.0",
  "tipo_estudio": "torax-rx", "tarea": "clasificacion",
  "etiquetas": ["NORMAL", "PNEUMONIA"],
  "estado_evaluacion": "ok",                 // pendiente | en_curso | ok | error
  "accuracy": 0.93,                          // null hasta que termine
  "metricas": { "n_casos": 200, "accuracy": 0.95, "sensibilidad": 0.98, "especificidad": 0.92,
                "precision": 0.92, "f1": 0.95, "auc": 0.99, "f1_macro": 0.95,
                "casos_con_error": 0, "duracion_s": 38.4,
                "matriz_confusion": { "etiquetas": ["NORMAL","PNEUMONIA"],
                                      "valores": [[92,8],[2,98]] } },
  "conjunto": "torax-rx", "conjunto_version": "v1",
  "manifiesto": { "casos": 200, "congelado_en": "2026-09-10", "hash": "sha256:…" },
  "evaluador_id": "tarea-…", "evaluado_en": "…", "error": null,
  "creado": "…", "publicado": "…",
  "nombre_visible": "EfficientNet-B0 · Neumonía",   // solo los modelos iniciales de la demo
  "predeterminado": true }

// Trabajo
{ "id": "uuid", "estudio_id": "uuid", "modelo_id": "uuid",
  "estado": "ok",                            // pendiente | en_curso | ok | error
  "intentos": 1, "worker_id": "ip-10-0-30-14", "duracion_ms": 640,
  "resultado": { "prediccion": "PNEUMONIA",
                 "probabilidades": { "NORMAL": 0.08, "PNEUMONIA": 0.92 } },
  "error": null, "creado": "…", "actualizado": "…" }
```

### Los mensajes de las colas

El worker y el evaluador no tienen API: leen su cola y publican en `resultados`.

```jsonc
// inferencias: lo publica la api (y el reenviador del procesador, si el envío falló)
{ "trabajo_id": "uuid",
  "modelo": { "nombre", "version", "bucket", "prefix" },
  "estudio": { "bucket", "key" } }

// evaluaciones: lo publica la api al publicar un modelo (y el procesador, con datos_demo)
{ "tipo": "evaluar_modelo", "modelo_id", "nombre", "version", "tipo_estudio", "prefix", "etiquetas" }

// resultados: lo publican worker y evaluador; lo consume el procesador
{ "tipo": "inferencia", "trabajo_id", "estado": "en_curso", "worker", "intento" }
{ "tipo": "inferencia", "trabajo_id", "estado": "ok", "worker", "prediccion", "probabilidades", "duracion_ms" }
{ "tipo": "inferencia", "trabajo_id", "estado": "error", "error" }
{ "tipo": "evaluacion", "modelo_id", "estado": "en_curso", "evaluador" }
{ "tipo": "evaluacion", "modelo_id", "estado": "ok", "evaluador", "metricas", "conjunto",
  "conjunto_version", "manifiesto", "terminado" }
{ "tipo": "evaluacion", "modelo_id", "estado": "error", "evaluador", "error" }
```

Worker y evaluador no escriben en la base. El procesador aplica cada resultado solo si el registro
sigue `pendiente` o `en_curso`, así que un mensaje repetido o tardío no cambia nada.

## 7. Contrato del modelo

Un modelo es un prefijo en S3 con dos objetos:

```
modelos/<nombre>/<version>/modelo.onnx
modelos/<nombre>/<version>/modelo.json
```

`modelo.json` declara todo lo que el motor necesita para ejecutar el ONNX sin conocer la red. El
del modelo elegido, **verificado contra el grafo y contra casos etiquetados** (§5.1, paso 2):

```jsonc
{
  "nombre": "torax-rx-neumonia",
  "version": "1.0.0",
  "tipo_estudio": "torax-rx",
  "tarea": "clasificacion",
  "origen": "https://huggingface.co/Rhishamah/mediscan-pneumonia · CNN 16 MB · Chest X-Ray (Pneumonia)",
  "entrada": {
    "nombre": "input",               // nombre del tensor de entrada del grafo
    "layout": "NCHW",                // NCHW | NHWC (los modelos de Keras suelen ser NHWC)
    "forma": [1, 3, 224, 224],
    "dtype": "float32",
    "espacio_color": "RGB",          // RGB | L | gris_replicado
    "redimension": "estirar",        // estirar | recortar_centro
    "escala": 255,                   // divide el píxel por esto
    "media": [0.485, 0.456, 0.406],  // normalización ImageNet
    "desvio": [0.229, 0.224, 0.225]
  },
  "salida": {
    "nombre": "output",
    "tipo": "logit_sigmoide",        // logits (softmax) | probabilidades | logit_sigmoide (1 valor)
    "etiquetas": ["NORMAL", "PNEUMONIA"],
    "positiva": "PNEUMONIA",
    "umbral": 0.5
  }
}
```

**Cómo se verificó**, porque un contrato mal escrito no da error: da predicciones malas. El grafo
declara `input` de forma `[batch, 3, 224, 224]` y `output` de `[batch, 1]`, un solo valor, que es
lo que hace `logit_sigmoide`. Con esa normalización y ese orden de etiquetas, sobre 40 casos
etiquetados del split de test da accuracy 0,975, sensibilidad 1,0, especificidad 0,95 y AUC 0,99.
Con las otras normalizaciones probadas (solo dividir por 255, o media y desvío 0,5) la accuracy
cae a 0,50, que es azar. `tools/verificar_modelo.py` repite esa comprobación.

Validación al publicar (`POST /api/modelos/publicar`): campos obligatorios, `forma` de 4
dimensiones con batch 1 coherente con `layout` y con `espacio_color`, `etiquetas` sin repetir,
`positiva ∈ etiquetas`, enums válidos. La validación contra el grafo (que los tensores existan con
esas formas) la hace el evaluador al cargar el modelo: la API no tiene ONNX Runtime.

## 8. Formato del conjunto de evaluación

```
torax-rx/v1/manifiesto.json
torax-rx/v1/verdad.jsonl
torax-rx/v1/casos/<uuid>.png
```

```jsonc
// manifiesto.json
{ "conjunto": "torax-rx", "version": "v1", "casos": 200,
  "congelado_en": "2026-09-07",
  "etiquetas": ["NORMAL", "PNEUMONIA"],
  "criterios": "hf-vision/chest-xray-pneumonia (test): hasta 100 por clase, PNG RGB, semilla 42",
  "hash": "sha256:<hash de los sha256 de los casos, ordenados por nombre>" }
```

```jsonl
// verdad.jsonl — una línea por caso; el nombre no insinúa el diagnóstico
{"caso": "3f2a…-….png", "etiqueta": "PNEUMONIA"}
{"caso": "9c10…-….png", "etiqueta": "NORMAL"}
```

El evaluador verifica que las líneas de `verdad.jsonl` coinciden con `casos` del manifiesto y con
los objetos bajo `casos/`, y que cada etiqueta está en las del modelo. Si no, la evaluación termina
en `error` sin correr nada. La versión a usar es la mayor `vN` que exista bajo `<tipo_estudio>/`
(hoy `torax-rx/` y `cerebro-rm/`).

## 9. Esquema de la base

`migraciones/001_inicial.sql`. Las migraciones las aplica el procesador al arrancar, con un candado
de la base para que dos tareas no lo hagan a la vez. `002_procesador.sql` agrega
`modelo.actualizado` (para vencer las evaluaciones que quedaron sin noticias) y `003_demo.sql`, la
tabla `demo_inicializacion` (la outbox con la que el procesador encola la evaluación de los
modelos de la demo).

```sql
create table modelo (
  id                 uuid primary key default gen_random_uuid(),
  nombre             text not null,
  version            text not null,
  tipo_estudio       text not null,
  tarea              text not null,
  etiquetas          jsonb not null,
  s3_prefix          text not null,           -- modelos/<nombre>/<version>/
  contrato           jsonb not null,          -- copia de modelo.json al publicar
  -- evaluación (la escribe el procesador, con lo que publica el evaluador)
  estado_evaluacion  text not null check (estado_evaluacion in ('pendiente','en_curso','ok','error')),
  accuracy           numeric(5,4),
  metricas           jsonb,
  conjunto           text,
  conjunto_version   text,
  manifiesto         jsonb,
  evaluador_id       text,
  evaluado_en        timestamptz,
  error              text,
  creado             timestamptz not null default now(),
  publicado          timestamptz not null default now(),
  unique (nombre, version)
);
create index modelo_pendientes on modelo (estado_evaluacion, publicado);

create table estudio (
  id            uuid primary key default gen_random_uuid(),
  tipo_estudio  text not null,
  s3_key        text not null,
  content_type  text not null,
  tamano_bytes  bigint,
  estado        text not null check (estado in ('pendiente_subida','subido')),
  creado        timestamptz not null default now()
);

create table trabajo (                        -- el estado de cada inferencia; la cola es SQS
  id            uuid primary key default gen_random_uuid(),
  estudio_id    uuid not null references estudio(id),
  modelo_id     uuid not null references modelo(id),
  estado        text not null check (estado in ('pendiente','en_curso','ok','error')),
  intentos      int  not null default 0,
  worker_id     text,
  resultado     jsonb,
  duracion_ms   int,
  error         text,
  creado        timestamptz not null default now(),
  actualizado   timestamptz not null default now()
);
create index trabajo_pendientes on trabajo (estado, actualizado);
```

## 10. Métricas de evaluación

Calculadas en `ateneo_ml.metricas` solo con NumPy (la imagen `ml` no trae scikit-learn).

- Siempre: `n_casos`, `accuracy`, `matriz_confusion`, `duracion_s`, `casos_con_error`.
- Binaria (este modelo, porque declara `positiva`): `sensibilidad`, `especificidad`, `precision`,
  `f1` y `auc` (por ranking, sin dependencias).
- Multiclase: `precision_macro`, `sensibilidad_macro`, `f1_macro`, y el detalle por clase.

Un caso que no se puede decodificar cuenta en `casos_con_error` y no en la matriz. Si más del 5 %
de los casos falla, la evaluación termina en `error`.

## 11. Requisitos no funcionales

| Requisito | Cómo |
|-----------|------|
| Tareas sin estado | Nada en disco salvo la caché de modelos en EFS (worker) y un directorio temporal del evaluador que se borra al terminar cada evaluación. ECS reemplaza tareas sin aviso. |
| Configuración por entorno | `pydantic-settings` lee las variables que Terraform escribe en cada definición de tarea; `DATABASE_URL` la inyecta ECS desde Secrets Manager, solo a api y procesador. Sin IP ni nombres fijos. |
| Sin credenciales de AWS en el código | `boto3` sin argumentos: en AWS, el rol de la tarea. En local, `AWS_ENDPOINT_URL_*` apunta a MinIO y a ElasticMQ. |
| `GET /health` rápido y sin base | En la api: es el health check del ALB. |
| Logs a stdout | Una línea por evento con `trabajo_id` / `modelo_id`; ECS los manda a CloudWatch Logs (`/ecs/ateneo/<servicio>`, 7 días). |
| Timeouts explícitos | S3 `connect 5 s / read 15 s` (30 s en el evaluador); long polling de 20 s en las colas; el evaluador loguea el progreso cada 25 casos. |
| Tiempo en UTC | Todo `timestamptz`; el frontend convierte. |
| Límites de entrada | Imagen ≤ 20 MB, MIME `image/png` o `image/jpeg`; modelo ≤ 512 MB. |
| Rutas del cliente | El bucket web devuelve `index.html` como documento de error; en local lo hace la api. |
| Autenticación | Cognito. API Gateway valida el access token en todo `/api/*` salvo `/api/health` y `/api/publico/*`, y el backend lo vuelve a validar (`Depends(usuario_actual)`). |

## 12. Pantallas

Cuatro vistas con ruteo del lado del cliente: `/`, `/modelos`, `/modelos/<id>` y `/publicar`
(`/consulta`, de la versión anterior, cae en el catálogo). En AWS el sitio lo sirve S3 por HTTP y
los datos van a API Gateway por HTTPS. Portada, catálogo y fichas son públicos; publicar y analizar
un estudio piden sesión.

**Portada (`/`)** — qué es Ateneo, los modelos incluidos (los cinco de la demo, con el mejor de
cada tipo marcado), cómo funciona en tres pasos y la invitación a publicar uno propio. Muestra en
vivo cuántos modelos hay, cuántos están listos para usar, cuántos tipos de estudio y la mejor
accuracy.

**Catálogo (`/modelos`)** — tarjetas de los modelos publicados, filtrables por tipo de estudio, de a
nueve por página; los evaluados primero, del mejor al peor. Cada tarjeta lleva a su ficha.

**Ficha (`/modelos/<id>`)**
- **El rendimiento**: la `accuracy`, las métricas secundarias, la matriz de confusión, los casos,
  el conjunto y su versión, el hash del manifiesto, el evaluador y la fecha. Mientras se evalúa,
  el estado («En cola», «Evaluando…»), y la ficha se actualiza sola cada 4 s.
- **Analizar un estudio** (con sesión): zona de arrastre con vista previa local, «Subiendo» → «En
  cola» → «Procesando» → la etiqueta predicha con las barras de probabilidad por clase, la
  duración y el worker que atendió. Cierra con el aviso de que no reemplaza el criterio clínico y
  de que el estudio se borra a los 7 días. Sin sesión, pide ingresar o crear una cuenta.

**Publicar (`/publicar`)** (con sesión)
- **Subir un modelo**: zona de arrastre para el `.onnx` y su `modelo.json` (los dos de una, o el
  ONNX y el contrato escrito en el editor, que trae plantilla). Debajo, lo leído del contrato
  —tipo de estudio, tarea, etiquetas— y el destino `modelos/<nombre>/<version>/`, con aviso si esa
  versión ya existe. **Subir y publicar** muestra el progreso del archivo y después sigue la
  evaluación en vivo.
- **En el bucket**: una fila por prefijo con `modelo.json` —nombre, versión, tipo de estudio, si ya
  está en el catálogo y el estado de su evaluación— con su botón **Publicar** / **Volver a
  publicar**, que re-evalúa sin volver a subir nada.

**Barra y pie**: las secciones, el tema claro u oscuro, la sesión («Ingresar», o el email y
«Salir») y el estado de la API (`/api/health`, con la tarea que atendió).

## 13. Criterios de aceptación

Los criterios de la Entrega 2 (con `eval-1`, `asg-inf` y el ALB interno) se verificaron en local el
2026-09-07: publicación y evaluación de 200 casos en 14,4 s (accuracy 0,97, sensibilidad 0,95,
especificidad 0,99, AUC 0,995, 0 casos ilegibles), inferencias de 59 a 292 ms, y con el worker
apagado el trabajo hacía 3 intentos y terminaba en `error` sin colgar nada.

Con la arquitectura de la Entrega 3 quedan así. El despliegue del 25/10 creó toda la
infraestructura sin errores, pero **estos pasos todavía no se recorrieron en AWS**: son el guion
del ensayo de la Entrega 4.

1. **Subir y publicar** con el `.onnx` y su contrato deja los dos archivos en
   `modelos/<nombre>/<version>/` y la fila en `pendiente`; el evaluador arranca solo (de 0 a 1
   tarea) y la pasa a `ok` con `accuracy` en menos de 5 min para 200 casos. Volver a subir esa
   misma versión responde `409`.
2. La fila del modelo dice contra qué se midió: `conjunto`, `conjunto_version`, `manifiesto.hash`
   y `evaluador_id` (la tarea de ECS) poblados.
3. Desde CloudShell, fuera de la VPC, `aws s3api get-object` sobre un caso del conjunto da
   `AccessDenied`, aunque la evaluación sí terminó.
4. **Consultar** con una imagen del tipo del modelo devuelve `202` de inmediato y el trabajo pasa a
   `ok` en menos de 10 s, con `worker_id` poblado.
5. Con más de 10 mensajes esperando por tarea en `inferencias` durante unos minutos, el servicio
   `worker` suma tareas (hasta 4) y vuelve a 1 cuando la cola se vacía.
6. Un mensaje de `inferencias` que falla tres veces termina en su cola de fallidos y la alarma
   avisa por SNS; el trabajo queda en `error` y nada queda colgado.
7. Volver a apretar **Publicar** sobre un modelo `en_curso` responde `409`; sobre uno `ok` lo
   re-evalúa.
8. Sin token, todo `/api/*` salvo `/api/health` y `/api/publico/*` responde `401` en API Gateway.
9. Toda la aplicación corre en local con `docker compose up` (Postgres, MinIO y ElasticMQ), sin
   credenciales de AWS.

## 14. Fuera de alcance (evolución)

- Juntas de varios modelos y consenso.
- Permisos por rol, organizaciones (instituciones y publicadores), planes, consumo y facturación.
- DICOM y de-identificación en origen.
- Conector con los sistemas del centro (PACS, HIS, FHIR).
- Evaluación única y firmada por (modelo, conjunto, versión); historial de evaluaciones;
  re-evaluación periódica.
- Carga multiparte (las imágenes del pre-MVP pesan menos de 1 MB).
- HTTPS en la descarga del sitio: sin dominio ni CloudFront en el lab, S3 lo sirve por HTTP. Los
  datos y los tokens sí viajan por HTTPS, a API Gateway.

Salieron de esta lista porque se implementaron: la subida del ONNX desde la web (§5.2), la cola
SQS en lugar de la tabla `trabajo` (§5.3) y el login (§11).
