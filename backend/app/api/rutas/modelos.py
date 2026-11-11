"""Lo del publicador: qué hay en el bucket, firmar la subida y publicar. Todo pide token y una
cuenta de publicador (o de admin de plataforma).

El catálogo —la lista de publicados y la ficha de cada uno— no está acá: es público y vive en
rutas/publico.py, bajo el único prefijo que el autorizador de API Gateway exime.
"""

from fastapi import APIRouter, Depends, status

from ...aplicacion.casos_uso.modelos import (
    ListarModelosDisponibles, PrepararSubidaModelo, PublicarModelo,
)
from ...dominio.usuario import PUBLICAN, Usuario
from ..dependencias import (
    dep_listar_disponibles, dep_preparar_subida, dep_publicar_modelo, exigir_grupos, usuario_actual,
)
from ..esquemas import (
    ErrorRespuesta, ModeloDisponibleRespuesta, ModeloRespuesta, PrepararSubidaModeloPeticion,
    PublicarModeloPeticion, SubidaModeloRespuesta,
)

router = APIRouter(prefix="/api/modelos", tags=["modelos"], dependencies=[Depends(exigir_grupos(*PUBLICAN))],
                   responses={401: {"model": ErrorRespuesta}, 403: {"model": ErrorRespuesta}})


@router.get("/disponibles", response_model=list[ModeloDisponibleRespuesta])
def disponibles(caso: ListarModelosDisponibles = Depends(dep_listar_disponibles)):
    return [ModeloDisponibleRespuesta.desde(m) for m in caso.ejecutar()]


@router.post(
    "/subidas",
    response_model=SubidaModeloRespuesta,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}},
)
def preparar_subida(peticion: PrepararSubidaModeloPeticion,
                    caso: PrepararSubidaModelo = Depends(dep_preparar_subida)):
    """Firma la subida del ONNX. El navegador lo manda directo al bucket."""
    return SubidaModeloRespuesta.desde(caso.ejecutar(peticion.nombre, peticion.version, peticion.tamano_bytes))


@router.post(
    "/publicar",
    response_model=ModeloRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorRespuesta}, 409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}},
)
def publicar(peticion: PublicarModeloPeticion, usuario: Usuario = Depends(usuario_actual),
             caso: PublicarModelo = Depends(dep_publicar_modelo)):
    """403 también si trae contrato para un modelo que publicó otra cuenta."""
    return ModeloRespuesta.desde(caso.ejecutar(usuario, peticion.nombre, peticion.version, peticion.contrato))
