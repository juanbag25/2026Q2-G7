# API Gateway (HTTP API): la única puerta de entrada (decisión 01). Da una dirección HTTPS con
# certificado de AWS sin dominio propio, valida el token de Cognito y limita la tasa.
#   GET /callback, GET /logout → Lambda: los pasos 3 y 4 del login de la clase (cognito.tf)
#   GET /api/health            → VPC Link → ALB interno, sin token
#   GET /api/publico/{proxy+}  → el catálogo, sin token: el Visitante de la spec
#   GET|POST /api/{proxy+}     → VPC Link → ALB interno, con el access token validado

resource "aws_apigatewayv2_api" "ateneo" {
  name          = "ateneo"
  protocol_type = "HTTP"

  # El sitio vive en otro origen (S3). API Gateway contesta él mismo los preflight OPTIONS
  # cuando ninguna ruta los toma: por eso las rutas son GET y POST y no ANY, que mandaría el
  # OPTIONS al autorizador y el navegador vería un 401 sin cabeceras de CORS.
  cors_configuration {
    allow_origins = [local.url_sitio]
    allow_methods = ["GET", "POST"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/ateneo"
  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.ateneo.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 50
    throttling_burst_limit = 100
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      pedido    = "$context.requestId"
      ip        = "$context.identity.sourceIp"
      cuando    = "$context.requestTime"
      ruta      = "$context.routeKey"
      estado    = "$context.status"
      latencia  = "$context.integrationLatency"
      error     = "$context.error.message"
      autorizar = "$context.authorizer.error"
    })
  }
}

locals {
  url_api      = aws_apigatewayv2_api.ateneo.api_endpoint # https://<id>.execute-api.<región>.amazonaws.com
  url_callback = "${local.url_api}/callback"
  url_logout   = "${local.url_api}/logout"
}

# --- La API: VPC Link al ALB interno, con el token validado ---------------------------

resource "aws_apigatewayv2_vpc_link" "ateneo" {
  name               = "ateneo"
  subnet_ids         = local.sub["aplicacion"]
  security_group_ids = [local.sg["vpclink"]]
}

resource "aws_apigatewayv2_integration" "alb" {
  api_id             = aws_apigatewayv2_api.ateneo.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.ateneo.id
  integration_uri    = aws_lb_listener.api.arn

  # El camino tal cual llegó (/api/...). Con el stage $default ya es así; queda escrito.
  request_parameters = {
    "overwrite:path" = "$request.path"
  }
}

# Firma, emisor, vencimiento y cliente. Un access token de Cognito no trae aud: API Gateway
# compara la audiencia contra su client_id. Vale cualquiera de los tres clientes.
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.ateneo.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = local.cognito_emisor
    audience = [for c in aws_cognito_user_pool_client.web : c.id]
  }
}

locals {
  # ruta => ¿pide token? API Gateway elige la ruta con más segmentos literales antes que la
  # greedy, así que /api/publico/… entra sin token y todo el resto de /api/* lo sigue pidiendo.
  # El catálogo es lo único público (sección 09): el backend lo sirve bajo ese prefijo y nada
  # más cuelga de ahí.
  rutas_api = {
    "GET /api/health"           = false
    "GET /api/publico/{proxy+}" = false
    "GET /api/{proxy+}"         = true
    "POST /api/{proxy+}"        = true
  }
}

resource "aws_apigatewayv2_route" "api" {
  for_each           = local.rutas_api
  api_id             = aws_apigatewayv2_api.ateneo.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.alb.id}"
  authorization_type = each.value ? "JWT" : "NONE"
  authorizer_id      = each.value ? aws_apigatewayv2_authorizer.cognito.id : null
}

# --- Login: la Lambda del callback (el recorrido de la clase) --------------------------

data "archive_file" "callback" {
  type        = "zip"
  source_file = "${path.module}/lambda/callback.py"
  output_path = "${path.module}/.build/callback.zip"
}

resource "aws_cloudwatch_log_group" "callback" {
  name              = "/aws/lambda/ateneo-callback"
  retention_in_days = 7
}

# Sin VPC: tiene que llegar al endpoint de tokens de Cognito, que está en internet.
resource "aws_lambda_function" "callback" {
  function_name    = "ateneo-callback"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.12"
  handler          = "callback.handler"
  filename         = data.archive_file.callback.output_path
  source_code_hash = data.archive_file.callback.output_base64sha256
  timeout          = 15
  depends_on       = [aws_cloudwatch_log_group.callback]

  environment {
    variables = {
      COGNITO_DOMINIO = local.cognito_dominio
      # ingreso, institucion o publicador => cliente: el sitio pone el suyo al principio del state
      CLIENTES = jsonencode({
        for cliente, c in aws_cognito_user_pool_client.web : cliente => { id = c.id, secreto = c.client_secret }
      })
      URL_CALLBACK = local.url_callback # tiene que ser idéntica a la del pedido de /authorize
      URL_SITIO    = local.url_sitio
    }
  }
}

resource "aws_lambda_permission" "callback" {
  statement_id  = "apigateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ateneo.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "callback" {
  api_id                 = aws_apigatewayv2_api.ateneo.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.callback.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "login" {
  for_each  = toset(["GET /callback", "GET /logout"])
  api_id    = aws_apigatewayv2_api.ateneo.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.callback.id}"
}
