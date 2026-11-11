# Ateneo · Arquitectura de la aplicación

> Estado: borrador 3 · 2026-10-15 · Entrega 3
> Complementa a [specs.md](specs.md) (qué hace) y a «Ateneo en AWS 2.0» (la infraestructura, en
> [terraform/](terraform/README.md)). Este documento dice **cómo está construido el código** para
> que entre en esa infraestructura y para que crezca sin reescribirse.

---

## 1. Componentes y dónde corren

Cuatro servicios de ECS sobre Fargate, dos imágenes, y el sitio en S3.

| Componente | Repo | Imagen | Capa de red | Proceso | Entrada |
|------------|------|--------|-------------|---------|---------|
| Sitio | `frontend/` | etapa `frontend` de `backend` | bucket web, por HTTP | — | el navegador |
| api | `backend/` | `backend` | aplicación | `uvicorn app.main:app :8080` | 8080, solo desde el ALB interno |
| procesador | `backend/` | `backend` | aplicación | `python -m app.procesador` | ninguna: lee `resultados` |
| worker | `worker/` + `ateneo_ml/` | `ml` | inferencia, sin internet | `python -m worker.main` | ninguna: lee `inferencias` |
| evaluador | `evaluador/` + `ateneo_ml/` | `ml` | evaluación, aislada | `python -m evaluador.main` | ninguna: lee `evaluaciones` |
| Migraciones | `migraciones/` | `backend` | — | las aplica el procesador al arrancar | — |
| Herramientas | `tools/` | `ml` | tu máquina, o el constructor con `datos_demo` | — | — |

```
 navegador ──HTTP──► S3 sitio (bucket web)
     │
     ├──HTTPS + token──► API Gateway ──VPC Link──► ALB interno + WAF ──► api ──► RDS
     │                                                                    │      ▲
     │  POST prefirmado                                    inferencias ◄──┤      │ escribe
     ▼                                                    evaluaciones ◄──┘      │
 S3 estudios · S3 modelos                                      │                 │
                              worker ◄── inferencias ──────────┘                 │
                                │ ──► resultados ──► procesador ─────────────────┘
                              evaluador ◄── evaluaciones
                                │ ──► resultados
                                └──► S3 evaluación (solo por el endpoint de la VPC)
```

Las flechas son las que permiten los grupos de seguridad (`terraform/seguridad.tf`). **El worker y
el evaluador no tocan la base ni tienen credenciales**: publican en `resultados` y el procesador,
el único escritor, lo aplica. **Nadie llama al worker ni al evaluador**: no abren puertos.

## 2. Estructura del repositorio

```
TP-AWS/
├── specs.md · architecture.md · README.md
├── backend/                     # imagen backend: api y procesador
│   ├── app/
│   │   ├── main.py              # la api: crea la app y monta el sitio en "/" (solo en local)
│   │   ├── procesador.py        # el procesador: migraciones, cola resultados, reenviador
│   │   ├── config.py            # Settings (pydantic-settings) desde variables de entorno
│   │   ├── dominio/             # entidades y reglas puras; sin FastAPI, sin boto3, sin SQL
│   │   │   ├── modelo.py · estudio.py · trabajo.py · usuario.py
│   │   │   ├── contrato.py      # validación de modelo.json (misma que ateneo_ml, ver §7)
│   │   │   └── errores.py       # NoEncontrado, Conflicto, EntradaInvalida, NoAutenticado, ServicioNoDisponible
│   │   ├── aplicacion/          # casos de uso; dependen solo de puertos
│   │   │   ├── puertos.py       # Protocols: repositorios, almacenes, colas, registro de resultados
│   │   │   └── casos_uso/ modelos.py · estudios.py · inferencias.py · resultados.py
│   │   ├── infraestructura/     # adaptadores; uno por tecnología
│   │   │   ├── postgres/        # pool psycopg 3 · repositorios con SQL explícito · migraciones
│   │   │   ├── s3/              # almacén de estudios (prefirmado) · catálogo de modelos en S3
│   │   │   ├── sqs/             # ColaSqs: enviar, recibir, borrar
│   │   │   ├── cognito/         # verificador de access tokens (JWKS del user pool)
│   │   │   └── aws.py           # los clientes de boto3
│   │   └── api/                 # FastAPI: routers, esquemas pydantic, dependencias (DI), errores, sitio
│   ├── tests/
│   └── requirements.txt
├── ateneo_ml/                   # compartido worker + evaluador · SOLO numpy, pillow, onnxruntime
├── worker/                      # imagen ml · lee inferencias, publica en resultados
│   ├── main.py · config.py · aplicacion.py · puertos.py · consumidor.py
│   └── infraestructura/ proveedor_efs_s3.py · fuente_s3.py · cola_sqs.py
├── evaluador/                   # imagen ml · lee evaluaciones, publica en resultados
│   ├── main.py · config.py · aplicacion.py · puertos.py · consumidor.py
│   └── infraestructura/ conjunto_s3.py · modelo_s3.py · colas_sqs.py
├── frontend/                    # React + Vite + TypeScript
├── migraciones/ 001_inicial.sql · 002_procesador.sql
├── tools/                       # descargar_modelo · verificar_modelo · preparar_conjunto · subir_conjunto
├── docker/                      # Dockerfile.backend · Dockerfile.ml · Dockerfile.tests · elasticmq.conf
├── docker-compose.yml           # la misma topología en local: Postgres, MinIO, ElasticMQ y los cuatro servicios
└── terraform/                   # toda la infraestructura: terraform apply levanta todo
```

