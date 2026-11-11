"""Los adaptadores de Cognito: el verificador de access tokens, con una clave RSA propia en lugar del
JWKS del pool, y el directorio de cuentas, con el Stubber de botocore."""

from __future__ import annotations

import time
from types import SimpleNamespace

import boto3
import jwt
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.dominio.errores import NoAutenticado, ServicioNoDisponible
from app.infraestructura.cognito.directorio import DirectorioCognito
from app.infraestructura.cognito.verificador import VerificadorCognito

POOL = "us-east-1_prueba"
CLIENTE = "cliente123"
EMISOR = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL}"

CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class JwksFijo:
    """Hace de PyJWKClient: siempre la clave pública de CLAVE."""
    def __init__(self, error: Exception | None = None):
        self.error = error

    def get_signing_key_from_jwt(self, _token):
        if self.error:
            raise self.error
        return SimpleNamespace(key=CLAVE.public_key())


def _token(clave=CLAVE, **cambios) -> str:
    claims = {"sub": "sub-123", "iss": EMISOR, "client_id": CLIENTE, "token_use": "access",
              "exp": int(time.time()) + 300, "scope": "openid email"}
    claims.update(cambios)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, clave, algorithm="RS256")


@pytest.fixture
def verificador():
    return VerificadorCognito("us-east-1", POOL, [CLIENTE, "cliente-institucion"], jwks=JwksFijo())


def test_access_token_valido_devuelve_el_usuario_con_sus_grupos(verificador):
    u = verificador.verificar(_token(**{"cognito:groups": ["publicador"]}))
    assert u.sub == "sub-123" and u.grupos == ("publicador",)


def test_acepta_cualquiera_de_los_clientes_del_pool(verificador):
    assert verificador.verificar(_token(client_id="cliente-institucion")).grupos == ()


def test_lee_el_username_que_piden_las_llamadas_admin(verificador):
    """No es el sub: con el email como nombre de usuario, Cognito genera uno propio."""
    u = verificador.verificar(_token(username="9f1c-usuario"))
    assert u.username == "9f1c-usuario" and u.sub == "sub-123"
    assert verificador.verificar(_token()).username is None


@pytest.mark.parametrize("cambios", [
    {"exp": int(time.time()) - 10},                    # vencido
    {"iss": "https://cognito-idp.us-east-1.amazonaws.com/otro_pool"},
    {"client_id": "otro-cliente"},
    {"token_use": "id"},                               # un id token no sirve para la API
    {"token_use": None},
])
def test_rechaza(verificador, cambios):
    with pytest.raises(NoAutenticado):
        verificador.verificar(_token(**cambios))


def test_rechaza_otra_firma(verificador):
    with pytest.raises(NoAutenticado):
        verificador.verificar(_token(clave=OTRA_CLAVE))


def test_rechaza_basura(verificador):
    with pytest.raises(NoAutenticado):
        verificador.verificar("no-es-un-jwt")


def test_sin_claves_es_servicio_no_disponible():
    v = VerificadorCognito("us-east-1", POOL, [CLIENTE], jwks=JwksFijo(error=jwt.PyJWKClientConnectionError("sin red")))
    with pytest.raises(ServicioNoDisponible):
        v.verificar(_token())


def test_settings_pide_el_pool_y_los_clientes_de_cognito():
    base = {"database_url": "postgresql://x", "bucket_modelos": "m", "bucket_estudios": "e",
            "cola_inferencias_url": "http://sqs/q"}
    assert Settings(**base).cognito_user_pool_id is None
    s = Settings(**base, cognito_user_pool_id=POOL, cognito_client_ids=f"{CLIENTE}, otro")
    assert s.clientes_cognito == [CLIENTE, "otro"]
    with pytest.raises(ValueError):
        Settings(**base, cognito_user_pool_id=POOL)


# ---- el directorio de cuentas (los grupos, para elegir el tipo) ------------------------

def _cognito():
    return boto3.client("cognito-idp", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")


def _grupos(*nombres):
    return [{"GroupName": n, "UserPoolId": POOL} for n in nombres]


def test_lee_los_grupos_por_username_y_sigue_las_paginas():
    cognito = _cognito()
    with Stubber(cognito) as stub:
        pedido = {"UserPoolId": POOL, "Username": "u-1", "Limit": 60}
        stub.add_response("admin_list_groups_for_user", {"Groups": _grupos("medico"), "NextToken": "otra"}, pedido)
        stub.add_response("admin_list_groups_for_user", {"Groups": _grupos("publicador")}, {**pedido, "NextToken": "otra"})
        assert DirectorioCognito(cognito, POOL).grupos_de("u-1") == ("medico", "publicador")
        stub.assert_no_pending_responses()


def test_sin_grupos_es_una_tupla_vacia():
    cognito = _cognito()
    with Stubber(cognito) as stub:
        stub.add_response("admin_list_groups_for_user", {"Groups": []})
        assert DirectorioCognito(cognito, POOL).grupos_de("u-1") == ()


def test_agrega_al_grupo_por_username():
    cognito = _cognito()
    with Stubber(cognito) as stub:
        stub.add_response("admin_add_user_to_group", {},
                          {"UserPoolId": POOL, "Username": "u-1", "GroupName": "admin_institucion"})
        DirectorioCognito(cognito, POOL).agregar_a_grupo("u-1", "admin_institucion")
        stub.assert_no_pending_responses()


def test_una_cuenta_que_ya_no_existe_es_no_autenticado():
    cognito = _cognito()
    with Stubber(cognito) as stub:
        stub.add_client_error("admin_list_groups_for_user", service_error_code="UserNotFoundException",
                              http_status_code=400)
        with pytest.raises(NoAutenticado):
            DirectorioCognito(cognito, POOL).grupos_de("u-1")


@pytest.mark.parametrize("codigo", ["AccessDeniedException", "TooManyRequestsException", "ResourceNotFoundException"])
def test_si_cognito_rechaza_es_servicio_no_disponible_y_dice_por_que(codigo):
    """Si LabRole no pudiera llamar a Cognito, el 502 lo dice (y el log también)."""
    cognito = _cognito()
    with Stubber(cognito) as stub:
        stub.add_client_error("admin_add_user_to_group", service_error_code=codigo, http_status_code=400)
        with pytest.raises(ServicioNoDisponible, match=codigo):
            DirectorioCognito(cognito, POOL).agregar_a_grupo("u-1", "publicador")


def test_sin_red_es_servicio_no_disponible():
    class SinRed:
        def admin_list_groups_for_user(self, **_):
            raise EndpointConnectionError(endpoint_url="https://cognito-idp.us-east-1.amazonaws.com")

    with pytest.raises(ServicioNoDisponible, match="no contestó"):
        DirectorioCognito(SinRed(), POOL).grupos_de("u-1")
