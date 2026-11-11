"""Disparador de post-confirmación de Cognito: pone en su grupo a quien se registró por «crear cuenta».

Hay un cliente por puerta del sitio (cognito.tf). Los de «crear cuenta» de institución y de
publicador dan su grupo: el evento trae el cliente con el que se confirmó la cuenta, y su nombre
dice el grupo. El de «Ingresar» (ateneo-ingreso) no da ninguno: el Hosted UI muestra «Sign up» en
cualquier cliente, y quien se registra desde ahí elige el tipo una sola vez dentro de la app
(POST /api/cuenta/tipo). No hay grupo por defecto: un cliente que no está en el mapa, o ninguno,
deja la cuenta sin grupo. Corre solo al confirmar un registro, no al recuperar una contraseña.

Si algo falla, el usuario igual queda confirmado (un error acá le rompería el registro): queda
sin grupo, elige el tipo en la app, y el log lo dice.
"""

from __future__ import annotations

import json
import logging
import os

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")
GRUPO_POR_CLIENTE = json.loads(os.environ["GRUPO_POR_CLIENTE"])   # {"ateneo-institucion": "admin_institucion", …}
SIN_CLIENTE = "CLIENT_ID_NOT_APPLICABLE"   # lo que trae el evento cuando confirma un admin, no un cliente


def _grupo(pool: str, cliente_id: str | None) -> str | None:
    """El grupo del cliente por el que se registró, o None si ese cliente no da ninguno."""
    if not cliente_id or cliente_id == SIN_CLIENTE:
        return None
    nombre = cognito.describe_user_pool_client(UserPoolId=pool, ClientId=cliente_id)["UserPoolClient"]["ClientName"]
    return GRUPO_POR_CLIENTE.get(nombre)


def handler(evento: dict, _contexto) -> dict:
    if evento.get("triggerSource") != "PostConfirmation_ConfirmSignUp":
        return evento

    pool = evento["userPoolId"]
    usuario = evento["userName"]
    cliente_id = (evento.get("callerContext") or {}).get("clientId")
    try:
        grupo = _grupo(pool, cliente_id)
        if grupo is None:
            log.info("usuario %s sin grupo (cliente %s): elige el tipo en la app", usuario, cliente_id)
            return evento
        cognito.admin_add_user_to_group(UserPoolId=pool, Username=usuario, GroupName=grupo)
        log.info("usuario %s al grupo %s", usuario, grupo)
    except Exception:                                              # noqa: BLE001
        log.exception("no se pudo asignar el grupo a %s: queda sin grupo y elige el tipo en la app", usuario)
    return evento
