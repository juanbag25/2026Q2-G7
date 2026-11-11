# La arquitectura del HTML («Ateneo en AWS 2.0»), comprobada contra un AWS simulado: sin
# credenciales ni cuenta.   terraform init -backend=false && terraform test

mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/LabRole" }
  }
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = { id = "pl-63a5400a" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = {
      arn = "arn:aws:sqs:us-east-1:123456789012:ateneo-cola"
      url = "https://sqs.us-east-1.amazonaws.com/123456789012/ateneo-cola"
    }
  }
  mock_resource "aws_lb" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/ateneo-interno/0123456789abcdef"
      arn_suffix = "app/ateneo-interno/0123456789abcdef"
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/ateneo-api/0123456789abcdef" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/ateneo-interno/0123456789abcdef/0123456789abcdef" }
  }
  mock_resource "aws_s3_bucket_website_configuration" {
    defaults = { website_endpoint = "ateneo-web-prueba.s3-website-us-east-1.amazonaws.com" }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn        = "arn:aws:lambda:us-east-1:123456789012:function:ateneo"
      invoke_arn = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:ateneo/invocations"
    }
  }
  mock_resource "aws_apigatewayv2_api" {
    defaults = {
      api_endpoint  = "https://abc123.execute-api.us-east-1.amazonaws.com"
      execution_arn = "arn:aws:execute-api:us-east-1:123456789012:abc123"
    }
  }
  mock_resource "aws_cognito_user_pool" {
    defaults = {
      id       = "us-east-1_prueba"
      arn      = "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_prueba"
      endpoint = "cognito-idp.us-east-1.amazonaws.com/us-east-1_prueba"
    }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/ateneo/repo" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:ateneo-alertas" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:ateneo" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:ateneo/database-url-abc" }
  }
  mock_resource "aws_appautoscaling_policy" {
    defaults = { arn = "arn:aws:autoscaling:us-east-1:123456789012:scalingPolicy:x:resource/ecs/service/ateneo/s:policyName/p" }
  }
  mock_resource "aws_wafv2_web_acl" {
    defaults = { arn = "arn:aws:wafv2:us-east-1:123456789012:regional/webacl/ateneo/0123" }
  }
}

mock_provider "random" {}
mock_provider "archive" {}
mock_provider "external" {
  mock_data "external" {
    defaults = { result = { directorio = "/mock/paquete" } }
  }
}

variables {
  sufijo = "prueba"
  # Los dos pasos que salen de Terraform y llaman al CLI: en las pruebas no hay cuenta.
  # Esperar las imágenes le pregunta a ECR; crear los buckets los crea de verdad (s3.tf).
  esperar_imagenes = false
  crear_buckets    = false
}

run "red" {
  command = apply

  assert {
    condition     = length(aws_subnet.capa) == 11 && length(aws_route_table.capa) == 6
    error_message = "Once subredes en seis capas, una tabla de ruteo por capa."
  }
  assert {
    condition     = aws_route.aplicacion_nat.route_table_id == aws_route_table.capa["aplicacion"].id
    error_message = "Solo la capa de aplicación sale por el NAT."
  }
  assert {
    condition     = length(module.endpoints.endpoints["s3"].route_table_ids) == 3 && !contains(module.endpoints.endpoints["s3"].route_table_ids, aws_route_table.capa["datos"].id)
    error_message = "El endpoint de S3 va en aplicación, inferencia y evaluación; datos no lo necesita."
  }
  assert {
    condition = alltrue([
      for k, e in module.endpoints.endpoints : e.subnet_ids == toset([aws_subnet.capa["endpoints-a"].id, aws_subnet.capa["endpoints-b"].id])
      if k != "s3"
    ]) && length([for k, e in module.endpoints.endpoints : k if k != "s3"]) == 4
    error_message = "Cuatro endpoints de interfaz (ecr.api, ecr.dkr, logs, sqs) en sus propias subredes."
  }
  assert {
    condition     = length(aws_network_acl.evaluacion.egress) == 1 && one(aws_network_acl.evaluacion.egress).from_port == 443
    error_message = "La NACL de evaluación solo deja salir al 443."
  }
  assert {
    condition = length([
      for r in aws_vpc_security_group_ingress_rule.r : r
      if contains([for g in ["procesador", "worker", "evaluador", "constructor"] : aws_security_group.g[g].id], r.security_group_id)
    ]) == 0
    error_message = "procesador, worker, evaluador y constructor no tienen reglas de entrada."
  }
  assert {
    condition = toset([
      for r in aws_vpc_security_group_ingress_rule.r : r.referenced_security_group_id if r.security_group_id == aws_security_group.g["db"].id
    ]) == toset([aws_security_group.g["api"].id, aws_security_group.g["procesador"].id])
    error_message = "A la base llegan solo api y procesador."
  }
}

