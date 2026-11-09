"""La junta de modelos (spec funcional F8): varios modelos sobre el mismo estudio y el informe de
consenso. Todo pide token; API Gateway ya cubre estas rutas con `/api/{proxy+}`."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from ...aplicacion.casos_uso.consultas import ConsultarConsulta, CrearConsulta
from ..dependencias import dep_consultar_consulta, dep_crear_consulta, usuario_actual
from ..esquemas import ConsultaRespuesta, CrearConsultaPeticion, ErrorRespuesta

router = APIRouter(prefix="/api/consultas", tags=["consultas"], dependencies=[Depends(usuario_actual)])


@router.post(
    "",
    response_model=ConsultaRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorRespuesta}, 409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}},
)
def crear(peticion: CrearConsultaPeticion, caso: CrearConsulta = Depends(dep_crear_consulta)):
    """De 2 a 5 modelos distintos, evaluados y del tipo del estudio: un trabajo y un mensaje por modelo."""
    return ConsultaRespuesta.desde(caso.ejecutar(peticion.estudio_id, peticion.modelo_ids))


@router.get("/{consulta_id}", response_model=ConsultaRespuesta, responses={404: {"model": ErrorRespuesta}})
def obtener(consulta_id: UUID, caso: ConsultarConsulta = Depends(dep_consultar_consulta)):
    """Cada modelo por separado y, cuando terminaron todos, el consenso ponderado."""
    return ConsultaRespuesta.desde(caso.ejecutar(consulta_id))
