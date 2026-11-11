"""El informe de consenso de una junta, para clasificación (spec funcional §6.5).

Funciones puras: sin IO, sin reloj. Reciben lo que opinó cada modelo y cuánto pesa su opinión.

- **Peso** de cada modelo = su métrica verificada por Ateneo contra el conjunto reservado: el AUC
  si el evaluador lo midió (binaria), si no la accuracy (multiclase). Nunca un número del
  publicador.
- **Consenso** = el promedio de las probabilidades ponderado por esos pesos; la etiqueta es la de
  mayor probabilidad promedio.
- **Acuerdo** = la parte del peso total que suman los modelos cuya predicción coincide con el
  consenso.
- **Revisión prioritaria** cuando el acuerdo es menor a 0,70. Que varios modelos coincidan da
  confianza; que no coincidan es una alerta útil, no un ruido a esconder.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .modelo import Modelo

UMBRAL_ACUERDO = 0.70
MINIMO_VOTOS = 2


@dataclass(frozen=True)
class Peso:
    metrica: str        # "auc" | "accuracy"
    valor: float


def _numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return None
    return float(valor)


def peso_de(modelo: Modelo) -> Peso | None:
    """None si el modelo no tiene evaluación verificada (p. ej., lo están volviendo a evaluar):
    su resultado se muestra, pero no pesa en el consenso."""
    if modelo.estado_evaluacion != "ok":
        return None
    metricas = modelo.metricas or {}
    auc = _numero(metricas.get("auc"))
    if auc is not None:
        return Peso("auc", auc)
    accuracy = _numero(modelo.accuracy if modelo.accuracy is not None else metricas.get("accuracy"))
    return Peso("accuracy", accuracy) if accuracy is not None else None


@dataclass(frozen=True)
class Voto:
    peso: float
    prediccion: str
    probabilidades: Mapping[str, float]


@dataclass(frozen=True)
class Consenso:
    prediccion: str
    probabilidades: dict[str, float]
    acuerdo: float      # 0..1
    votos: int

    @property
    def revision_prioritaria(self) -> bool:
        return self.acuerdo < UMBRAL_ACUERDO


def calcular_consenso(votos: Sequence[Voto]) -> Consenso | None:
    """None con menos de dos votos: con un solo modelo no hay junta que consensuar."""
    if len(votos) < MINIMO_VOTOS:
        return None
    pesos = [max(v.peso, 0.0) for v in votos]
    total = sum(pesos)
    if total <= 0:                       # ningún modelo pesa: todos valen lo mismo
        pesos, total = [1.0] * len(votos), float(len(votos))

    etiquetas: list[str] = []            # en el orden del contrato del primer modelo
    for v in votos:
        etiquetas += [e for e in v.probabilidades if e not in etiquetas]
    probabilidades = {
        e: sum(p * float(v.probabilidades.get(e, 0.0)) for p, v in zip(pesos, votos)) / total
        for e in etiquetas
    }
    prediccion = max(etiquetas, key=probabilidades.__getitem__)    # empate: la primera
    acuerdo = sum(p for p, v in zip(pesos, votos) if v.prediccion == prediccion) / total
    return Consenso(prediccion=prediccion, probabilidades=probabilidades, acuerdo=acuerdo, votos=len(votos))
