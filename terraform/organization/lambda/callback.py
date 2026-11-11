"""Callback del login: el punto HTTPS fijo entre Cognito y el sitio en S3 (cognito.tf).

GET /callback?code=…&state=…  Canjea el código por los tokens en el endpoint /oauth2/token de
                              Cognito, con el secreto del cliente, y redirige al sitio con los
                              tokens en el fragmento: http://<sitio>/#access_token=…&id_token=…
                              El fragmento no viaja al servidor: S3 nunca lo ve ni lo registra.
                              Hay un cliente por puerta del sitio (ingreso, institucion,
                              publicador); el sitio pone el suyo al principio del state
                              ("ingreso.<al azar>"). Sin uno conocido no canjea: no adivina.
GET /logout                   Cognito ya cerró su sesión; vuelve al sitio.

Si algo falla, redirige igual al sitio con #error=… para que la pantalla lo muestre. Nunca
escribe en el log ni el código ni los tokens.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger()
log.setLevel(logging.INFO)

DOMINIO = os.environ["COGNITO_DOMINIO"]       # https://ateneo-xxx.auth.us-east-1.amazoncognito.com
CLIENTES = json.loads(os.environ["CLIENTES"])  # {"ingreso": {"id": …, "secreto": …}, "institucion": …, "publicador": …}
URL_CALLBACK = os.environ["URL_CALLBACK"]     # la misma que mandó el sitio a /oauth2/authorize
URL_SITIO = os.environ["URL_SITIO"].rstrip("/")


def _redirigir(url: str) -> dict:
    return {"statusCode": 302, "headers": {"Location": url, "Cache-Control": "no-store"}}


def _al_sitio(**fragmento: str) -> dict:
    return _redirigir(f"{URL_SITIO}/#{urllib.parse.urlencode(fragmento)}")


def _cliente(estado: str) -> dict | None:
    """El cliente con el que el sitio pidió el código: va antes del primer punto del state. Si no
    es uno conocido, None: un código se canjea solo con el cliente que lo pidió, así que probar
    con otro (antes, el de publicador) fallaría igual."""
    return CLIENTES.get(estado.split(".", 1)[0])


def _canjear(codigo: str, cliente: dict) -> dict:
    """POST /oauth2/token con grant authorization_code. Cliente confidencial: Basic auth."""
    cuerpo = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": cliente["id"],
        "code": codigo,
        "redirect_uri": URL_CALLBACK,
    }).encode()
    credencial = base64.b64encode(f"{cliente['id']}:{cliente['secreto']}".encode()).decode()
    pedido = urllib.request.Request(
        f"{DOMINIO}/oauth2/token", data=cuerpo, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {credencial}"},
    )
    with urllib.request.urlopen(pedido, timeout=10) as respuesta:
        return json.load(respuesta)


def handler(evento: dict, _contexto) -> dict:
    if evento.get("rawPath", "").endswith("/logout"):
        return _redirigir(f"{URL_SITIO}/")

    params = evento.get("queryStringParameters") or {}
    estado = params.get("state", "")

    # El usuario canceló o Cognito rechazó el pedido: vuelve con el motivo.
    if "error" in params:
        log.info("Cognito devolvió error: %s", params["error"])
        return _al_sitio(error=params["error"], error_description=params.get("error_description", ""), state=estado)

    codigo = params.get("code")
    if not codigo:
        return _al_sitio(error="sin_codigo", error_description="Cognito no mandó el código", state=estado)

    cliente = _cliente(estado)
    if cliente is None:
        log.warning("el state no nombra un cliente conocido")
        return _al_sitio(error="cliente_desconocido", error_description="El ingreso no empezó desde el sitio",
                         state=estado)

    try:
        tokens = _canjear(codigo, cliente)
    except urllib.error.HTTPError as e:
        # 400 invalid_grant: el código ya se usó, venció (5 min) o el redirect_uri no coincide.
        try:
            motivo = json.load(e).get("error", f"http_{e.code}")
        except ValueError:
            motivo = f"http_{e.code}"
        log.warning("Cognito rechazó el canje: %s", motivo)
        return _al_sitio(error=motivo, error_description="No se pudo completar el ingreso", state=estado)
    except (urllib.error.URLError, TimeoutError) as e:
        log.error("Cognito no contestó: %s", e)
        return _al_sitio(error="cognito_no_disponible", error_description="Cognito no contestó", state=estado)

    log.info("ingreso completado")
    # Sin refresh token: en la URL queda lo justo. A la hora, el sitio vuelve a pasar por el login.
    return _al_sitio(
        access_token=tokens["access_token"],
        id_token=tokens["id_token"],
        expires_in=str(tokens.get("expires_in", 3600)),
        token_type=tokens.get("token_type", "Bearer"),
        state=estado,
    )