run "computo" {
  command = apply

  assert {
    condition     = length(aws_ecs_service.s) == 4 && aws_lb.interno.internal
    error_message = "Cuatro servicios de Fargate detrás de un ALB interno."
  }
  assert {
    condition = alltrue([for s in ["api", "procesador"] : strcontains(aws_ecs_task_definition.s[s].container_definitions, "DATABASE_URL")]) && !anytrue([
      for s in ["worker", "evaluador"] : strcontains(aws_ecs_task_definition.s[s].container_definitions, "DATABASE_URL")
    ])
    error_message = "Solo api y procesador reciben la base; las capas que corren modelos de terceros no tienen secretos."
  }
  assert {
    condition     = length(aws_ecs_task_definition.s["worker"].volume) == 1 && strcontains(aws_ecs_task_definition.s["worker"].container_definitions, "/mnt/modelos")
    error_message = "El worker monta EFS como caché de modelos."
  }
  assert {
    condition     = aws_appautoscaling_target.s["evaluador"].min_capacity == 0 && aws_appautoscaling_target.s["evaluador"].max_capacity == 1
    error_message = "El evaluador pasa de 0 a 1 tarea según su cola."
  }
  assert {
    condition     = one(aws_ecs_cluster.ateneo.setting).name == "containerInsights" && one(aws_ecs_cluster.ateneo.setting).value == "enabled"
    error_message = "Container Insights publica RunningTaskCount, el divisor del backlog por tarea."
  }
  assert {
    condition     = keys(aws_appautoscaling_policy.backlog) == ["procesador", "worker"]
    error_message = "worker y procesador escalan por backlog por tarea."
  }
  assert {
    condition = alltrue([
      for p in aws_appautoscaling_policy.backlog :
      one([for m in p.target_tracking_scaling_policy_configuration[0].customized_metric_specification[0].metrics : m if m.return_data]).expression == "esperando / tareas"
    ])
    error_message = "El backlog por tarea es mensajes esperando ÷ tareas corriendo."
  }
  assert {
    condition     = keys(aws_appautoscaling_policy.crecer) == ["evaluador"] && aws_appautoscaling_policy.crecer["evaluador"].step_scaling_policy_configuration[0].adjustment_type == "ExactCapacity"
    error_message = "Solo el evaluador escala por escalones: target tracking no arranca de cero tareas."
  }
  assert {
    condition     = strcontains(aws_ecs_task_definition.s["api"].container_definitions, ":${output.version_codigo}")
    error_message = "Las imágenes llevan el hash del código como etiqueta."
  }
  assert {
    condition     = [for k in ["inferencias", "evaluaciones", "resultados"] : jsondecode(module.colas[k].redrive_policy).maxReceiveCount] == [3, 2, 5]
    error_message = "Tres colas, cada una con su cola de fallidos: 3, 2 y 5 intentos."
  }
  assert {
    condition     = length(aws_wafv2_web_acl_association.alb) == 1
    error_message = "WAF asociado al ALB."
  }
}

