# Ateneo

**Marketplace de modelos de inteligencia artificial para imágenes médicas.** Proyecto de
Cloud Computing 82.08 · ITBA.

Ateneo permite publicar modelos, comparar su rendimiento y usarlos para analizar estudios.
La plataforma evalúa cada modelo contra un conjunto de imágenes reservado y muestra las
métricas obtenidas en el catálogo. También permite consultar varios modelos sobre una misma
imagen y obtener un informe de consenso.

El proyecto implementa una demostración académica de estos flujos: utiliza modelos
preentrenados en formato ONNX y conjuntos públicos de prueba. **Ateneo evalúa y ejecuta
modelos; no los entrena.**

## Índice

- [Funcionalidades](#funcionalidades)
- [Inicio rápido en local](#inicio-rápido-en-local)
- [Probar la aplicación](#probar-la-aplicación)
- [Cómo funciona](#cómo-funciona)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Desarrollo y pruebas](#desarrollo-y-pruebas)
- [Despliegue en AWS](#despliegue-en-aws)
- [Solución de problemas](#solución-de-problemas)
- [Documentación técnica](#documentación-técnica)

## Funcionalidades

- **Catálogo:** consultar los modelos disponibles, sus versiones y sus métricas verificadas.
- **Análisis individual:** subir una imagen y obtener la predicción de un modelo elegido.
- **Junta de modelos:** seleccionar entre 2 y 5 modelos evaluados del mismo tipo de estudio
  y analizar una imagen con todos ellos. El consenso pondera las probabilidades según las
  métricas verificadas y marca revisión prioritaria cuando el acuerdo es menor al 70 %.
- **Publicación:** subir un archivo `.onnx` y su contrato `modelo.json`, que describe la
  entrada, el preprocesamiento y la salida del modelo, para evaluarlo y sumarlo al catálogo.
- **Acceso por roles en AWS:** catálogo público; publicación para publicadores; análisis
  para médicos e instituciones; acceso a ambas funciones para administradores de la plataforma.
  En local, la demo funciona sin iniciar sesión.

## Inicio rápido en local

### Requisitos

- Git, si todavía no clonaste el repositorio.
- Docker con Docker Compose v2 (`docker compose`) y el motor de Docker en ejecución.
- Conexión a internet para construir las imágenes y descargar los modelos y datos iniciales.
- Puertos locales libres: `8080`, `5432`, `9000`, `9001` y `9324`.

**No necesitás instalar Python, Node.js ni configurar credenciales de AWS para ejecutar la demo
con Docker.** La configuración local ya está definida en [docker-compose.yml](docker-compose.yml).

### 1. Levantar los servicios

Desde la raíz del repositorio:

```bash
docker compose up -d --build
```

El comando construye el sitio y los servicios, prepara la base de datos e inicia la descarga
de los cinco modelos de demostración. **Que el comando termine no significa que los modelos
ya estén evaluados:** la preparación inicial requiere varios minutos.

### 2. Abrir la aplicación

Entrá a <http://localhost:8080>. No hace falta registrarse ni publicar un modelo para empezar.
El catálogo muestra el progreso y se actualiza automáticamente; podés usar cada modelo
apenas termina su evaluación.

Para esperar desde la terminal a que los cinco estén listos:

```bash
docker compose run --rm herramientas python tools/esperar_modelo.py --timeout 1800
```

El comando termina correctamente cuando la demo está lista; informa un error si falla la
preparación o se agota el tiempo de espera de 30 minutos. Si ocurre, consultá
[Solución de problemas](#solución-de-problemas).

### 3. Verificar y detener

| Recurso local | Dirección | Uso |
| --- | --- | --- |
| Aplicación | <http://localhost:8080> | Catálogo, análisis y publicación |
| API interactiva | <http://localhost:8080/api/docs> | Explorar y probar los endpoints |
| Estado de la API | <http://localhost:8080/api/health> | Comprobar que la API responde |
| Estado de la demo | <http://localhost:8080/api/publico/demo> | Ver el avance de los cinco modelos |
| Consola de MinIO | <http://localhost:9001> | Inspeccionar archivos; usuario y contraseña: `minioadmin` |

Para detener los servicios:

```bash
docker compose down
```

Los volúmenes conservan la base de datos, los archivos y las cachés. Al volver a ejecutar
`docker compose up -d`, se reutilizan los modelos ya evaluados con sus IDs y métricas.
`docker compose down -v` elimina esos volúmenes y sus datos.

## Probar la aplicación

### Modelos incluidos

La demo prepara los siguientes modelos, todos en versión `1.0.0`:

| Tipo de estudio | Modelos | Clases de salida |
| --- | --- | --- |
| Radiografía de tórax (`torax-rx`) | Mediscan · Neumonía; DenseNet121 · Neumonía; EfficientNet-B0 · Neumonía | `NORMAL`, `PNEUMONIA` |
| Resonancia de cerebro (`cerebro-rm`) | EfficientNetB3 · Tumor cerebral; CNN · Tumor cerebral | `glioma`, `meningioma`, `notumor`, `pituitary` |

Cada tipo tiene un conjunto reservado de 200 casos. Los modelos se evalúan por separado
contra el conjunto de su tipo; las imágenes y etiquetas de esos conjuntos no se exponen
por la API pública.

El [registro de modelos](models/catalogo.json) fija las revisiones y los hashes SHA-256 de
los pesos. El repositorio versiona contratos y manifiestos; los pesos se descargan durante
la preparación. Mediscan no declara licencia y los otros cuatro modelos declaran MIT.
Los orígenes, contratos y licencias se detallan en [models_specs.md](models_specs.md).

### Analizar con un modelo

1. Entrá a **Modelos** y abrí la ficha de uno que haya terminado su evaluación.
2. Subí una imagen **PNG o JPEG de hasta 20 MB**, del tipo de estudio correspondiente.
3. Iniciá el análisis y esperá el resultado. La pantalla identifica el modelo y la versión utilizados.

### Consultar una junta

1. Entrá a **Junta** desde la navegación, el catálogo o la ficha de un modelo.
2. Elegí de 2 a 5 modelos evaluados del mismo tipo de estudio.
3. Subí una imagen e iniciá la consulta.
4. Revisá los resultados individuales y el informe de consenso. Podés probar este flujo con
   los tres modelos de tórax incluidos en la demo.

### Publicar un modelo propio (opcional)

1. Prepará el archivo `.onnx` (hasta 512 MB) y su contrato `modelo.json`.
2. Entrá a **Publicar**, seleccioná los archivos y usá **Subir y publicar**.
3. Seguí el estado de evaluación desde el catálogo y la ficha del modelo.

La combinación de nombre y versión identifica al modelo y no se sobrescribe: para cambiar
sus archivos, publicá una versión nueva. El contrato y el conjunto de evaluación requerido
se describen en [specs.md](specs.md) y [models_specs.md](models_specs.md).

Para obtener los archivos del modelo Mediscan de ejemplo:

```bash
docker compose run --rm herramientas python tools/descargar_modelo.py --carpeta /salida/modelo --solo-descargar
```

Quedan en `tmp/modelo/modelo.onnx` y `tmp/modelo/modelo.json` de tu máquina. Esa identidad
ya está publicada si activaste la demo; estos archivos sirven para probar la publicación
en un entorno donde todavía no exista.

Para iniciar sin cargar los datos de demostración, en Bash o Zsh:

```bash
DATOS_DEMO=false docker compose up -d --build
```

Esto desactiva la preparación automática; conserva los modelos existentes y permite publicar otros.

## Cómo funciona

La aplicación procesa los análisis y las evaluaciones de forma asíncrona:

```text
Navegador → API → cola inferencias  → worker    → cola resultados → procesador → PostgreSQL
               → cola evaluaciones → evaluador → cola resultados → procesador → PostgreSQL
```

La API recibe las solicitudes y encola los trabajos. El **worker** ejecuta las inferencias;
el **evaluador** mide los modelos contra los conjuntos reservados. Ambos publican sus
resultados en una cola y el **procesador** los guarda en la base. La web consulta el estado
hasta mostrar el resultado.

Los modelos y estudios se suben directamente desde el navegador al almacenamiento mediante
URLs prefirmadas. El worker y el evaluador consumen colas, no reciben peticiones HTTP ni
acceden a la base de datos. Ambos comparten el motor ONNX y el preprocesamiento de `ateneo_ml/`.

| Componente | Entorno local | AWS |
| --- | --- | --- |
| Sitio web | Compilado y servido por el backend | Sitio estático en S3 |
| API y procesos | Contenedores de Docker Compose | Cuatro servicios en ECS Fargate |
| Base de datos | PostgreSQL 16 | RDS PostgreSQL 16 |
| Archivos | MinIO | S3 |
| Colas | ElasticMQ | SQS, con colas de fallidos |
| Caché de modelos del worker | Volumen de Docker | EFS |
| Autenticación | Sin login | Cognito y permisos por rol |
| Acceso a la API | `localhost:8080` | API Gateway con HTTPS, ALB interno y WAF |

## Estructura del repositorio

| Ruta | Contenido |
| --- | --- |
| `frontend/` | Interfaz en React, TypeScript y Vite |
| `backend/` | API FastAPI, lógica de aplicación, acceso a datos y procesador de resultados |
| `worker/` | Consumidor de la cola de inferencias |
| `evaluador/` | Consumidor de la cola de evaluaciones |
| `ateneo_ml/` | Contratos, preprocesamiento, motor ONNX y métricas compartidos |
| `migraciones/` | Migraciones SQL de la base de datos |
| `models/` | Registro, contratos y manifiestos de los modelos y conjuntos iniciales |
| `tools/` | Descarga y verificación de modelos, preparación de conjuntos y herramientas de demo |
| `docker/` | Dockerfiles y configuración de ElasticMQ |
| `terraform/` | Infraestructura de AWS y scripts de despliegue |
| `tests/` y `backend/tests/` | Pruebas de la aplicación y los componentes de ML |
| `.github/workflows/` | Validación de Terraform y operaciones de infraestructura |

## Desarrollo y pruebas

### Frontend con recarga automática

Requiere Node.js 20 (la versión usada por la imagen de construcción) y los servicios de Docker
levantados. Desde la raíz:

```bash
cd frontend
npm ci
npm run dev
```

Abrí <http://localhost:5173>. Vite redirige `/api` al backend en `localhost:8080`.
Para verificar la compilación del frontend, ejecutá `npm run build` en `frontend/`.

### Aplicar cambios a los contenedores

El sitio servido en el puerto `8080` está compilado dentro de la imagen del backend.
Después de modificar `frontend/` o `backend/`, reconstruí los servicios:

```bash
docker compose up -d --build api procesador
```

Si modificás `worker/`, `evaluador/` o `ateneo_ml/`:

```bash
docker compose up -d --build worker evaluador
```

### Pruebas con Docker

No requiere instalar las dependencias de Python en tu máquina:

```bash
docker compose run --rm --build tests
```

### Pruebas con Python local

Usá Python 3.11, la versión de las imágenes Docker. Desde la raíz, creá el entorno:

```bash
python -m venv .venv
```

Activación en Linux/macOS (Bash o Zsh):

```bash
source .venv/bin/activate
```

Activación en Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Con el entorno activo:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -rs
```

La suite cubre `ateneo_ml`, worker, evaluador y backend. Las pruebas de integración con
PostgreSQL se omiten si no se define `TEST_DEMO_DATABASE_URL`, que debe apuntar a una base
exclusiva para pruebas. Esto también aplica al contenedor de tests por defecto.
En Windows, si falta el runtime de Visual C++, los tests que dependen de `onnx` pueden
omitirse; usá la ejecución con Docker para disponer de esas dependencias.

## Despliegue en AWS

El despliegue está preparado para **AWS Academy Learner Lab**. Terraform crea la red, el
almacenamiento, las colas, la autenticación y los servicios; también construye y publica
las imágenes. Se puede ejecutar desde CloudShell sin instalar Docker allí.

Seguí la guía de [primer despliegue](terraform/README.md#primer-despliegue): incluye la
inicialización del estado remoto, la configuración de `email_admin` y `email_alertas`,
el comando de despliegue y la obtención de la URL del sitio.

En AWS, el catálogo es público y las acciones requieren una cuenta con el rol correspondiente.
API Gateway y WAF aplican límites de pedidos configurables; los valores y sus restricciones
se documentan en la [guía de infraestructura](terraform/README.md).

Los workflows **Aplicar** y **Destruir** también permiten operar desde GitHub Actions.
Requieren cargar las credenciales del laboratorio en los secrets del repositorio y renovarlas
cada sesión: ver [el pipeline](terraform/README.md#el-pipeline-de-github-actions).

La infraestructura consume crédito del laboratorio mientras está desplegada. Al terminar la
sesión, eliminá los recursos con el procedimiento de la guía:

```bash
bash terraform/organization/scripts/tf.sh destroy
```

## Solución de problemas

### La web no responde o los modelos siguen pendientes

Primero verificá los contenedores y los logs:

```bash
docker compose ps -a
docker compose logs --tail=100 api demo-init procesador evaluador
```

`demo-init` y `migraciones` son tareas que terminan después de preparar los datos; que
aparezcan detenidas con código de salida `0` es normal. El estado de la API no implica que
los cinco modelos ya estén listos: consultá `/api/publico/demo` o el catálogo.

### Falló la descarga o la carga de los datos iniciales

Después de corregir la causa que muestran los logs (por ejemplo, un problema de conexión),
reintentá la preparación. Se conserva la caché:

```bash
docker compose run --rm demo-init
```

### Un modelo inicial quedó con error de evaluación

Reintentá explícitamente la identidad afectada; este ejemplo usa DenseNet121:

```bash
docker compose exec procesador python -m app.reintentar_demo --nombre torax-rx-densenet121 --version 1.0.0
docker compose restart procesador
docker compose run --rm herramientas python tools/esperar_modelo.py --nombre torax-rx-densenet121 --version 1.0.0 --timeout 1800
```

El reintento conserva el ID, afecta solo al modelo indicado y rechaza modelos que ya estén
listos o en curso. No requiere borrar volúmenes ni volver a publicar los otros modelos.

Para seguir los resultados en tiempo real:

```bash
docker compose logs -f evaluador procesador
```

## Documentación técnica

| Documento | Qué consultar |
| --- | --- |
| [specs.md](specs.md) | Flujos del producto, API, contratos, permisos y criterios de aceptación |
| [architecture.md](architecture.md) | Diseño del código, componentes, puertos y adaptadores |
| [terraform/README.md](terraform/README.md) | Configuración y operación de AWS, Cognito, límites y pipeline |
| [arquitectura-aws.drawio](arquitectura-aws.drawio) | Diagrama de infraestructura; se abre con draw.io |
| [models_specs.md](models_specs.md) | Modelos de la demo, contratos, conjuntos de evaluación y licencias |
