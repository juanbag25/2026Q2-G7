from __future__ import annotations

from dataclasses import dataclass

from ...dominio.estudio import Estudio
from ...dominio.usuario import Usuario
from ..puertos import AlmacenEstudios, Reloj, RepositorioEstudios, SubidaFirmada


@dataclass(frozen=True)
class EstudioCreado:
    estudio: Estudio
    subida: SubidaFirmada


class CrearEstudio:
    """Registra el estudio y devuelve la URL prefirmada para que el navegador suba directo a S3."""

    def __init__(self, estudios: RepositorioEstudios, almacen: AlmacenEstudios, reloj: Reloj,
                 max_bytes: int, prefijo: str):
        self._estudios = estudios
        self._almacen = almacen
        self._reloj = reloj
        self._max_bytes = max_bytes
        self._prefijo = prefijo

    def ejecutar(self, usuario: Usuario, tipo_estudio: str, content_type: str, tamano_bytes: int) -> EstudioCreado:
        estudio = Estudio.nuevo(tipo_estudio, content_type, tamano_bytes, self._max_bytes,
                                self._prefijo, self._reloj.ahora(), creado_por=usuario.sub)
        self._estudios.guardar(estudio)
        subida = self._almacen.firmar_subida(estudio.s3_key, content_type, self._max_bytes)
        return EstudioCreado(estudio=estudio, subida=subida)