**Por qué `ateneo_ml` es un paquete aparte, y worker y evaluador comparten imagen.** La accuracy
que publica el evaluador solo mide lo que el usuario recibe si los dos corren el mismo
preprocesamiento, el mismo motor y el mismo posprocesamiento. Un paquete compartido en una sola
imagen lo garantiza por construcción. El backend **no** lo importa: no tiene ONNX Runtime.

## 3. Principios de diseño

### 3.1 Puertos y adaptadores en cada servicio

```
   api / procesador / consumidores  ──►  aplicacion (casos de uso)  ──►  dominio
              │                                      ▲
              └──────────── infraestructura ─────────┘   (los adaptadores implementan los puertos)
```

- **Dominio**: dataclasses y reglas (`Modelo.republicar()`, `Modelo.verificar_compatible(estudio)`,
  `Estudio.confirmar(...)`). Sin imports de frameworks.
- **Aplicación**: casos de uso, una clase con `ejecutar(...)`. Reciben puertos por constructor. No
  saben si detrás hay S3 o MinIO, SQS o ElasticMQ, Postgres o un dict.
- **Puertos**: `typing.Protocol`, chicos, con nombre de negocio (`ColaEvaluaciones`, no `SqsClient`).
- **Infraestructura**: único lugar con `boto3`, `psycopg`, `jwt`, `onnxruntime`.
- **api / procesador / consumidores**: traducen (HTTP o mensajes) ↔ casos de uso.
  `dependencias.py` y `procesador.py` son los *composition roots*: lo único que instancia adaptadores.

### 3.2 SOLID, con el ejemplo concreto de este código

| Principio | Cómo se ve acá | Qué evita |
|-----------|----------------|-----------|
| **S** · Responsabilidad única | `EncolarInferencia` solo valida, inserta y encola; `AplicarResultado` solo aplica lo que llega de la cola; el worker solo infiere; el evaluador solo evalúa. El worker no escribe en la base y la API no llama al worker. | Un `main.py` con SQL, boto3 y reglas mezcladas. |
| **O** · Abierto/cerrado | Un modelo nuevo con otro tamaño, layout NCHW u otra normalización **no cambia código**: cambia `modelo.json`. Un formato de imagen nuevo es un `DecodificadorImagen` registrado por extensión; una tarea nueva (`segmentacion`) es un posprocesador y un calculador de métricas más. | `if modelo == "neumonia": … elif …` |
| **L** · Sustitución de Liskov | Todos los adaptadores de un puerto cumplen el contrato **incluyendo los errores**: un objeto que no existe lanza `NoEncontrado` en S3, en MinIO y en el fake de memoria. | Tests que pasan con el fake y fallan en AWS. |
| **I** · Segregación de interfaces | `ColaInferencias` y `ColaEvaluaciones` tienen un solo método. `TrabajosSinEnviar` y `EvaluacionesSinNoticias` exponen solo lo que usa el reenviador; `RegistroResultados`, solo lo que escribe el procesador. Ningún caso de uso recibe métodos que no usa. | Un `Repositorio` gigante. |
| **D** · Inversión de dependencias | Casos de uso y adaptadores importan `puertos.py`; **nadie importa `infraestructura` salvo `dependencias.py` y `procesador.py`**. | Cambiar de psycopg a SQLAlchemy tocando casos de uso. |

Reglas adicionales:

- **Errores del dominio, no de la tecnología.** Los adaptadores traducen (`ClientError 404` →
  `NoEncontrado`; un error de SQS → `ServicioNoDisponible`). Un solo `exception_handler`
  los convierte en HTTP. Los routers no tienen `try/except`.
- **Los casos de uso devuelven entidades**; la API las convierte a esquemas pydantic.
- **Configuración inmutable y tipada** (`Settings`), cargada una vez e inyectada.
- **Tiempo inyectado** (`Reloj`) para tests deterministas.

## 4. Backend

### 4.1 Puertos (`backend/app/aplicacion/puertos.py`)

