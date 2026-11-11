from fastapi import APIRouter, Depends, status

from ...aplicacion.casos_uso.estudios import CrearEstudio
from ...dominio.usuario import CONSULTAN, Usuario
from ..dependencias import dep_crear_estudio, exigir_grupos, usuario_actual
from ..esquemas import CrearEstudioPeticion, ErrorRespuesta, EstudioCreadoRespuesta

router = APIRouter(prefix="/api/estudios", tags=["estudios"], dependencies=[Depends(exigir_grupos(*CONSULTAN))],
                   responses={401: {"model": ErrorRespuesta}, 403: {"model": ErrorRespuesta}})


@router.post(
    "",
    response_model=EstudioCreadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorRespuesta}},
)
def crear(peticion: CrearEstudioPeticion, usuario: Usuario = Depends(usuario_actual),
          caso: CrearEstudio = Depends(dep_crear_estudio)):
    return EstudioCreadoRespuesta.desde(
        caso.ejecutar(usuario, peticion.tipo_estudio, peticion.content_type, peticion.tamano_bytes)
    )
