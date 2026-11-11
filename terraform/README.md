# Ateneo en AWS 2.0, como código

La arquitectura de «Ateneo en AWS 2.0» (Entrega 3) entera en Terraform: `terraform apply` levanta
todo en una cuenta limpia del Learner Lab y `terraform destroy` lo borra, imágenes y buckets
incluidos. Quien lo corre no necesita Docker.

```
terraform/
    organization/   el root module: es acá donde se corre plan y apply
    modules/
        cola/       módulo propio: una cola de trabajo con su cola de fallidos
```

Las dos rutas no son una elección nuestra: los workflows que trae la plantilla de los repos de
`itba-cloud` las tienen escritas (`tfsec` corre sobre `terraform/organization`, `terraform-docs`
sobre `terraform/modules`).

| Pieza | Archivo |
|-------|---------|
| VPC 10.0.0.0/16: once subredes en seis capas, una tabla de ruteo por capa, un NAT, NACL de evaluación | `red.tf` |
| Endpoint Gateway de S3 y cuatro de interfaz (`ecr.api`, `ecr.dkr`, `logs`, `sqs`) en subredes propias | `red.tf`, módulo externo `vpc-endpoints` |
| Grupos de seguridad encadenados; procesador, worker, evaluador y constructor sin entrada | `seguridad.tf` |
| API Gateway (HTTP API, HTTPS) → VPC Link → ALB interno + WAF | `api.tf`, `balanceador.tf` |
| El autorizador JWT en todo `/api/*` salvo `/api/health` y `/api/publico/*`, que es el catálogo que ve el Visitante | `api.tf`, `backend/app/api/rutas/publico.py` |
| Cognito: cuatro grupos, Hosted UI con tres clientes («Ingresar» y crear cuenta de cada tipo), Lambda de post-confirmación, admin inicial | `cognito.tf` |
| El login de la clase: sitio en S3 y Lambda en `/callback` | `cognito.tf`, `api.tf`, `lambda/` |
| ECS Fargate: api, procesador, worker, evaluador | `ecs.tf`, `escalado.tf` |
| ECR y el constructor de imágenes | `imagenes.tf`, `plantillas/constructor.sh.tftpl` |
| SQS: `inferencias`, `evaluaciones`, `resultados`, cada una con su cola de fallidos | `colas.tf`, `modules/cola/` |
| RDS PostgreSQL 16 y su URL en Secrets Manager | `datos.tf` |
| Cinco buckets: web (el sitio), modelos, estudios, evaluación, artefactos | `s3.tf`, `scripts/buckets.sh` |
| EFS como caché de modelos de los workers | `efs.tf` |
| SNS y alarmas: colas de fallidos y 5xx del ALB | `alertas.tf` |

## Qué hace `terraform apply`

1. Empaqueta el código del repositorio (backend, frontend, worker, evaluador, `ateneo_ml`) y
   calcula su hash: es la etiqueta de las imágenes.
2. Crea la red, la base, los buckets, las colas, Cognito y API Gateway; sube el paquete al bucket
   de artefactos.
3. Lanza el constructor: una `t3.large` en la capa de aplicación que construye las imágenes
   `backend` y `ml`, las sube a ECR, sube el sitio al bucket web y, con `datos_demo`, siembra
   los cinco modelos iniciales y un conjunto de 200 casos de Hugging Face por tipo de estudio
   (Rx de tórax y RM de cerebro). Después se apaga.
4. Espera las imágenes (unos diez minutos la primera vez) y crea los servicios de ECS.
5. Imprime la dirección del sitio y el admin inicial. La verificación es abrir el sitio y entrar.

Un cambio de código produce otro hash: Terraform reemplaza el constructor, se construyen imágenes
nuevas y ECS cambia las tareas de a poco. **Sin cambios, el plan sale vacío.**

## Primer despliegue

En CloudShell, parado en el clon de `main`, que ya trae todo: la creación de los buckets por CLI
(sin eso el apply muere en el Learner Lab, más abajo en las restricciones) y los cinco modelos de
los dos tipos de estudio.