```python
class RepositorioModelos(Protocol): ...          # guardar · obtener · buscar · listar
class RepositorioEstudios(Protocol): ...         # guardar · obtener
class RepositorioTrabajos(Protocol): ...         # guardar · obtener
class RepositorioConsultas(Protocol): ...        # la junta: guardar(consulta, trabajos) en una transacción · obtener · trabajos_de

class ColaInferencias(Protocol):
    def enviar(self, p: PeticionInferencia) -> None: ...        # ServicioNoDisponible
class ColaEvaluaciones(Protocol):
    def enviar(self, p: PeticionEvaluacion) -> None: ...        # ServicioNoDisponible

class RegistroResultados(Protocol):              # el procesador; cada método aplica solo si el
    def inferencia_en_curso(...) -> bool: ...    # registro sigue pendiente o en_curso
    def inferencia_terminada(...) -> bool: ...
    def inferencia_fallida(...) -> bool: ...
    def evaluacion_en_curso(...) -> bool: ...
    def evaluacion_terminada(...) -> bool: ...
    def evaluacion_fallida(...) -> bool: ...

class TrabajosSinEnviar(Protocol): ...           # tomar_para_reenviar · vencer_en_curso
class EvaluacionesSinNoticias(Protocol): ...     # vencer_en_curso
class AlmacenEstudios(Protocol): ...             # firmar_subida · describir
class CatalogoModelosEnBucket(Protocol): ...     # listar · leer_contrato · existe · firmar_subida · …
class VerificadorTokens(Protocol):
    def verificar(self, token: str) -> Usuario: ...             # NoAutenticado
class Reloj(Protocol): ...
```

### 4.2 Los casos de uso que importan

```python
class PublicarModelo:
    def ejecutar(self, usuario, nombre, version, contrato_crudo=None) -> Modelo:
        contrato = ContratoModelo.desde_json(crudo)                         # EntradaInvalida → 422
        if existente and contrato_crudo is not None:
            existente.verificar_autor(usuario)                              # SinPermiso → 403
        modelo = existente.republicar(...) if existente else Modelo.publicar(..., usuario.sub)  # Conflicto → 409
        if contrato_crudo is not None:                                      # recién subido desde la web
            self.catalogo.describir_modelo(prefix)                          # ¿llegó el ONNX?
            self.catalogo.escribir_contrato(prefix, contrato_crudo)
        self.modelos.guardar(modelo)                                        # pendiente
        try:
            self.cola.enviar(PeticionEvaluacion.de(modelo))                 # a `evaluaciones`
        except ServicioNoDisponible:
            modelo.no_se_pudo_encolar(...)                                  # error: se puede republicar
            self.modelos.guardar(modelo)

class EncolarInferencia:
    def ejecutar(self, usuario, estudio_id, modelo_id) -> Trabajo:
        if not usuario.es_suyo(estudio.creado_por): raise NoEncontrado(...) # lo ajeno no existe → 404
        ...                                                                 # confirmar subida, compatibilidad
        self.trabajos.guardar(trabajo)                                      # pendiente
        try:
            self.cola.enviar(PeticionInferencia(...))                       # a `inferencias`
        except ServicioNoDisponible:
            pass                                                            # lo reenvía el procesador

class AplicarResultado:                                                     # en el procesador
    def ejecutar(self, cuerpo: dict) -> bool: ...                           # MensajeInvalido si no se entiende

class CrearConsulta:                                                        # la junta (§4.6)
    def ejecutar(self, estudio_id, modelo_ids) -> InformeConsulta:
        consulta = Consulta.junta(estudio, modelos, ahora)                  # 2 a 5, evaluados, mismo tipo
        self.consultas.guardar(consulta, consulta.trabajos_para(...))       # una transacción
        for trabajo, modelo in ...:
            mandar_a_la_cola(self.cola, trabajo, modelo, ...)               # lo mismo que EncolarInferencia

class ConsultarConsulta:
    def ejecutar(self, id) -> InformeConsulta:
        return consulta.informe(trabajos, modelos)                          # estado y consenso, al leer
```

Cada decisión de negocio vive en el dominio (`republicar`, `confirmar`, `verificar_compatible`); los
casos de uso solo ordenan llamadas. Con fakes en memoria se prueban en milisegundos.

### 4.3 El procesador

El único que escribe resultados (decisión 04 de «Ateneo en AWS 2.0»). Un proceso por tarea, con dos
hilos:

- **Principal**: long polling de `resultados` (de a 10), `AplicarResultado` por mensaje y recién
  después `delete_message`. Si la base falla, el mensaje no se borra: SQS lo vuelve a entregar y,
  tras 5 intentos, lo pasa a la cola de fallidos. Un mensaje ilegible se descarta.
- **Reenviador**, cada minuto: `ReenviarPendientes` vuelve a encolar los trabajos `pendiente` de más
  de 10 minutos (el envío de la api falló) y vence los `en_curso` sin noticias; `VencerEvaluaciones`
  vence los modelos `en_curso` sin noticias hace 2 horas (el evaluador murió en el último intento).
- **Al arrancar** aplica las migraciones con `pg_advisory_lock`: dos tareas no lo hacen a la vez.

