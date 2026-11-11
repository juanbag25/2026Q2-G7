# Ateneo

Marketplace de modelos de IA clínica · Cloud Computing 82.08 · ITBA.

Una portada que cuenta qué ofrece Ateneo y dos secciones detrás, una por público.
**Publicar un modelo** (el ONNX va del navegador directo al bucket con una URL prefirmada, la API
valida su contrato y el evaluador, en una subred aislada, lo mide contra el conjunto reservado) y
**consultar un estudio** (la API encola el pedido en SQS, un worker lo toma y el procesador escribe
el resultado).

Esta versión implementa la arquitectura de «Ateneo en AWS 2.0»: ECS Fargate, API Gateway
con HTTPS, Cognito, tres colas de SQS y un despliegue completo con `terraform apply`.

- [specs.md](specs.md) · qué hace: flujos, API, contrato del modelo, esquema, criterios de aceptación.
- [architecture.md](architecture.md) · cómo está construido: servicios, puertos y adaptadores, colas.
- [terraform/README.md](terraform/README.md) · la infraestructura, el login con Cognito y cómo desplegar.

## Estructura

```
ateneo_ml/    preprocesamiento + motor ONNX + métricas, compartido por worker y evaluador
backend/      imagen backend: la api (FastAPI) y el procesador (escribe los resultados)
worker/       imagen ml: lee la cola inferencias, sin base y sin puertos
evaluador/    imagen ml: lee la cola evaluaciones, en la subred aislada
frontend/     React + Vite + TypeScript (portada + publicación + consulta), con login de Cognito
migraciones/  SQL; las aplica el procesador al arrancar
tools/        bajar y verificar el modelo, preparar y subir el conjunto
terraform/    toda la infraestructura como código
docker/       Dockerfiles de las dos imágenes, de los tests y la configuración de ElasticMQ
```

## Correr en local (Docker)

Reproduce la topología de AWS: Postgres hace de RDS, MinIO de S3 y ElasticMQ de SQS (las mismas
tres colas, con sus colas de fallidos), y cada servicio corre en su contenedor. En local no hay
login: la api sirve el sitio en `/` y todos son anónimos.

```bash
docker compose up -d --build            # db, minio, sqs, demo-init, migraciones, api, procesador, worker, evaluador
```

**El sitio se compila adentro de la imagen del backend** (`docker/Dockerfile.backend` tiene una
etapa de node), así que después de tocar `frontend/` o `backend/` hay que reconstruir:
`docker compose up -d --build api procesador`.

Abrí <http://localhost:8080>. La primera vez se descargan y verifican los cinco modelos
preentrenados del [registro](models/catalogo.json), todos v1.0.0, de dos tipos de estudio:

- Rx de tórax, NORMAL / PNEUMONIA (`torax-rx`):
  - **Mediscan · Neumonía** (`torax-rx-neumonia`).
  - **DenseNet121 · Neumonía** (`torax-rx-densenet121`).
  - **EfficientNet-B0 · Neumonía** (`torax-rx-efficientnet-b0`).
- RM de cerebro, glioma / meningioma / notumor / pituitary (`cerebro-rm`):
  - **EfficientNetB3 · Tumor cerebral** (`cerebro-rm-efficientnetb3`).
  - **CNN · Tumor cerebral** (`cerebro-rm-cnn`).

Cada tipo de estudio tiene su conjunto reservado de 200 casos, definido en
[`models/conjuntos.json`](models/conjuntos.json): se prepara una sola vez y todos los modelos
de ese tipo se publican y evalúan por separado contra él. **No necesitás subir ni publicar un modelo.**
Cada modelo aparece en el catálogo apenas se publica, con «Esperando la evaluación», y la web
se actualiza sola; podés usar los que ya terminaron mientras se preparan los otros. La primera preparación requiere internet y tarda varios minutos.
`up -d` no espera la evaluación.

```bash
# Esperar los cinco:
docker compose run --rm herramientas python tools/esperar_modelo.py --timeout 1800
# O esperar uno en particular:
docker compose run --rm herramientas python tools/esperar_modelo.py --nombre torax-rx-densenet121 --version 1.0.0
```

Hay dos flujos de consulta:

- **Con un modelo:** Modelos → ficha del modelo elegido → subir una imagen del tipo de estudio →
  resultado, que identifica nombre y versión.
