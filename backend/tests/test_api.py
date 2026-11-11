"""La API con casos de uso falsos (dependency_overrides): códigos HTTP y forma de las respuestas."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("WEB_DIR", "/no/existe")   # sin sitio estático en los tests

from app.aplicacion.casos_uso.estudios import EstudioCreado  # noqa: E402
from app.aplicacion.casos_uso.modelos import SubidaModelo  # noqa: E402
from app.aplicacion.puertos import SubidaFirmada  # noqa: E402
from app.api import dependencias  # noqa: E402
from app.dominio.errores import Conflicto, NoAutenticado, NoEncontrado, SinPermiso  # noqa: E402
from app.dominio.estudio import Estudio  # noqa: E402
from app.dominio.modelo import Modelo  # noqa: E402
from app.dominio.trabajo import Trabajo  # noqa: E402
from app.dominio.usuario import Usuario  # noqa: E402
from app.main import crear_app  # noqa: E402

from .fakes import ADMIN, INSTITUCION, MEDICO_A, PUBLICADOR_A, SIN_ROL, RelojFijo  # noqa: E402


def _modelo() -> Modelo:
    t = RelojFijo().ahora()
    return Modelo(id=uuid4(), nombre="torax", version="1.0.0", tipo_estudio="torax-rx", tarea="clasificacion",
                  etiquetas=["NORMAL", "PNEUMONIA"], s3_prefix="modelos/torax/1.0.0/", contrato={},
                  estado_evaluacion="pendiente", creado=t, publicado=t)


def _trabajo() -> Trabajo:
    return Trabajo.nuevo(type("E", (), {"id": uuid4()})(), type("M", (), {"id": uuid4()})(), RelojFijo().ahora(),
                         creado_por=MEDICO_A.sub)


def _estudio_creado() -> EstudioCreado:
    e = Estudio.nuevo("torax-rx", "image/png", 1234, 20_000_000, "estudios/", RelojFijo().ahora(), MEDICO_A.sub)
    return EstudioCreado(estudio=e, subida=SubidaFirmada(url="http://s3.local/estudios", campos={"key": e.s3_key}))


class CasoFalso:
    def __init__(self, resultado=None, error=None):
        self.resultado, self.error, self.llamadas = resultado, error, []

    def ejecutar(self, *a, **k):
        self.llamadas.append((a, k))
        if self.error:
            raise self.error
        return self.resultado


@pytest.fixture
def cliente():
    app = crear_app()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: None   # sin Cognito: anónimo
    yield app, TestClient(app)
    app.dependency_overrides.clear()


# El token es el nombre de la cuenta: "Bearer medico" es un access token válido de un médico.
CUENTAS = {"medico": MEDICO_A, "institucion": INSTITUCION, "publicador": PUBLICADOR_A, "admin": ADMIN,
           "sin-rol": SIN_ROL}


class VerificadorFalso:
    """Acepta los tokens de CUENTAS; cualquier otro es NoAutenticado, como un JWT vencido."""
    def __init__(self):
        self.vistos = []

    def verificar(self, token):
        self.vistos.append(token)
        if token not in CUENTAS:
            raise NoAutenticado("token inválido")
        return CUENTAS[token]


def test_health(cliente):
    _, c = cliente
    assert c.get("/health").json() == {"ok": True}
    assert "instancia" in c.get("/api/health").json()


def test_publicar_202(cliente):
    app, c = cliente
    caso = CasoFalso(resultado=_modelo())
    app.dependency_overrides[dependencias.dep_publicar_modelo] = lambda: caso
    r = c.post("/api/modelos/publicar", json={"nombre": "torax", "version": "1.0.0"})
    assert r.status_code == 202
    assert r.json()["estado_evaluacion"] == "pendiente" and r.json()["accuracy"] is None
    assert caso.llamadas == [((Usuario.anonimo(), "torax", "1.0.0", None), {})]


def test_publicar_409_con_forma_de_error(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_publicar_modelo] = lambda: CasoFalso(error=Conflicto("ya está en_curso"))
    r = c.post("/api/modelos/publicar", json={"nombre": "torax", "version": "1.0.0"})
    assert r.status_code == 409 and r.json() == {"error": "conflicto", "detalle": "ya está en_curso"}


def test_publicar_422_por_validacion_pydantic(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_publicar_modelo] = lambda: CasoFalso(resultado=_modelo())
    r = c.post("/api/modelos/publicar", json={"nombre": "con espacios", "version": "1"})
    assert r.status_code == 422 and r.json()["error"] == "entrada_invalida"


def test_publicar_lleva_el_contrato_subido_al_caso_de_uso(cliente):
    app, c = cliente
    caso = CasoFalso(resultado=_modelo())
    app.dependency_overrides[dependencias.dep_publicar_modelo] = lambda: caso
    contrato = {"nombre": "torax", "version": "1.0.0"}
    r = c.post("/api/modelos/publicar", json={"nombre": "torax", "version": "1.0.0", "contrato": contrato})
    assert r.status_code == 202
    assert caso.llamadas == [((Usuario.anonimo(), "torax", "1.0.0", contrato), {})]


def test_publicar_403_si_cambia_el_contrato_de_un_modelo_ajeno(cliente):
    app, c = cliente
    error = SinPermiso("torax v1.0.0 lo publicó otra cuenta: su contrato solo lo cambia quien lo publicó")
    app.dependency_overrides[dependencias.dep_publicar_modelo] = lambda: CasoFalso(error=error)
    r = c.post("/api/modelos/publicar", json={"nombre": "torax", "version": "1.0.0", "contrato": {}})
    assert r.status_code == 403 and r.json() == {"error": "sin_permiso", "detalle": error.detalle}


def test_preparar_subida_201_con_la_firma(cliente):
    app, c = cliente
    firmada = SubidaFirmada(url="http://s3.local/modelos", campos={"key": "modelos/torax/2.0.0/modelo.onnx"})
    caso = CasoFalso(resultado=SubidaModelo(prefix="modelos/torax/2.0.0/", subida=firmada))
    app.dependency_overrides[dependencias.dep_preparar_subida] = lambda: caso
    r = c.post("/api/modelos/subidas", json={"nombre": "torax", "version": "2.0.0", "tamano_bytes": 16_000_000})
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["prefix"] == "modelos/torax/2.0.0/"
    assert cuerpo["subida"]["campos"]["key"].endswith("modelo.onnx")
    assert caso.llamadas == [(("torax", "2.0.0", 16_000_000), {})]


def test_preparar_subida_409_si_la_version_ya_existe(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_preparar_subida] = lambda: CasoFalso(error=Conflicto("ya hay un modelo"))
    r = c.post("/api/modelos/subidas", json={"nombre": "torax", "version": "1.0.0", "tamano_bytes": 16})
    assert r.status_code == 409 and r.json()["error"] == "conflicto"


def test_preparar_subida_422_sin_tamano(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_preparar_subida] = lambda: CasoFalso(resultado=None)
    r = c.post("/api/modelos/subidas", json={"nombre": "torax", "version": "2.0.0", "tamano_bytes": 0})
    assert r.status_code == 422 and r.json()["error"] == "entrada_invalida"


def test_modelo_404(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_consultar_modelo] = lambda: CasoFalso(error=NoEncontrado("nope"))
    assert c.get(f"/api/publico/modelos/{uuid4()}").status_code == 404


def test_trabajo_respuesta(cliente):
    app, c = cliente
    t = _trabajo()
    caso = CasoFalso(resultado=t)
    app.dependency_overrides[dependencias.dep_consultar_trabajo] = lambda: caso
    r = c.get(f"/api/trabajos/{t.id}")
    assert r.status_code == 200 and r.json()["estado"] == "pendiente" and r.json()["resultado"] is None
    assert "creado_por" not in r.json()                     # el `sub` no sale de la API
    assert caso.llamadas == [((Usuario.anonimo(), t.id), {})]


def test_trabajo_ajeno_es_404_con_forma_de_error(cliente):
    app, c = cliente
    t = _trabajo()
    error = NoEncontrado(f"no existe el trabajo {t.id}")
    app.dependency_overrides[dependencias.dep_consultar_trabajo] = lambda: CasoFalso(error=error)
    r = c.get(f"/api/trabajos/{t.id}")
    assert r.status_code == 404 and r.json() == {"error": "no_encontrado", "detalle": error.detalle}


def test_ruta_desconocida_bajo_api_es_404_json(cliente):
    _, c = cliente
    r = c.get("/api/nada")
    assert r.status_code == 404


def test_con_cognito_sin_token_es_401(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_listar_disponibles] = lambda: CasoFalso(resultado=[])
    r = c.get("/api/modelos/disponibles")
    assert r.status_code == 401 and r.json()["error"] == "no_autenticado"


def test_con_cognito_token_invalido_es_401(cliente):
    app, c = cliente
    verificador = VerificadorFalso()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: verificador
    app.dependency_overrides[dependencias.dep_listar_disponibles] = lambda: CasoFalso(resultado=[])
    r = c.get("/api/modelos/disponibles", headers={"Authorization": "Bearer vencido"})
    assert r.status_code == 401 and verificador.vistos == ["vencido"]


def test_con_cognito_token_valido_pasa(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_listar_disponibles] = lambda: CasoFalso(resultado=[])
    r = c.get("/api/modelos/disponibles", headers={"Authorization": "Bearer publicador"})
    assert r.status_code == 200 and r.json() == []


def test_health_no_pide_token(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    assert c.get("/api/health").status_code == 200


def test_el_catalogo_se_ve_sin_token(cliente):
    """El Visitante de la spec: la portada muestra el catálogo sin que nadie haya ingresado."""
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_listar_modelos] = lambda: CasoFalso(resultado=[_modelo()])
    r = c.get("/api/publico/modelos")
    assert r.status_code == 200 and [m["nombre"] for m in r.json()] == ["torax"]


def test_la_ficha_del_catalogo_se_ve_sin_token(cliente):
    app, c = cliente
    m = _modelo()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_consultar_modelo] = lambda: CasoFalso(resultado=m)
    r = c.get(f"/api/publico/modelos/{m.id}")
    assert r.status_code == 200 and r.json()["id"] == str(m.id)


def test_bajo_publico_solo_catalogo_y_estado_demo(cliente):
    """Las rutas exentas de JWT solo consultan el catálogo o un estado sin datos reservados."""
    app, _ = cliente
    rutas = sorted(r.path for r in app.routes if getattr(r, "path", "").startswith("/api/publico"))
    assert rutas == ["/api/publico/demo", "/api/publico/modelos", "/api/publico/modelos/{modelo_id}"]


# ---- quién entra a cada ruta: 401 sin token, 403 con el rol equivocado ---------------

PUBLICAN = {"publicador", "admin"}
CONSULTAN = {"medico", "institucion", "admin"}

# (método, ruta, cuerpo, el caso de uso que la atiende, lo que devuelve, qué cuentas pasan)
RUTAS = [
    ("GET", "/api/modelos/disponibles", None, "dep_listar_disponibles", lambda: [], PUBLICAN),
    ("POST", "/api/modelos/subidas", {"nombre": "torax", "version": "2.0.0", "tamano_bytes": 16},
     "dep_preparar_subida",
     lambda: SubidaModelo(prefix="modelos/torax/2.0.0/", subida=SubidaFirmada(url="http://s3.local", campos={})),
     PUBLICAN),
    ("POST", "/api/modelos/publicar", {"nombre": "torax", "version": "1.0.0"}, "dep_publicar_modelo", _modelo,
     PUBLICAN),
    ("POST", "/api/estudios", {"tipo_estudio": "torax-rx", "nombre_archivo": "rx.png", "content_type": "image/png",
                               "tamano_bytes": 1234}, "dep_crear_estudio", _estudio_creado, CONSULTAN),
    ("POST", "/api/inferencias", {"estudio_id": str(uuid4()), "modelo_id": str(uuid4())}, "dep_encolar_inferencia",
     _trabajo, CONSULTAN),
    ("GET", f"/api/trabajos/{uuid4()}", None, "dep_consultar_trabajo", _trabajo, CONSULTAN),
]
CASOS_RUTA = [pytest.param(*r, id=r[3].removeprefix("dep_")) for r in RUTAS]


def _pedir(app, c, metodo, ruta, cuerpo, dep, resultado, token=None):
    caso = CasoFalso(resultado=resultado())
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[getattr(dependencias, dep)] = lambda: caso
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return c.request(metodo, ruta, json=cuerpo, headers=headers), caso


@pytest.mark.parametrize("metodo, ruta, cuerpo, dep, resultado, pasan", CASOS_RUTA)
def test_sin_token_es_401(cliente, metodo, ruta, cuerpo, dep, resultado, pasan):
    r, caso = _pedir(*cliente, metodo, ruta, cuerpo, dep, resultado)
    assert r.status_code == 401 and r.json()["error"] == "no_autenticado"
    assert caso.llamadas == []


@pytest.mark.parametrize("metodo, ruta, cuerpo, dep, resultado, pasan", CASOS_RUTA)
def test_con_el_rol_equivocado_es_403_y_no_llega_al_caso_de_uso(cliente, metodo, ruta, cuerpo, dep, resultado, pasan):
    for cuenta in sorted(set(CUENTAS) - pasan):
        r, caso = _pedir(*cliente, metodo, ruta, cuerpo, dep, resultado, token=cuenta)
        assert r.status_code == 403, cuenta
        assert r.json()["error"] == "sin_permiso" and r.json()["detalle"].startswith("esto es para cuentas de")
        assert caso.llamadas == []


@pytest.mark.parametrize("metodo, ruta, cuerpo, dep, resultado, pasan", CASOS_RUTA)
def test_con_el_rol_correcto_pasa_y_el_caso_de_uso_sabe_quien_es(cliente, metodo, ruta, cuerpo, dep, resultado, pasan):
    for cuenta in sorted(pasan):
        r, caso = _pedir(*cliente, metodo, ruta, cuerpo, dep, resultado, token=cuenta)
        assert r.status_code < 300, (cuenta, r.status_code, r.text)
        assert len(caso.llamadas) == 1
        if dep != "dep_listar_disponibles" and dep != "dep_preparar_subida":   # los que guardan autoría
            assert caso.llamadas[0][0][0] == CUENTAS[cuenta]


def test_el_403_le_dice_a_la_institucion_que_publicar_es_para_publicadores(cliente):
    r, _ = _pedir(*cliente, "POST", "/api/modelos/publicar", {"nombre": "torax", "version": "1.0.0"},
                  "dep_publicar_modelo", _modelo, token="institucion")
    assert r.json() == {"error": "sin_permiso",
                        "detalle": "esto es para cuentas de publicador y la tuya es de institución"}


def test_lo_publico_no_pide_rol(cliente):
    """Una cuenta sin grupo (la Lambda falló) igual ve el catálogo."""
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_listar_modelos] = lambda: CasoFalso(resultado=[])
    r = c.get("/api/publico/modelos", headers={"Authorization": "Bearer sin-rol"})
    assert r.status_code == 200


# Con token y sin rol, a propósito: es cómo una cuenta sin rol elige el suyo (rutas/cuenta.py).
SIN_ROL_A_PROPOSITO = {"/api/cuenta/tipo"}


def test_toda_ruta_con_token_pide_un_rol(cliente):
    """Una ruta nueva bajo /api que no cuelgue de un router con exigir_grupos queda abierta a
    cualquier cuenta: este test la encuentra. /api/publico y /api/health son las únicas sin token,
    y la elección del tipo de cuenta, la única con token y sin rol."""
    app, _ = cliente
    abiertas, sin_token = [], []
    for r in app.routes:
        ruta = getattr(r, "path", "")
        if not ruta.startswith("/api/") or ruta.startswith(("/api/publico", "/api/health", "/api/docs", "/api/openapi")):
            continue
        nombres = {getattr(d.call, "__qualname__", "") for d in r.dependant.dependencies}
        if ruta in SIN_ROL_A_PROPOSITO:
            if "usuario_actual" not in nombres:
                sin_token.append(ruta)
        elif not any(n.startswith("exigir_grupos.") for n in nombres):
            abiertas.append(ruta)
    assert abiertas == [] and sin_token == []
