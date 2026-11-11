# Sección 08: cinco buckets con nombre de sufijo aleatorio (son únicos en todo AWS) y cifrado
# SSE-S3. Cuatro privados, con el acceso público bloqueado y los pedidos sin TLS denegados.
# El quinto, web, es el sitio estático: el paso 1 del login de la clase (cognito.tf).
# terraform destroy los vacía y los borra: la regla de uso es destruir al final de cada sesión.
#
# Los buckets no los crea `aws_s3_bucket`. El Learner Lab tiene un deny explícito sobre
# s3:GetBucketObjectLockConfiguration en una SCP de la organización, y el provider lee esa
# configuración cada vez que refresca un `aws_s3_bucket`, aunque el bucket no use object lock:
# el apply muere con AccessDenied. No se arregla dando permisos (una SCP no se sobreescribe desde
# la cuenta) ni pineando el provider. Así que los crea el CLI, que sí puede, y Terraform
# administra todo lo demás: cada configuración es un recurso aparte que lee solo lo suyo.
# El detalle está en scripts/buckets.sh y el desvío, en la sección 12 de la arquitectura.

resource "terraform_data" "buckets" {
  for_each = var.crear_buckets ? local.buckets : {}

  # Los provisioners de destroy solo pueden mirar `self`, así que todo lo que necesita el borrado
  # viaja acá adentro.
  input = {
    nombre = each.value
    script = abspath("${path.module}/scripts/buckets.sh")
  }

  # Si cambia el nombre del bucket, es otro bucket: se crea el nuevo y se borra el viejo.
  triggers_replace = [each.value]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "bash '${abspath("${path.module}/scripts/buckets.sh")}' crear '${each.value}'"
  }

  provisioner "local-exec" {
    when        = destroy
    on_failure  = continue # un bucket que sobrevive cuesta centavos; wedgear el destroy, no
    interpreter = ["/bin/bash", "-c"]
    command     = "bash '${self.output.script}' borrar '${self.output.nombre}'"
  }
}

locals {
  # El nombre es el id del bucket y el ARN se arma con él: no hay recurso del que leerlos.
  arn_bucket = { for clave, nombre in local.buckets : clave => "arn:aws:s3:::${nombre}" }
}

# El cifrado en reposo, escrito y no heredado del valor por defecto de la cuenta. AWS cifra con
# SSE-S3 todo objeto nuevo desde enero de 2023, así que esto no cambia nada en ejecución: lo que
# cambia es que se ve en el plan y en la consola. La devolución de la E2 pidió que lo guardado en
# un bucket esté cifrado, y una afirmación así no puede quedar apoyada en un valor por defecto.
resource "aws_s3_bucket_server_side_encryption_configuration" "b" {
  for_each = local.buckets
  bucket   = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }

  depends_on = [terraform_data.buckets]
}

resource "aws_s3_bucket_public_access_block" "b" {
  for_each           = local.buckets
  bucket             = each.value
  block_public_acls  = true
  ignore_public_acls = true
  # Sin ACL públicas en ninguno: el sitio se abre con su política, no con ACL.
  block_public_policy     = each.key != "web"
  restrict_public_buckets = each.key != "web"

  depends_on = [terraform_data.buckets]
}

# Un ONNX pisado se recupera.
resource "aws_s3_bucket_versioning" "modelos" {
  bucket = local.buckets.modelos
  versioning_configuration {
    status = "Enabled"
  }

  depends_on = [terraform_data.buckets]
}

resource "aws_s3_bucket_lifecycle_configuration" "estudios" {
  bucket = local.buckets.estudios

  rule {
    id     = "borrar-7-dias"
    status = "Enabled"
    filter {}
    expiration {
      days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [terraform_data.buckets]
}

resource "aws_s3_bucket_lifecycle_configuration" "artefactos" {
  bucket = local.buckets.artefactos

  rule {
    id     = "borrar-30-dias"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }

  depends_on = [terraform_data.buckets]
}

# El navegador sube con un POST prefirmado. El origen es el sitio en S3, que no cambia: el CORS
# sale de acá y ya no hay que copiar ninguna dirección a mano.
resource "aws_s3_bucket_cors_configuration" "subidas" {
  for_each = toset(["estudios", "modelos"])
  bucket   = local.buckets[each.key]

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["POST", "PUT", "GET", "HEAD"]
    allowed_origins = [local.url_sitio]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }

  depends_on = [terraform_data.buckets]
}

# --- Políticas ------------------------------------------------------------------------

locals {
  sin_tls = {
    for k in ["modelos", "estudios", "evaluacion", "artefactos"] : k => {
      Sid       = "SoloConTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [local.arn_bucket[k], "${local.arn_bucket[k]}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }
  }

  # bucket => lista de sentencias, ya en JSON
  politicas = {
    modelos    = jsonencode([local.sin_tls["modelos"]])
    estudios   = jsonencode([local.sin_tls["estudios"]])
    artefactos = jsonencode([local.sin_tls["artefactos"]])
    # El conjunto reservado solo se lee por el endpoint de la VPC, venga de quien venga. Deniega
    # leer, no escribir: el operador (o el constructor, con datos_demo) sube los casos.
    evaluacion = jsonencode([local.sin_tls["evaluacion"], {
      Sid       = "LeerSoloDesdeElEndpointDeLaVPC"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${local.arn_bucket["evaluacion"]}/*"
      Condition = { StringNotEquals = { "aws:sourceVpce" = module.endpoints.endpoints["s3"].id } }
    }])
    # El sitio se lee por el endpoint de sitio web de S3, que es HTTP: acá no va la regla de TLS.
    web = jsonencode([{
      Sid       = "SitioPublico"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${local.arn_bucket["web"]}/*"
    }])
  }
}

resource "aws_s3_bucket_policy" "b" {
  for_each = local.politicas
  bucket   = local.buckets[each.key]
  policy   = jsonencode({ Version = "2012-10-17", Statement = jsondecode(each.value) })

  depends_on = [terraform_data.buckets, aws_s3_bucket_public_access_block.b]
}

# --- El sitio: S3 como servidor web, por HTTP -----------------------------------------

resource "aws_s3_bucket_website_configuration" "web" {
  bucket = local.buckets.web

  index_document {
    suffix = "index.html"
  }

  # /publicar y /consulta no son archivos: S3 contesta index.html y la app resuelve la ruta.
  error_document {
    key = "index.html"
  }

  depends_on = [terraform_data.buckets]
}

locals {
  url_sitio = "http://${aws_s3_bucket_website_configuration.web.website_endpoint}"
}

# Lo que el sitio necesita saber de la infraestructura, al lado del index.html. El build no lleva
# ninguna dirección: el constructor sube el sitio sin tocar este archivo.
resource "aws_s3_object" "config_web" {
  bucket        = local.buckets.web
  key           = "config.json"
  content_type  = "application/json"
  cache_control = "no-cache"
  content = jsonencode({
    api = local.url_api
    cognito = {
      dominio  = local.cognito_dominio
      clientes = { for cliente, c in aws_cognito_user_pool_client.web : cliente => c.id } # ingreso, institucion, publicador
      callback = local.url_callback
      logout   = local.url_logout
    }
  })

  depends_on = [terraform_data.buckets]
}