Idempotencia: cada `update` lleva `where estado in ('pendiente', 'en_curso')`. Un resultado repetido
o tardío no cambia nada, así que una entrega doble de SQS no se nota.

Los mensajes de `resultados`:

```
{"tipo": "inferencia", "trabajo_id", "estado": "en_curso", "worker", "intento"}
{"tipo": "inferencia", "trabajo_id", "estado": "ok", "worker", "prediccion", "probabilidades", "duracion_ms"}
{"tipo": "inferencia", "trabajo_id", "estado": "error", "error"}
{"tipo": "evaluacion", "modelo_id", "estado": "en_curso" | "ok" | "error", "evaluador", …métricas agregadas}
```

### 4.4 Persistencia

- `psycopg 3` + `psycopg_pool.ConnectionPool` (mín 1, máx 4 por proceso; `db.t3.micro` admite
  ~80 conexiones). Solo api y procesador tienen `DATABASE_URL`, que ECS inyecta desde Secrets Manager.
- SQL explícito en los repositorios, `row_factory=dict_row`, mapeo a dataclasses en un solo lugar
  por tabla. Sin ORM.
- Transacciones cortas, una por operación.
- Migraciones: SQL numerado + `infraestructura/postgres/migraciones.py` (tabla `migracion_aplicada`).

### 4.5 API y sitio estático

- Routers por recurso; reciben casos de uso por `Depends`. `dependencias.py` es el único módulo
  de la api que importa `infraestructura`.
- `errores.py`: `NoAutenticado` 401, `SinPermiso` 403, `NoEncontrado` 404, `Conflicto` 409,
  `EntradaInvalida` 422, `ServicioNoDisponible` 502.
- `sitio.py`: en local monta el sitio en `/` **después** de los routers y devuelve `index.html` para
  cualquier `404` fuera de `/api`. En AWS el sitio está en S3 y la tarea arranca sin él.
- `GET /health` (el health check del ALB) sin dependencias ni base; `GET /api/health` agrega el
  hostname de la tarea.
- Sin CORS en el backend: el sitio está en S3 y la API detrás de API Gateway, que es quien contesta
  el CORS. El de los buckets de estudios y modelos, para el `POST` prefirmado, lo escribe Terraform.
- **Las dos subidas son la misma pieza.** La imagen del estudio y el ONNX del modelo salen del
  navegador hacia S3 con un `presigned POST` firmado por la API, que ata el content type y el
  tamaño máximo; el archivo nunca atraviesa la capa de aplicación.
- Autenticación: `Depends(usuario_actual)`. Con `COGNITO_USER_POOL_ID` y `COGNITO_CLIENT_IDS`
  valida el access token de `Authorization: Bearer` contra las claves del user pool y devuelve un
  `Usuario` con su `sub` y sus grupos; sin token o con uno inválido, `401 no_autenticado`. API
  Gateway ya lo validó: esta es la segunda capa. Sin esas variables (local, tests), todos son
  anónimos, y el anónimo trae todos los grupos: pasa por todo como antes.
- **Autorización por rol**, en cada router: `dependencies=[Depends(exigir_grupos(*grupos))]`. Sin
  ninguno de esos grupos, `403 sin_permiso` con un detalle que dice qué cuenta hace falta y cuál es
  la del usuario. Es la versión mínima de la matriz de la spec (E3 §2), en dos reglas que viven en
  `dominio/usuario.py`:

  | Rutas | Grupos (`PUBLICAN` / `CONSULTAN`) |
  |---|---|
  | `/api/modelos/*` | `publicador`, `admin_plataforma` |
  | `/api/estudios`, `/api/inferencias`, `/api/trabajos/{id}` | `medico`, `admin_institucion`, `admin_plataforma` |
  | `/api/publico/*`, `/api/health` | sin token |

  Un test recorre las rutas de la app y falla si alguna bajo `/api` (salvo esas dos) no pide rol.
- **Autoría.** `estudio` y `trabajo` guardan `creado_por`, y `modelo` `publicado_por`: el `sub` de
  Cognito (migración 005). `CrearEstudio`, `EncolarInferencia` y `PublicarModelo` reciben el
  `Usuario`. Encolar sobre un estudio ajeno o consultar un trabajo ajeno da el mismo `404` que un id
  que no existe (tener el UUID no alcanza, y la respuesta no confirma que esté); el admin de
  plataforma ve todo. Cambiarle el contrato a un modelo publicado solo lo puede quien lo publicó
  (`403`); volver a evaluarlo sin contrato, cualquiera que publica. Los modelos de la demo los
  publica `Usuario.plataforma()`. El `sub` no sale en ninguna respuesta.
- La interfaz solo esconde lo que la cuenta no puede hacer (`frontend/src/utilidades/roles.ts`,
  espejo de las dos reglas); decide el backend.

### 4.6 La junta de modelos

