from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from .contrato import ContratoModelo
from .errores import Conflicto, EntradaInvalida, SinPermiso
from .estudio import Estudio
from .usuario import Usuario

ESTADOS_EVALUACION = ("pendiente", "en_curso", "ok", "error")


@dataclass(frozen=True)
class ResultadoEvaluacion:
    """Lo que publica el evaluador: métricas agregadas, nunca resultados caso por caso."""
    metricas: dict[str, Any]
    conjunto: str
    conjunto_version: str
    manifiesto: dict[str, Any]
    evaluador_id: str
    evaluado_en: datetime

    @property
    def accuracy(self) -> float:
        return float(self.metricas["accuracy"])


@dataclass
class Modelo:
    id: UUID
    nombre: str
    version: str
    tipo_estudio: str
    tarea: str
    etiquetas: list[str]
    s3_prefix: str
    contrato: dict[str, Any]
    estado_evaluacion: str
    creado: datetime
    publicado: datetime
    accuracy: float | None = None
    metricas: dict[str, Any] | None = None
    conjunto: str | None = None
    conjunto_version: str | None = None
    manifiesto: dict[str, Any] | None = None
    evaluador_id: str | None = None
    evaluado_en: datetime | None = None
    error: str | None = None
    publicado_por: str | None = None   # el `sub` de quien lo publicó primero; republicar no lo cambia
    _campos_evaluacion: tuple[str, ...] = field(
        default=("accuracy", "metricas", "conjunto", "conjunto_version", "manifiesto",
                 "evaluador_id", "evaluado_en", "error"),
        init=False, repr=False, compare=False,
    )

    @staticmethod
    def publicar(contrato: ContratoModelo, s3_prefix: str, ahora: datetime, publicado_por: str) -> "Modelo":
        return Modelo(
            id=uuid4(),
            nombre=contrato.nombre,
            version=contrato.version,
            tipo_estudio=contrato.tipo_estudio,
            tarea=contrato.tarea,
            etiquetas=list(contrato.salida.etiquetas),
            s3_prefix=s3_prefix,
            contrato=contrato.crudo,
            estado_evaluacion="pendiente",
            creado=ahora,
            publicado=ahora,
            publicado_por=publicado_por,
        )

    def verificar_autor(self, usuario: Usuario) -> None:
        """Cambiarle el contrato a un modelo publicado es cosa de quien lo publicó (o de un admin
        de plataforma): si no, cualquier publicador podría pisarle las etiquetas a otro. Volver a
        evaluarlo sin contrato no cambia nada del modelo y no pasa por acá."""
        if not usuario.es_suyo(self.publicado_por):
            raise SinPermiso(
                f"{self.nombre} v{self.version} lo publicó otra cuenta: su contrato solo lo cambia quien lo publicó"
            )

    def republicar(self, contrato: ContratoModelo, ahora: datetime) -> None:
        """Vuelve a poner el modelo en la cola de evaluación, borrando lo anterior."""
        if self.estado_evaluacion in ("pendiente", "en_curso"):
            raise Conflicto(
                f"el modelo {self.nombre} v{self.version} ya está {self.estado_evaluacion}; esperá a que termine"
            )
        self.tipo_estudio = contrato.tipo_estudio
        self.tarea = contrato.tarea
        self.etiquetas = list(contrato.salida.etiquetas)
        self.contrato = contrato.crudo
        self.estado_evaluacion = "pendiente"
        self.publicado = ahora
        for campo in self._campos_evaluacion:
            setattr(self, campo, None)

    def no_se_pudo_encolar(self, motivo: str) -> None:
        """La cola de evaluaciones no contestó: queda en error para que se pueda volver a publicar."""
        self.estado_evaluacion = "error"
        self.error = motivo

    def verificar_compatible(self, estudio: Estudio) -> None:
        if estudio.tipo_estudio != self.tipo_estudio:
            raise EntradaInvalida(
                f"el modelo es de '{self.tipo_estudio}' y el estudio es de '{estudio.tipo_estudio}'"
            )
