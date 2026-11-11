# Tres modelos disponibles desde el primer despliegue

Estado: ampliación a tres modelos implementada y verificada localmente.

Investigación e implementación realizadas el 20 de octubre de 2026. La preparación automática, los tres modelos y la UI están implementados. La infraestructura se validó con proveedores simulados; no se desplegaron recursos reales en AWS.

## 1. Objetivo y experiencia del usuario

Ateneo debe ofrecer tres modelos preentrenados y evaluados para que el usuario elija cuál usar, sin tener que descargar, subir ni publicar uno. Conservar la posibilidad de publicar modelos propios como una opción adicional.

Mantener el flujo actual:

1. Entrar a la portada o al catálogo `/modelos`.
2. Elegir una de las tres tarjetas y abrir `/modelos/<id>`.
3. Subir una imagen en la ficha del modelo elegido.
4. Consultar el resultado de la inferencia, identificando el modelo utilizado.

La selección se realiza al abrir la ficha. No agregar un asistente, un paso obligatorio, una nueva pantalla de consulta ni un selector adicional para repetir esa elección. No ejecutar los tres modelos por cada consulta ni combinar sus predicciones. Cada consulta usa exclusivamente el modelo seleccionado.

Aplica a Docker Compose y al código de despliegue para AWS Academy. La implementación no incluye ejecutar un despliegue real de AWS sin una solicitud explícita.

## 2. Base que debe conservarse

Actualmente funcionan:

- Modelo `torax-rx-neumonia` v1.0.0, descargado con revisión y SHA-256 fijos.
- Preparación del conjunto `torax-rx/v1`, publicación interna y evaluación automáticas.
- Caché persistente, validación de artefactos, outbox en PostgreSQL y protección frente a procesadores concurrentes.
- Estado público `/api/publico/demo`, espera de disponibilidad y recuperación explícita.
- Catálogo y fichas públicas; permisos existentes para publicar y consultar en AWS.
- UI que distingue modelos listos de modelos en preparación y presenta publicar como opcional.

Conservar el modelo que el usuario ya publicó, incluyendo su ID, fechas, métricas y objetos. Los modelos agregados no deben requerir borrar la base ni reiniciar desde cero.

«Preentrenado» significa que los pesos ya fueron entrenados por su autor. Ateneo prepara, evalúa y ejecuta inferencias: no entrena los modelos ni inventa sus métricas.

## 3. Modelos seleccionados

Los dos nuevos modelos clasifican las mismas radiografías de tórax que el inicial: `NORMAL` frente a `PNEUMONIA`. Comparten `tipo_estudio = torax-rx` y pueden evaluarse sobre el conjunto reservado existente, sin incorporar otra modalidad ni otro motor.

| Identidad interna propuesta | Nombre visible | Archivo de origen | Tamaño del ONNX |
| --- | --- | --- | --- |
| `torax-rx-neumonia` v1.0.0 | Mediscan · Neumonía | `mediscan_pneumonia.onnx` | 16.025.329 bytes |
| `torax-rx-densenet121` v1.0.0 | DenseNet121 · Neumonía | `densenet121.onnx` | 30.310.489 bytes |
| `torax-rx-efficientnet-b0` v1.0.0 | EfficientNet-B0 · Neumonía | `efficientnet_b0.onnx` | 18.646.118 bytes |

DenseNet121 y EfficientNet-B0 son dos redes con artefactos diferentes publicadas por el mismo autor. Se usan individualmente; no se incorpora el ensemble del autor ni su tercer modelo ConvNeXt-Tiny.

### 3.1 Modelo inicial: conservar sin cambios