```bash
git clone https://github.com/nnicokim/TP-AWS.git ~/ateneo && cd ~/ateneo
bash terraform/organization/scripts/bootstrap-estado.sh            # una vez por cuenta: bucket del estado + backend.hcl
cp terraform/organization/terraform.tfvars.example terraform/organization/terraform.tfvars
nano terraform/organization/terraform.tfvars                       # email_admin y email_alertas
bash terraform/organization/scripts/tf.sh apply
bash terraform/organization/scripts/tf.sh output url
```

Después:

1. Abrí `url`. El admin entra con la contraseña temporal que le mandó Cognito. Cualquiera puede
   crear una cuenta: desde «Registrate como institución / publicador» queda con ese tipo, y desde
   «Ingresar → Sign up» lo elige la primera vez que entra.
2. Con `datos_demo = true`, esperá la preparación y evaluación automáticas de los cinco modelos
   iniciales. La web informa el estado y actualiza el catálogo; no hay que pulsar «Publicar».
   El evaluador arranca solo (de 0 a 1 tarea) cuando el procesador encola la evaluación.
3. En `/modelos`, abrí la ficha del modelo evaluado y subí una imagen de su tipo de estudio con tu cuenta de institución.

Si pusiste `email_alertas`, AWS manda una confirmación de SNS que hay que aceptar una vez.

**La regla de uso: se destruye al terminar cada sesión de trabajo** (`tf.sh destroy`). Prendido
cuesta unos USD 7 por día; una sesión de tres horas, alrededor de un dólar.

## Login con Cognito

El recorrido de la clase, paso por paso. No es el PKCE de la decisión 08 del HTML: la cátedra pide
este, con el sitio en S3 (cambia también la decisión 11).

| # | Qué pasa | Dónde |
|---|----------|-------|
| 1 | El usuario abre el sitio en S3, por HTTP | `s3.tf` (bucket web como sitio estático) |
| 2 | «Ingresar» (o «crear cuenta») redirige al Hosted UI de Cognito por el cliente de esa puerta, con un `state` al azar que empieza con el nombre del cliente | `frontend/src/api/sesion.ts` |
| 3 | Cognito vuelve a `GET /callback` de API Gateway, que es HTTPS | `cognito.tf` (`callback_urls`), `api.tf` |
| 4 | La Lambda canjea el código por los tokens (con el secreto del cliente) y redirige a `http://<sitio>/#access_token=…&id_token=…` | `lambda/callback.py` |
| 5 | El sitio lee los tokens del fragmento, comprueba el `state`, los guarda en `localStorage` y limpia la URL | `sesion.ts` → `recibirDelCallback()` |
| 6 | Cada pedido lleva `Authorization: Bearer <access token>`: API Gateway lo valida y el backend también, y lee los grupos | `frontend/src/api/cliente.ts`, `api.tf`, `backend/app/infraestructura/cognito/` |

- **Por qué el callback no va directo al sitio.** Cognito solo acepta callbacks HTTPS (salvo
  `localhost`), y el sitio de S3 es HTTP: sin CloudFront ni dominio propio no hay certificado.
- **Registro: tres clientes, uno por puerta.** «Registrate como institución» y «… como
  publicador» abren el alta de su propio cliente, y la Lambda de post-confirmación ve por cuál se
  confirmó la cuenta y la pone en su grupo (`admin_institucion` o `publicador`). «Ingresar» tiene
  un tercero, `ateneo-ingreso`, que no da grupo. Hace falta porque el autorregistro es de todo el
  user pool, no de un cliente, y el Hosted UI muestra el link «Sign up» en cualquiera: antes,
  quien se registraba desde «Ingresar» quedaba en el grupo del cliente de publicador, y un médico
  terminaba sin poder analizar estudios. No hay grupo por defecto: un cliente que la Lambda no
  conoce no da ninguno. El sitio pone el cliente al principio del `state` para que la Lambda del
  callback sepa con qué secreto canjear; si no nombra uno conocido, no canjea. Médicos e
  integrantes llegan por invitación (`aws cognito-idp admin-create-user`); los admins, con
  `email_admin`.
