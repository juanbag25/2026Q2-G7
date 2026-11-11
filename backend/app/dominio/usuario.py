"""Quién hace el pedido. La API lo arma desde el access token de Cognito.

Un grupo de Cognito por rol (terraform/organization/cognito.tf). Quien se registra por «crear
cuenta» queda en el de su tipo (lo pone la Lambda de post-confirmación); quien se registra desde
«Ingresar», sin grupo hasta que elige el tipo dentro de la app (dominio/cuenta.py). La API aplica
la versión mínima de la matriz de la spec (E3 §2), en dos lugares:

- **El rol**, ruta por ruta (api/dependencias.py, `exigir_grupos`): los que publican modelos y los
  que consultan estudios. Con el rol equivocado, 403.
- **La autoría**, en los casos de uso: cada estudio y cada trabajo guarda el `sub` de quien lo
  creó, y un usuario solo ve lo suyo. Lo ajeno se contesta como si no existiera (404). El admin
  de plataforma ve todo.

Lo que falta de la matriz (organizaciones, que el admin de institución vea lo de sus médicos,
cuentas pendientes de aprobación) está en architecture.md §13.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .errores import SinPermiso

MEDICO = "medico"
ADMIN_INSTITUCION = "admin_institucion"
PUBLICADOR = "publicador"
ADMIN_PLATAFORMA = "admin_plataforma"
GRUPOS = (MEDICO, ADMIN_INSTITUCION, PUBLICADOR, ADMIN_PLATAFORMA)

# Quién hace qué. El admin de plataforma, todo.
PUBLICAN = (PUBLICADOR, ADMIN_PLATAFORMA)                    # /api/modelos/*
CONSULTAN = (MEDICO, ADMIN_INSTITUCION, ADMIN_PLATAFORMA)    # /api/estudios, /api/inferencias, /api/trabajos

_NOMBRES = {
    MEDICO: "médico",
    ADMIN_INSTITUCION: "institución",
    PUBLICADOR: "publicador",
    ADMIN_PLATAFORMA: "administración de Ateneo",
}


def _enumerar(grupos: Iterable[str], conjuncion: str) -> str:
    nombres = [_NOMBRES.get(g, g) for g in grupos]
    return nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} {conjuncion} {nombres[-1]}"


def describir_grupos(grupos: Iterable[str]) -> str:
    """Los grupos como los lee una persona: «institución», «médico y publicador»."""
    return _enumerar(grupos, "y")


@dataclass(frozen=True)
class Usuario:
    sub: str
    grupos: tuple[str, ...] = ()
    # El claim `username` del access token: lo que piden las llamadas admin de Cognito (los grupos
    # de rutas/cuenta.py). Con el email como nombre de usuario, Cognito genera uno propio, que no
    # hay por qué suponer igual al `sub`. None sin Cognito.
    username: str | None = None

    @staticmethod
    def anonimo() -> "Usuario":
        """Sin Cognito configurado (docker compose, tests) no hay a quién pedirle permisos: el
        anónimo tiene todos los roles y pasa como antes de que existieran."""
        return Usuario(sub="anonimo", grupos=GRUPOS)

    @staticmethod
    def plataforma() -> "Usuario":
        """Ateneo mismo: la demo que siembra los modelos iniciales y su recuperación por consola."""
        return Usuario(sub="plataforma", grupos=(ADMIN_PLATAFORMA,))

    @property
    def es_admin_plataforma(self) -> bool:
        return ADMIN_PLATAFORMA in self.grupos

    def exigir(self, grupos: Iterable[str]) -> None:
        """SinPermiso (403) si no está en ninguno de `grupos`. El detalle dice qué cuenta hace falta."""
        grupos = tuple(grupos)
        if any(g in self.grupos for g in grupos):
            return
        # El admin de plataforma entra a todo: nombrarlo en cada mensaje no ayuda a nadie.
        pedidos = [g for g in grupos if g != ADMIN_PLATAFORMA] or list(grupos)
        tuya = (f"la tuya es de {describir_grupos(self.grupos)}" if self.grupos
                else "la tuya todavía no tiene un rol: elegí si es de una institución o de un publicador")
        raise SinPermiso(f"esto es para cuentas de {_enumerar(pedidos, 'o')} y {tuya}")

    def es_suyo(self, autor: str | None) -> bool:
        """Si lo creó él. El admin de plataforma cuenta como dueño de todo. Una fila sin autor
        (anterior a la migración 005) no es de nadie: solo la toca un admin."""
        return self.es_admin_plataforma or (autor is not None and autor == self.sub)
