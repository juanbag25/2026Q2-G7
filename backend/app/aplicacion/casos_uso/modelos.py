from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ...dominio.contrato import ContratoInvalido, ContratoModelo
from ...dominio.errores import Conflicto, EntradaInvalida, ServicioNoDisponible
from ...dominio.modelo import Modelo
from ...dominio.usuario import Usuario
from ..puertos import (
    CatalogoModelosEnBucket, ColaEvaluaciones, EvaluacionesSinNoticias, PeticionEvaluacion, Reloj,
    RepositorioModelos, SubidaFirmada,
)

log = logging.getLogger(__name__)


def prefijo_de(prefijo_base: str, nombre: str, version: str) -> str:
    """modelos/<nombre>/<version>/, con los dos segmentos validados."""
    for campo, valor in (("nombre", nombre), ("version", version)):
        if not valor or "/" in valor or valor in (".", ".."):
            raise EntradaInvalida(f"{campo} inválido: '{valor}'")
    return f"{prefijo_base}{nombre}/{version}/"


@dataclass(frozen=True)
class ModeloDisponible:
    nombre: str
    version: str
    tipo_estudio: str
    publicado: bool
    modelo_id: UUID | None


class ListarModelosDisponibles:
    """Qué hay en el bucket, y cuáles de esos ya están en el catálogo."""

    def __init__(self, catalogo: CatalogoModelosEnBucket, modelos: RepositorioModelos):
        self._catalogo = catalogo
        self._modelos = modelos

    def ejecutar(self) -> list[ModeloDisponible]:
        publicados = {(m.nombre, m.version): m for m in self._modelos.listar()}
        salida: list[ModeloDisponible] = []
        for ref in self._catalogo.listar():
            existente = publicados.get((ref.nombre, ref.version))
            try:
                tipo = ContratoModelo.desde_json(self._catalogo.leer_contrato(ref.prefix)).tipo_estudio
            except ContratoInvalido as e:
                tipo = f"contrato inválido: {e}"
            salida.append(ModeloDisponible(
                nombre=ref.nombre, version=ref.version, tipo_estudio=tipo,
                publicado=existente is not None, modelo_id=existente.id if existente else None,
            ))
        return sorted(salida, key=lambda m: (m.nombre, m.version))


@dataclass(frozen=True)
class SubidaModelo:
    prefix: str
    subida: SubidaFirmada


class PrepararSubidaModelo:
    """Firma la subida del ONNX: del navegador directo al bucket, sin pasar por la API.

    Es el mismo mecanismo que usan los estudios (URL prefirmada), por la misma
    razón: un modelo pesa decenas o cientos de MB y no tiene por qué atravesar
    la capa de aplicación.
    """

    def __init__(self, catalogo: CatalogoModelosEnBucket, max_bytes: int, prefijo_modelos: str):
        self._catalogo = catalogo
        self._max_bytes = max_bytes
        self._prefijo = prefijo_modelos

    def ejecutar(self, nombre: str, version: str, tamano_bytes: int) -> SubidaModelo:
        if tamano_bytes <= 0 or tamano_bytes > self._max_bytes:
            raise EntradaInvalida(f"el modelo tiene que pesar entre 1 y {self._max_bytes} bytes")
        prefix = prefijo_de(self._prefijo, nombre, version)
        if self._catalogo.existe(prefix):
            raise Conflicto(
                f"ya hay un modelo en {prefix}: una versión publicada no se pisa, subí otra versión"
            )
        return SubidaModelo(prefix=prefix, subida=self._catalogo.firmar_subida(prefix, self._max_bytes))


