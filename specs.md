# Ateneo · Especificación del pre-MVP

> Estado: borrador 3 · 2026-09-07 · el código de este repo implementa lo que dice acá
> Alcance: el paso anterior al MVP. Una portada y dos secciones que demuestran los dos caminos de la
> arquitectura —inferencia (app → tabla `trabajo` → ALB interno → worker) y evaluación (subred
> aislada → dataset reservado → métricas en la base)— con un modelo ONNX bajado de internet que
> subimos a mano a S3, y un dataset público que hace de "conjunto reservado".

> **Entrega 3.** Lo que cambia es el transporte, no el producto: la tabla
> `trabajo` deja de ser la cola (D4, D5) y los pedidos viajan por SQS (`inferencias`,
> `evaluaciones`); worker y evaluador ya no escriben en la base ni se los llama por HTTP, y un
> procesador aplica los resultados (D6). Hay login con Cognito. Ver [architecture.md](architecture.md).

Documentos relacionados: [architecture.md](architecture.md) (diseño de la aplicación) ·
`ateneo-en-aws.html` y `ateneo-paso-a-paso.html` (infraestructura, fuera del repo por ahora).

---

## 1. Objetivo

Probar de punta a punta, con código real y mínimo, que la infraestructura construida en la guía
soporta el producto:

1. **Publicar un modelo (simulado).** Un botón hace lo que en el producto real pasa cuando un
   publicador sube un modelo: el modelo entra al catálogo y la instancia aislada `eval-1` lo mide
   contra el conjunto reservado. Al terminar, la fila del modelo tiene su accuracy.
2. **Inferir una imagen.** Un usuario sube una imagen médica desde el navegador, el backend encola
   un trabajo, un worker lo procesa y la pantalla muestra la predicción.

**No es un MVP.** No hay permisos por rol ni facturación (la junta de varios modelos ya está: §5.4). Lo
que sí hay, de punta a punta, es el camino del publicador —subir el ONNX y su contrato desde la
pantalla— y el del usuario clínico. El resto queda en §13 como evolución.

## 2. Decisiones tomadas

Resueltas en la conversación del 2026-09-07. Las que siguen abiertas están en §2.1.

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

### 2.1 Notas y cosas que siguen abiertas

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

## 3. Actores

- **Operador** (nosotros): prepara y sube el conjunto reservado, enciende `eval-1`. El modelo ya
  no lo sube: lo sube el publicador desde la pantalla (queda el camino a mano para sembrar el
  bucket sin navegador).
- **Publicador**: sube un modelo con su contrato en `/publicar` y mira su evaluación. Sin cuenta.
- **Usuario clínico**: elige un modelo medido y consulta un estudio en `/consulta`. Sin cuenta.
- **Sistemas**: backend con despachador (capa app), worker de inferencia (capa inferencia),
  evaluador (`eval-1`).

## 4. Dominio

| Concepto | Qué es | Dónde vive |
|----------|--------|------------|
| **Modelo** | Un artefacto ONNX versionado con su contrato (`modelo.json`) y, una vez evaluado, sus métricas. Una fila por versión. | `s3://ateneo-modelos/modelos/<nombre>/<version>/` + tabla `modelo` |
| **Estudio** | Una imagen subida por un usuario, de un tipo de estudio (`torax-rx`). Expira a los 7 días. | `s3://ateneo-estudios/estudios/<uuid>.<ext>` + tabla `estudio` |
| **Trabajo** | Una inferencia de un modelo sobre un estudio, con estado, intentos y resultado. Es la "cola". | tabla `trabajo` |
| **Conjunto de evaluación** | Casos reservados de un tipo de estudio, congelados en una versión, con manifiesto y verdad. | `s3://ateneo-evaluacion/<tipo>/<version>/` |

Reglas:

- Un modelo solo se infiere sobre estudios de su mismo `tipo_estudio`, y se evalúa contra el
  conjunto de su mismo `tipo_estudio`, en la versión más reciente que exista en el bucket.
