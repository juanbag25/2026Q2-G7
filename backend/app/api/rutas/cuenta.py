"""El tipo de cuenta: quien se registró desde «Ingresar» queda sin grupo y lo elige acá, una vez.

Es la única ruta con token que no pide un rol, y a propósito: es cómo una cuenta sin rol consigue
el suyo. Por eso no usa `exigir_grupos`, y solo da institución o publicador (dominio/cuenta.py).
API Gateway ya la cubre con `POST /api/{proxy+}`.
"""

from fastapi import APIRouter, Depends

from ...aplicacion.casos_uso.cuenta import ElegirTipoCuenta
from ...dominio.usuario import Usuario
from ..dependencias import dep_elegir_tipo_cuenta, usuario_actual
from ..esquemas import ElegirTipoCuentaPeticion, ErrorRespuesta, TipoCuentaRespuesta

router = APIRouter(prefix="/api/cuenta", tags=["cuenta"], responses={401: {"model": ErrorRespuesta}})


@router.post(
    "/tipo",
    response_model=TipoCuentaRespuesta,
    responses={409: {"model": ErrorRespuesta}, 422: {"model": ErrorRespuesta}, 502: {"model": ErrorRespuesta}},
)
def elegir_tipo(peticion: ElegirTipoCuentaPeticion, usuario: Usuario = Depends(usuario_actual),
                caso: ElegirTipoCuenta = Depends(dep_elegir_tipo_cuenta)):
    """200 si la cuenta quedó en ese tipo, o ya estaba. 409 si ya tiene otro, en Cognito o elegido
    antes; también sin Cognito, donde el usuario local ya puede todo. El token no cambia: para que
    traiga el grupo, el sitio vuelve a pasar por el login."""
    return TipoCuentaRespuesta.desde(caso.ejecutar(usuario, peticion.tipo))
