"""El tipo de cuenta que elige quien se registró desde «Ingresar»: institución o publicador.

Instituciones y publicadores se registran solos (spec E3 §1, «un usuario, un rol»). El
autorregistro de Cognito es de todo el user pool, y el formulario del Hosted UI no deja elegir el
rol: un atributo propio no puede ser obligatorio y se muestra como texto libre. Por eso quien se
registra desde «Ingresar» queda sin grupo y lo elige dentro de la app, una sola vez
(aplicacion/casos_uso/cuenta.py). Médicos y admins no se eligen: llegan por invitación o con la
infraestructura.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errores import EntradaInvalida
from .usuario import ADMIN_INSTITUCION, PUBLICADOR

# tipo que se elige => grupo de Cognito en el que queda. Nada más: ni médico ni admin.
GRUPO_POR_TIPO = {
    "institucion": ADMIN_INSTITUCION,
    "publicador": PUBLICADOR,
}


def grupo_del_tipo(tipo: str) -> str:
    """El grupo de un tipo que se puede elegir. EntradaInvalida (422) para cualquier otro."""
    if tipo not in GRUPO_POR_TIPO:
        raise EntradaInvalida(f"el tipo de cuenta es «institucion» o «publicador», no «{tipo}»")
    return GRUPO_POR_TIPO[tipo]


def tipo_de_los_grupos(grupos: Iterable[str]) -> str | None:
    """El tipo que corresponde a esos grupos, si tienen el de uno solo de los dos. Un médico, un
    admin o una cuenta sin grupos no tienen tipo."""
    grupos = set(grupos)
    tipos = [tipo for tipo, grupo in GRUPO_POR_TIPO.items() if grupo in grupos]
    return tipos[0] if len(tipos) == 1 else None
