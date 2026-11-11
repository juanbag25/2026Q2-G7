"""Las dos Lambdas del login (terraform/organization/lambda/) con un Cognito falso: en qué grupo
queda quien se registra, según el cliente por el que entró, y con qué cliente se canjea el código.

El mapa de grupos es el que arma cognito.tf (plan.tftest.hcl comprueba ese lado): solo los dos
clientes de «crear cuenta» dan grupo; ateneo-ingreso, el de «Ingresar», no da ninguno.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.parse
from pathlib import Path

import pytest

LAMBDAS = Path(__file__).resolve().parents[1] / "terraform" / "organization" / "lambda"
GRUPO_POR_CLIENTE = {"ateneo-institucion": "admin_institucion", "ateneo-publicador": "publicador"}
NOMBRES = {"id-ingreso": "ateneo-ingreso", "id-institucion": "ateneo-institucion", "id-publicador": "ateneo-publicador"}


def _cargar(nombre: str, monkeypatch, **entorno: str):
    """Importa la Lambda con su entorno, como la arranca AWS: lee las variables al importarse."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)
    spec = importlib.util.spec_from_file_location(f"lambda_{nombre}", LAMBDAS / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class CognitoFalso:
    def __init__(self, falla: bool = False):
        self.falla = falla
        self.descritos: list[str] = []
        self.agregados: list[tuple[str, str]] = []

    def describe_user_pool_client(self, UserPoolId, ClientId):
        self.descritos.append(ClientId)
        if self.falla or ClientId not in NOMBRES:
            raise RuntimeError("ResourceNotFoundException")
        return {"UserPoolClient": {"ClientName": NOMBRES[ClientId]}}

    def admin_add_user_to_group(self, UserPoolId, Username, GroupName):
        self.agregados.append((Username, GroupName))


# ---- post-confirmación ---------------------------------------------------------------

@pytest.fixture
def post_confirmacion(monkeypatch):
    modulo = _cargar("post_confirmacion", monkeypatch, GRUPO_POR_CLIENTE=json.dumps(GRUPO_POR_CLIENTE))
    modulo.cognito = CognitoFalso()
    return modulo


def _registro(cliente_id, disparador="PostConfirmation_ConfirmSignUp"):
    return {"triggerSource": disparador, "userPoolId": "us-east-1_prueba", "userName": "u-123",
            "callerContext": {"clientId": cliente_id} if cliente_id is not None else {}}


@pytest.mark.parametrize("cliente, grupo", [("id-institucion", "admin_institucion"), ("id-publicador", "publicador")])
def test_crear_cuenta_da_el_grupo_de_su_cliente(post_confirmacion, cliente, grupo):
    evento = _registro(cliente)
    assert post_confirmacion.handler(evento, None) is evento
    assert post_confirmacion.cognito.agregados == [("u-123", grupo)]


def test_registrarse_desde_ingresar_no_da_grupo(post_confirmacion):
    """El bug: un médico que hacía «Ingresar → Sign up» terminaba de publicador."""
    evento = _registro("id-ingreso")
    assert post_confirmacion.handler(evento, None) is evento
    assert post_confirmacion.cognito.agregados == []


@pytest.mark.parametrize("cliente", [None, "", "CLIENT_ID_NOT_APPLICABLE"])
def test_sin_cliente_no_hay_grupo_por_defecto(post_confirmacion, cliente):
    post_confirmacion.handler(_registro(cliente), None)
    assert post_confirmacion.cognito.agregados == []
    assert post_confirmacion.cognito.descritos == []          # ni siquiera pregunta


def test_un_cliente_que_no_esta_en_el_mapa_no_da_grupo(post_confirmacion, monkeypatch):
    """Aunque se pierda el mapa entero: no hay un grupo de repuesto."""
    monkeypatch.setattr(post_confirmacion, "GRUPO_POR_CLIENTE", {})
    post_confirmacion.handler(_registro("id-publicador"), None)
    assert post_confirmacion.cognito.agregados == []


def test_si_cognito_falla_el_registro_igual_se_confirma(post_confirmacion):
    post_confirmacion.cognito = CognitoFalso(falla=True)
    evento = _registro("id-publicador")
    assert post_confirmacion.handler(evento, None) is evento
    assert post_confirmacion.cognito.agregados == []


def test_recuperar_la_contrasena_no_toca_los_grupos(post_confirmacion):
    post_confirmacion.handler(_registro("id-publicador", "PostConfirmation_ConfirmForgotPassword"), None)
    assert post_confirmacion.cognito.agregados == [] and post_confirmacion.cognito.descritos == []


def test_ya_no_lee_un_grupo_por_defecto(monkeypatch):
    """GRUPO_POR_DEFECTO era «publicador»: si quedara en el entorno de algún despliegue viejo, no se usa."""
    modulo = _cargar("post_confirmacion", monkeypatch, GRUPO_POR_CLIENTE=json.dumps(GRUPO_POR_CLIENTE),
                     GRUPO_POR_DEFECTO="publicador")
    modulo.cognito = CognitoFalso()
    modulo.handler(_registro("id-ingreso"), None)
    modulo.handler(_registro(None), None)
    assert modulo.cognito.agregados == []


# ---- callback ------------------------------------------------------------------------

CLIENTES = {c: {"id": f"id-{c}", "secreto": f"secreto-{c}"} for c in ("ingreso", "institucion", "publicador")}


@pytest.fixture
def callback(monkeypatch):
    modulo = _cargar("callback", monkeypatch, COGNITO_DOMINIO="https://ateneo.auth.us-east-1.amazoncognito.com",
                     CLIENTES=json.dumps(CLIENTES), URL_CALLBACK="https://api.ejemplo/callback",
                     URL_SITIO="http://sitio.ejemplo/")
    modulo.canjes = []

    def canjear(codigo, cliente):
        modulo.canjes.append((codigo, cliente["id"]))
        return {"access_token": "a", "id_token": "i", "expires_in": 3600, "token_type": "Bearer"}

    monkeypatch.setattr(modulo, "_canjear", canjear)
    return modulo


def _vuelta(modulo, state: str) -> dict[str, str]:
    respuesta = modulo.handler({"rawPath": "/callback", "queryStringParameters": {"code": "c0d1g0", "state": state}}, None)
    assert respuesta["statusCode"] == 302
    sitio, _, fragmento = respuesta["headers"]["Location"].partition("#")
    assert sitio == "http://sitio.ejemplo/"
    return dict(urllib.parse.parse_qsl(fragmento))


@pytest.mark.parametrize("cliente", ["ingreso", "institucion", "publicador"])
def test_el_state_elige_el_cliente_del_canje(callback, cliente):
    fragmento = _vuelta(callback, f"{cliente}.al-azar")
    assert callback.canjes == [("c0d1g0", f"id-{cliente}")]
    assert fragmento["access_token"] == "a" and fragmento["state"] == f"{cliente}.al-azar"


@pytest.mark.parametrize("state", ["", "al-azar", "medico.al-azar", "admin_plataforma.x"])
def test_un_state_sin_cliente_conocido_no_se_canjea_con_otro(callback, state):
    """Antes caía en el de publicador. Ahora no se adivina: vuelve al sitio con el error."""
    fragmento = _vuelta(callback, state)
    assert callback.canjes == []
    assert fragmento["error"] == "cliente_desconocido" and "access_token" not in fragmento