run "login_de_la_clase" {
  command = apply

  assert {
    condition = alltrue([
      for c in aws_cognito_user_pool_client.web : contains(c.callback_urls, "https://abc123.execute-api.us-east-1.amazonaws.com/callback")
    ])
    error_message = "Cognito vuelve al /callback de API Gateway (HTTPS), no al sitio."
  }
  assert {
    condition     = aws_lambda_function.callback.environment[0].variables.URL_SITIO == "http://ateneo-web-prueba.s3-website-us-east-1.amazonaws.com"
    error_message = "La Lambda del callback redirige al sitio en S3."
  }
  assert {
    condition     = jsondecode(aws_s3_object.config_web.content).cognito.callback == aws_lambda_function.callback.environment[0].variables.URL_CALLBACK
    error_message = "El sitio y la Lambda usan el mismo redirect_uri, o Cognito rechaza el canje."
  }
  assert {
    condition     = keys(jsondecode(aws_s3_object.config_web.content).cognito.clientes) == ["ingreso", "institucion", "publicador"]
    error_message = "Un cliente por puerta del sitio: «Ingresar» y crear cuenta de institución o de publicador."
  }
  assert {
    condition     = length(aws_cognito_user_group.g) == 4 && aws_cognito_user_pool.ateneo.lambda_config[0].post_confirmation == aws_lambda_function.post_confirmacion.arn
    error_message = "Cuatro grupos y la Lambda de post-confirmación que asigna el grupo."
  }
  # Quien se registra desde «Ingresar» elige el tipo en la app: si este mapa nombrara a
  # ateneo-ingreso, o volviera un grupo por defecto, un médico terminaría de publicador.
  assert {
    condition     = jsondecode(aws_lambda_function.post_confirmacion.environment[0].variables.GRUPO_POR_CLIENTE) == { "ateneo-institucion" = "admin_institucion", "ateneo-publicador" = "publicador" }
    error_message = "Solo los dos clientes de crear cuenta dan grupo al registrarse; ateneo-ingreso no da ninguno."
  }
  assert {
    condition     = length(aws_lambda_function.post_confirmacion.environment[0].variables) == 1
    error_message = "La Lambda de post-confirmación no tiene grupo por defecto: solo recibe GRUPO_POR_CLIENTE."
  }
  assert {
    condition     = length(aws_apigatewayv2_authorizer.cognito.jwt_configuration[0].audience) == 3
    error_message = "API Gateway acepta los tokens de los tres clientes."
  }
  assert {
    condition = alltrue([
      for ruta, tipo in {
        "GET /api/health"           = "NONE"
        "GET /api/publico/{proxy+}" = "NONE"
        "GET /api/{proxy+}"         = "JWT"
        "POST /api/{proxy+}"        = "JWT"
      } : aws_apigatewayv2_route.api[ruta].authorization_type == tipo
    ]) && length(aws_apigatewayv2_route.api) == 4
    error_message = "La API pide token salvo /api/health y el catálogo de /api/publico/."
  }
  assert {
    condition     = aws_apigatewayv2_integration.alb.connection_type == "VPC_LINK"
    error_message = "API Gateway llega al ALB interno por el VPC Link."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.b["web"].block_public_policy == false && alltrue([for k in ["modelos", "estudios", "evaluacion", "artefactos"] : aws_s3_bucket_public_access_block.b[k].block_public_policy])
    error_message = "Solo el bucket web (el sitio) es público."
  }
  assert {
    condition = length(aws_s3_bucket_server_side_encryption_configuration.b) == 5 && alltrue([
      for c in aws_s3_bucket_server_side_encryption_configuration.b :
      one(one(c.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    ])
    error_message = "Los cinco buckets declaran el cifrado en reposo, no lo heredan del valor por defecto."
  }
  # Los buckets los crea el CLI, no `aws_s3_bucket` (ver s3.tf), así que los ARN de las políticas
  # se arman con el nombre en lugar de leerse del recurso. Si eso se rompe, se rompe en silencio:
  # la política se aplicaría a otro bucket, o a ninguno.
  assert {
    condition = alltrue([
      for clave, nombre in output.buckets :
      strcontains(aws_s3_bucket_policy.b[clave].policy, "\"arn:aws:s3:::${nombre}/*\"")
    ])
    error_message = "Cada política apunta al ARN de su propio bucket."
  }
  assert {
    condition     = keys(aws_s3_bucket_public_access_block.b) == ["artefactos", "estudios", "evaluacion", "modelos", "web"]
    error_message = "Las configuraciones de bucket cubren los cinco buckets."
  }
}

run "sin_waf_con_admin" {
  command = apply
  variables {
    waf_activo  = false
    email_admin = "admin@ejemplo.com"
  }

  assert {
    condition     = length(aws_wafv2_web_acl.alb) == 0 && length(aws_wafv2_web_acl_association.alb) == 0
    error_message = "waf_activo = false apaga el WAF."
  }
  assert {
    condition     = length(aws_cognito_user_in_group.admin) == 1 && aws_cognito_user_in_group.admin[0].group_name == "admin_plataforma"
    error_message = "El admin inicial se crea con Terraform, en admin_plataforma."
  }
}

# El repliegue de la sección 12: si el lab no permite Container Insights, no hay divisor y los
# tres servicios de cola vuelven a escalones sobre los mensajes visibles.
run "sin_container_insights" {
  command = apply
  variables {
    container_insights = false
  }

  assert {
    condition     = one(aws_ecs_cluster.ateneo.setting).value == "disabled" && length(aws_appautoscaling_policy.backlog) == 0
    error_message = "container_insights = false apaga Container Insights y el backlog por tarea."
  }
  assert {
    condition     = keys(aws_appautoscaling_policy.crecer) == ["evaluador", "procesador", "worker"]
    error_message = "Sin divisor, los tres servicios de cola escalan por escalones."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.cola_con_trabajo["worker"].threshold == 10
    error_message = "El umbral del worker sigue siendo mensajes_por_worker."
  }
}
