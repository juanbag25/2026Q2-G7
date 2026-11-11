"""Adaptador del directorio de cuentas: los grupos de cada usuario en el user pool, con boto3.

Lo usa solo la elección del tipo de cuenta (aplicacion/casos_uso/cuenta.py). Las tareas de la api
llaman como `LabRole`, igual que la Lambda de post-confirmación, que también agrega grupos, y
llegan a Cognito por el NAT de la capa de aplicación. Traduce los fallos de AWS a errores del
dominio.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from botocore.exceptions import BotoCoreError, ClientError

from ...dominio.errores import NoAutenticado, ServicioNoDisponible


@contextmanager
def _desde_cognito(que: str) -> Iterator[None]:
    try:
        yield
    except ClientError as e:
        codigo = e.response.get("Error", {}).get("Code", "")
        if codigo == "UserNotFoundException":
            raise NoAutenticado("tu cuenta ya no existe en Cognito: ingresá de nuevo") from e
        raise ServicioNoDisponible(f"Cognito no dejó {que} ({codigo or e})") from e
    except BotoCoreError as e:
        raise ServicioNoDisponible(f"Cognito no contestó al {que}: {e}") from e


class DirectorioCognito:
    def __init__(self, cognito, user_pool_id: str):
        self._cognito = cognito
        self._pool = user_pool_id

    def grupos_de(self, username: str) -> tuple[str, ...]:
        grupos: list[str] = []
        pedido = {"UserPoolId": self._pool, "Username": username, "Limit": 60}
        while True:
            with _desde_cognito("leer los grupos"):
                respuesta = self._cognito.admin_list_groups_for_user(**pedido)
            grupos += [g["GroupName"] for g in respuesta.get("Groups", [])]
            if not respuesta.get("NextToken"):
                return tuple(grupos)
            pedido["NextToken"] = respuesta["NextToken"]

    def agregar_a_grupo(self, username: str, grupo: str) -> None:
        """Cognito no se queja si ya estaba: repetirlo no cambia nada."""
        with _desde_cognito("agregar el grupo"):
            self._cognito.admin_add_user_to_group(UserPoolId=self._pool, Username=username, GroupName=grupo)
