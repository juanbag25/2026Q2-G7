from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from .errores import EntradaInvalida

MIME_PERMITIDOS = {"image/png": "png", "image/jpeg": "jpg"}
ESTADOS = ("pendiente_subida", "subido")


@dataclass(frozen=True)
class ObjetoAlmacenado:
    tamano_bytes: int
    etag: str | None


@dataclass
class Estudio:
    id: UUID
    tipo_estudio: str
    s3_key: str
    content_type: str
    tamano_bytes: int | None
    estado: str
    creado: datetime
    creado_por: str | None = None      # el `sub` de Cognito; None en las filas anteriores a la 005

    @staticmethod
    def nuevo(tipo_estudio: str, content_type: str, tamano_bytes: int, max_bytes: int,
              prefijo: str, ahora: datetime, creado_por: str) -> "Estudio":
        if not tipo_estudio or "/" in tipo_estudio:
            raise EntradaInvalida("tipo_estudio inválido")
        if content_type not in MIME_PERMITIDOS:
            raise EntradaInvalida(f"content_type '{content_type}' no permitido; opciones: {sorted(MIME_PERMITIDOS)}")
        if tamano_bytes <= 0 or tamano_bytes > max_bytes:
            raise EntradaInvalida(f"tamano_bytes tiene que estar entre 1 y {max_bytes}")
        id_ = uuid4()
        return Estudio(
            id=id_,
            tipo_estudio=tipo_estudio,
            s3_key=f"{prefijo}{id_}.{MIME_PERMITIDOS[content_type]}",
            content_type=content_type,
            tamano_bytes=tamano_bytes,
            estado="pendiente_subida",
            creado=ahora,
            creado_por=creado_por,
        )

    def confirmar(self, objeto: ObjetoAlmacenado) -> None:
        if self.tamano_bytes is not None and objeto.tamano_bytes != self.tamano_bytes:
            raise EntradaInvalida(
                f"el archivo subido pesa {objeto.tamano_bytes} bytes y se declararon {self.tamano_bytes}"
            )
        self.tamano_bytes = objeto.tamano_bytes
        self.estado = "subido"

    @property
    def nombre_archivo(self) -> str:
        return self.s3_key.rsplit("/", 1)[-1]
