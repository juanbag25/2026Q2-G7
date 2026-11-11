"""POST /api/cuenta/tipo: pide token pero no rol. Con un caso de uso falso (qué le llega) y con el
real sobre fakes de Cognito y de la base (qué contesta), como en test_api.py."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("WEB_DIR", "/no/existe")   # sin sitio estático en los tests

from app.aplicacion.casos_uso.cuenta import ElegirTipoCuenta, TipoElegido  # noqa: E402
from app.api import dependencias  # noqa: E402
from app.dominio.usuario import ADMIN_INSTITUCION, PUBLICADOR  # noqa: E402
from app.main import crear_app  # noqa: E402

from .fakes import SIN_ROL, DirectorioMemoria, RelojFijo, RepoCuentasMemoria  # noqa: E402
from .test_api import CasoFalso, VerificadorFalso  # noqa: E402


@pytest.fixture
def cliente():
    """Con Cognito: el token es el nombre de la cuenta ("Bearer sin-rol"), como en test_api.py."""
    app = crear_app()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    yield app, TestClient(app)
    app.dependency_overrides.clear()


def _caso(app, caso):
    app.dependency_overrides[dependencias.dep_elegir_tipo_cuenta] = lambda: caso
    return caso


def _real(app, **directorio):
    """El caso de uso de verdad, con la cuenta sin rol recién registrada en el Cognito falso."""
    cognito = DirectorioMemoria({SIN_ROL.username: []}, **directorio)
    _caso(app, ElegirTipoCuenta(RepoCuentasMemoria(), cognito, RelojFijo()))
    return cognito


def _elegir(c, tipo, token="sin-rol"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.post("/api/cuenta/tipo", json={"tipo": tipo}, headers=headers)


@pytest.mark.parametrize("token", [None, "vencido"])
def test_sin_un_token_valido_es_401_y_no_llega_al_caso_de_uso(cliente, token):
    app, c = cliente
    caso = _caso(app, CasoFalso(resultado=TipoElegido("institucion", ADMIN_INSTITUCION)))
    r = _elegir(c, "institucion", token=token)
    assert r.status_code == 401 and r.json()["error"] == "no_autenticado"
    assert caso.llamadas == []


def test_una_cuenta_sin_rol_puede_elegir(cliente):
    """La única ruta con token que no pide rol: es cómo una cuenta sin rol consigue el suyo."""
    app, c = cliente
    caso = _caso(app, CasoFalso(resultado=TipoElegido("institucion", ADMIN_INSTITUCION)))
    r = _elegir(c, "institucion")
    assert r.status_code == 200 and r.json() == {"tipo": "institucion", "grupo": "admin_institucion"}
    assert caso.llamadas == [((SIN_ROL, "institucion"), {})]


def test_elegir_repetir_y_cambiar(cliente):
    """Publicador: 200. Otra vez publicador: 200, sin cambios. Institución: 409, queda publicador."""
    app, c = cliente
    cognito = _real(app)
    r = _elegir(c, "publicador")
    assert r.status_code == 200 and r.json() == {"tipo": "publicador", "grupo": "publicador"}
    assert _elegir(c, "publicador").status_code == 200
    r = _elegir(c, "institucion")
    assert r.status_code == 409
    assert r.json() == {"error": "conflicto", "detalle": "tu cuenta ya es de publicador: el tipo se elige una sola vez"}
    assert cognito.cuentas[SIN_ROL.username] == [PUBLICADOR]


@pytest.mark.parametrize("tipo", ["medico", "admin_plataforma", "admin_institucion", "cualquiera"])
def test_medico_admin_o_cualquier_otra_cosa_es_422(cliente, tipo):
    app, c = cliente
    cognito = _real(app)
    r = _elegir(c, tipo)
    assert r.status_code == 422 and r.json()["error"] == "entrada_invalida"
    assert cognito.cuentas[SIN_ROL.username] == []


def test_sin_el_campo_tipo_es_422(cliente):
    app, c = cliente
    _real(app)
    r = c.post("/api/cuenta/tipo", json={}, headers={"Authorization": "Bearer sin-rol"})
    assert r.status_code == 422 and r.json()["error"] == "entrada_invalida"


def test_con_cognito_caido_es_502(cliente):
    app, c = cliente
    _real(app, caido=True)
    r = _elegir(c, "institucion")
    assert r.status_code == 502 and r.json()["error"] == "servicio_no_disponible"


def test_sin_cognito_el_anonimo_ya_puede_todo_y_es_409():
    app = crear_app()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: None
    app.dependency_overrides[dependencias.dep_elegir_tipo_cuenta] = (
        lambda: ElegirTipoCuenta(RepoCuentasMemoria(), None, RelojFijo()))
    r = TestClient(app).post("/api/cuenta/tipo", json={"tipo": "publicador"})
    assert r.status_code == 409 and r.json()["error"] == "conflicto"