- Un conjunto en una versión es inmutable. Agregar casos crea otra versión.
- El evaluador y el worker usan **exactamente el mismo** código de preprocesamiento e inferencia
  (`ateneo_ml`): si no, la accuracy publicada no mide lo que el usuario recibe.
- La accuracy en la fila del modelo siempre dice contra qué se midió: `conjunto`, `conjunto_version`
  y el `hash` del manifiesto.

## 5. Flujos

### 5.1 Preparación (una vez, por el operador)

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
4. Subida por la consola de S3 a `ateneo-evaluacion/torax-rx/v1/` (§04 de la guía), o
   `tools/subir_conjunto.py` para conjuntos chicos y para el desarrollo local.
5. Lanzar `eval-1` desde `lt-eval` con el user data del evaluador (§9.5 de la guía).

### 5.2 Subir un modelo, publicarlo y evaluarlo

```
Navegador              Backend (app)          S3 modelos        Postgres          eval-1 (evaluador)      S3 evaluación
   │ POST /api/modelos/subidas ────►│ list prefijo (409 si existe)            │                          │
   │ ◄── 201 {prefix, subida}       │                     │                  │                          │
   │ POST modelo.onnx (form prefirmado) ──────────────────►│                  │                          │
   │ POST /api/modelos/publicar ───►│ valida contrato     │                  │                          │
   │      {nombre, version, contrato}│ head modelo.onnx ─►│                  │                          │
   │                                │ put modelo.json ───►│                  │                          │
   │                                │ upsert modelo pendiente ──────────────►│                          │
   │ ◄── 202 {modelo_id}            │                     │                  │   poll 10 s              │
   │                                │                     │                  │◄─ SELECT … SKIP LOCKED ──│
   │                                │                     │◄──── GET modelo.onnx + modelo.json ─────────│
   │                                │                     │                  │   GET manifiesto/verdad/casos ─►│ (por vpce)
   │                                │                     │                  │   inferir 200 casos      │
   │                                │                     │                  │◄─ UPDATE ok, metricas ───│
   │ GET /api/modelos/{id} (polling 3 s) ─►│ ────────────────────────────────►│                          │
   │ ◄── {estado_evaluacion, accuracy, metricas}                             │                          │
```

1. El publicador elige el `.onnx` y su contrato (o lo escribe en la pantalla, que trae una
   plantilla). `POST /api/modelos/subidas` reserva `modelos/<nombre>/<version>/` —`409` si ese
   prefijo ya tiene algo: una versión publicada no se pisa— y devuelve el `presigned POST`. El
   navegador manda el archivo directo a S3.
2. **Subir y publicar** termina con `POST /api/modelos/publicar` llevando el contrato. El backend
   lo valida (§7), confirma con `head_object` que el ONNX llegó, escribe el `modelo.json` al lado
   e inserta o actualiza la fila con `estado_evaluacion = pendiente`, borrando métricas anteriores.
   Responde `202`. Sobre un modelo que ya está en el bucket, el mismo pedido sin `contrato` lo
   vuelve a encolar leyendo el `modelo.json` que ya existe.
3. El evaluador en `eval-1` toma la fila, baja el modelo, lee manifiesto, verdad y casos de la
   versión más reciente de `torax-rx/` por el endpoint de la VPC, infiere cada caso con
   `ateneo_ml`, calcula métricas y actualiza la fila: `estado_evaluacion = ok`, `accuracy`,
   `metricas`, `conjunto`, `conjunto_version`, `manifiesto`, `evaluador_id`, `evaluado_en`.
   Si algo falla: `error` con el mensaje.
4. La UI hace polling y la tarjeta del modelo pasa de "Evaluando…" a la accuracy con el resto de
   las métricas. **Los casos nunca salen de la subred; lo que sale es un número.**

### 5.3 Inferir una imagen (asíncrono)

