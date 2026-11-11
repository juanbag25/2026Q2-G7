# Sección 09: Cognito, con un grupo por rol y login administrado. El login sigue el recorrido de
# la clase (no el PKCE de la decisión 08 del HTML):
#   1. el navegador abre el sitio en S3, por HTTP (s3.tf)
#   2. el sitio redirige al Hosted UI de Cognito
#   3. Cognito vuelve a GET /callback de API Gateway, que es HTTPS: Cognito no acepta un
#      callback HTTP, y sin dominio propio ni CloudFront el sitio no puede ser HTTPS
#   4. la Lambda canjea el código por los tokens y redirige al sitio con los tokens en el
#      fragmento: http://<sitio>/#access_token=… (api.tf, lambda/callback.py)
#   5. el sitio los lee de la URL y los guarda en localStorage
#   6. cada pedido a la API lleva el access token; API Gateway lo valida y el backend también
#
# Instituciones y publicadores se registran solos. Hay un cliente por puerta del sitio: «crear
# cuenta» de institución y de publicador, cada uno con su grupo (lo pone la Lambda de
# post-confirmación), e «Ingresar», que no da grupo. El autorregistro es de todo el user pool y
# el Hosted UI muestra «Sign up» en cualquier cliente: quien se registra desde «Ingresar» queda
# sin grupo y elige el tipo una sola vez dentro de la app (POST /api/cuenta/tipo). Ningún camino
# da un grupo por defecto. Médicos e integrantes llegan por invitación; los admins se crean acá.

locals {
  grupos_cognito = {
    medico            = "Médicos de una institución aprobada: consultan estudios"
    admin_institucion = "Quien administra una institución"
    publicador        = "Quien publica modelos"
    admin_plataforma  = "Administración de Ateneo"
  }

  # Los clientes del Hosted UI: «Ingresar» y crear cuenta de cada tipo.
  clientes_cognito = toset(["ingreso", "institucion", "publicador"])

  # cliente => grupo en el que queda quien se registra por él. «ingreso» no está, a propósito.
  grupo_al_registrarse = {
    institucion = "admin_institucion"
    publicador  = "publicador"
  }
}

resource "aws_cognito_user_pool" "ateneo" {
  name = "ateneo"

  # El email es el nombre de usuario, y Cognito lo verifica con un código antes de dejar entrar.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # Hasta 50 mails por día con el remitente de Cognito: alcanza para la demo (riesgo 08).
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  lambda_config {
    post_confirmation = aws_lambda_function.post_confirmacion.arn
  }

  deletion_protection = "INACTIVE" # terraform destroy tiene que poder borrarlo
}

resource "aws_cognito_user_group" "g" {
  for_each     = local.grupos_cognito
  name         = each.key
  description  = each.value
  user_pool_id = aws_cognito_user_pool.ateneo.id
}

# El prefijo es único en toda la región, como los nombres de bucket: lleva el mismo sufijo.
resource "aws_cognito_user_pool_domain" "ateneo" {
  domain                = "ateneo-${local.sufijo}"
  user_pool_id          = aws_cognito_user_pool.ateneo.id
  managed_login_version = 1 # Hosted UI clásico; el 2 (managed login) exige además un recurso de branding
}

resource "aws_cognito_user_pool_client" "web" {
  for_each     = local.clientes_cognito
  name         = "ateneo-${each.key}"
  user_pool_id = aws_cognito_user_pool.ateneo.id

  # Cliente confidencial: el secreto lo tiene solo la Lambda del callback.
  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  # Las dos en API Gateway (HTTPS). La de logout también: la Lambda rebota al sitio.
  callback_urls = [local.url_callback]
  logout_urls   = [local.url_logout]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

locals {
  cognito_dominio = "https://${aws_cognito_user_pool_domain.ateneo.domain}.auth.${var.region}.amazoncognito.com"
  cognito_emisor  = "https://${aws_cognito_user_pool.ateneo.endpoint}" # iss de los tokens
}

# --- La Lambda de post-confirmación: el grupo de «crear cuenta» -----------------------

data "archive_file" "post_confirmacion" {
  type        = "zip"
  source_file = "${path.module}/lambda/post_confirmacion.py"
  output_path = "${path.module}/.build/post_confirmacion.zip"
}

resource "aws_cloudwatch_log_group" "post_confirmacion" {
  name              = "/aws/lambda/ateneo-post-confirmacion"
  retention_in_days = 7
}

# Por nombre de cliente y no por id: el pool depende de esta función, así que la función no
# puede depender de los clientes.
resource "aws_lambda_function" "post_confirmacion" {
  function_name    = "ateneo-post-confirmacion"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.12"
  handler          = "post_confirmacion.handler"
  filename         = data.archive_file.post_confirmacion.output_path
  source_code_hash = data.archive_file.post_confirmacion.output_base64sha256
  timeout          = 5 # Cognito espera a lo sumo 5 segundos a un disparador
  depends_on       = [aws_cloudwatch_log_group.post_confirmacion]

  environment {
    variables = {
      # Sin ateneo-ingreso y sin grupo por defecto: un cliente que no está acá no da ninguno.
      GRUPO_POR_CLIENTE = jsonencode({ for cliente, grupo in local.grupo_al_registrarse : "ateneo-${cliente}" => grupo })
    }
  }
}

resource "aws_lambda_permission" "post_confirmacion" {
  statement_id  = "cognito"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_confirmacion.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.ateneo.arn
}

# --- El admin de plataforma inicial ---------------------------------------------------

resource "aws_cognito_user" "admin" {
  count        = var.email_admin != "" ? 1 : 0
  user_pool_id = aws_cognito_user_pool.ateneo.id
  username     = var.email_admin

  attributes = {
    email          = var.email_admin
    email_verified = true
  }
  desired_delivery_mediums = ["EMAIL"] # Cognito le manda la contraseña temporal
}

resource "aws_cognito_user_in_group" "admin" {
  count        = var.email_admin != "" ? 1 : 0
  user_pool_id = aws_cognito_user_pool.ateneo.id
  group_name   = aws_cognito_user_group.g["admin_plataforma"].name
  username     = aws_cognito_user.admin[0].username
}