- **El tipo de cuenta se elige en la app, una sola vez.** Con sesión y sin grupos, el sitio
  pregunta «¿Tu cuenta es de una institución o de un publicador?» en cualquier ruta, y la
  respuesta va a `POST /api/cuenta/tipo`, que pide token pero no rol. El backend no decide con los
  grupos del token, que se emitió antes de elegir: lee los de Cognito (`AdminListGroupsForUser`),
  fija la elección en la tabla `cuenta` con el `sub` como clave (`insert … on conflict do nothing`
  y releer: de dos pedidos a la vez gana uno) y recién después agrega el grupo
  (`AdminAddUserToGroup`). Una elección distinta de la guardada, o un grupo distinto en Cognito,
  es `409`. Las tareas de la api llaman a Cognito como `LabRole`, por el NAT. Después el sitio
  vuelve a pasar por el login: la sesión de Cognito dura una hora, así que no pide la contraseña,
  y el token nuevo trae el grupo. Antes de preguntar, el sitio consulta `GET /api/cuenta/tipo`: si
  la cuenta ya eligió (en otro navegador, o el token es de antes de elegir), trae un token nuevo
  en vez de volver a preguntar.
- **Por qué no se elige en el formulario de Cognito.** Un atributo propio no puede ser
  obligatorio, el Hosted UI lo muestra como texto libre y no se completa por URL, y el Hosted UI
  no les pasa `clientMetadata` a los disparadores. Un formulario de alta propio haría tipear la
  contraseña en el sitio, que se sirve por HTTP desde S3 (no hay CloudFront en el lab); el Hosted
  UI la mantiene en HTTPS.
- **Qué guarda el navegador.** Access e id token, una hora. Sin refresh token en la URL: al
  vencer, «Ingresar» vuelve a pasar por Cognito, que recuerda la sesión y no pide la contraseña.

## Correcciones respecto de la Entrega 2

La devolución formal de la E2 todavía no llegó. Lo que sigue son las ocho inconsistencias que
encontramos nosotros auditando la entrega anterior antes de diseñar la 2.0, y qué las corrige en
este código. Cuando llegue la devolución se agrega acá lo que falte.

| # | Qué estaba mal en la E2 | Qué lo corrige |
|---|-------------------------|----------------|
| 1 | `specs.md` §14 daba la subida del ONNX desde la web como fuera de alcance, pero ya estaba implementada | La spec la describe como parte del alcance: es la pantalla `/publicar`, con URL prefirmada contra el bucket de modelos |
| 2 | `architecture.md` §9 le pasaba `BUCKET_MODELOS` al worker, que no lo necesita | El worker recibe solo `MODELOS_DIR=/mnt/modelos` (`ecs.tf`): lee los pesos de la caché de EFS y no habla con el bucket. La variable quedó en api, procesador y evaluador, que sí la usan |
| 3 | `generar-env.sh` escribía el usuario `ateneo`, y en la cuenta era `atenteo` | No hay más scripts de entorno a mano: `terraform apply` arma todo y los nombres salen de `locals.tf` y del sufijo guardado en el estado, nunca escritos dos veces |
| 4 | `apagar.sh` no borraba los ALB, que siguieron cobrando | `terraform destroy` borra lo que creó, balanceador incluido, y `destruir.yml` lo corre desde el pipeline |
| 5 | En la cuenta, `inf-b` y `data-b` colgaban de la tabla de ruteo principal | Una tabla de ruteo por capa y una asociación explícita por subred (`red.tf`): ninguna subred queda en la principal por omisión |
| 6 | El diagrama tenía una flecha worker → RDS, dibujaba el standby de RDS y el EFS fuera de las zonas | El worker no tiene credenciales de base ni grupo de seguridad hacia ella; RDS es Single-AZ y no tiene standby; el EFS tiene un mount target por zona (`efs.tf`). El diagrama nuevo se rehace sobre este código |
| 7 | El artifact de arquitectura decía «cuatro buckets» y eran cinco | Cinco, enumerados arriba y en `local.buckets`: web, modelos, estudios, evaluación y artefactos |
| 8 | La AMI dorada no era reproducible desde el repositorio | No hay más AMI dorada: las dos imágenes se construyen dentro de la cuenta a partir del código del repositorio y la etiqueta es su hash (`imagenes.tf`). Mismo commit, misma imagen |

## Restricciones del Learner Lab que este código respeta

- **No crea roles de IAM.** Tareas de ECS, Lambdas y constructor usan `LabRole` o
  `LabInstanceProfile` (se leen con `data`).