Varios modelos sobre el mismo estudio y un informe de consenso (spec funcional F8 y §6.5, solo
clasificación). Entra sin tocar worker, evaluador, colas ni Terraform:

- **Una consulta agrupa N trabajos** (`migraciones/004_consultas.sql`: tabla `consulta` y
  `trabajo.consulta_id`, nulo en las consultas individuales). `POST /api/consultas` valida la
  junta entera en el dominio (`Consulta.junta`: de 2 a 5 modelos distintos, del tipo del estudio,
  con las mismas etiquetas y con evaluación `ok`), guarda la consulta y sus trabajos en una sola
  transacción y deja **un mensaje por trabajo** en `inferencias`, el mismo que manda
  `EncolarInferencia`. Los modelos corren en paralelo en los workers que haya, y la cola cuenta
  N mensajes para el escalado. Si la cola no contesta, el reenviador los manda como a cualquier
  trabajo pendiente.
- **Nada de la junta se guarda: se calcula al leer.** `GET /api/consultas/{id}` arma el informe
  con los trabajos y las métricas vigentes de cada modelo (`Consulta.informe`). El procesador
  sigue aplicando resultados de a uno, sin saber de juntas, y no hay un consenso guardado que se
  pueda desincronizar.
- **El consenso es una función pura** (`dominio/consenso.py`). Peso de cada modelo = su métrica
  verificada (`metricas["auc"]` si el evaluador la midió, si no `accuracy`). Consenso = promedio
  de las probabilidades ponderado por esos pesos, etiqueta por argmax. Acuerdo = parte del peso
  total de los modelos cuya predicción coincide con el consenso; **revisión prioritaria** si es
  menor a 0,70. Un modelo que perdió su métrica (lo volvieron a publicar) muestra su resultado
  pero no vota.
- **Estado de la consulta**, derivado de sus trabajos: `en_cola` → `procesando` → `completa`
  (todos ok), `parcial` (alguno falló y alguno anduvo) o `error` (fallaron todos). El consenso sale
  cuando terminaron todos y al menos dos votan; con uno solo, ese resultado sin consenso.

## 5. Worker

Sin estado, sin base, sin puertos. Un proceso por tarea con `intra_op_num_threads = vCPU`.

- `Consumidor`: long polling de `inferencias` de a un mensaje. Por cada uno, `ProcesarMensaje`
  publica `en_curso`, infiere, publica el resultado y **recién entonces** borra el mensaje.
  - Error definitivo (imagen ilegible, modelo incompatible, objeto inexistente): publica el error
    y borra.
  - Error transitorio: devuelve el mensaje a la cola en 10 s. En el tercer intento publica el error
    y lo deja: SQS lo pasa a la cola de fallidos.
- `ProveedorEfsS3`: busca `/mnt/modelos/<nombre>/<version>/` (EFS); si no está, baja de S3 a un
  directorio temporal y hace `rename` atómico (dos workers no se pisan). LRU de sesiones cargadas.
- `FuenteS3`: `get_object` con timeouts; `NoEncontrado` si no está.
- `Inferir.ejecutar`: `decodificar → preprocesar → motor.inferir → posprocesar`, todo `ateneo_ml`.
- SIGTERM (ECS al reemplazar o achicar): termina el mensaje que tiene y sale.

## 6. Evaluador

Una sola tarea, que pasa de 0 a 1 según su cola (una certificación es una medición atribuible a una
máquina). A la tarea no se entra: todo queda en su log y en lo que publica.

- `ConsumidorEvaluaciones`: toma un mensaje de `evaluaciones`, lo evalúa con un **latido** que
  renueva la invisibilidad cada 5 minutos (una evaluación puede pasar los 30 de la cola), y recién
  después lo borra.
- `EvaluarModelo.ejecutar` publica `en_curso` y siempre termina con un `ok` o un `error`:
  1. Bajar `modelo.json` y `modelo.onnx` a un temporal; construir `OnnxMotor`.
  2. `conjuntos.ultima_version(tipo_estudio)` (prefijos `vN/`), leer manifiesto y verdad, validar
     consistencia. Si falla: `terminar_error`.
  3. Por cada caso: `leer → decodificar → preprocesar → inferir → posprocesar`. Un caso ilegible
     suma a `casos_con_error`.
  4. `calcular_metricas(...)` y publicar **solo el agregado**: métricas, versión y hash del
     conjunto. El resultado caso por caso nunca sale de la subred (regla 6 de la spec).
- Identidad: el id de la tarea, del endpoint de metadatos de ECS (la NACL no lo filtra).

## 7. `ateneo_ml`: el contrato hecho código

