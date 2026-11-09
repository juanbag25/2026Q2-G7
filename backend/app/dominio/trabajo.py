from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from .estudio import Estudio
from .modelo import Modelo

ESTADOS = ("pendiente", "en_curso", "ok", "error")


@dataclass(frozen=True)
class ResultadoInferencia:
    prediccion: str
    probabilidades: dict[str, float]
    worker_id: str
    duracion_ms: int

    def como_dict(self) -> dict[str, Any]:
        return {"prediccion": self.prediccion, "probabilidades": self.probabilidades}


@dataclass
class Trabajo:
    id: UUID
    estudio_id: UUID
    modelo_id: UUID
    estado: str
    intentos: int
    creado: datetime
    actualizado: datetime
    worker_id: str | None = None
    resultado: dict[str, Any] | None = None
    duracion_ms: int | None = None
    error: str | None = None
    creado_por: str | None = None      # el `sub` de Cognito; None en las filas anteriores a la 005

    @staticmethod
    def nuevo(estudio: Estudio, modelo: Modelo, ahora: datetime, creado_por: str) -> "Trabajo":
        return Trabajo(
            id=uuid4(),
            estudio_id=estudio.id,
            modelo_id=modelo.id,
            estado="pendiente",
            intentos=0,
            creado=ahora,
            actualizado=ahora,
            creado_por=creado_por,
        )