```
Navegador              Backend (API)        Postgres      Backend (despachador)     ALB int → Worker     S3
   │ POST /api/estudios ─►│                    │                  │                       │             │
   │ ◄── {estudio_id, subida: {url, campos}}   │                  │                       │             │
   │ POST archivo (form prefirmado) ───────────────────────────────────────────────────────────────────►│
   │ POST /api/inferencias ─►│ head_object ─────────────────────────────────────────────────────────────►│
   │                      │ INSERT trabajo pendiente ─►│          │                       │             │
   │ ◄── 202 {trabajo_id} │                    │                  │                       │             │
   │                      │                    │◄─ SELECT pendiente SKIP LOCKED ─│         │             │
   │                      │                    │── en_curso ─────►│                       │             │
   │                      │                    │                  │── POST /inferir ─────►│             │
   │                      │                    │                  │                       │◄─ GET ──────│
   │                      │                    │                  │◄── {prediccion, …} ───│             │
   │                      │                    │◄─ UPDATE ok ─────│                       │             │
   │ GET /api/trabajos/{id} (polling 1,5 s) ─►│                  │                       │             │
   │ ◄── {estado, resultado, worker_id}        │                  │                       │             │
```

1. El usuario elige un modelo publicado y arrastra una imagen.
2. `POST /api/estudios` valida MIME y tamaño (≤ 20 MB) y devuelve un `presigned POST` con
   `content-length-range`. El navegador sube directo a S3.
3. `POST /api/inferencias {estudio_id, modelo_id}`: el backend confirma la subida con `head_object`,
   verifica que el tipo de estudio coincide, inserta `trabajo` en `pendiente` y responde `202`.
4. El **despachador** (una tarea de fondo en cada proceso del backend, cada 1 s) toma trabajos
   `pendiente` con `SKIP LOCKED` (varias instancias del backend compiten sin pisarse), los marca
   `en_curso`, llama `POST {INFERENCIA_URL}/inferir` con timeout de 30 s y:
   - si responde: guarda `resultado`, `worker_id`, `duracion_ms`, estado `ok`;
   - si hay timeout o error: vuelve a `pendiente` con `intentos + 1`; con 3 intentos pasa a
     `error` y guarda el motivo.
5. La UI hace polling de `GET /api/trabajos/{id}` y muestra la etiqueta predicha, las
   probabilidades por clase, el worker que atendió (hostname, prueba 4 de la demo), la duración y
   la cantidad de intentos.

### 5.4 Consultar a una junta de modelos

Lo que da el nombre al producto: varios modelos opinan sobre el mismo estudio y un informe marca
si coinciden (spec funcional F8 y §6.5; por ahora, solo clasificación).

1. En `/junta` el usuario elige el tipo de estudio y de **2 a 5 modelos distintos** de ese tipo,
   todos con la evaluación terminada (`estado_evaluacion = ok`).
2. Sube la imagen **una sola vez**, igual que en §5.3 (`POST /api/estudios` y el `presigned POST`).
3. `POST /api/consultas {estudio_id, modelo_ids}`: el backend confirma la subida, valida la junta
   entera, guarda la consulta con **un trabajo `pendiente` por modelo** y deja un mensaje por
   trabajo en `inferencias`. Responde `202`. Los modelos corren en paralelo, en los workers que
   haya; worker, procesador y colas no cambian.
4. La UI hace polling de `GET /api/consultas/{id}`: cada modelo muestra su resultado apenas llega.
   Cuando terminaron todos y al menos dos anduvieron, arriba aparece el **informe de consenso**:
   - **peso** de cada modelo = su métrica verificada (el AUC si el evaluador lo midió; si no, la
     accuracy);
   - **consenso** = promedio de las probabilidades ponderado por esos pesos → la etiqueta de mayor
     probabilidad;
   - **acuerdo** = parte del peso total que suman los modelos que coinciden con el consenso;
   - **revisión prioritaria** si el acuerdo es menor al 70 %, destacada arriba del informe.
5. Si algún modelo falla, la consulta queda `parcial` y el consenso se arma con los que
   anduvieron; con uno solo no hay consenso, y si fallan todos queda en `error`. El resultado
   cierra con «Herramienta de soporte a la decisión clínica. No reemplaza el criterio médico.»

Nada de la junta se guarda aparte: el estado y el consenso se calculan al leer, con los trabajos
y las métricas de cada modelo.

## 6. API del backend

