"""Quién hace el pedido. La API lo arma desde el access token de Cognito.

Un grupo de Cognito por rol (terraform/organization/cognito.tf); la Lambda de post-confirmación
pone a cada uno en el suyo al registrarse. La API aplica la versión mínima de la matriz de la
spec (E3 §2), en dos lugares:

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


@dataclass(frozen=True)
class Usuario:
    sub: str
    grupos: tuple[str, ...] = ()

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
        tuya = (f"la tuya es de {_enumerar(self.grupos, 'y')}" if self.grupos
                else "la tuya todavía no tiene un rol asignado: avisale a la administración de Ateneo")
        raise SinPermiso(f"esto es para cuentas de {_enumerar(pedidos, 'o')} y {tuya}")

    def es_suyo(self, autor: str | None) -> bool:
        """Si lo creó él. El admin de plataforma cuenta como dueño de todo. Una fila sin autor
        (anterior a la migración 005) no es de nadie: solo la toca un admin."""
        return self.es_admin_plataforma or (autor is not None and autor == self.sub)
