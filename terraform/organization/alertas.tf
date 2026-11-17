# Observabilidad (sección 10): un tema de SNS con la suscripción por email del admin, y alarmas
# que avisan cuando hay mensajes en cualquier cola de fallidos, el ALB devuelve errores 5xx o el
# WAF corta a alguien por pedir de más. Los avisos a los usuarios quedan en la app; SNS es para
# operación (decisión 10).

resource "aws_sns_topic" "alertas" {
  name = "ateneo-alertas"
}

resource "aws_sns_topic_subscription" "mail" {
  count     = var.email_alertas != "" ? 1 : 0
  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = var.email_alertas # AWS manda un mail de confirmación: hay que aceptarlo una vez
}

resource "aws_cloudwatch_metric_alarm" "fallidos" {
  for_each = local.colas

  alarm_name          = "ateneo-${each.key}-con-fallidos"
  alarm_description   = "Hay mensajes de ${each.key} que agotaron sus intentos y quedaron en ${module.colas[each.key].nombre_fallidos}."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = module.colas[each.key].nombre_fallidos }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}

# Un tope por tasa del WAF bloqueó pedidos en el último minuto (balanceador.tf): alguien pasó el
# tope por cuenta o, en las rutas sin token, el tope por IP. Una alarma por regla, para que el
# mail diga cuál. Sin bloqueos el WAF no publica el dato, y eso es «sin problema».
resource "aws_cloudwatch_metric_alarm" "waf_tasa" {
  for_each = var.waf_activo ? local.reglas_tasa : {}

  alarm_name          = "ateneo-waf-${each.key}"
  alarm_description   = "El WAF contestó 429 a pedidos que pasaron el tope ${each.key} (${each.value} por minuto)."
  namespace           = "AWS/WAFV2"
  metric_name         = "BlockedRequests"
  dimensions          = { WebACL = aws_wafv2_web_acl.alb[0].visibility_config[0].metric_name, Rule = each.key, Region = var.region }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}

# 5xx de la api (Target) y del propio ALB (sin tareas sanas, por ejemplo), en cinco minutos.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "ateneo-alb-5xx"
  alarm_description   = "El ALB interno devolvió errores 5xx."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]

  metric_query {
    id = "api"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.interno.arn_suffix }
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id = "alb"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_ELB_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.interno.arn_suffix }
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "total"
    expression  = "FILL(api, 0) + FILL(alb, 0)"
    label       = "5xx"
    return_data = true
  }
}
