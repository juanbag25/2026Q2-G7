"""Las rutas de la junta con casos de uso falsos (dependency_overrides), como en test_api.py."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("WEB_DIR", "/no/existe")   # sin sitio estático en los tests

from app.api import dependencias  # noqa: E402
from app.dominio.consulta import Consulta  # noqa: E402
from app.dominio.errores import Conflicto, EntradaInvalida, NoAutenticado, NoEncontrado  # noqa: E402
from app.dominio.estudio import Estudio  # noqa: E402
from app.dominio.modelo import Modelo  # noqa: E402
from app.main import crear_app  # noqa: E402

from .fakes import RelojFijo  # noqa: E402


class CasoFalso:
    def __init__(self, resultado=None, error=None):
        self.resultado, self.error, self.llamadas = resultado, error, []

    def ejecutar(self, *a, **k):
        self.llamadas.append((a, k))
        if self.error:
            raise self.error
        return self.resultado


def _informe(terminada: bool):
    """Una junta de dos modelos de tórax que no coinciden: revisión prioritaria."""
    t = RelojFijo().ahora()
    estudio = Estudio(id=uuid4(), tipo_estudio="torax-rx", s3_key="estudios/x.png", content_type="image/png",
                      tamano_bytes=10, estado="subido", creado=t)
    modelos = [
        Modelo(id=uuid4(), nombre=n, version="1.0.0", tipo_estudio="torax-rx", tarea="clasificacion",
               etiquetas=["NORMAL", "PNEUMONIA"], s3_prefix=f"modelos/{n}/1.0.0/", contrato={},
               estado_evaluacion="ok", creado=t, publicado=t, accuracy=0.9, metricas={"accuracy": 0.9, "auc": auc})
        for n, auc in (("torax-rx-densenet121", 0.98), ("otro", 0.9))
    ]
    consulta = Consulta.junta(estudio, modelos, t)
    trabajos = consulta.trabajos_para(estudio, modelos, t)
    if terminada:
        for trabajo, p in zip(trabajos, (0.9, 0.2)):
            trabajo.estado = "ok"
            trabajo.resultado = {"prediccion": "PNEUMONIA" if p > 0.5 else "NORMAL",
                                 "probabilidades": {"NORMAL": 1 - p, "PNEUMONIA": p}}
    return consulta.informe(trabajos, {m.id: m for m in modelos}), modelos


@pytest.fixture
def cliente():
    app = crear_app()
    app.dependency_overrides[dependencias.dep_verificador] = lambda: None   # sin Cognito: anónimo
    yield app, TestClient(app)
    app.dependency_overrides.clear()


class VerificadorFalso:
    def verificar(self, token):
        raise NoAutenticado("token inválido")


def test_crear_junta_202_en_cola(cliente):
    app, c = cliente
    informe, modelos = _informe(terminada=False)
    caso = CasoFalso(resultado=informe)
    app.dependency_overrides[dependencias.dep_crear_consulta] = lambda: caso
    estudio_id, ids = uuid4(), [str(m.id) for m in modelos]
    r = c.post("/api/consultas", json={"estudio_id": str(estudio_id), "modelo_ids": ids})
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["estado"] == "en_cola" and cuerpo["consenso"] is None
    assert [i["estado"] for i in cuerpo["inferencias"]] == ["pendiente", "pendiente"]
    assert cuerpo["inferencias"][0]["modelo"]["nombre_visible"] == "DenseNet121 · Neumonía"   # del registro
    assert cuerpo["inferencias"][0]["peso"] == {"metrica": "auc", "valor": 0.98}
    assert caso.llamadas == [((estudio_id, [m.id for m in modelos]), {})]


@pytest.mark.parametrize("cuantos", [1, 6])
def test_crear_junta_422_fuera_de_dos_a_cinco(cliente, cuantos):
    app, c = cliente
    caso = CasoFalso(resultado=None)
    app.dependency_overrides[dependencias.dep_crear_consulta] = lambda: caso
    r = c.post("/api/consultas", json={"estudio_id": str(uuid4()), "modelo_ids": [str(uuid4()) for _ in range(cuantos)]})
    assert r.status_code == 422 and r.json()["error"] == "entrada_invalida"
    assert caso.llamadas == []


@pytest.mark.parametrize("error, codigo", [
    (Conflicto("densenet v1.0.0 no tiene evaluación verificada"), 409),
    (EntradaInvalida("una junta lleva modelos distintos"), 422),
    (NoEncontrado("no existe el estudio"), 404),
])
def test_crear_junta_errores_del_dominio(cliente, error, codigo):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_crear_consulta] = lambda: CasoFalso(error=error)
    r = c.post("/api/consultas", json={"estudio_id": str(uuid4()), "modelo_ids": [str(uuid4()), str(uuid4())]})
    assert r.status_code == codigo and r.json()["detalle"] == error.detalle


def test_leer_junta_con_consenso_y_revision_prioritaria(cliente):
    app, c = cliente
    informe, modelos = _informe(terminada=True)
    app.dependency_overrides[dependencias.dep_consultar_consulta] = lambda: CasoFalso(resultado=informe)
    r = c.get(f"/api/consultas/{informe.consulta.id}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "completa"
    consenso = cuerpo["consenso"]
    assert consenso["prediccion"] == "PNEUMONIA" and consenso["votos"] == 2
    assert consenso["acuerdo"] == pytest.approx(0.98 / 1.88)
    assert consenso["revision_prioritaria"] is True and consenso["umbral_acuerdo"] == 0.7
    assert [i["coincide"] for i in cuerpo["inferencias"]] == [True, False]
    assert cuerpo["inferencias"][1]["resultado"]["prediccion"] == "NORMAL"


def test_leer_junta_404(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_consultar_consulta] = lambda: CasoFalso(error=NoEncontrado("nope"))
    assert c.get(f"/api/consultas/{uuid4()}").status_code == 404


def test_la_junta_pide_token(cliente):
    app, c = cliente
    app.dependency_overrides[dependencias.dep_verificador] = lambda: VerificadorFalso()
    app.dependency_overrides[dependencias.dep_crear_consulta] = lambda: CasoFalso(resultado=None)
    app.dependency_overrides[dependencias.dep_consultar_consulta] = lambda: CasoFalso(resultado=None)
    assert c.post("/api/consultas", json={"estudio_id": str(uuid4()),
                                          "modelo_ids": [str(uuid4()), str(uuid4())]}).status_code == 401
    assert c.get(f"/api/consultas/{uuid4()}").status_code == 401
