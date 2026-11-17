variable "region" {
  description = "El Learner Lab solo habilita todo en us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "zonas" {
  description = "Las dos AZ. La subred de evaluación va solo en la primera (sección 06)."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.zonas) == 2 && length(distinct(var.zonas)) == 2
    error_message = "Hacen falta exactamente dos zonas, distintas: el ALB y cada capa de subredes van en las dos."
  }

  # Cambiar region sin cambiar zonas fallaba recién en el apply, al crear la primera subred.
  validation {
    condition     = alltrue([for z in var.zonas : can(regex("^${var.region}[a-z]$", z))])
    error_message = "Las zonas tienen que ser de var.region: con region = \"us-east-1\", por ejemplo \"us-east-1a\"."
  }
}

variable "sufijo" {
  description = "Sufijo de los buckets y del dominio de Cognito (únicos en todo AWS). Vacío = uno al azar, fijo desde el primer apply."
  type        = string
  default     = ""

  # Va en el nombre de los cinco buckets (S3 no acepta mayúsculas ni guiones bajos) y en el
  # prefijo del dominio de Cognito, que además rechaza las palabras aws, amazon y cognito. Uno
  # que no sirve fallaba recién en el apply, con parte de la infraestructura ya creada.
  validation {
    condition = var.sufijo == "" || (
      can(regex("^[a-z0-9]([a-z0-9-]{0,18}[a-z0-9])?$", var.sufijo)) &&
      !strcontains(var.sufijo, "aws") && !strcontains(var.sufijo, "amazon") && !strcontains(var.sufijo, "cognito")
    )
    error_message = "Vacío, o de 1 a 20 minúsculas, dígitos y guiones, sin guion al principio ni al final, y sin «aws», «amazon» ni «cognito»."
  }
}

variable "email_admin" {
  description = "El admin_plataforma inicial. Cognito le manda una contraseña temporal. Vacío = sin admin (los admins se crean con Terraform)."
  type        = string
  default     = ""

  validation {
    condition     = var.email_admin == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email_admin))
    error_message = "Una dirección de mail (alguien@dominio.com), o vacío para no crear el admin inicial."
  }
}

variable "email_alertas" {
  description = "Recibe las alarmas de operación por SNS (colas de fallidos, 5xx del ALB). Vacío = sin suscripción."
  type        = string
  default     = ""

  validation {
    condition     = var.email_alertas == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email_alertas))
    error_message = "Una dirección de mail (alguien@dominio.com), o vacío para no suscribir a nadie a las alarmas."
  }
}

variable "datos_demo" {
  description = "Prepara el modelo verificado y 200 casos de demostración; el procesador publica y encola su evaluación automáticamente."
  type        = bool
  default     = true
}

variable "waf_activo" {
  description = "WAF en el ALB: los dos topes por cliente y las reglas administradas de AWS. false si el laboratorio no lo permite (sección 12)."
  type        = bool
  default     = true
}

# --- Límites de pedidos --------------------------------------------------------------------
# Tres números que se cambian en vivo: un apply los actualiza sin reemplazar nada. El WAF pone en
# cero sus cuentas al cambiar un tope y puede tardar hasta un minuto en volver a cortar.
#
# La api atiende unos 200 pedidos por segundo con sus 4 tareas de 0,5 vCPU: unos 50 por tarea
# en rutas que consultan la base. Es una estimación, no una medición.

variable "api_pedidos_por_segundo" {
  description = <<-EOT
    Pedidos por segundo que API Gateway deja pasar por cada ruta, sumando a todos los clientes.
    Lo que el WAF bloquea ya pasó por acá y gastó de este límite: por eso es 500 y no los 200 que
    atiende la api. Queda lugar para la api entera aunque alguien mande 300 por segundo que el
    WAF está cortando.
  EOT
  type        = number
  default     = 500

  validation {
    condition     = var.api_pedidos_por_segundo >= 1 && var.api_pedidos_por_segundo <= 10000
    error_message = "Entre 1 y 10.000: el límite de una ruta no puede pasar el de la cuenta, que es de 10.000 por segundo."
  }
}

variable "api_rafaga" {
  description = "Pedidos que API Gateway acepta de golpe en una ruta por encima del promedio: el tamaño del balde. Dos segundos de api_pedidos_por_segundo."
  type        = number
  default     = 1000

  validation {
    condition     = var.api_rafaga >= 1 && var.api_rafaga <= 5000
    error_message = "Entre 1 y 5.000: la ráfaga de una ruta no puede pasar la de la cuenta."
  }
}

variable "waf_pedidos_por_cuenta" {
  description = <<-EOT
    Pedidos por minuto que el WAF le deja hacer a cada token (encabezado Authorization) en todas
    las rutas; desde el siguiente contesta 429. La pestaña que más pide (la de la junta, esperando
    resultados mientras se preparan los modelos) hace unos 70: 300 deja lugar para cuatro abiertas
    a la vez. Una cuenta en el tope usa 5 por segundo, el 1 % del límite de API Gateway.
  EOT
  type        = number
  default     = 300

  validation {
    condition     = var.waf_pedidos_por_cuenta >= 10
    error_message = "El WAF no acepta topes por tasa menores que 10."
  }
}

variable "waf_pedidos_por_ip" {
  description = <<-EOT
    Pedidos por minuto que el WAF le deja hacer a cada IP en las rutas sin token (/api/health y
    /api/publico/*). Todas las pestañas detrás de un mismo NAT comparten IP: una pide /api/health
    cada 10 s y, mientras se preparan los modelos, el catálogo cada 5 s, unos 30 por minuto. 1.200
    deja entrar a un aula entera, unas 40 pestañas.
  EOT
  type        = number
  default     = 1200

  validation {
    condition     = var.waf_pedidos_por_ip >= 10
    error_message = "El WAF no acepta topes por tasa menores que 10."
  }
}

variable "crear_buckets" {
  description = <<-EOT
    Que el apply cree los buckets llamando al CLI (scripts/buckets.sh). Siempre true en una cuenta
    de verdad: es la única forma de crearlos, porque el provider no puede refrescar un
    `aws_s3_bucket` en el Learner Lab (ver s3.tf). false solo en `terraform test`, donde no hay
    cuenta contra la que correr el CLI.
  EOT
  type        = bool
  default     = true
}

variable "esperar_imagenes" {
  description = "Que el apply espere a que el constructor suba las imágenes antes de crear los servicios. Usa la CLI de AWS (está en CloudShell). false = ECS reintenta solo hasta que aparezcan."
  type        = bool
  default     = true
}

variable "container_insights" {
  description = <<-EOT
    Container Insights en el cluster de ECS. Prendido publica RunningTaskCount, el divisor del
    backlog por tarea con el que escalan worker y procesador (escalado.tf). Apagado, los dos caen
    a escalones sobre los mensajes visibles, sin dividir. false si el laboratorio no lo permite
    (sección 12).
  EOT
  type        = bool
  default     = true
}

variable "mensajes_por_worker" {
  description = "Mensajes esperando en `inferencias` por tarea del worker a partir de los cuales se agrega otra."
  type        = number
  default     = 10

  # Es el objetivo del backlog por tarea y el umbral de la alarma de escalones (escalado.tf): con
  # 0, «hay al menos 0 mensajes esperando» siempre es cierto, y el worker crece sin trabajo.
  validation {
    condition     = var.mensajes_por_worker >= 1
    error_message = "Al menos 1 mensaje por tarea."
  }
}
