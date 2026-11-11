"""Ateneo · API (servicio `api` de ECS, capa de aplicación).

`uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2`
Cada proceso arma su propio contenedor y su pool. No hay bucles de fondo: lo que corre
solo (escribir resultados, reenviar, vencer) es del procesador (procesador.py).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import dependencias, errores, sitio
from .api.rutas import consultas, cuenta, estudios, inferencias, modelos, publico, salud
from .config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s · %(message)s",
)
logging.getLogger("botocore").setLevel(logging.WARNING)
log = logging.getLogger("ateneo.api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    settings = Settings()
    contenedor = dependencias.armar(settings)
    contenedor.abrir()
    app.state.contenedor = contenedor
    log.info("api lista · inferencias=%s · evaluaciones=%s · cognito=%s",
             settings.cola_inferencias_url, settings.cola_evaluaciones_url, settings.cognito_user_pool_id or "no")
    try:
        yield
    finally:
        contenedor.cerrar()
        log.info("api detenida")


def crear_app() -> FastAPI:
    app = FastAPI(title="Ateneo", version="0.1.0", lifespan=ciclo_de_vida,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    errores.registrar(app)
    app.include_router(salud.router)
    app.include_router(publico.router)      # el catálogo, sin token (ver rutas/publico.py)
    app.include_router(modelos.router)
    app.include_router(estudios.router)
    app.include_router(inferencias.router)
    app.include_router(consultas.router)    # la junta de modelos
    app.include_router(cuenta.router)       # el tipo de cuenta: con token y sin rol
    sitio.montar(app, os.environ.get("WEB_DIR", "/opt/ateneo/web"))   # siempre al final
    return app


app = crear_app()
