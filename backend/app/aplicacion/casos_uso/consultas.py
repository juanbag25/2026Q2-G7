"""La junta de modelos (spec funcional F8): crearla y leer su informe de consenso."""

from __future__ import annotations

import logging
from uuid import UUID

from ...dominio.consulta import Consulta, InformeConsulta
from ..puertos import (
    AlmacenEstudios, ColaInferencias, Reloj, RepositorioConsultas, RepositorioEstudios, RepositorioModelos,
)
from .inferencias import estudio_subido, mandar_a_la_cola

log = logging.getLogger(__name__)


class CrearConsulta:
    """Valida la junta entera antes de tocar nada, guarda la consulta con un trabajo `pendiente`
    por modelo y deja un mensaje por trabajo en la cola `inferencias`, con el mismo mecanismo que
    una consulta individual: los modelos corren en paralelo, en los workers que haya."""

    def __init__(self, estudios: RepositorioEstudios, modelos: RepositorioModelos,
                 consultas: RepositorioConsultas, almacen: AlmacenEstudios, reloj: Reloj,
                 cola: ColaInferencias, bucket_modelos: str, bucket_estudios: str):
        self._estudios = estudios
        self._modelos = modelos
        self._consultas = consultas
        self._almacen = almacen
        self._reloj = reloj
        self._cola = cola
        self._bucket_modelos = bucket_modelos
        self._bucket_estudios = bucket_estudios

    def ejecutar(self, estudio_id: UUID, modelo_ids: list[UUID]) -> InformeConsulta:
        modelos = [self._modelos.obtener(id_) for id_ in modelo_ids]
        estudio = estudio_subido(self._estudios, self._almacen, estudio_id)
        ahora = self._reloj.ahora()
        consulta = Consulta.junta(estudio, modelos, ahora)
        trabajos = consulta.trabajos_para(estudio, modelos, ahora)
        self._consultas.guardar(consulta, trabajos)
        for trabajo, modelo in zip(trabajos, modelos):
            mandar_a_la_cola(self._cola, trabajo, modelo, estudio, self._bucket_modelos, self._bucket_estudios)
        log.info("junta encolada consulta_id=%s modelos=%s estudio=%s",
                 consulta.id, ",".join(m.nombre for m in modelos), estudio.id)
        return consulta.informe(trabajos, {m.id: m for m in modelos})


class ConsultarConsulta:
    """Los trabajos de la junta y el consenso, calculado en el momento con las métricas verificadas."""

    def __init__(self, consultas: RepositorioConsultas, modelos: RepositorioModelos):
        self._consultas = consultas
        self._modelos = modelos

    def ejecutar(self, id: UUID) -> InformeConsulta:
        consulta = self._consultas.obtener(id)
        trabajos = self._consultas.trabajos_de(id)
        modelos = {mid: self._modelos.obtener(mid) for mid in {t.modelo_id for t in trabajos}}
        return consulta.informe(trabajos, modelos)
