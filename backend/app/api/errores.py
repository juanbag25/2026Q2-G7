"""Errores del dominio → HTTP, en un solo lugar. Los routers no tienen try/except."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..dominio.errores import (
    Conflicto, EntradaInvalida, ErrorDominio, FalloDefinitivo, NoAutenticado, NoEncontrado,
    ServicioNoDisponible, SinPermiso,
)

log = logging.getLogger(__name__)

CODIGOS_HTTP: dict[type[ErrorDominio], int] = {
    NoAutenticado: 401,
    SinPermiso: 403,
    NoEncontrado: 404,
    Conflicto: 409,
    EntradaInvalida: 422,
    ServicioNoDisponible: 502,
    FalloDefinitivo: 502,
}


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(_: Request, e: ErrorDominio) -> JSONResponse:
        estado = CODIGOS_HTTP.get(type(e), 400)
        return JSONResponse(status_code=estado, content={"error": e.codigo, "detalle": e.detalle})

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, e: RequestValidationError) -> JSONResponse:
        detalles = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        return JSONResponse(status_code=422, content={"error": "entrada_invalida", "detalle": detalles})

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, e: Exception) -> JSONResponse:
        log.exception("error no manejado")
        return JSONResponse(status_code=500, content={"error": "interno", "detalle": "error interno del servidor"})
