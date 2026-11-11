"""El tipo de cuenta: quien se registró desde «Ingresar» elige, una sola vez, si su cuenta es de una
institución o de un publicador (dominio/cuenta.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ...dominio.cuenta import GRUPO_POR_TIPO, grupo_del_tipo
from ...dominio.errores import Conflicto, NoAutenticado
from ...dominio.usuario import Usuario, describir_grupos
from ..puertos import DirectorioCuentas, Reloj, RepositorioCuentas

log = logging.getLogger(__name__)

UNA_SOLA_VEZ = "el tipo se elige una sola vez"


@dataclass(frozen=True)
class TipoElegido:
    tipo: str      # institucion | publicador
    grupo: str     # el grupo de Cognito en el que quedó: admin_institucion | publicador


class ElegirTipoCuenta:
    """POST /api/cuenta/tipo. Contra las carreras (dos pestañas, dos clics), no decide con los grupos
    del token, que se emitió antes de elegir:

    1. Lee los grupos reales en Cognito. Si ya tiene el de ese tipo, no hay nada que hacer; si tiene
       otro, 409.
    2. Fija la elección en la base, con el `sub` como clave: de dos pedidos a la vez, uno inserta y
       el otro relee lo que quedó. Si es otro tipo, 409.
    3. Recién entonces agrega el grupo en Cognito: el de la elección guardada, aunque conteste 409.
       Si eso falla a mitad de camino, el próximo pedido lo completa, y después de un 409 el login
       siempre trae un grupo.

    El token del navegador no cambia: el sitio vuelve a pasar por el login para traer uno con el
    grupo. Sin Cognito (docker compose) no hay directorio: el usuario anónimo ya tiene todos los
    roles, y elegir un tipo da 409.
    """

    def __init__(self, cuentas: RepositorioCuentas, directorio: DirectorioCuentas | None, reloj: Reloj):
        self._cuentas = cuentas
        self._directorio = directorio
        self._reloj = reloj

    def ejecutar(self, usuario: Usuario, tipo: str) -> TipoElegido:
        grupo = grupo_del_tipo(tipo)                                   # 422: ni médico ni admin
        if self._directorio is None:
            raise Conflicto("sin Cognito no hay tipo de cuenta que elegir: el usuario local ya tiene todos los roles")
        if not usuario.username:
            raise NoAutenticado("el token no dice qué usuario de Cognito sos: ingresá de nuevo")

        actuales = self._directorio.grupos_de(usuario.username)
        if actuales:
            if set(actuales) == {grupo}:
                return TipoElegido(tipo, grupo)                        # ya estaba: repetirla no cambia nada
            raise Conflicto(f"tu cuenta ya es de {describir_grupos(actuales)}: {UNA_SOLA_VEZ}")

        guardado = self._cuentas.fijar_tipo(usuario.sub, tipo, self._reloj.ahora())
        self._directorio.agregar_a_grupo(usuario.username, GRUPO_POR_TIPO[guardado])
        if guardado != tipo:
            log.info("cuenta %s: pidió %s, ya había elegido %s", usuario.sub, tipo, guardado)
            raise Conflicto(f"tu cuenta ya se eligió como {describir_grupos([GRUPO_POR_TIPO[guardado]])}: {UNA_SOLA_VEZ}")
        log.info("cuenta %s: eligió %s, grupo %s", usuario.sub, tipo, grupo)
        return TipoElegido(tipo, grupo)
