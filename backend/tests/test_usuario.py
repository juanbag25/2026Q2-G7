"""El usuario del token: qué grupos pasan, qué dice el 403 y de quién es cada cosa."""

from __future__ import annotations

import pytest

from app.dominio.errores import SinPermiso
from app.dominio.usuario import CONSULTAN, GRUPOS, PUBLICAN, Usuario

from .fakes import ADMIN, INSTITUCION, MEDICO_A, PUBLICADOR_A, SIN_ROL


@pytest.mark.parametrize("usuario", [PUBLICADOR_A, ADMIN])
def test_publican_el_publicador_y_el_admin(usuario):
    usuario.exigir(PUBLICAN)


@pytest.mark.parametrize("usuario", [MEDICO_A, INSTITUCION, ADMIN])
def test_consultan_el_medico_la_institucion_y_el_admin(usuario):
    usuario.exigir(CONSULTAN)


def test_el_403_dice_que_cuenta_hace_falta_y_cual_es_la_tuya():
    with pytest.raises(SinPermiso) as e:
        INSTITUCION.exigir(PUBLICAN)
    assert e.value.detalle == "esto es para cuentas de publicador y la tuya es de institución"
    with pytest.raises(SinPermiso) as e:
        PUBLICADOR_A.exigir(CONSULTAN)
    assert e.value.detalle == "esto es para cuentas de médico o institución y la tuya es de publicador"


def test_sin_grupo_el_403_lo_dice():
    with pytest.raises(SinPermiso, match="todavía no tiene un rol"):
        SIN_ROL.exigir(CONSULTAN)


def test_el_anonimo_tiene_todos_los_roles():
    """Sin Cognito (docker compose, tests) no hay control de acceso: pasa como antes."""
    anonimo = Usuario.anonimo()
    assert set(anonimo.grupos) == set(GRUPOS)
    anonimo.exigir(PUBLICAN)
    anonimo.exigir(CONSULTAN)


def test_es_suyo():
    assert MEDICO_A.es_suyo(MEDICO_A.sub)
    assert not MEDICO_A.es_suyo("otro-sub")
    assert not MEDICO_A.es_suyo(None)
    assert ADMIN.es_suyo("otro-sub") and ADMIN.es_suyo(None)
