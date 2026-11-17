# Sección 07: un cluster de ECS con cuatro servicios sobre Fargate y dos imágenes.
#
#   servicio     imagen   subred       tareas   CPU · memoria   escala por                       entrada
#   api          backend  aplicación   2 a 4    0,5 · 1 GB      CPU al 60 %                      8080, solo desde el ALB
#   procesador   backend  aplicación   1 a 2    0,25 · 0,5 GB   resultados por tarea             ninguna
#   worker       ml       inferencia   1 a 4    1 · 2 GB        inferencias por tarea            ninguna
#   evaluador    ml       evaluación   0 a 1    2 · 4 GB        hay mensajes en evaluaciones     ninguna
#
# Solo api y procesador reciben DATABASE_URL (de Secrets Manager). Cuando cambia la imagen, ECS
# reemplaza las tareas de a poco y no saca una vieja hasta que la nueva está sana; si las nuevas
# no llegan a estar sanas, vuelve solo a la versión anterior.

resource "aws_ecs_cluster" "ateneo" {
  name = "ateneo"

  # Publica RunningTaskCount, que es el divisor del backlog por tarea con el que escalan worker
  # y procesador (escalado.tf). Es la única fuente de esa métrica: sin Container Insights no hay
  # por qué dividir. Se paga por métrica y por log de rendimiento, centavos en una sesión de
  # trabajo, y la regla de uso es destruir todo al terminarla.
  setting {
    name  = "containerInsights"
    value = var.container_insights ? "enabled" : "disabled"
  }
}

locals {
  colas_url = { for k, c in module.colas : "COLA_${upper(k)}_URL" => c.url }

  servicios = {
    api = {
      imagen  = "backend", cpu = 512, memoria = 1024, capa = "aplicacion", minimo = 2, maximo = 4
      comando = null, puerto = 8080, base = true
      entorno = {
        BUCKET_MODELOS       = local.buckets.modelos
        BUCKET_ESTUDIOS      = local.buckets.estudios
        ORIGEN_WEB           = local.url_sitio
        COGNITO_USER_POOL_ID = aws_cognito_user_pool.ateneo.id
        COGNITO_CLIENT_IDS   = join(",", [for c in aws_cognito_user_pool_client.web : c.id])
        WEB_DIR              = "/sin-sitio" # el sitio lo sirve S3; la api atiende solo /api
        DATOS_DEMO           = tostring(var.datos_demo)
      }
    }
    procesador = {
      imagen  = "backend", cpu = 256, memoria = 512, capa = "aplicacion", minimo = 1, maximo = 2
      comando = ["python", "-m", "app.procesador"], puerto = null, base = true
      entorno = {
        BUCKET_MODELOS  = local.buckets.modelos
        BUCKET_ESTUDIOS = local.buckets.estudios
        DATOS_DEMO      = tostring(var.datos_demo)
      }
    }
    worker = {
      imagen  = "ml", cpu = 1024, memoria = 2048, capa = "inferencia", minimo = 1, maximo = 4
      comando = null, puerto = null, base = false
      entorno = {
        MODELOS_DIR = "/mnt/modelos" # EFS
      }
    }
    evaluador = {
      imagen  = "ml", cpu = 2048, memoria = 4096, capa = "evaluacion", minimo = 0, maximo = 1
      comando = ["python", "-m", "evaluador.main"], puerto = null, base = false
      entorno = {
        BUCKET_EVALUACION = local.buckets.evaluacion
        BUCKET_MODELOS    = local.buckets.modelos
      }
    }
  }
}

resource "aws_cloudwatch_log_group" "servicio" {
  for_each          = local.servicios
  name              = "/ecs/ateneo/${each.key}"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "s" {
  for_each = local.servicios

  family                   = "ateneo-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memoria
  execution_role_arn       = data.aws_iam_role.lab.arn # baja la imagen, escribe logs, lee el secreto
  task_role_arn            = data.aws_iam_role.lab.arn # lo que usa el código: S3, SQS

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # el constructor es x86_64
  }

  dynamic "volume" {
    for_each = each.key == "worker" ? ["modelos"] : []
    content {
      name = volume.value
      efs_volume_configuration {
        file_system_id     = aws_efs_file_system.modelos.id
        transit_encryption = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name      = each.key
    image     = local.imagen[each.value.imagen]
    essential = true
    command   = each.value.comando
    environment = [
      for k, v in merge({ AWS_REGION = var.region }, local.colas_url, each.value.entorno) : { name = k, value = v }
    ]
    secrets      = each.value.base ? [{ name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn }] : null
    portMappings = each.value.puerto != null ? [{ containerPort = each.value.puerto, protocol = "tcp" }] : null
    mountPoints  = each.key == "worker" ? [{ sourceVolume = "modelos", containerPath = "/mnt/modelos", readOnly = false }] : null
    stopTimeout  = 60 # termina el mensaje que tiene entre manos antes de salir
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.servicio[each.key].name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}

resource "aws_ecs_service" "s" {
  for_each = local.servicios

  name             = each.key
  cluster          = aws_ecs_cluster.ateneo.id
  task_definition  = aws_ecs_task_definition.s[each.key].arn
  desired_count    = each.value.minimo
  launch_type      = "FARGATE"
  platform_version = "LATEST"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = each.value.puerto != null ? 60 : null

  # Una imagen que se cae al arrancar, o una api que nunca pasa el health check: sin esto, ECS
  # lanza tareas nuevas para siempre, las viejas siguen atendiendo y el apply termina en verde
  # con el servicio a medio desplegar. Con esto, tras varias tareas fallidas corta el despliegue
  # y vuelve a la definición de tarea anterior, y el evento queda en la consola del servicio.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = local.sub[each.value.capa]
    security_groups  = [local.sg[each.key]]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.value.puerto != null ? [each.value.puerto] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = each.key
      container_port   = load_balancer.value
    }
  }

  # La cantidad de tareas la maneja el escalado (escalado.tf).
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [
    terraform_data.imagenes,
    aws_lb_listener.api,
    aws_route.aplicacion_nat,
    aws_route_table_association.capa,
    module.endpoints,
    aws_efs_mount_target.modelos,
    aws_secretsmanager_secret_version.database_url,
    aws_network_acl.evaluacion,
    aws_vpc_security_group_egress_rule.r,
    aws_vpc_security_group_ingress_rule.r,
  ]
}