```python
@dataclass(frozen=True)
class ContratoModelo:
    nombre: str; version: str; tipo_estudio: str; tarea: str
    entrada: EspecEntrada   # nombre, layout, forma, dtype, espacio_color, redimension, escala, media, desvio
    salida: EspecSalida     # nombre, tipo, etiquetas, positiva, umbral
    @staticmethod
    def desde_json(d: dict) -> "ContratoModelo": ...     # EntradaInvalida con el campo que falla

def preprocesar(img: PIL.Image.Image, e: EspecEntrada) -> np.ndarray:
    # 1. color: RGB | L | gris_replicado (convert("L").convert("RGB"), luma ITU-R 601, para modelos entrenados en gris)
    # 2. redimensión: estirar | recortar_centro, al alto×ancho de `forma`
    # 3. float32 / escala, luego (x - media) / desvio si están
    # 4. layout: HWC → NCHW si corresponde; agregar batch
class OnnxMotor(Motor): ...                              # InferenceSession, intra_op_num_threads
def posprocesar(salida, s: EspecSalida) -> Prediccion:   # logits→softmax | probabilidades | logit_sigmoide
def calcular_metricas(verdades, predicciones, probabilidades, etiquetas, positiva) -> dict
```

El backend necesita la misma validación de `modelo.json` sin traer `onnxruntime`: `contrato.py`
no importa nada pesado, así que el backend lo **copia** como `app/dominio/contrato.py` con un test
que compara ambos archivos byte a byte. Es la única duplicación consentida, y está vigilada.

Registros por diccionario (decodificadores por extensión, posprocesadores por `salida.tipo`,
métricas por `tarea`): agregar uno es agregar una entrada.

Tests sin modelo real: un ONNX diminuto generado en el test (una capa identidad) con tensores
fijos, más un test contra `modelo.onnx` real marcado `@slow` que solo corre si el archivo está.

## 8. Frontend

React + Vite + TypeScript, CSS propio, sin librerías.

Tres vistas, una por público: la **portada** cuenta qué es Ateneo y abre las otras dos;
**publicación** es la vista de quien sube modelos; **consulta** la de quien atiende pacientes. El
único estado que comparten es el que ya vive en la API.

```
src/
├── api/ cliente.ts · tipos.ts · modelos.ts · estudios.ts · inferencias.ts · trabajos.ts
│   ├── s3.ts                   # subir un archivo con un presigned POST, con progreso (XHR)
│   ├── configuracion.ts        # /config.json: dónde está la API y los clientes de Cognito
│   └── sesion.ts               # login con Cognito: ingresar, crear cuenta, recibir los tokens, salir
├── hooks/
│   ├── useModelos.ts           # publicados + disponibles; refresco
│   ├── usePublicacion.ts       # subir el ONNX → publicar + polling del modelo cada 3 s
│   ├── useInferencia.ts        # crear estudio → POST a S3 → encolar → polling del trabajo cada 1,5 s
│   ├── useSalud.ts             # GET /api/health cada 10 s, para la barra y el pie
│   ├── useSesion.ts            # la sesión de Cognito; re-renderiza al ingresar o salir
│   └── useTema.ts              # claro/oscuro; sin elección manda prefers-color-scheme
├── enrutador.tsx               # useRuta() + <Enlace>: History API, tres rutas, ~60 líneas
├── components/
│   ├── Marca · Navegacion · PieSitio · DiagramaFlujo · PideIngreso   # identidad, marco y login
│   ├── SubirModelo · ListaDisponibles · CatalogoModelos · TarjetaEvaluacion
│   └── SelectorModelo · ResumenMedida · CargadorImagen · EstadoTrabajo · ResultadoInferencia · EstadoApi
├── pages/
│   ├── Inicio.tsx              # "/"          portada: qué es, el recorrido, las dos puertas
│   ├── Publicar.tsx            # "/publicar"  bucket → alta → evaluación en vivo → catálogo
│   └── Consulta.tsx            # "/consulta"  modelo medido → estudio → predicción
├── utilidades/ formato.ts · contrato.ts                     # lectura del modelo.json en el navegador
└── estilos/ base.css · sitio.css · paneles.css              # tokens, sitio, paneles
```

- Componentes sin `fetch`: reciben datos y callbacks. Los hooks usan `api/`. Cambiar la API es
  tocar `api/`.
- Polling con `setInterval` dentro del hook, cancelado al terminar o al desmontar. Cuando exista
  algo mejor (SSE), cambia el hook, no los componentes.
- Subida a S3 con el `presigned POST` tal cual (`FormData` con los campos + el archivo), en
  `api/s3.ts` y con `XMLHttpRequest`: es el único que informa el progreso, y un ONNX pesa decenas
  de MB. La usan las dos subidas, la del estudio y la del modelo.
- **Dónde está la API lo dice `/config.json`.** En AWS lo escribe Terraform en el bucket web
  (dirección de API Gateway y clientes de Cognito); en local no existe y las rutas quedan relativas
  (`/api/...`, que Vite pasa a `localhost:8080`). El build no cambia entre entornos.
