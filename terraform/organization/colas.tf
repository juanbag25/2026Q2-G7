# Sección 08 y decisión 03: una cola por tipo de trabajo, cada una con su cola de fallidos. El par
# lo arma el módulo ../modules/cola, que es lo que garantiza que no haya cola sin su DLQ.
#
#   cola          publica              consume      invisible mientras se procesa   a fallidos tras
#   inferencias   api, procesador      worker       2 min                           3 intentos
#   evaluaciones  api, procesador*     evaluador    30 min, extendible             2 intentos
#   resultados    worker, evaluador    procesador   1 min                           5 intentos
#
#   * el procesador solo con datos_demo = true: encola la evaluación del modelo de demostración.

locals {
  colas = {
    inferencias  = { visibilidad = 120, intentos = 3, retencion = 86400 }
    evaluaciones = { visibilidad = 1800, intentos = 2, retencion = 345600 }
    resultados   = { visibilidad = 60, intentos = 5, retencion = 345600 }
  }
}

module "colas" {
  source   = "../modules/cola"
  for_each = local.colas

  nombre      = each.key
  visibilidad = each.value.visibilidad
  intentos    = each.value.intentos
  retencion   = each.value.retencion
}
