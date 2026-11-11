"""Configuración del backend: la API y el procesador. Todo viene del entorno (la definición
de tarea de ECS en AWS, docker-compose.yml en local)."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    database_url: str                        # en AWS lo inyecta ECS desde Secrets Manager
    aws_region: str = "us-east-1"
    bucket_modelos: str
    bucket_estudios: str
    # Las tres colas. La API encola en las dos primeras; el procesador consume la tercera y
    # reenvía a la primera.
    cola_inferencias_url: str
    cola_evaluaciones_url: str | None = None
    cola_resultados_url: str | None = None
    origen_web: str | None = None            # informativo: el sitio (en AWS, el bucket web)

    web_dir: str = "/opt/ateneo/web"         # de dónde se sirve el sitio estático (solo en local)
    migraciones_dir: str = "/opt/ateneo/migraciones"
    max_bytes_estudio: int = 20 * 1024 * 1024
    max_bytes_modelo: int = 512 * 1024 * 1024

    # El reenviador del procesador.
    intervalo_reenvio_s: float = 60.0
    reenvio_minutos: int = 10                # pendiente sin tomar → se vuelve a encolar
    vencimiento_en_curso_minutos: int = 10   # inferencia en_curso sin noticias → error
    vencimiento_evaluacion_minutos: int = 120  # evaluación en_curso sin noticias → error

    # Con el pool y los clientes, cada pedido a /api/* tiene que traer un access token válido
    # de ese user pool. Sin ellos (docker compose, tests) todos son anónimos.
    cognito_user_pool_id: str | None = None  # us-east-1_XXXXXXXXX
    cognito_client_ids: str | None = None    # separados por coma: ingreso, institución y publicador

    # Solo desarrollo local: host público de MinIO para las URLs prefirmadas
    # (el backend habla con http://minio:9000 pero el navegador ve http://localhost:9000).
    s3_url_publica: str | None = None

    prefijo_modelos: str = "modelos/"
    prefijo_estudios: str = "estudios/"
    datos_demo: bool = False
    demo_reenvio_segundos: int = 900

    @model_validator(mode="after")
    def _cognito_completo(self) -> "Settings":
        if bool(self.cognito_user_pool_id) != bool(self.clientes_cognito):
            raise ValueError("Cognito: hacen falta COGNITO_USER_POOL_ID y COGNITO_CLIENT_IDS, o ninguno")
        return self

    @property
    def clientes_cognito(self) -> list[str]:
        return [c.strip() for c in (self.cognito_client_ids or "").split(",") if c.strip()]

    def exigir(self, *campos: str) -> None:
        """Lo que un proceso necesita y el otro no: la API, la cola de evaluaciones; el procesador, la de resultados."""
        faltan = [c.upper() for c in campos if not getattr(self, c)]
        if faltan:
            raise ValueError(f"faltan variables de entorno: {', '.join(faltan)}")