Prefijo `/api`. JSON en UTF-8. Errores con `{ "error": "codigo", "detalle": "texto" }`.
Todo lo que no es `/api/*` ni `/health` lo sirve el sitio estático; un `404` fuera de `/api`
devuelve `index.html` (rutas del lado del cliente).

| Método y ruta | Cuerpo | Respuesta | Errores |
|---------------|--------|-----------|---------|
| `GET /health` | — | `{"ok": true}` (sin base; lo usa el ALB) | — |
| `GET /api/health` | — | `{"ok": true, "instancia": "ip-10-0-10-23"}` | — |
| `GET /api/modelos/disponibles` | — | `[{nombre, version, tipo_estudio, publicado: bool, modelo_id?}]` (lista prefijos `modelos/*/*/modelo.json` en S3) | — |
| `POST /api/modelos/subidas` | `{nombre, version, tamano_bytes}` | `201 {prefix, subida: {url, campos}}` | `409` ese prefijo ya tiene algo · `422` tamaño fuera de rango (máx. 512 MB) |
| `POST /api/modelos/publicar` | `{nombre, version, contrato?}` | `202 Modelo` (estado `pendiente`) | `404` no llegó el `modelo.onnx` (o no hay `modelo.json` en S3, sin `contrato`) · `422` contrato inválido · `409` ya está `pendiente` o `en_curso` |
| `GET /api/modelos` | — | `[Modelo]` publicados, orden `creado desc` | — |
| `GET /api/modelos/{id}` | — | `Modelo` | `404` |
| `POST /api/estudios` | `{tipo_estudio, nombre_archivo, content_type, tamano_bytes}` | `201 {estudio_id, subida: {url, campos}}` | `422` MIME o tamaño no permitido |
| `POST /api/inferencias` | `{estudio_id, modelo_id}` | `202 Trabajo` (estado `pendiente`) | `404` · `409` estudio no subido · `422` tipo de estudio distinto |
| `GET /api/trabajos/{id}` | — | `Trabajo` | `404` |
| `POST /api/consultas` | `{estudio_id, modelo_ids}` (de 2 a 5) | `202 Consulta` (estado `en_cola`, un trabajo `pendiente` por modelo) | `404` · `409` estudio no subido o modelo sin evaluación `ok` · `422` menos de 2 o más de 5, repetidos, otro tipo de estudio u otras etiquetas |
| `GET /api/consultas/{id}` | — | `Consulta` con cada modelo y, al terminar, el consenso | `404` |

Esquemas:

```jsonc
// Modelo
{ "id": "uuid", "nombre": "torax-rx-efficientnetb0", "version": "1.0.0",
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
  "evaluador_id": "i-0abc…", "evaluado_en": "…", "error": null,
  "creado": "…", "publicado": "…" }

// Trabajo
{ "id": "uuid", "estudio_id": "uuid", "modelo_id": "uuid",
  "estado": "ok",                            // pendiente | en_curso | ok | error
  "intentos": 1, "worker_id": "ip-10-0-30-14", "duracion_ms": 640,
  "resultado": { "prediccion": "PNEUMONIA",
                 "probabilidades": { "NORMAL": 0.08, "PNEUMONIA": 0.92 } },
  "error": null, "creado": "…", "actualizado": "…" }
```

```jsonc
// Consulta (la junta)
{ "id": "uuid", "estudio_id": "uuid", "creada": "…",
  "estado": "completa",                      // en_cola | procesando | completa | parcial | error
  "consenso": { "prediccion": "PNEUMONIA",   // null hasta que terminan todos, o con menos de 2 ok
                "probabilidades": { "NORMAL": 0.36, "PNEUMONIA": 0.64 },
                "acuerdo": 0.67, "revision_prioritaria": true, "umbral_acuerdo": 0.7, "votos": 3 },
  "inferencias": [                           // un Trabajo por modelo, el de más peso primero, más:
    { "...": "los campos de Trabajo",
      "modelo": { "id": "uuid", "nombre": "torax-rx-neumonia", "version": "1.0.0",
                  "nombre_visible": "Mediscan · Neumonía" },
      "peso": { "metrica": "auc", "valor": 0.995 },   // null si el modelo perdió su métrica
      "coincide": true } ] }                 // null mientras no hay consenso
```