- **Login** (`api/sesion.ts`): el recorrido de la clase, descrito en `terraform/README.md`.
  `cliente.ts` manda el access token en cada pedido y, ante un `401`, descarta la sesión: la sección
  vuelve a pedir el ingreso (`components/PideIngreso.tsx`). Crear cuenta deja elegir institución o
  publicador; cada uno entra por su cliente de Cognito.
- **Ruteo propio, no react-router.** `enrutador.tsx` es `useSyncExternalStore` sobre
  `history.pushState` más un `<Enlace>` que respeta ctrl/cmd/click del medio. Son tres rutas fijas
  y una dependencia menos; el bucket web devuelve `index.html` como documento de error (y `sitio.py`
  en local), así que recargar `/consulta` funciona.
- **Identidad visual**: la misma de los documentos del proyecto (verde clínico `#0E6B66`, Archivo
  para títulos, Source Sans 3 para el cuerpo, IBM Plex Mono para los datos), en tokens de CSS con
  tema claro y oscuro. Las fuentes vienen de Google Fonts con `display=swap` y una pila del sistema
  detrás: si el navegador no las alcanza, el sitio sigue legible.

### 8.1 La junta en la interfaz

- `pages/Junta.tsx` (`/junta`): tipo de estudio → de 2 a 5 modelos evaluados → la imagen, una
  sola vez → el informe. Se llega desde la barra, desde el catálogo («Consultar en junta», con el
  tipo filtrado) y desde la ficha de un modelo evaluado (`/junta?con=<id>`, con ese modelo elegido).
- `hooks/useJunta.ts`: crear el estudio → POST a S3 → `POST /consultas` → polling de
  `GET /consultas/{id}` cada 1,5 s hasta `completa`, `parcial` o `error`. `api/consultas.ts` es su
  cliente.
- `components/SelectorJunta.tsx` (los modelos, con la métrica con que pesa cada uno) y
  `components/ResultadoJunta.tsx`: arriba el informe de consenso —la predicción, el acuerdo contra
  la marca del 70 % y la revisión prioritaria destacada—, debajo cada modelo con «coincide» o
  «discrepa» (reusa `ResultadoInferencia`) y al final la leyenda de soporte a la decisión clínica.

## 9. Configuración por servicio

| Servicio | Variable | Uso |
|----------|----------|-----|
| api | `DATABASE_URL` (secreto) · `BUCKET_MODELOS` · `BUCKET_ESTUDIOS` · `COLA_INFERENCIAS_URL` · `COLA_EVALUACIONES_URL` · `COGNITO_USER_POOL_ID` · `COGNITO_CLIENT_IDS` · `ORIGEN_WEB` | encolar y validar tokens |
| procesador | `DATABASE_URL` (secreto) · `COLA_RESULTADOS_URL` · `COLA_INFERENCIAS_URL` · buckets | aplicar resultados y reenviar |
| worker | `COLA_INFERENCIAS_URL` · `COLA_RESULTADOS_URL` · `MODELOS_DIR=/mnt/modelos` · `CACHE_SESIONES=4` | caché EFS · LRU |
| evaluador | `COLA_EVALUACIONES_URL` · `COLA_RESULTADOS_URL` · `BUCKET_EVALUACION` · `BUCKET_MODELOS` | evaluar y publicar |
| todos (local) | `AWS_ENDPOINT_URL_S3=http://minio:9000` · `AWS_ENDPOINT_URL_SQS=http://sqs:9324` | boto3 los lee solo; en AWS no se definen |

En AWS las escribe Terraform en cada definición de tarea (`terraform/ecs.tf`).

## 10. Desarrollo local

```
docker compose up -d --build      # db · minio · sqs (ElasticMQ) · migraciones · api · procesador · worker · evaluador
```

Reproduce la topología de AWS: Postgres hace de RDS, MinIO de S3 y ElasticMQ de SQS, con las mismas
tres colas y sus colas de fallidos (`docker/elasticmq.conf`). El sitio lo sirve la api en
<http://localhost:8080>, sin login. Ver el README.

## 11. Pruebas

| Nivel | Qué | Con qué |
|-------|-----|---------|
| Dominio | `republicar` (409), `verificar_compatible`, validación de contrato | pytest, sin IO |
| Casos de uso | orquestación con fakes en memoria; encolar con la cola caída; reenviar y vencer; autoría (lo ajeno da 404) | pytest |
| Junta | consenso con números hechos a mano (`test_consenso.py`); crear y leer la junta con fakes, incluida la junta de 3 con un modelo caído y la junta ajena, que da 404 (`test_consultas.py`); rutas y roles (`test_api_consultas.py`) | pytest |
| Procesador | aplicar cada resultado una sola vez; descartar lo ilegible; no borrar si la base falla | pytest |
| Worker y evaluador | qué publican y cuándo borran el mensaje; el latido del evaluador | pytest, sin SQS |
| `ateneo_ml` | preprocesamiento, posprocesamiento, métricas a mano; motor con un ONNX de una capa | pytest + onnxruntime |
| Adaptadores | SQS con el `Stubber` de botocore; tokens con una clave RSA propia | pytest |
| API | routers con casos de uso falsos (`dependency_overrides`); 401 sin token y 403 con el rol equivocado, ruta por ruta | `TestClient` |
| Infraestructura | la arquitectura de «Ateneo en AWS 2.0» contra un AWS simulado | `terraform test` |