- **En junta:** Junta (en la barra, en el catálogo o en la ficha) → elegir de 2 a 5 modelos
  evaluados del mismo tipo → subir la imagen una vez → cada modelo la analiza por separado, en
  paralelo (un mensaje por modelo en la cola `inferencias`), y arriba el informe de consenso:
  promedio de probabilidades ponderado por la métrica verificada de cada modelo, el acuerdo y
  **revisión prioritaria** si el acuerdo baja del 70 %. Con los tres de `torax-rx` se ve entero.

Ateneo evalúa y ejecuta inferencias, no entrena los pesos.

Reiniciar conserva IDs y métricas de los modelos ya evaluados. Los pesos se descargan por
revisión inmutable y SHA-256 y persisten en S3/MinIO y caché por identidad. Se versionan
contratos y manifiestos, no los pesos: Mediscan no declara licencia y los otros cuatro
declaran MIT. Ver [models_specs.md](models_specs.md) y los README de cada modelo.

Se puede desactivar la preparación con `DATOS_DEMO=false docker compose up -d`; no borra
modelos existentes ni impide publicar otros.

### Publicar otros modelos (opcional)

La página `/publicar` sigue aceptando ONNX y contrato. Si querés probar la subida del mismo
modelo en otro entorno, podés obtener los dos archivos así:

```bash
docker compose run --rm herramientas python tools/descargar_modelo.py --carpeta /salida/modelo --solo-descargar
```

Arrastrá `tmp/modelo/modelo.onnx` y `tmp/modelo/modelo.json` y usá **Subir y publicar**.
Una versión existente no se sobrescribe: en el entorno con demo ya estará publicada.
Podés usar radiografías propias de prueba o preparar una carpeta local de ejemplos con
`tools/preparar_conjunto.py` como describe su ayuda. Los casos reservados no se sirven por la API pública.

### Recuperación

```bash
docker compose logs --tail=100 demo-init procesador evaluador
# Reintentar descarga/carga tras corregir el problema (la caché se conserva):
docker compose run --rm demo-init
# Si falló la evaluación o se agotaron los envíos, reintentar explícitamente:
docker compose exec procesador python -m app.reintentar_demo --nombre torax-rx-densenet121 --version 1.0.0
docker compose restart procesador
docker compose run --rm herramientas python tools/esperar_modelo.py --timeout 1800
```

La recuperación actúa solo sobre la identidad indicada, conserva su ID y rechaza reintentar
un modelo que ya esté listo o en curso. Los otros modelos no se republican.
No hace falta borrar volúmenes ni modelos. `GET /api/publico/demo` informa solo el estado,
sin credenciales ni etiquetas del conjunto reservado. Informa estado global, cantidades
esperadas/listas/con error/pendientes y una lista de estados e IDs por modelo inicial.
Un estado parcial permite seguir usando los modelos listos; no cuenta modelos de usuarios
como parte de los cinco iniciales.

Útiles:

```bash
docker compose logs -f evaluador          # ver la evaluación avanzar
docker compose logs -f procesador         # ver llegar los resultados
docker compose exec db psql -U ateneo -c "select nombre, estado_evaluacion, accuracy from modelo"
```

Consola de MinIO: <http://localhost:9001> (minioadmin / minioadmin).

## Desarrollo sin Docker (tests y frontend con recarga)

```bash
python -m venv .venv && .venv/Scripts/activate      # o source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                               # tests de ateneo_ml, worker, evaluador, backend
cd frontend && npm install && npm run dev            # http://localhost:5173, proxy /api → :8080
```

En Windows sin el runtime de Visual C++, `onnx` no carga y sus tests se saltean:
`docker compose run --rm tests` corre la suite completa.

El 5173 es **solo para desarrollar** con recarga en caliente, y necesita el Docker levantado: hace
proxy de `/api` al 8080.

## Desplegar en AWS Academy

Ver [terraform/README.md](terraform/README.md). En CloudShell:

```bash
git clone https://github.com/nnicokim/TP-AWS.git ~/ateneo && cd ~/ateneo
bash terraform/organization/scripts/bootstrap-estado.sh                 # una vez por cuenta
cp terraform/organization/terraform.tfvars.example terraform/organization/terraform.tfvars   # email_admin y email_alertas
bash terraform/organization/scripts/tf.sh apply                          # todo: red, base, imágenes, servicios
bash terraform/organization/scripts/tf.sh output url                     # el sitio
bash terraform/organization/scripts/tf.sh destroy                        # al terminar cada sesión de trabajo
```
