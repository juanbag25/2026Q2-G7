from __future__ import annotations

import logging
from uuid import UUID

from ...dominio.errores import Conflicto, NoEncontrado, ServicioNoDisponible
from ...dominio.estudio import Estudio
from ...dominio.modelo import Modelo
from ...dominio.trabajo import Trabajo
from ...dominio.usuario import Usuario
from ..puertos import (
    AlmacenEstudios, ColaInferencias, PeticionInferencia, Reloj, RepositorioEstudios,
    RepositorioModelos, RepositorioTrabajos, TrabajosSinEnviar,
)

log = logging.getLogger(__name__)


def _peticion(trabajo: Trabajo, modelo: Modelo, estudio: Estudio,
              bucket_modelos: str, bucket_estudios: str) -> PeticionInferencia:
    return PeticionInferencia(
        trabajo_id=trabajo.id,
        modelo_nombre=modelo.nombre, modelo_version=modelo.version,
        modelo_bucket=bucket_modelos, modelo_prefix=modelo.s3_prefix,
        estudio_bucket=bucket_estudios, estudio_key=estudio.s3_key,
    )


class EncolarInferencia:
    """Confirma la subida, valida compatibilidad, inserta el trabajo en `pendiente` y lo
    deja en la cola `inferencias`.

    Si la cola no contesta, el trabajo queda `pendiente` igual y el reenviador del procesador
    lo vuelve a mandar: el usuario no ve un error por una falla que se arregla sola.
    """

    def __init__(self, estudios: RepositorioEstudios, modelos: RepositorioModelos,
                 trabajos: RepositorioTrabajos, almacen: AlmacenEstudios, reloj: Reloj,
                 cola: ColaInferencias, bucket_modelos: str, bucket_estudios: str):
        self._estudios = estudios
        self._modelos = modelos
        self._trabajos = trabajos
        self._almacen = almacen
        self._reloj = reloj
        self._cola = cola
        self._bucket_modelos = bucket_modelos
        self._bucket_estudios = bucket_estudios

    def ejecutar(self, usuario: Usuario, estudio_id: UUID, modelo_id: UUID) -> Trabajo:
        estudio = self._estudios.obtener(estudio_id)
        if not usuario.es_suyo(estudio.creado_por):
            # Antes de tocar nada: ni se confirma la subida ni se crea el trabajo.
            raise NoEncontrado(f"no existe el estudio {estudio_id}")
        modelo = self._modelos.obtener(modelo_id)
        if estudio.estado != "subido":
            try:
                estudio.confirmar(self._almacen.describir(estudio.s3_key))
            except NoEncontrado:
                raise Conflicto("el archivo del estudio todavía no está en S3; subilo antes de inferir") from None
            self._estudios.guardar(estudio)
        modelo.verificar_compatible(estudio)
        trabajo = Trabajo.nuevo(estudio, modelo, self._reloj.ahora(), creado_por=usuario.sub)
        self._trabajos.guardar(trabajo)
        try:
            self._cola.enviar(_peticion(trabajo, modelo, estudio, self._bucket_modelos, self._bucket_estudios))
        except ServicioNoDisponible as e:
            log.warning("no se pudo encolar trabajo_id=%s; lo reenvía el procesador: %s", trabajo.id, e)
        log.info("trabajo encolado trabajo_id=%s modelo=%s estudio=%s", trabajo.id, modelo.nombre, estudio.id)
        return trabajo


class ConsultarTrabajo:
    """El trabajo, si es de quien pregunta. El ajeno da el mismo 404 que uno que no existe: tener
    el UUID no alcanza, y la respuesta no confirma que esté."""

    def __init__(self, trabajos: RepositorioTrabajos):
        self._trabajos = trabajos

    def ejecutar(self, usuario: Usuario, id: UUID) -> Trabajo:
        trabajo = self._trabajos.obtener(id)
        if not usuario.es_suyo(trabajo.creado_por):
            raise NoEncontrado(f"no existe el trabajo {id}")
        return trabajo


class ReenviarPendientes:
    """La red de seguridad del envío, en el procesador.

    Vuelve a mandar a la cola los trabajos que siguen `pendiente` después de `minutos`
    (el envío original falló, o el mensaje se perdió), y da por perdidos los `en_curso` que
    no tienen noticias hace `vencimiento_minutos` (el worker murió en el último intento y el
    mensaje terminó en la DLQ). Un reenvío de más no hace daño: el procesador ignora el
    resultado de un trabajo que ya terminó.
    """

    def __init__(self, sin_enviar: TrabajosSinEnviar, estudios: RepositorioEstudios,
                 modelos: RepositorioModelos, cola: ColaInferencias,
                 bucket_modelos: str, bucket_estudios: str,
                 minutos: int, vencimiento_minutos: int, limite: int = 50):
        self._sin_enviar = sin_enviar
        self._estudios = estudios
        self._modelos = modelos
        self._cola = cola
        self._bucket_modelos = bucket_modelos
        self._bucket_estudios = bucket_estudios
        self._minutos = minutos
        self._vencimiento = vencimiento_minutos
        self._limite = limite

    def ejecutar(self) -> int:
        vencidos = self._sin_enviar.vencer_en_curso(
            self._vencimiento, "el worker no respondió; el mensaje quedó en la cola de fallidos")
        if vencidos:
            log.warning("%s trabajos en_curso vencidos pasaron a error", vencidos)
        enviados = 0
        for trabajo in self._sin_enviar.tomar_para_reenviar(self._minutos, self._limite):
            try:
                modelo = self._modelos.obtener(trabajo.modelo_id)
                estudio = self._estudios.obtener(trabajo.estudio_id)
                self._cola.enviar(_peticion(trabajo, modelo, estudio, self._bucket_modelos, self._bucket_estudios))
                enviados += 1
            except ServicioNoDisponible as e:
                log.warning("reenvío fallido trabajo_id=%s: %s", trabajo.id, e)
                break                                       # la cola no contesta: probar en la próxima vuelta
        if enviados:
            log.info("reenviados %s trabajos pendientes", enviados)
        return enviados