### API del worker (interna, puerto 8081, solo desde `sg-alb-int`)

| Método y ruta | Cuerpo | Respuesta |
|---------------|--------|-----------|
| `GET /health` | — | `{"ok": true}` |
| `POST /inferir` | `{trabajo_id, modelo: {nombre, version, bucket, prefix}, estudio: {bucket, key}}` | `{trabajo_id, worker, prediccion, probabilidades, duracion_ms}` |

El worker es idempotente por construcción: misma entrada, misma salida, no escribe nada.
`400` si el contrato no se puede aplicar a la imagen; `404` si falta el objeto en S3.

### Quién puede llamar a cada ruta (Entrega 4)

Con Cognito, cada ruta de `/api` salvo `/api/publico/*` y `/api/health` pide el access token
(`401 no_autenticado` sin él) y una cuenta de alguno de estos grupos (`403 sin_permiso` si no):

| Rutas | Cuentas |
|-------|---------|
| `/api/modelos/disponibles` · `/api/modelos/subidas` · `/api/modelos/publicar` | publicador · admin de plataforma |
| `POST /api/estudios` · `POST /api/inferencias` · `GET /api/trabajos/{id}` | médico · admin de institución · admin de plataforma |
| `/api/publico/*` · `/api/health` | cualquiera, sin token |

Además, cada estudio y cada trabajo es de quien lo creó: `POST /api/inferencias` sobre un estudio
ajeno y `GET /api/trabajos/{id}` de un trabajo ajeno responden el mismo `404` que un id que no
existe; el admin de plataforma ve todo. `POST /api/modelos/publicar` con `contrato` sobre un modelo
que publicó otra cuenta responde `403`; sin `contrato` (volver a evaluarlo) lo puede cualquiera que
publica.

```jsonc
// 403
{ "error": "sin_permiso", "detalle": "esto es para cuentas de publicador y la tuya es de institución" }
```

Sin Cognito (local, tests) no hay control de acceso: el usuario anónimo pasa por todo.

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
en `error` sin correr nada. La versión a usar es la mayor `vN` que exista bajo `torax-rx/`.

## 9. Esquema de la base

`migraciones/001_inicial.sql`, aplicado con `psql` desde una instancia de la capa app.

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
  -- evaluación (la escribe eval-1)
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