- **Los buckets los crea el CLI, no `aws_s3_bucket`.** El lab tiene un deny explícito sobre
  `s3:GetBucketObjectLockConfiguration` en una SCP, y el provider lee esa configuración cada vez
  que refresca un bucket: el apply muere con `AccessDenied` aunque el bucket no use object lock.
  No se arregla con permisos (una SCP no se sobreescribe) ni pineando el provider. Un paso del
  apply llama a `scripts/buckets.sh`, que crea lo que falte y al destruir vacía y borra; todo el
  resto de la configuración de cada bucket la sigue administrando Terraform. Por eso el apply
  necesita el `aws` CLI en la máquina, igual que para esperar las imágenes.
- **Sin CloudFront ni dominio propio.** El HTTPS lo pone API Gateway; el sitio es HTTP.
- **RDS sin Multi-AZ**, solo `us-east-1`, sin instance refresh (ya no hay grupos de EC2).
- **Credenciales de sesión:** se corre desde CloudShell. `scripts/tf.sh` deja el proveedor de AWS
  en `/tmp` para no llenar el giga de `$HOME`.

### Lo que todavía no se probó en un Learner Lab (sección 12 del HTML)

| Qué verificar | Si el lab no lo permite |
|---------------|-------------------------|
| VPC Link de HTTP API hacia un ALB interno | ALB público que solo acepte un encabezado secreto que agrega API Gateway |
| Servicios de Fargate (rol vinculado de ECS) y el escalado de Application Auto Scaling | Las mismas imágenes sobre EC2 con Auto Scaling |
| Cuota de vCPU de Fargate (todo escalado son 8,5 vCPU) | Bajar tamaños y máximos en `ecs.tf` |
| Container Insights en el cluster (publica `RunningTaskCount`, el divisor del backlog por tarea) | `container_insights = false`: worker y procesador escalan por escalones sobre los mensajes visibles |
| WAF asociado a un ALB | `waf_activo = false` |
| Disparador Lambda de Cognito | Registrarse desde «Ingresar» y elegir el tipo en la app, que no depende de la Lambda |
| Llamadas admin a Cognito desde las tareas de la api con `LabRole` (`AdminListGroupsForUser`, `AdminAddUserToGroup`), para elegir el tipo | Registrarse por «Registrate como institución / publicador», que da el grupo con la Lambda |
| Push a ECR desde EC2 con `LabInstanceProfile` | Construir con Docker en la máquina de quien corre Terraform |
| Bucket web público (bloqueo de acceso público a nivel de cuenta) | Servir el sitio desde la api, detrás de API Gateway |

## Lo que marca tfsec, y por qué

El pipeline de la cátedra corre `tfsec` sobre `terraform/organization` y comenta los hallazgos en
el PR. Hoy son **17, en 9 reglas**: 1 crítico, 1 alto, 2 medios y 13 bajos. Ninguno es un error:
tfsec lee el código contra una lista genérica de buenas prácticas y no sabe nada de esta
arquitectura ni del Learner Lab. Lo que sigue contesta cada uno.

Para reproducirlo:

```bash
docker run --rm -v "$PWD:/src" aquasec/tfsec /src/terraform/organization
```

### Lo que se arregló

Tres hallazgos que eran gratis y no tenían contra. Los altos pasaron de cuatro a uno.

| Regla | Qué se hizo |
|-------|-------------|
| `aws-ecr-enable-image-scans` (alto) | `image_scanning_configuration` en los dos repositorios: al subir, AWS compara las capas contra las vulnerabilidades conocidas. El escaneo básico de ECR no cuesta nada |
| `aws-elb-drop-invalid-headers` (alto) | `drop_invalid_header_fields` en el ALB: un encabezado HTTP malformado se tira ahí en vez de llegar a la api |
| `aws-rds-enable-iam-auth` (medio) | `iam_database_authentication_enabled`: queda habilitado aunque la aplicación siga entrando con la contraseña de Secrets Manager. No cambia nada de cómo se conecta |

### Lo que queda, y por qué

