# Decisión 01 y 12: el ALB interno reparte entre las tareas de la api y les hace health check.
# Sin IP pública: solo lo alcanza el VPC Link de API Gateway. El WAF va acá porque no se puede
# asociar a una HTTP API, y por el ALB pasa todo lo que entra.

resource "aws_lb" "interno" {
  name               = "ateneo-interno"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [local.sg["alb"]]
  subnets            = local.sub["aplicacion"]

  # Un encabezado HTTP malformado se tira acá en vez de llegar a la api. Es gratis y cierra la
  # clase de ataques que mete dos encabezados y se aprovecha de que el proxy y el servidor no
  # interpreten igual cuál vale.
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  name                 = "ateneo-api"
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip" # Fargate: cada tarea tiene su propia interfaz
  vpc_id               = aws_vpc.ateneo.id
  deregistration_delay = 30

  # Cada 10 s, y con 2 respuestas buenas seguidas la tarea recibe tráfico: unos 20 s. Con los
  # valores por defecto (cada 30 s, 5 buenas) eran dos minutos y medio, y como ECS no saca una
  # tarea vieja hasta que la nueva está sana (ecs.tf), cada despliegue de la api los esperaba.
  # Con 3 malas seguidas (30 s) la saca. /health no toca la base (backend/app/api/rutas/salud.py),
  # así que preguntar más seguido no le cuesta nada a la api.
  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.interno.arn
  port              = 80
  protocol          = "HTTP" # tramo dentro de la VPC entre grupos encadenados (riesgo 09)

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# --- WAF ------------------------------------------------------------------------------
#
# Dos clases de reglas. Las dos por tasa van primero y cuentan cuántos pedidos manda cada
# cliente: el límite de API Gateway es uno solo para todos, así que sin ellas uno que martilla le
# saca el lugar a los demás y llena la api. Las administradas de AWS miran el contenido.
#
# El WAF está detrás de API Gateway: cuando bloquea, el pedido ya gastó su lugar en el límite de
# API Gateway. Por eso ese límite queda por encima de lo que atiende la api (variables.tf). El WAF
# cuida a la api de un cliente solo; contra muchos a la vez hace falta CloudFront con WAF delante
# de todo, que el laboratorio no concede.

locals {
  # Las reglas administradas de AWS: inyección SQL, entradas maliciosas conocidas y lo común.
  reglas_waf = ["AWSManagedRulesCommonRuleSet", "AWSManagedRulesKnownBadInputsRuleSet", "AWSManagedRulesSQLiRuleSet"]

  # Las dos por tasa, nombre => tope por minuto. El nombre es también su métrica en CloudWatch,
  # la que miran las alarmas (alertas.tf).
  reglas_tasa = {
    "por-cuenta" = var.waf_pedidos_por_cuenta
    "por-ip"     = var.waf_pedidos_por_ip
  }

  # La IP del cliente. El ALB ve la del VPC Link, y el Forwarded que agrega la HTTP API
  # (for=…;host=…;proto=…) el WAF no lo sabe leer: este lo escribe API Gateway (api.tf).
  encabezado_ip = "x-ip-cliente"
}

resource "aws_wafv2_web_acl" "alb" {
  count = var.waf_activo ? 1 : 0
  name  = "ateneo"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # El 429 de los topes lleva el formato de error del backend, así el sitio muestra el detalle
  # en vez de un código (frontend/src/api/cliente.ts).
  custom_response_body {
    key          = "demasiados-pedidos"
    content_type = "APPLICATION_JSON"
    content = jsonencode({
      error   = "demasiados_pedidos"
      detalle = "Llegaron demasiados pedidos tuyos en el último minuto. Esperá un momento y volvé a intentar."
    })
  }

  # Por token: cada valor distinto de Authorization es un cliente, y en la práctica una sesión de
  # una cuenta. API Gateway lo reenvía tal cual (la api lo vuelve a validar) y en las rutas con
  # token ya comprobó la firma: no se puede inventar uno. Minúsculas y espacios comprimidos,
  # porque «Bearer x» y «bearer  x» son el mismo token para la api y tienen que ser la misma
  # cuenta acá. Un pedido sin el encabezado no tiene clave y esta regla no lo cuenta.
  rule {
    name     = "por-cuenta"
    priority = 0

    action {
      block {
        custom_response {
          response_code            = 429
          custom_response_body_key = "demasiados-pedidos"
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = local.reglas_tasa["por-cuenta"]
        evaluation_window_sec = 60
        aggregate_key_type    = "CUSTOM_KEYS"

        custom_key {
          header {
            name = "authorization"
            text_transformation {
              priority = 0
              type     = "COMPRESS_WHITE_SPACE"
            }
            text_transformation {
              priority = 1
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "por-cuenta"
      sampled_requests_enabled   = true
    }
  }

  # Por IP, solo en las dos rutas sin token. Cuenta por la ruta y no por la falta de
  # Authorization: si no, alguien que manda un token inventado distinto en cada pedido no cae en
  # ninguna de las dos. La ruta se decodifica y normaliza antes de comparar, para que
  # /api/%70ublico/ o /api//publico/ no se escapen. Si el encabezado no llega, el WAF no aplica la
  # regla (no corta a nadie); si llega con algo que no es una IP, no lo cuenta.
  rule {
    name     = "por-ip"
    priority = 1

    action {
      block {
        custom_response {
          response_code            = 429
          custom_response_body_key = "demasiados-pedidos"
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = local.reglas_tasa["por-ip"]
        evaluation_window_sec = 60
        aggregate_key_type    = "FORWARDED_IP"

        forwarded_ip_config {
          header_name       = local.encabezado_ip
          fallback_behavior = "NO_MATCH"
        }

        scope_down_statement {
          regex_match_statement {
            regex_string = "^/api/(publico/|health$)"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "URL_DECODE"
            }
            text_transformation {
              priority = 1
              type     = "NORMALIZE_PATH"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "por-ip"
      sampled_requests_enabled   = true
    }
  }

  dynamic "rule" {
    for_each = local.reglas_waf
    content {
      name     = rule.value
      priority = length(local.reglas_tasa) + rule.key # después de las dos por tasa

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          name        = rule.value
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = rule.value
        sampled_requests_enabled   = true
      }
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "ateneo"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "alb" {
  count        = var.waf_activo ? 1 : 0
  resource_arn = aws_lb.interno.arn
  web_acl_arn  = aws_wafv2_web_acl.alb[0].arn
}
