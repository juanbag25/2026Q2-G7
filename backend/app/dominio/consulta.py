"""La consulta en junta (spec funcional F8): de 2 a 5 modelos distintos sobre el mismo estudio.

Cada modelo corre en su propio trabajo, con su mensaje en la cola `inferencias`, igual que una
consulta individual: worker, evaluador y colas no se enteran de que hay una junta, y los modelos
corren en paralelo en los workers que haya. El estado de la consulta y el informe de consenso no
se guardan: se calculan al leer, con los trabajos y las métricas verificadas de cada modelo. Así
el procesador sigue aplicando resultados de a uno y no hay nada que se desincronice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from .consenso import Consenso, Peso, Voto, calcular_consenso, peso_de
from .errores import Conflicto, EntradaInvalida
from .estudio import Estudio
from .modelo import Modelo
from .trabajo import Trabajo

MINIMO_MODELOS = 2
MAXIMO_MODELOS = 5
TAREAS_CON_CONSENSO = ("clasificacion",)

# en_cola → procesando → completa (todas ok) | parcial (alguna falló y alguna anduvo) | error (todas fallaron)
ESTADOS = ("en_cola", "procesando", "completa", "parcial", "error")


def estado_de(trabajos: Sequence[Trabajo]) -> str:
    estados = [t.estado for t in trabajos]
    if not all(t.terminado for t in trabajos):
        return "en_cola" if all(e == "pendiente" for e in estados) else "procesando"
    if all(e == "ok" for e in estados):
        return "completa"
    return "error" if all(e == "error" for e in estados) else "parcial"


@dataclass(frozen=True)
class InferenciaDeJunta:
    trabajo: Trabajo
    modelo: Modelo
    peso: Peso | None           # None: el modelo perdió su métrica verificada y no vota
    coincide: bool | None       # con el consenso; None mientras no hay consenso o si no votó


@dataclass(frozen=True)
class InformeConsulta:
    consulta: "Consulta"
    estado: str
    inferencias: list[InferenciaDeJunta]
    consenso: Consenso | None


@dataclass
class Consulta:
    id: UUID
    estudio_id: UUID
    creada: datetime

    @staticmethod
    def junta(estudio: Estudio, modelos: Sequence[Modelo], ahora: datetime) -> "Consulta":
        if not MINIMO_MODELOS <= len(modelos) <= MAXIMO_MODELOS:
            raise EntradaInvalida(
                f"una junta lleva de {MINIMO_MODELOS} a {MAXIMO_MODELOS} modelos; llegaron {len(modelos)}")
        if len({m.id for m in modelos}) != len(modelos):
            raise EntradaInvalida("una junta lleva modelos distintos: hay uno repetido")
        etiquetas = set(modelos[0].etiquetas)
        for m in modelos:
            m.verificar_compatible(estudio)                  # mismo tipo de estudio que la imagen
            if m.tarea not in TAREAS_CON_CONSENSO:
                raise EntradaInvalida(f"la junta no tiene consenso para la tarea '{m.tarea}'")
            if set(m.etiquetas) != etiquetas:
                raise EntradaInvalida("los modelos de una junta tienen que clasificar las mismas etiquetas")
            if m.estado_evaluacion != "ok":
                raise Conflicto(
                    f"{m.nombre} v{m.version} no tiene evaluación verificada ({m.estado_evaluacion}): "
                    "la junta pondera cada modelo con su métrica medida"
                )
        return Consulta(id=uuid4(), estudio_id=estudio.id, creada=ahora)

    def trabajos_para(self, estudio: Estudio, modelos: Sequence[Modelo], ahora: datetime) -> list[Trabajo]:
        return [Trabajo.nuevo(estudio, m, ahora, consulta_id=self.id) for m in modelos]

    def informe(self, trabajos: Sequence[Trabajo], modelos: Mapping[UUID, Modelo]) -> InformeConsulta:
        """El consenso sale cuando terminaron todas y al menos dos anduvieron (spec §4.4): mientras
        tanto cada modelo muestra lo suyo, sin un consenso que cambie con cada resultado."""
        estado = estado_de(trabajos)
        pesos = {t.id: peso_de(modelos[t.modelo_id]) for t in trabajos}
        votantes = [t for t in trabajos if t.estado == "ok" and t.resultado and pesos[t.id] is not None]
        consenso = None
        if estado in ("completa", "parcial"):
            consenso = calcular_consenso([
                Voto(pesos[t.id].valor, t.resultado["prediccion"], t.resultado["probabilidades"])  # type: ignore[union-attr,index]
                for t in votantes
            ])
        ids_votantes = {t.id for t in votantes}
        inferencias = [
            InferenciaDeJunta(
                trabajo=t, modelo=modelos[t.modelo_id], peso=pesos[t.id],
                coincide=(t.resultado["prediccion"] == consenso.prediccion)  # type: ignore[index]
                if consenso is not None and t.id in ids_votantes else None,
            )
            for t in trabajos
        ]
        # El de más peso primero; a igual peso, por nombre: el orden no cambia entre lecturas.
        inferencias.sort(key=lambda i: (-(i.peso.valor if i.peso else -1.0), i.modelo.nombre, i.modelo.version))
        return InformeConsulta(consulta=self, estado=estado, inferencias=inferencias, consenso=consenso)