| Severidad | Regla | Respuesta |
|-----------|-------|-----------|
| **CRÍTICO** | `aws-elb-http-not-used` | El listener del ALB es HTTP:80, y así se queda. Ese ALB es `internal = true`: no tiene IP pública y lo único que lo alcanza es el VPC Link de API Gateway, encadenado por grupos de seguridad. El HTTPS que ve el usuario lo termina API Gateway. HTTPS en ese tramo necesitaría un certificado para un nombre interno, o sea dominio propio y ACM, que es lo que el lab no da (es el riesgo 09 de la arquitectura) |
| **ALTO** | `aws-sns-enable-topic-encryption` | Cifrar el topic con la clave que administra AWS **rompe las alarmas**: CloudWatch no puede publicar en un topic cifrado con `alias/aws/sns`, porque esa política de clave no se puede editar. Hacerlo bien pide una CMK con una política que le dé permiso a `cloudwatch.amazonaws.com`: una pieza más, un dólar por mes y algo que el lab puede no permitir. El topic solo lleva alertas de operación a los admins, no datos de pacientes |
| MEDIO | `aws-ec2-require-vpc-flow-logs-for-all-vpcs` | Los flow logs se pagan por GB ingerido en CloudWatch. En un lab con crédito finito, no |
| MEDIO | `aws-rds-enable-deletion-protection` | **A propósito en `false`.** La regla de uso es destruir al terminar cada sesión; con la protección puesta, `terraform destroy` falla y la base sigue cobrando |
| BAJO ×7 | `aws-cloudwatch-log-group-customer-key` | Los grupos de logs ya se cifran con la clave de CloudWatch. Una clave propia por grupo son siete claves a ~USD 1 por mes |
| BAJO ×2 | `aws-ecr-repository-customer-key` | Igual: ECR cifra con la clave de AWS; una CMK por repositorio es plata que no compra nada acá |
| BAJO ×2 | `aws-lambda-enable-tracing` | X-Ray en las dos Lambdas del login. Suma una dependencia y un costo por traza para dos funciones que se invocan una vez por inicio de sesión |
| BAJO | `aws-rds-enable-performance-insights` | `db.t3.micro` lo soporta y siete días de retención son gratis, pero habilitarlo abre un hallazgo **alto** nuevo (`aws-rds-enable-performance-insights-encryption`), que pide una CMK para cifrar esos datos. Cambiar un bajo por un alto no es una mejora |
| BAJO | `aws-ssm-secret-use-customer-key` | El secreto con la URL de la base ya se cifra con la clave de Secrets Manager |

No hay ningún `tfsec:ignore` en el código, a propósito: preferimos que el hallazgo aparezca en el
PR y que la respuesta esté acá, en vez de silenciarlo.

## Un equipo de varias personas

Los buckets y el dominio de Cognito llevan un sufijo al azar que queda en el estado, así que cada
integrante puede levantar su propio entorno en su lab sin choques. Lo que se comparte es el
repositorio: `terraform.tfvars` y `backend.hcl` son de cada uno y no se commitean.

El hash del código se calcula sobre los archivos tal como están en disco: un clon de Windows con
finales de línea CRLF da otro hash que uno de Linux. Corré Terraform siempre desde CloudShell.

## Pruebas sin cuenta

```bash
cd terraform/organization
terraform init -backend=false
terraform validate
terraform test          # la arquitectura del HTML contra un AWS simulado: red, cómputo, login, variables
```

## Módulos, funciones y meta-argumentos

Lo que pide la entrega, y dónde está.

### Módulos

| | Módulo | Dónde se llama | Qué encapsula |
|-|--------|----------------|----------------|
| **propio** | [`modules/cola`](modules/cola/README.md) | `organization/colas.tf`, con `for_each` sobre las tres colas | La cola, su cola de fallidos y las dos políticas que las emparejan. La arquitectura dice que ninguna cola de trabajo va sin su DLQ (sección 08, decisión 03): acá no se puede olvidar. 6 variables con `validation`, 7 salidas. |
| **externo** | [`terraform-aws-modules/vpc/aws//modules/vpc-endpoints`](https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/6.7.3/submodules/vpc-endpoints) `6.7.3` | `organization/red.tf` | Los cinco endpoints de la VPC. Resuelve en un lugar la diferencia entre un gateway (lleva tablas de ruteo) y uno de interfaz (lleva subredes, grupo y DNS privado). |

La versión del módulo externo está fijada exacta, no con `~>`: el lock de Terraform solo fija
proveedores, así que esa línea es lo único que garantiza que la cátedra baje lo mismo que probamos.

