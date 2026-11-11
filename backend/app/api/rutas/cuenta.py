"""El tipo de cuenta: quien se registró desde «Ingresar» queda sin grupo y lo elige acá, una vez.

Son las únicas rutas con token que no piden un rol, y a propósito: son cómo una cuenta sin rol
consigue el suyo. Por eso no usan `exigir_grupos`, y solo dan institución o publicador
(dominio/cuenta.py). API Gateway ya las cubre con `GET /api/{proxy+}` y `POST /api/{proxy+}`.
"""

from fastapi import APIRouter, Depends

from ...aplicacion.casos_uso.cuenta import ConsultarTipoCuenta, ElegirTipoCuenta
from ...dominio.usuario import Usuario
from ..dependencias import dep_consultar_tipo_cuenta, dep_elegir_tipo_cuenta, usuario_actual
from ..esquemas import ElegirTipoCuentaPeticion, ErrorRespuesta, EstadoCuentaRespuesta, TipoCuentaRespuesta

router = APIRouter(prefix="/api/cuenta", tags=["cuenta"],
                   responses={401: {"model": ErrorRespuesta}, 502: {"model": ErrorRespuesta}})


@router.get("/tipo", response_model=EstadoCuentaRespuesta)
def consultar_tipo(usuario: Usuario = Depends(usuario_actual),
                   caso: ConsultarTipoCuenta = Depends(dep_consultar_tipo_cuenta)):
    """Los grupos que tiene la cuenta en Cognito ahora, que pueden no ser los del token: el sitio lo
    pregunta antes de mostrar la elección, para no preguntar algo que ya está respondido."""
    return EstadoCuentaRespuesta.desde(caso.ejecutar(usuario))


@router.post(
    "/tipo",
    response_model=TipoCuentaRespuesta,
    responses={409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}},
)
def elegir_tipo(peticion: ElegirTipoCuentaPeticion, usuario: Usuario = Depends(usuario_actual),
                caso: ElegirTipoCuenta = Depends(dep_elegir_tipo_cuenta)):
    """200 si la cuenta quedó en ese tipo, o ya estaba. 409 si ya tiene otro, en Cognito o elegido
    antes; también sin Cognito, donde el usuario local ya puede todo. El token no cambia: para que
    traiga el grupo, el sitio vuelve a pasar por el login."""
    return TipoCuentaRespuesta.desde(caso.ejecutar(usuario, peticion.tipo))