- Fuente: [Rhishamah/mediscan-pneumonia](https://huggingface.co/Rhishamah/mediscan-pneumonia).
- Revisión: `f31fffeac0caa11017df1b0948cc54f73a05033e`.
- SHA-256: `208b1439d819fede1a4b43e49809d0ca77768ee66184e110c14df1eb838ea67f`.
- Conservar su `modelo.json` y `manifest.json` existentes, entrada `input` y salida `output`.
- La fuente no declara una licencia de redistribución. Mantener la decisión del usuario de descargar pesos verificados, sin incluirlos en Git.

### 3.2 DenseNet121

- Fuente: [ZubaerNiloy/pneumonia-ensemble-onnx](https://huggingface.co/ZubaerNiloy/pneumonia-ensemble-onnx).
- Revisión fijada: `d30e6fe12acc63248e0e669725e2d5944b541df1`.
- [Descarga fijada de densenet121.onnx](https://huggingface.co/ZubaerNiloy/pneumonia-ensemble-onnx/resolve/d30e6fe12acc63248e0e669725e2d5944b541df1/densenet121.onnx).
- SHA-256 verificado: `081336d6f50f9254982532511fae8f85dd97c5eb4e3ee75c76ebbd7c8fe52592`.
- Licencia declarada en la ficha de esa revisión: MIT. Conservar procedencia y atribución.

### 3.3 EfficientNet-B0

- Fuente y revisión: las mismas que DenseNet121.
- [Descarga fijada de efficientnet_b0.onnx](https://huggingface.co/ZubaerNiloy/pneumonia-ensemble-onnx/resolve/d30e6fe12acc63248e0e669725e2d5944b541df1/efficientnet_b0.onnx).
- SHA-256 verificado: `09ce0d3d0a1ed9c7eb42b421558f340abde85ae795fbbb20c21fd3c254b24da2`.
- Licencia declarada en la ficha de esa revisión: MIT. Conservar procedencia y atribución.

### 3.4 Fuentes de la verificación

La [API del repositorio con metadatos de archivos](https://huggingface.co/api/models/ZubaerNiloy/pneumonia-ensemble-onnx?blobs=true) identifica revisión, tamaños y hashes. Se descargaron los dos candidatos únicamente a una carpeta temporal y se comprobaron sus bytes contra esos hashes.

El [código original de inferencia del autor](https://huggingface.co/spaces/ZubaerNiloy/pneumonia-detection/blob/b916bd6697c07628967c8eb0f12e2c33a18d1b17/index.html), revisión `b916bd6697c07628967c8eb0f12e2c33a18d1b17`, documenta conversión a RGB, resize a 224 × 224, normalización ImageNet y aplicación de sigmoide con umbral 0.5. La [API de ese Space](https://huggingface.co/api/spaces/ZubaerNiloy/pneumonia-detection?blobs=true) confirma que sus dos archivos tienen los mismos hashes que los seleccionados.

Se verificaron en un contenedor temporal sin red con `onnx.checker`, ONNX Runtime **1.18.0**, `OnnxMotor`, `Inferidor` y el preprocesamiento actual del proyecto:

| Verificación | DenseNet121 | EfficientNet-B0 |
| --- | --- | --- |
| ONNX IR / opset | 8 / 17 | 8 / 17 |
| Entrada | `input`, float32, `[1, 3, 224, 224]` | `input`, float32, `[1, 3, 224, 224]` |
| Salida | `logit`, float32, `[1, 1]` | `logit`, float32, `[1, 1]` |
| Carga y ejecución en CPU | Correctas | Correctas |
| Prueba preliminar: 4 casos por clase | 6 aciertos de 8 | 5 aciertos de 8 |

Esta prueba confirma compatibilidad técnica, no calidad clínica ni una accuracy final. No se seleccionaron normalización, umbral u orden de clases para maximizar estos aciertos. La implementación completó también la evaluación real sobre los mismos 200 casos antes de mostrarlos como listos (ver la verificación al final). No copiar a Ateneo las métricas que la web del autor atribuye a su ensemble.

## 4. Contratos y artefactos versionados

Mantener el esquema existente: `models/<nombre>/<version>/modelo.json`, `manifest.json` y `README.md`. Versionar contratos y manifiestos, no los pesos. Descargar automáticamente cada ONNX desde su revisión inmutable, validar tamaño y SHA-256 y reutilizar su caché. No usar URLs con `main` para los pesos.

Agregar un registro versionado de modelos, por ejemplo `models/catalogo.json`, que enumere las tres identidades y las rutas de sus manifiestos. Ese registro será la fuente de verdad del conjunto predeterminado, evitando repetir listas en Python, Terraform y React.

Los contratos nuevos tendrán estos valores comunes, confirmados por el código y los grafos:

```json
{
  "version": "1.0.0",
  "tipo_estudio": "torax-rx",
  "tarea": "clasificacion",
  "entrada": {
    "nombre": "input",
    "layout": "NCHW",
    "forma": [1, 3, 224, 224],
    "dtype": "float32",
    "espacio_color": "RGB",
    "redimension": "estirar",
    "escala": 255,
    "media": [0.485, 0.456, 0.406],
    "desvio": [0.229, 0.224, 0.225]
  },
  "salida": {
    "nombre": "logit",
    "tipo": "logit_sigmoide",
    "etiquetas": ["NORMAL", "PNEUMONIA"],
    "positiva": "PNEUMONIA",
    "umbral": 0.5
  }
}
```

Completar `nombre` con la identidad correspondiente y `origen` con el enlace al artefacto fijado. La interpolación de Pillow no es idéntica a la del navegador del autor; conservar el preprocesamiento existente y registrar las métricas que ese pipeline produzca. No cambiar globalmente el motor ni el contrato del modelo inicial para adaptar estos candidatos.

El manifiesto debe incluir nombre, versión, URL, revisión, tamaño, SHA-256, licencia declarada y referencia al código de preprocesamiento. Documentar nombres visibles y arquitectura sin usar la arquitectura como sustituto de la identidad interna. Pesos o contratos incompatibles requieren otra versión.

## 5. Generalización de la preparación y publicación

### 5.1 Preparación de artefactos

Generalizar `tools/demo_assets.py`, que actualmente tiene una única identidad y rutas constantes:

- Recorrer el registro de modelos y procesar cada identidad por separado.
- Mantener una caché por nombre y versión; evitar colisiones entre archivos llamados `modelo.onnx`.
- Verificar cada descarga antes de copiarla al bucket. No sobrescribir un artefacto incompatible bajo una versión existente.
- Crear marcas de preparación y estado por modelo, por ejemplo `demo/<nombre>/<version>/estado.json` y `artefactos.json`. Una marca global no debe afirmar que los tres están listos por haber preparado uno.
- Conservar las rutas de objetos `modelos/<nombre>/<version>/modelo.onnx` y `modelo.json`.
- Aislar fallos: si un modelo falla, continuar preparando los otros. Registrar el error específico en logs y un estado público seguro.
- Reutilizar el conjunto `torax-rx/v1` una sola vez. No descargar, convertir ni cargar 200 imágenes por cada modelo.
- Verificar casos, etiquetas y hash, publicando el manifiesto del conjunto al final. No generar otra selección de imágenes para favorecer un modelo.

La primera instalación requiere internet. Los arranques siguientes deben reutilizar pesos y conjunto persistidos. No incorporar los casos reservados en el frontend ni publicar sus etiquetas por la API.

### 5.2 Registro interno y outbox

Generalizar `backend/app/demo.py` para procesar las tres identidades:

- Reutilizar `PublicarModelo`; no insertar métricas ni simular tokens de administrador.
- Conservar unicidad por `(nombre, version)` y emplear esa identidad también como clave de outbox y presupuesto de reintentos. La tabla `demo_inicializacion` ya permite varias claves.
- Sustituir el único candado por un candado determinista por identidad. No usar `hash()` de Python, que cambia entre procesos.
- Confirmar la fila y su outbox antes de enviar a SQS; conservar la semántica de entrega al menos una vez y la aplicación idempotente de resultados.
- Si un modelo está `ok`, conservar ID, fechas y métricas. Si está pendiente o en curso, dejar continuar su evaluación sin republicarlo.
- Mantener recuperación limitada de envíos fallidos y pendientes sin noticias. Un error en un modelo no debe detener los otros dos.
- No usar un único booleano `terminado` que detenga el inicializador después del primer modelo completado.
- Encolar una evaluación independiente por modelo y dejar que el evaluador actual las consuma. No aumentar la concurrencia de Fargate ni las cuotas del Lab para evaluar los tres al mismo tiempo.

Al actualizar una instalación existente, reconocer el modelo inicial y preparar solamente lo que falte. No borrar los objetos o métricas del usuario para migrar las marcas globales anteriores.

### 5.3 Estado, espera y recuperación

Mantener `/api/publico/demo` para el estado de los modelos predeterminados, ampliando su respuesta con:

- `activo`, estado global, cantidad esperada, cantidad lista y cantidad con error.
- Lista por modelo con nombre, versión, estado y, si ya existe en catálogo, ID.
- Estado global `ok` solo cuando los tres estén evaluados correctamente; distinguir preparación, disponibilidad parcial y error final.

Los conteos de los modelos predeterminados no incluyen modelos adicionales publicados por usuarios. El catálogo general sigue mostrándolos a todos.

Actualizar todos los consumidores juntos: frontend, comando de espera, documentación y pruebas. No exponer URLs firmadas, credenciales, excepciones internas ni verdad del conjunto reservado.

`tools/esperar_modelo.py` debe esperar los tres por defecto, admitir seleccionar una identidad y terminar con error o timeout cuando corresponda. Con disponibilidad parcial, la web sigue permitiendo usar los modelos listos aunque el comando que espera los tres todavía no termine correctamente.

`python -m app.reintentar_demo` debe permitir indicar nombre y versión, preservar los modelos sanos y limitar la recuperación al elegido. No reiniciar o reevaluar los otros para recuperar uno.

### 5.4 Docker y AWS

- `docker compose up -d --build` debe preparar y publicar los tres automáticamente, sin pasos manuales en `/publicar`.
- Conservar los volúmenes y servicios existentes. La ampliación no agrega tres backends ni tres workers.
- Actualizar el constructor de AWS para que el mismo preparador recorra el registro.
- Conservar `datos_demo` / `DATOS_DEMO` como control del conjunto predeterminado. Desactivarlo no borra modelos existentes ni impide publicar otros.
- Incluir los nuevos contratos, manifiestos y registro en el hash y ZIP de despliegue. Mantener el empaquetado que copia bytes mediante lista explícita y excluye secretos/estado.
- Los ~49 MB adicionales de pesos se descargan en preparación, no se agregan a Git ni al bundle del navegador.
- Mantener permisos, tamaños y escalado actuales salvo que una medición demuestre un problema. Si hay que ajustar memoria o caché para alternar modelos, documentar el motivo.
- Terraform puede terminar antes de que estén evaluados los tres; documentar la espera. Validar Terraform con proveedores simulados sin desplegar recursos reales.

## 6. UI: tres opciones, mismo recorrido

### Portada

- Cuando termine la preparación, mostrar las tres tarjetas predeterminadas, con nombres distinguibles y enlaces a sus fichas.
- Evitar que la selección actual de los tres modelos de mayor accuracy oculte alguno de los predeterminados cuando un usuario publique un cuarto. Reservar la sección principal para los modelos incluidos, sin ocultar los adicionales del catálogo.
- Indicar «3 modelos listos para usar» solo cuando los tres estén realmente en `ok`; durante la preparación mostrar cantidades reales, por ejemplo «2 de 3 modelos iniciales listos».
- Mantener «Elegí un modelo → Subí tu estudio → Consultá el resultado» y «Publicar uno propio» como acción opcional.

### Catálogo `/modelos`

- Mostrar tres tarjetas diferenciadas: Mediscan, DenseNet121 y EfficientNet-B0, cada una con nombre, versión, tipo de estudio, estado y métricas propias.
- Conservar búsqueda, filtros, ordenamiento y paginación. Los modelos del usuario son opciones adicionales: no limitar el catálogo a tres elementos.
- Una tarjeta abre la ficha del modelo que representa. Se puede hacer más explícito el texto de la acción, por ejemplo «Usar este modelo», preservando navegación con teclado y móvil.
- No etiquetar como listo un modelo cuya evaluación esté pendiente o fallida. Si uno falla, los otros siguen disponibles y el mensaje explica qué opción no pudo prepararse.
- Mantener las métricas comparables sobre el mismo conjunto. La etiqueta «Mejor del tipo» debe derivarse de las métricas reales del catálogo, sin favorecimientos manuales.

### Ficha e inferencia

- Identificar claramente nombre y versión del modelo elegido junto al área de consulta.
- Reutilizar el formulario, subida a S3, encolado, polling y presentación de resultados existentes.
- Enviar el `modelo_id` de esa ficha, no el del modelo inicial fijado en una constante.
- Mostrar el nombre del modelo también al presentar el resultado; cambiar de ficha no debe conservar un resultado atribuible al modelo anterior.
- No agregar comparación simultánea, votación, ensemble ni selección automática por accuracy.
  (Después llegó la junta de modelos como pantalla aparte, `/junta`; la ficha sigue corriendo un
  solo modelo.)

### Publicación propia

- Mantener el formulario ONNX + contrato y sus permisos actuales.
- Aclarar que ya hay modelos disponibles y publicar uno propio es opcional, con acceso al catálogo.
- Generalizar los mensajes de `EstadoDemo`, `ModelosListos` y los conteos para contemplar preparación parcial, tres modelos iniciales y modelos de usuarios.
- Respetar los cambios visuales previos: sin títulos entre corchetes y sin reintroducir los enlaces eliminados del footer.

## 7. Pruebas y criterios de aceptación

1. Los manifiestos de los candidatos coinciden con revisión, tamaño y SHA-256 investigados. Cargan con ONNX Runtime 1.18 y los contratos específicos correctos.
2. En una instalación local aislada y limpia, un único arranque prepara el conjunto una vez y registra exactamente una entrada por cada modelo predeterminado.
3. Los tres completan una evaluación real sobre el mismo manifiesto de 200 casos. La UI y la API muestran sus métricas individuales; no se exige igualar métricas de otro entorno ni se inventan valores.
4. El comando de espera global termina correctamente solo cuando los tres están listos. Su opción individual verifica únicamente el modelo indicado.
5. En la instalación actual, la ampliación agrega dos entradas y conserva el ID, las fechas y las métricas del inicial. Se preservan los modelos de usuarios.
6. Reiniciar o reconstruir no duplica registros, descargas ni evaluaciones. Dos procesadores concurrentes no publican la misma identidad dos veces.
7. Simular un hash inválido, una descarga interrumpida, un envío fallido y una evaluación fallida en uno de los modelos: los otros continúan y la disponibilidad parcial se refleja correctamente.
8. La recuperación individual modifica solo el modelo elegido. Las cachés separan artefactos y contratos de las tres identidades.
9. La portada muestra los tres predeterminados incluso si se publica un cuarto modelo con mayor accuracy. El catálogo permite acceder también a ese cuarto y mantiene sus filtros.
10. Probar el recorrido de una inferencia con cada modelo; el trabajo debe referenciar el ID seleccionado y producir probabilidades válidas para sus clases.
11. Comprobar estados iniciales, parciales, listos y fallidos; actualización automática; navegación con teclado; distribución móvil; y conservación de la publicación opcional.
12. Actualizar README, arquitectura y documentación de Terraform. Ejecutar las pruebas afectadas y las simuladas de infraestructura; dejar expresamente pendiente la prueba real en AWS si no se autorizó.

Usar proyecto Compose, puertos y volúmenes separados para las pruebas desde cero. No ejecutar `down -v` sobre el entorno del usuario ni destruir recursos AWS.

## 8. Fuera de alcance de esta ampliación

No entrenar modelos, no cambiar el objetivo clínico, no agregar otro dataset/modalidad, no incorporar GPU ni servidores de inferencia externos. No reemplazar el modelo inicial ni deshabilitar la publicación propia. No implementar inferencia en el navegador, aunque ese sea el mecanismo del Space usado como fuente de preprocesamiento.

Las descargas temporales y pruebas de compatibilidad realizadas para esta investigación no son una instalación en Ateneo. La implementación posterior usa descargas verificadas en los entornos Docker, sin incorporar los pesos en Git.

## 9. Verificación de la implementación

- 125 pruebas Python aprobadas, con PostgreSQL aislado: concurrencia, estados parciales,
  recuperación individual, descargas interrumpidas e integridad de manifiestos y artefactos.
- Dos pruebas de selección de la UI aprobadas: un cuarto modelo con mayor accuracy no
  desplaza los incluidos y no se confunden versiones durante una preparación parcial.
- Compilación TypeScript/Vite aprobada. Terraform validado y sus cinco pruebas simuladas aprobadas.
- Instalación limpia con un único arranque: tres registros, un conjunto de 200 casos y tres
  evaluaciones independientes. Accuracy medida: Mediscan 0.97, DenseNet121 0.665, EfficientNet-B0 0.70.
  Estos valores son de la demostración local; no son garantías clínicas ni umbrales de aceptación.
- Inferencia completa verificada con cada uno de los tres IDs, probabilidades válidas y ficha correcta.
- Reinicio y repetición de preparación conservan IDs, fechas y métricas sin reevaluar.
- Actualización del entorno habitual: se agregaron dos modelos y se conservó el inicial
  `95dc47fb-bc03-42d1-9034-46eb8f51b5df` con sus fechas y métricas originales.
- Comandos de espera global e individual verificados. El entorno del usuario queda funcionando.
- Revisión visual y navegación manual en móvil/teclado pendientes: no hay navegador integrado
  disponible. Despliegue real en AWS pendiente de autorización.

## 10. Ampliación: un segundo tipo de estudio (RM de cerebro)

Implementada y verificada localmente el 20 de octubre de 2026. Suma dos modelos de otra
modalidad y región, con su propio conjunto reservado. Reemplaza, para esta ampliación, el
«no agregar otro dataset/modalidad» de la sección 8.

### 10.1 Búsqueda

Requisitos: clasificación de imagen 2D, pesos en ONNX (el único motor es ONNX Runtime 1.18 en
CPU), descarga pública por revisión inmutable, licencia declarada y preprocesamiento
documentado por el autor (código o ficha), para no tener que adivinarlo. Además, un dataset
etiquetado con las mismas clases, público y servido por la API de datasets-server de Hugging
Face, que es lo que ya usa `tools/preparar_conjunto.py`.

Se recorrieron las APIs de modelos y Spaces de Hugging Face por región y modalidad (cerebro,
piel/dermatoscopía, retina/OCT/fondo de ojo, rodilla, fractura, mama, histopatología, MedMNIST).

| Familia | Candidatos ONNX revisados | Resultado |
| --- | --- | --- |
| **RM de cerebro, 4 clases** | Udit013 (MIT, código y paper), Space NareshKumarSekar (MIT, `app.py`), Space visheshallahabadi (Apache-2.0, `app.py`), y varios sin licencia o sin ficha | **Elegida**: modelos con licencia y preprocesamiento documentado, más un test público CC0 con las mismas clases. |
| Dermatoscopía (HAM10000/ISIC) | hakim78, Krane04, robinlandais, vin0san, Eraly-ml | Fichas vacías o sin preprocesamiento; algunos fp16. |
| OCT de retina | animeshakr (MIT, paper) | Un solo candidato con licencia; 243 MB. |
| Rodilla, artrosis | c2p-cmd (MIT) | Un solo candidato; su ejemplo de inferencia transpone mal la imagen. |
| Histopatología | kaczmarj CAMELYON16 (CC-BY-4.0) | Espera embeddings de CTransPath, no una imagen. |
| BreastMNIST | Daemons-Q ResNet-18/50 | 28 × 28; la ficha documenta dudas de licencia y contaminación del dataset. |

### 10.2 Modelos seleccionados

| Identidad | Nombre visible | Fuente y revisión | Licencia | ONNX |
| --- | --- | --- | --- | --- |
| `cerebro-rm-efficientnetb3` v1.0.0 | EfficientNetB3 · Tumor cerebral | [Udit013/brain-tumor-efficientnetb3](https://huggingface.co/Udit013/brain-tumor-efficientnetb3) @ `31a6602d40ea14a1e012855c4529326d06f9c126` | MIT | 46.448.207 bytes, SHA-256 `320b1ef6…155991c` |
| `cerebro-rm-cnn` v1.0.0 | CNN · Tumor cerebral | [Space NareshKumarSekar/BrainTumor](https://huggingface.co/spaces/NareshKumarSekar/BrainTumor) @ `0323f6ee650bfa2b0ef5d3352e15971ea0d6c5e3` | MIT | 76.661.663 bytes, SHA-256 `98e70366…0e3ab7` |

Los dos comparten `tipo_estudio = cerebro-rm` y las etiquetas `glioma`, `meningioma`,
`notumor`, `pituitary`. Son autores y arquitecturas distintos: una EfficientNetB3 preentrenada
en ImageNet y una red convolucional propia de 6 convoluciones, las dos exportadas de Keras.

Contratos, tomados de la documentación de cada autor y del grafo, sin ajustar nada para
mejorar resultados:

- **EfficientNetB3**: entrada `input` NHWC [1, 256, 256, 3] con píxeles crudos (`escala` 1, sin
  media ni desvío: el grafo reescala y normaliza adentro). Salida `dense_2` ya pasada por
  softmax → `probabilidades`. Orden de clases: `CLASS_NAMES` de `src/btc/config.py` del autor.
- **CNN**: entrada `input_layer_1` NHWC [1, 224, 224, 3], dividida por 255 y sin otra
  normalización, como la función `classify_tumor` del `app.py` del Space. Salida `output_0` ya
  pasada por softmax → `probabilidades`. El `app.py` nombra las clases `Glioma`, `Meningioma`,
  `No Tumor`, `Pituitary`; el contrato conserva ese orden con el vocabulario del conjunto.

Los dos se verificaron en un contenedor sin red con `onnx.checker` y ONNX Runtime 1.18, y cargan
y corren con `OnnxMotor` e `Inferidor`.

**Descartado: ResNet-50 de visheshallahabadi.** Fue el segundo modelo en la primera versión
(Apache-2.0, preprocesamiento ImageNet documentado en su `app.py`). Sacó 200 de 200 sobre el
conjunto reservado, cuando el EfficientNetB3 del paper, entrenado con el mismo dataset, se
equivoca en 9. Un 100 % sobre este test indica que casi seguro vio esas imágenes al entrenar, y
su ficha no dice con qué datos lo hizo. En el catálogo se mostraba como «Mejor del tipo», así
que se reemplazó por la CNN, que tiene un error creíble y repartido entre clases.

### 10.3 Conjunto reservado `cerebro-rm/v1`

- Fuente: [AIOmarRehan/Brain_Tumor_MRI_Dataset](https://huggingface.co/datasets/AIOmarRehan/Brain_Tumor_MRI_Dataset),
  revisión `a1beff9ed4f903fb3cb2b433eb65cd151d901024`, licencia CC0-1.0. Su único split, `test`, es el
  `Testing` publicado del dataset de Masoud Nickparvar en Kaggle: 1311 imágenes (300 glioma,
  306 meningioma, 405 notumor, 300 pituitary), compiladas de Figshare, SARTAJ y Br35H.
- Se toman 50 casos por clase (200 en total, igual que tórax), PNG RGB, semilla 42. La
  selección es determinista; el hash cambia en cada preparación porque los casos se renombran
  con UUID, pero dos instalaciones desde cero dieron las mismas métricas.

**Limitación conocida.** El autor de EfficientNetB3 midió que el test de ese dataset tiene casi-
duplicados del train (el 44 % por pHash, el 7 % exactos). Un modelo entrenado con ese train da
métricas optimistas sobre este test, y ninguna de las dos fichas permite descartarlo. No hay un
test externo público con las cuatro clases (el de Navoneel Chakrabarty es binario), así que la
demo mide sobre este y lo declara. No son métricas clínicas.

### 10.4 Cambios de implementación

- `models/conjuntos.json`: un conjunto por tipo de estudio (origen en Hugging Face, split,
  etiquetas, casos por clase y versión). Antes estaba fijo en el código.
- `tools/demo_assets.py`: `ConjuntoDemo`, `conjuntos()` y `conjunto_de(modelo)`, que exige que las
  etiquetas del conjunto estén en las del contrato, igual que el evaluador. `validar_conjunto`
  usa el reparto del conjunto. `preparar` arma cada conjunto una sola vez por pasada; si falla
  el de un tipo, los modelos del otro siguen.
- El evaluador, el worker, el backend y Terraform no cambian: el evaluador ya buscaba el
  conjunto por `tipo_estudio`, y Terraform empaqueta `models/` entero.
- UI: nombres legibles para los tipos conocidos («Tórax · RX», «Cerebro · RM») en tarjetas,
  filtros, ficha y cargador. Se quitaron los carteles «X de Y modelos iniciales listos»
  (`EstadoDemo`) y «N modelos listos · No necesitás publicar un modelo para empezar»
  (`ModelosListos`), que no corresponden a un MVP (reemplaza lo pedido en la sección 6). Cada
  modelo sigue apareciendo en el catálogo apenas se publica, con «Esperando la evaluación».
- `.gitattributes` fuerza LF en `models/**/modelo.json`, porque su SHA-256 está fijado en el
  manifiesto y un CRLF en el checkout lo invalidaría.

### 10.5 Verificación

- 127 pruebas Python aprobadas, incluidas las 6 de integración contra una base PostgreSQL
  descartable. Pruebas nuevas: conjunto de cuatro clases con su reparto, y un conjunto que
  falla sin bloquear los modelos de otro tipo ni reintentarse dentro de la misma pasada.
- TypeScript sin errores y las dos pruebas de la UI aprobadas.
- Actualización del entorno habitual, sin borrar volúmenes: el conjunto `torax-rx/v1` existente
  pasó la validación nueva y no se volvió a bajar. Los tres modelos de tórax conservaron IDs y
  métricas. El conjunto `cerebro-rm/v1` se preparó una vez y se reutilizó al cambiar de modelo.
- Instalación limpia (`docker compose down -v` y `up`): cada conjunto se armó una vez, se
  registraron exactamente los cinco modelos iniciales y los cinco quedaron evaluados en unos
  cinco minutos.
- Evaluación real sobre `cerebro-rm/v1` (200 casos):

  | Modelo | Accuracy | F1 macro | Sensibilidad glioma · meningioma · notumor · pituitary |
  | --- | --- | --- | --- |
  | EfficientNetB3 | 0,955 | 0,954 | 0,82 · 1,0 · 1,0 · 1,0 |
  | CNN | 0,935 | 0,935 | 0,96 · 0,84 · 0,98 · 0,96 |

- Inferencia completa por la API con los dos modelos (glioma, notumor y pituitary): cada
  trabajo usa el modelo elegido y devuelve probabilidades válidas para las cuatro clases.
- Revisión visual: catálogo con filtros por tipo, «Mejor del tipo» por tipo, ficha con
  métricas macro y matriz 4 × 4. Despliegue real en AWS pendiente de autorización.