### Meta-argumentos

| Meta-argumento | Usos | Un ejemplo |
|----------------|------|------------|
| `for_each` | 32 | Las once subredes salen de un mapa de capas (`red.tf`); los cuatro servicios de Fargate, de `local.servicios` (`ecs.tf`) |
| `depends_on` | 15 | Cada configuración de bucket espera a `terraform_data.buckets`, porque los buckets no los crea el proveedor (`s3.tf`) |
| `count` | 6 | La suscripción de SNS existe solo si hay un mail de alertas (`alertas.tf`) |
| `lifecycle` | 2 | `ignore_changes` en el `desired_count` de los servicios, que lo maneja el escalado (`ecs.tf`), y en la AMI del constructor, que cambia sola cada tanto (`imagenes.tf`) |

### Funciones

27 distintas. Las que hacen algo que se nota:

| Función | Para qué |
|---------|----------|
| `fileset`, `filesha256`, `sha256`, `substr` | La etiqueta de las imágenes es el hash del código del repositorio: si no cambia el código, el plan sale vacío (`imagenes.tf`) |
| `templatefile` | El script del constructor, que se arma con las direcciones de la cuenta (`imagenes.tf`) |
| `jsonencode`, `jsondecode` | Las políticas de los buckets y de las colas |
| `merge` | Las once subredes, aplanando el mapa de capas; y los cinco endpoints, juntando el gateway con los cuatro de interfaz (`red.tf`) |
| `can`, `regex` | Las validaciones de `modules/cola`: un nombre que no sirve para una cola de SQS falla en el plan, no en el apply |
| `abspath` | La ruta del script de los buckets y la raíz del repositorio, que no dependen de desde dónde se corra |
| `toset`, `keys`, `flatten`, `distinct`, `sort`, `concat`, `length`, `contains`, `strcontains`, `split`, `join`, `replace`, `upper`, `endswith`, `tostring`, `urlencode` | El resto, repartidas |

Hay además 11 variables y 10 salidas en el root, y 5 bloques `validation`.

## El pipeline de GitHub Actions

Cuatro workflows en `.github/workflows/`. La división es por si necesitan credenciales de AWS o
no, porque las del Learner Lab vencen cada sesión:

| Workflow | Cuándo corre | Toca AWS | Qué hace |
|----------|--------------|----------|----------|
| `validar.yml` | solo, en cada push y cada PR | no | `fmt -check`, `init -backend=false`, `validate`, `test` |
| `plan.yml` | en el PR hacia `main`, y a mano | sí | bucket del estado, `init` y `plan`; guarda el plan como artifact |
| `aplicar.yml` | **solo a mano**, escribiendo «aplicar» | sí | bucket del estado, `init`, `validate` y `apply`; imprime el sitio y el admin inicial |
| `destruir.yml` | **solo a mano**, escribiendo «destruir» | sí | `tf.sh destroy` |

El ciclo `init` → `validate` → `plan` → `apply` que pide la entrega queda así: `validar.yml` hace
`init` y `validate` sin cuenta (es el chequeo de siempre), `plan.yml` hace `init` y `plan` contra
la cuenta, y `aplicar.yml` hace `init`, `validate` y `apply`. Cada uno es un step con su nombre en
el log del run, aunque `tf.sh` haga el init por su cuenta igual.

`validar` es el que tiene que estar siempre verde: no depende de credenciales. `plan` avisa en el
resumen y termina en verde si los secrets están vacíos, en lugar de pintar el PR de rojo. **Para
la entrega eso no alcanza:** hay que pegar las credenciales del lab antes de abrir el PR y
comprobar que el step `Plan` corrió y dejó el artifact con la salida de Terraform. No mires el
reloj: un plan sin cambios cierra en menos de un minuto. Lo que distingue un plan corrido de uno
salteado es el artifact, y que el resumen del run traiga la salida de `terraform plan`.

Los workflows no repiten comandos: llaman a `scripts/bootstrap-estado.sh` y `scripts/tf.sh`, los
mismos que usa una persona en CloudShell. Así el pipeline no puede desalinearse de esta guía.