## 12. Despliegue

`terraform apply` hace todo (ver `terraform/README.md`): empaqueta el código y calcula su hash, y
una instancia construye las dos imágenes, las sube a ECR con ese hash como etiqueta y sube el sitio
al bucket web. ECS reemplaza las tareas de a poco. Un cambio de código produce otro hash; sin
cambios, el plan sale vacío.

## 13. Decisiones que este diseño deja abiertas a propósito

| Evolución | Qué cambia | Qué no cambia |
|-----------|------------|---------------|
| Matriz de permisos completa (spec E3 §2) | Hoy hay dos reglas por router (`PUBLICAN`, `CONSULTAN`; la junta va con `CONSULTAN`, como una consulta individual) y autoría por `sub` (§4.5). Falta: organizaciones (que el admin de institución vea lo de sus médicos, no solo lo suyo), separar lo que hace el médico de lo que hace el admin de institución, cuentas pendientes de aprobación (403 hasta que un admin las apruebe), y que el admin de plataforma vea solo metadatos y agregados, como pide la spec (hoy ve y usa todo) | `exigir_grupos`, el login, los routers |
| Organizaciones y créditos | Tablas nuevas; `CrearConsulta` y `EncolarInferencia` reservan y el procesador cobra o libera | Worker, evaluador, colas |
| Carga de conjuntos desde la app | Un mensaje `ingerir_conjunto` en `evaluaciones` | Evaluador (otro caso de uso), procesador |
| Historial de evaluaciones | Tabla `evaluacion`; la fila del modelo apunta a la vigente | API pública, UI |
| DICOM | Un `DecodificadorImagen` más | Preprocesamiento, motor, métricas |
| Segmentación | Un posprocesador y un calculador de métricas por `tarea` | Motor, worker, evaluador |
| Consenso de segmentación y detección | Una función por tarea en `dominio/consenso.py` (mapas promediados, WBF), como dice la spec §6.5 | Consulta, cola, worker, API |

La junta de varios modelos estaba en esta tabla y ya no es evolución: está implementada (§4.6),
con el consenso calculado al leer en vez de en el procesador.

## Modelos iniciales y selección en la web

`models/catalogo.json` define los cinco modelos incluidos. Mediscan, DenseNet121 y
EfficientNet-B0 clasifican `torax-rx` en NORMAL/PNEUMONIA; EfficientNetB3 y una CNN propia
de NareshKumarSekar clasifican `cerebro-rm` en glioma/meningioma/notumor/pituitary. Cada uno
tiene identidad, contrato, hash, caché, marca de preparación y evaluación independientes.
`models/conjuntos.json` fija un conjunto reservado por tipo de estudio (origen en Hugging Face,
split, etiquetas y casos por clase). `tools/demo_assets.py` verifica los pesos y prepara cada
conjunto una sola vez, aunque lo compartan varios modelos; si falla el de un tipo, los modelos
del otro siguen. El evaluador no cambia: ya buscaba el conjunto por `tipo_estudio`.
El procesador recorre el registro, usa candados PostgreSQL deterministas por identidad y
una outbox transaccional antes de enviar a SQS. Un fallo no interrumpe los demás modelos.

`GET /api/publico/demo` devuelve el registro visible con estados y conteos de preparación;
no incluye secretos ni casos reservados. La API agrega `nombre_visible` y `predeterminado`
a los modelos del catálogo sin cambiar sus IDs. La portada conserva los modelos incluidos
aunque un usuario publique otro con mayor accuracy; el catálogo permite elegir también
modelos de usuarios. Las métricas de todas las tarjetas son las calculadas por el evaluador.

La selección sigue siendo catálogo → ficha `/modelos/<id>` → imagen → trabajo de inferencia.
La ficha y el resultado identifican el modelo. Cada trabajo contiene el ID seleccionado y
solo ejecuta ese modelo. El worker conserva su caché LRU existente de cuatro sesiones; no
se agregan workers por modelo, GPU ni inferencia en navegador. Para varios modelos sobre la
misma imagen está la junta (§4.6): sigue siendo un trabajo por modelo.

La recuperación `python -m app.reintentar_demo --nombre <nombre> --version <version>`
limita sus cambios a una identidad. El comando `tools/esperar_modelo.py` espera todos por
defecto y acepta los mismos argumentos para esperar uno. Los reinicios no republican
modelos evaluados ni reemplazan los que ya existían antes de ampliar el registro.