create table trabajo (                        -- la "cola", tal cual la guía §12
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

`migraciones/005_autoria.sql` agrega de quién es cada fila: `creado_por text` en `estudio` y
`trabajo`, y `publicado_por text` en `modelo`, con el `sub` de Cognito (`plataforma` para los
modelos de la demo). Las filas anteriores quedan en `null` y solo las ve un admin de plataforma.
Una junta es de quien creó sus trabajos: la consulta no guarda autor propio.

La junta (`migraciones/004_consultas.sql`): una consulta agrupa los trabajos de sus modelos. Un
trabajo sin consulta es una consulta individual.

```sql
create table consulta (
  id          uuid primary key default gen_random_uuid(),
  estudio_id  uuid not null references estudio(id),
  creada      timestamptz not null default now()
);
alter table trabajo add column consulta_id uuid references consulta(id);
```

## 10. Métricas de evaluación

Calculadas en `ateneo_ml.metricas` solo con NumPy (la imagen dorada no trae scikit-learn).

- Siempre: `n_casos`, `accuracy`, `matriz_confusion`, `duracion_s`, `casos_con_error`.
- Binaria (este modelo, porque declara `positiva`): `sensibilidad`, `especificidad`, `precision`,
  `f1` y `auc` (por ranking, sin dependencias).
- Multiclase: `precision_macro`, `sensibilidad_macro`, `f1_macro`, y el detalle por clase.

Un caso que no se puede decodificar cuenta en `casos_con_error` y no en la matriz. Si más del 5 %
de los casos falla, la evaluación termina en `error`.

## 11. Requisitos no funcionales

| Requisito (guía §12) | Cómo |
|----------------------|------|
| Instancias sin estado | Nada en disco local salvo la caché de modelos en EFS (worker), la copia del sitio estático (app, se rehace al nacer) y un directorio temporal del evaluador que se borra al terminar cada evaluación. |
| Configuración por entorno | `pydantic-settings` lee `/etc/ateneo.env` vía `EnvironmentFile`. Sin IP ni nombres fijos. |
| Sin credenciales de AWS en el código | `boto3` sin argumentos. Local: `AWS_ENDPOINT_URL` apunta a MinIO. |
| `GET /health` rápido y sin base | Backend y worker. |
| Logs a stdout | JSON por línea con `trabajo_id` / `modelo_id`. |
| Timeouts explícitos | Despachador → worker 30 s; S3 `connect 5 s / read 15 s`; evaluador loguea progreso cada 25 casos. |
| Tiempo en UTC | Todo `timestamptz`; el frontend convierte. |
| Límites de entrada | Imagen ≤ 20 MB, MIME `image/png` o `image/jpeg`. |
| Rutas del cliente | `404` fuera de `/api` → `index.html` (guía §10). |
| Sin autenticación | Punto de extensión `Depends(usuario_actual)`, hoy anónimo. |
| Permisos por rol y por autoría | Cada router pide los grupos de Cognito que admite (`403`); un estudio o un trabajo ajeno da `404`. Ver §6, «Quién puede llamar a cada ruta». |

## 12. Pantallas

Tres vistas servidas en `http://<alb>/`, con ruteo del lado del cliente (`/`, `/publicar`,
`/consulta`; un `404` fuera de `/api` devuelve `index.html`). Una por público: la portada explica,
publicación es de quien sube modelos, consulta es de quien atiende.

**Portada (`/`)** — qué es Ateneo, el recorrido de un modelo (publicar → medir aislado → catálogo →
consultar), las dos puertas y lo que el pre-MVP todavía no hace. Muestra en vivo cuántos modelos
hay publicados, cuántos evaluados, la mejor accuracy y cuántos esperan en el bucket.

**Publicación (`/publicar`)**
- **Subir un modelo**: zona de arrastre para el `.onnx` y su `modelo.json` (los dos de una, o el
  ONNX y el contrato escrito en el editor, que trae plantilla). Debajo, lo leído del contrato
  —tipo de estudio, tarea, etiquetas— y el destino `modelos/<nombre>/<version>/`, con aviso si esa
  versión ya existe. **Subir y publicar** muestra el progreso del archivo y después «dando de
  alta». Al lado, qué valida el alta.
- **En el bucket**: una fila por prefijo con `modelo.json` —nombre, versión, tipo de estudio, si ya
  está en el catálogo— y su botón **Publicar** / **Volver a publicar**, que re-evalúa sin volver a
  subir nada.
- **La evaluación**: tarjeta del modelo elegido con la `accuracy` grande, métricas secundarias,
  matriz de confusión, casos, conjunto y versión, hash del manifiesto, evaluador y fecha. Estados:
  «Sin evaluar», «Evaluando…» (spinner y polling cada 3 s), «La evaluación falló: …». Al lado, qué
  valida el alta y qué hace volver a publicar.
- **El catálogo**: tabla de los publicados (modelo, tipo de estudio, evaluación, accuracy, casos,
  conjunto, fecha) con la mejor accuracy de cada tipo marcada. Elegir una fila la muestra arriba.

**Consulta (`/consulta`)**
- **El modelo**: tarjetas de los modelos publicados con la accuracy a la vista; debajo, contra qué
  se midió (sensibilidad, especificidad, casos, conjunto) y la evaluación completa desplegable.
- **El estudio**: zona de arrastre / selector de archivo con vista previa local y botón
  **Consultar**, habilitado con modelo elegido e imagen cargada.
- **El resultado**: «Subiendo» → «En cola» → «Procesando» → etiqueta predicha destacada, barras de
  probabilidad por clase, duración, worker e intentos. Cierra con el aviso de que es orientativo y
  no reemplaza el criterio clínico.
- Errores legibles: «El worker no respondió tras 3 intentos», «Tipo de estudio distinto».

**Barra y pie**: `/api/health` con la instancia que atendió (para ver al ALB alternar) y
alternador de tema claro / oscuro.

**Junta (`/junta`)** — se llega desde la barra, desde el catálogo y desde la ficha de un modelo
evaluado.
- **Armá la junta**: tipo de estudio, los modelos del tipo con la métrica con que pesa cada uno
  (se eligen de 2 a 5; los que no terminaron la evaluación aparecen deshabilitados), la imagen y
  **Consultar a la junta**, con el mismo indicador de pasos que una consulta individual.
- **El informe**: arriba el consenso —la etiqueta, el acuerdo contra la marca del 70 % y
  «Revisión prioritaria» o «Los modelos coinciden»—; debajo cada modelo con su predicción, sus
  probabilidades, el worker que lo corrió y «Coincide» o «Discrepa»; al final la leyenda
  «Herramienta de soporte a la decisión clínica. No reemplaza el criterio médico.»

## 13. Criterios de aceptación

Los ocho se verificaron contra el entorno local con Docker el 2026-09-07. Lo medido:
publicación y evaluación de 200 casos en 14,4 s (accuracy 0,97, sensibilidad 0,95,
especificidad 0,99, AUC 0,995, 0 casos ilegibles); inferencias de 59 a 292 ms; y con el worker
apagado, el trabajo hace 3 intentos y termina en `error` sin colgar nada.


1. **Subir y publicar** con el `.onnx` y su contrato deja el objeto en
   `modelos/<nombre>/<version>/` —los dos archivos, comprobable con `aws s3 ls`— y la fila en
   `pendiente`; con `eval-1` encendida pasa a `ok` con `accuracy` en menos de 3 min para 200 casos.
   Volver a subir esa misma versión responde `409`.
2. La fila del modelo dice contra qué se midió: `conjunto`, `conjunto_version`, `manifiesto.hash`
   y `evaluador_id` poblados.
3. Desde CloudShell, `aws s3api get-object` sobre un caso del conjunto da `AccessDenied` mientras
   la evaluación anterior sí terminó (prueba 6 de la demo).
4. **Consultar** con una imagen de la carpeta `Testing` devuelve `202` de inmediato y el trabajo
   pasa a `ok` en menos de 5 s, con `worker_id` poblado.
5. Repetir seis veces muestra al menos dos `worker_id` distintos con `asg-inf` en 2 instancias
   (prueba 4).
6. Con `asg-inf` en 0, el trabajo queda `pendiente` con `intentos` subiendo cada ~30 s y pasa a
   `error` al tercero; al volver a subir el grupo, un trabajo nuevo se procesa. Nada queda colgado.
7. Volver a apretar **Publicar** sobre un modelo `en_curso` responde `409`; sobre uno `ok` lo
   re-evalúa.
8. Toda la aplicación corre en local con `docker compose up` (Postgres + MinIO) y los cuatro
   servicios en venv, sin credenciales de AWS.
9. **Junta**: con los tres modelos de `torax-rx` y una radiografía, `POST /api/consultas` responde
   `202` con tres trabajos `pendiente` y deja tres mensajes en `inferencias`; al terminar, la
   consulta queda `completa` con el consenso, el acuerdo y la marca de revisión prioritaria si el
   acuerdo baja del 70 %. Con un modelo caído queda `parcial` con el consenso de los otros dos.
   Pedir una junta de 1 o de 6 modelos, o con un modelo sin evaluar, se rechaza.

## 14. Fuera de alcance (evolución)

- Subida del ONNX desde la web con URL prefirmada (el botón simula lo que sigue después).
- Cola SQS en lugar de la tabla `trabajo` (riesgos 01 y 02 de la arquitectura).
- Consenso de juntas para segmentación y detección (la de clasificación está en §5.4).
- DICOM y de-identificación en origen.
- Usuarios, planes, consumo, facturación.
- Evaluación única y firmada por (modelo, conjunto, versión); historial de evaluaciones.
- Carga multiparte (las imágenes del pre-MVP pesan menos de 1 MB).
- HTTPS (sin dominio ni CloudFront en el lab).
