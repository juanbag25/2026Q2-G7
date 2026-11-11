from uuid import UUID

from fastapi import APIRouter, Depends, status

from ...aplicacion.casos_uso.inferencias import ConsultarTrabajo, EncolarInferencia
from ...dominio.usuario import CONSULTAN, Usuario
from ..dependencias import dep_consultar_trabajo, dep_encolar_inferencia, exigir_grupos, usuario_actual
from ..esquemas import EncolarInferenciaPeticion, ErrorRespuesta, TrabajoRespuesta

router = APIRouter(prefix="/api", tags=["inferencias"], dependencies=[Depends(exigir_grupos(*CONSULTAN))],
                   responses={401: {"model": ErrorRespuesta}, 403: {"model": ErrorRespuesta}})


@router.post(
    "/inferencias",
    response_model=TrabajoRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorRespuesta}, 409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}},
)
def encolar(peticion: EncolarInferenciaPeticion, usuario: Usuario = Depends(usuario_actual),
            caso: EncolarInferencia = Depends(dep_encolar_inferencia)):
    """404 también si el estudio es de otro usuario: lo ajeno no existe."""
    return TrabajoRespuesta.desde(caso.ejecutar(usuario, peticion.estudio_id, peticion.modelo_id))


@router.get("/trabajos/{trabajo_id}", response_model=TrabajoRespuesta, responses={404: {"model": ErrorRespuesta}})
def obtener(trabajo_id: UUID, usuario: Usuario = Depends(usuario_actual),
            caso: ConsultarTrabajo = Depends(dep_consultar_trabajo)):
    """404 también si el trabajo es de otro usuario: tener el UUID no alcanza."""
    return TrabajoRespuesta.desde(caso.ejecutar(usuario, trabajo_id))
