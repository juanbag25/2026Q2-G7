"""Puertos: lo que la aplicación necesita del mundo exterior, sin decir cómo.

Los adaptadores en `infraestructura/` los implementan. Los tests los reemplazan
por fakes en memoria. Nadie más los importa que los casos de uso y los adaptadores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from ..dominio.consulta import Consulta
from ..dominio.estudio import Estudio, ObjetoAlmacenado
from ..dominio.modelo import Modelo, ResultadoEvaluacion
from ..dominio.trabajo import ResultadoInferencia, Trabajo
from ..dominio.usuario import Usuario


# ---- valores que cruzan los puertos -------------------------------------------------

@dataclass(frozen=True)
class SubidaFirmada:
    url: str
    campos: dict[str, str]


@dataclass(frozen=True)
class RefModeloEnBucket:
    nombre: str
    version: str
    prefix: str            # modelos/<nombre>/<version>/


@dataclass(frozen=True)
class PeticionInferencia:
    trabajo_id: UUID
    modelo_nombre: str
    modelo_version: str
    modelo_bucket: str
    modelo_prefix: str
    estudio_bucket: str
    estudio_key: str

    def como_mensaje(self) -> dict[str, Any]:
        """El cuerpo del mensaje de la cola `inferencias`: todo lo que el worker necesita."""
        return {
            "trabajo_id": str(self.trabajo_id),
            "modelo": {"nombre": self.modelo_nombre, "version": self.modelo_version,
                       "bucket": self.modelo_bucket, "prefix": self.modelo_prefix},
            "estudio": {"bucket": self.estudio_bucket, "key": self.estudio_key},
        }


@dataclass(frozen=True)
class PeticionEvaluacion:
    modelo_id: UUID
    nombre: str
    version: str
    tipo_estudio: str
    prefix: str
    etiquetas: list[str]

    @staticmethod
    def de(m: Modelo) -> "PeticionEvaluacion":
        return PeticionEvaluacion(m.id, m.nombre, m.version, m.tipo_estudio, m.s3_prefix, list(m.etiquetas))

    def como_mensaje(self) -> dict[str, Any]:
        """El cuerpo del mensaje de la cola `evaluaciones`. El evaluador no tiene base: viaja todo."""
        return {
            "tipo": "evaluar_modelo",
            "modelo_id": str(self.modelo_id),
            "nombre": self.nombre,
            "version": self.version,
            "tipo_estudio": self.tipo_estudio,
            "prefix": self.prefix,
            "etiquetas": self.etiquetas,
        }


# ---- repositorios -------------------------------------------------------------------

class RepositorioModelos(Protocol):
    def guardar(self, m: Modelo) -> None: ...
    def obtener(self, id: UUID) -> Modelo: ...                      # NoEncontrado
    def buscar(self, nombre: str, version: str) -> Modelo | None: ...
    def listar(self) -> list[Modelo]: ...


class RepositorioEstudios(Protocol):
    def guardar(self, e: Estudio) -> None: ...
    def obtener(self, id: UUID) -> Estudio: ...                     # NoEncontrado


class RepositorioTrabajos(Protocol):
    def guardar(self, t: Trabajo) -> None: ...
    def obtener(self, id: UUID) -> Trabajo: ...                     # NoEncontrado


class RepositorioConsultas(Protocol):
    """La junta. La consulta y sus trabajos se guardan juntos: no queda una junta a medias."""
    def guardar(self, c: Consulta, trabajos: list[Trabajo]) -> None: ...
    def obtener(self, id: UUID) -> Consulta: ...                    # NoEncontrado
    def trabajos_de(self, id: UUID) -> list[Trabajo]: ...


class RepositorioCuentas(Protocol):
    """El tipo que eligió cada cuenta, con el `sub` como clave: se fija una sola vez."""
    def fijar_tipo(self, sub: str, tipo: str, ahora: datetime) -> str: ...   # el que quedó: el primero que llegó


class TrabajosSinEnviar(Protocol):
    """La usa solo el reenviador del procesador."""
    def tomar_para_reenviar(self, minutos: int, limite: int) -> list[Trabajo]: ...  # pendientes viejos; toca `actualizado`
    def vencer_en_curso(self, minutos: int, motivo: str) -> int: ...                # en_curso sin noticias → error


class EvaluacionesSinNoticias(Protocol):
    """Modelos en_curso de un evaluador que murió en el último intento (el mensaje quedó en la DLQ)."""
    def vencer_en_curso(self, minutos: int, motivo: str) -> int: ...


class RegistroResultados(Protocol):
    """Lo que escribe el procesador. Cada método aplica solo si el registro sigue sin terminar
    (pendiente o en_curso), así que un mensaje repetido no cambia nada. Devuelve si aplicó."""
    def inferencia_en_curso(self, trabajo_id: UUID, worker: str, intento: int) -> bool: ...
    def inferencia_terminada(self, trabajo_id: UUID, r: ResultadoInferencia) -> bool: ...
    def inferencia_fallida(self, trabajo_id: UUID, motivo: str) -> bool: ...
    def evaluacion_en_curso(self, modelo_id: UUID, evaluador: str) -> bool: ...
    def evaluacion_terminada(self, modelo_id: UUID, r: ResultadoEvaluacion) -> bool: ...
    def evaluacion_fallida(self, modelo_id: UUID, evaluador: str, motivo: str) -> bool: ...


# ---- almacenamiento -----------------------------------------------------------------

class AlmacenEstudios(Protocol):
    def firmar_subida(self, key: str, content_type: str, max_bytes: int) -> SubidaFirmada: ...
    def describir(self, key: str) -> ObjetoAlmacenado: ...          # NoEncontrado si no se subió


class CatalogoModelosEnBucket(Protocol):
    """El bucket de modelos. Los casos de uso hablan de prefijos; qué archivos
    hay adentro de cada uno lo sabe el adaptador."""
    def listar(self) -> list[RefModeloEnBucket]: ...                # prefijos con modelo.json
    def leer_contrato(self, prefix: str) -> dict[str, Any]: ...     # NoEncontrado
    def existe(self, prefix: str) -> bool: ...                      # el prefijo ya está ocupado
    def firmar_subida(self, prefix: str, max_bytes: int) -> SubidaFirmada: ...   # el ONNX
    def describir_modelo(self, prefix: str) -> ObjetoAlmacenado: ...             # NoEncontrado
    def escribir_contrato(self, prefix: str, contrato: dict[str, Any]) -> None: ...


# ---- servicios ----------------------------------------------------------------------

class ColaInferencias(Protocol):
    """Deja el pedido para que lo tome algún worker."""
    def enviar(self, p: PeticionInferencia) -> None: ...                  # ServicioNoDisponible


class ColaEvaluaciones(Protocol):
    """Deja el pedido para el evaluador, que arranca solo si estaba apagado."""
    def enviar(self, p: PeticionEvaluacion) -> None: ...                  # ServicioNoDisponible


class Reloj(Protocol):
    def ahora(self) -> datetime: ...


class VerificadorTokens(Protocol):
    def verificar(self, token: str) -> Usuario: ...     # NoAutenticado | ServicioNoDisponible


class DirectorioCuentas(Protocol):
    """Los grupos de cada cuenta en el user pool, como están ahora: los del token son de cuando se
    emitió. `username` es el claim del access token (Usuario.username), no el `sub`."""
    def grupos_de(self, username: str) -> tuple[str, ...]: ...          # NoAutenticado | ServicioNoDisponible
    def agregar_a_grupo(self, username: str, grupo: str) -> None: ...   # idem; si ya estaba, no falla