class PublicarModelo:
    """Da de alta un modelo del bucket y lo deja en la cola `evaluaciones`.

    Con `contrato`, viene de la subida desde la interfaz: se valida, se confirma
    que el ONNX llegó y recién ahí se escribe el modelo.json al lado. Sin él, el
    modelo ya estaba en el bucket con su contrato (la subida a mano del operador).

    Si la cola no contesta, el modelo queda en `error` con el motivo: se puede
    volver a publicar, y nada queda esperando una evaluación que nunca llega.

    El modelo nuevo queda a nombre de `usuario` (`publicado_por`). Uno que ya existe se puede
    volver a evaluar desde cualquier cuenta que publica, pero cambiarle el contrato solo lo
    puede quien lo publicó: si no, es 403.
    """

    def __init__(self, catalogo: CatalogoModelosEnBucket, modelos: RepositorioModelos, reloj: Reloj,
                 prefijo_modelos: str, cola: ColaEvaluaciones):
        self._catalogo = catalogo
        self._modelos = modelos
        self._reloj = reloj
        self._prefijo = prefijo_modelos
        self._cola = cola

    def ejecutar(self, usuario: Usuario, nombre: str, version: str,
                 contrato_crudo: dict[str, Any] | None = None) -> Modelo:
        prefix = prefijo_de(self._prefijo, nombre, version)
        crudo = contrato_crudo if contrato_crudo is not None else self._catalogo.leer_contrato(prefix)
        try:
            contrato = ContratoModelo.desde_json(crudo)
        except ContratoInvalido as e:
            raise EntradaInvalida(f"modelo.json inválido: {e}") from e
        if (contrato.nombre, contrato.version) != (nombre, version):
            raise EntradaInvalida(
                f"modelo.json dice {contrato.nombre} v{contrato.version} pero está en el prefijo de {nombre} v{version}"
            )

        ahora = self._reloj.ahora()
        existente = self._modelos.buscar(nombre, version)
        # El alta va primero porque es la que puede dar 409: así no escribimos en
        # S3 para después rechazar el pedido. Nada se persiste hasta el guardar.
        if existente is None:
            modelo = Modelo.publicar(contrato, prefix, ahora, publicado_por=usuario.sub)
        else:
            if contrato_crudo is not None:
                existente.verificar_autor(usuario)          # SinPermiso → 403, antes de escribir en S3
            existente.republicar(contrato, ahora)
            modelo = existente

        if contrato_crudo is not None:
            # El ONNX tiene que estar antes de escribir su contrato al lado:
            # un modelo.json sin modelo.onnx haría fallar la evaluación.
            self._catalogo.describir_modelo(prefix)
            self._catalogo.escribir_contrato(prefix, contrato_crudo)

        self._modelos.guardar(modelo)
        try:
            self._cola.enviar(PeticionEvaluacion.de(modelo))
        except ServicioNoDisponible as e:
            log.warning("no se pudo encolar la evaluación de %s v%s: %s", nombre, version, e)
            modelo.no_se_pudo_encolar("no se pudo encolar la evaluación; volvé a publicar el modelo")
            self._modelos.guardar(modelo)
        return modelo


class ListarModelos:
    def __init__(self, modelos: RepositorioModelos):
        self._modelos = modelos

    def ejecutar(self) -> list[Modelo]:
        return self._modelos.listar()


class ConsultarModelo:
    def __init__(self, modelos: RepositorioModelos):
        self._modelos = modelos

    def ejecutar(self, id: UUID) -> Modelo:
        return self._modelos.obtener(id)

class VencerEvaluaciones:
    """En el procesador: un modelo `en_curso` sin noticias hace `minutos` es de un evaluador que
    murió en el último intento (el mensaje quedó en la cola de fallidos). Pasa a `error` para
    que se pueda volver a publicar."""

    def __init__(self, sin_noticias: EvaluacionesSinNoticias, minutos: int):
        self._sin_noticias = sin_noticias
        self._minutos = minutos

    def ejecutar(self) -> int:
        n = self._sin_noticias.vencer_en_curso(
            self._minutos, "el evaluador no respondió; el mensaje quedó en la cola de fallidos")
        if n:
            log.warning("%s evaluaciones en_curso vencidas pasaron a error", n)
        return n