Aplicar y destruir no se disparan con un push, a propósito: el lab cuesta unos USD 7 por día
prendido y la regla de uso es destruir al terminar: prenderlo es una decisión de una persona.
Los tres comparten `concurrency: infraestructura`, así que nunca corren dos a la vez contra la
misma cuenta.

### Secrets que hay que cargar en el repositorio

En Settings → Secrets and variables → Actions → New repository secret:

| Secret | De dónde sale |
|--------|---------------|
| `AWS_ACCESS_KEY_ID` | AWS Details → AWS CLI en el Learner Lab |
| `AWS_SECRET_ACCESS_KEY` | idem |
| `AWS_SESSION_TOKEN` | idem |
| `EMAIL_ADMIN` | el mail del `admin_plataforma` inicial |
| `EMAIL_ALERTAS` | el mail que recibe las alarmas de operación |

Las tres primeras **vencen cada sesión del lab** (unas cuatro horas): hay que volver a pegarlas
antes de correr `plan`, `aplicar` o `destruir`.

## Inicialización automática de modelos

Con `datos_demo = true`, el constructor ejecuta `python -m tools.demo_assets`: descarga los
pesos desde una revisión fija y comprueba tamaño y SHA-256, conserva los artefactos existentes
y prepara y verifica los 200 casos de evaluación. Se publica el manifiesto al final y una marca
de finalización por modelo en el bucket de modelos. El registro `models/catalogo.json`
identifica los cinco: Mediscan, DenseNet121 y EfficientNet-B0 para `torax-rx`, y EfficientNetB3
y una CNN para `cerebro-rm`. Cada uno se evalúa individualmente contra el conjunto reservado de
su tipo de estudio, y no forman un ensemble. Contratos, registro y manifiestos viajan
en el paquete; los pesos se descargan con revisión fija y SHA-256. Mediscan no declara
licencia y los otros cuatro declaran MIT; no se redistribuyen pesos en Git.

El procesador, después de migrar la base, reutiliza el caso de uso de publicación con un
candado y una outbox transaccional por nombre y versión. Confirma la fila antes de enviar a SQS y conserva modelos
ya evaluados. El envío se intenta hasta tres veces; un pendiente sin noticias puede reenviarse
a los 15 minutos. Los errores de evaluación requieren recuperación explícita. SQS mantiene
su semántica de entrega al menos una vez; no se promete entrega exactamente una vez ante
una caída entre envío y confirmación. La preparación nunca usa tokens de administrador.

`datos_demo = false` desactiva preparación y registro sin borrar datos existentes. API Gateway
permite consultar `GET /api/publico/demo` sin autenticación: solo devuelve estado y, cuando
corresponde, los IDs públicos y nombres de los modelos, más cantidades listas, pendientes
y con error. La disponibilidad parcial no bloquea los modelos sanos. Las inferencias mantienen sus permisos de Cognito.

Para comprobar la finalización desde tu PC (sin credenciales AWS):

```bash
python3 tools/esperar_modelo.py --url "<salida api de Terraform>" --timeout 1800
```

Si falla, revisá el log del constructor y `/ecs/ateneo/procesador` y `/ecs/ateneo/evaluador`.
Tras corregir los artefactos, la recuperación del registro puede ejecutarse como tarea puntual
con la imagen backend, entorno y secreto de la definición del procesador:
`python -m app.reintentar_demo --nombre torax-rx-densenet121 --version 1.0.0`.
Solo recupera esa identidad. No republica un modelo `ok` ni cancela uno `en_curso`.

El empaquetado usa una lista explícita y copia bytes a `.build/source-<hash>` antes de generar
el ZIP; no lee binarios con `file()` ni incluye estados o secretos. Requiere `python3` en la
máquina que corre Terraform (disponible en CloudShell). La terminación de `apply` no asegura
que ya hayan terminado las cinco evaluaciones: verificá el endpoint o usá el comando de espera.

El comando de espera verifica los cinco por defecto; `--nombre <identidad> --version 1.0.0`
permite verificar uno. Cada preparación tiene sus marcas bajo `demo/<nombre>/<version>/`;
las marcas globales de instalaciones anteriores se conservan sin usarse como éxito global.
Los fallos de un modelo no detienen la preparación/registro de los otros. Las colas y los
tamaños de Fargate se mantienen; el evaluador procesa las evaluaciones sin forzar simultaneidad.
