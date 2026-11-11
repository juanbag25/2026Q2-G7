"""Las colas del backend: encolar, reenviar y el adaptador de SQS (con el Stubber de botocore)."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import boto3
import pytest
from botocore.stub import Stubber

from app.aplicacion.casos_uso.inferencias import EncolarInferencia, ReenviarPendientes
from app.aplicacion.puertos import PeticionInferencia
from app.config import Settings
from app.dominio.errores import ServicioNoDisponible
from app.infraestructura.sqs.colas import ColaSqs

from .fakes import MEDICO_A, ColaFalsa
from .test_casos_uso import mundo  # noqa: F401 — fixture compartida

URL = "https://sqs.us-east-1.amazonaws.com/123456789012/ateneo-inferencias"


class SinEnviarMemoria:
    """Fake de TrabajosSinEnviar sobre el repositorio en memoria, con su reloj."""

    def __init__(self, trabajos, reloj):
        self.trabajos, self.reloj = trabajos, reloj

    def tomar_para_reenviar(self, minutos, limite):
        limite_t = self.reloj.ahora() - timedelta(minutes=minutos)
        viejos = [t for t in self.trabajos.datos.values() if t.estado == "pendiente" and t.actualizado < limite_t]
        for t in viejos:
            t.actualizado = self.reloj.ahora()
        return viejos[:limite]

    def vencer_en_curso(self, minutos, motivo):
        limite_t = self.reloj.ahora() - timedelta(minutes=minutos)
        n = 0
        for t in self.trabajos.datos.values():
            if t.estado == "en_curso" and t.actualizado < limite_t:
                t.estado, t.error, n = "error", motivo, n + 1
        return n


def _encolar(mundo, cola, modelo=None):
    modelo, estudio = modelo or mundo.publicar(), mundo.crear_estudio()
    caso = EncolarInferencia(mundo.estudios, mundo.modelos, mundo.trabajos, mundo.almacen, mundo.reloj,
                             cola, "b-modelos", "b-estudios")
    return caso.ejecutar(MEDICO_A, estudio.id, modelo.id), modelo, estudio


def test_encolar_manda_todo_lo_que_necesita_el_worker(mundo):
    cola = ColaFalsa()
    t, modelo, estudio = _encolar(mundo, cola)
    assert t.estado == "pendiente" and len(cola.enviados) == 1
    assert cola.enviados[0].como_mensaje() == {
        "trabajo_id": str(t.id),
        "modelo": {"nombre": "torax", "version": "1.0.0", "bucket": "b-modelos", "prefix": modelo.s3_prefix},
        "estudio": {"bucket": "b-estudios", "key": estudio.s3_key},
    }


def test_si_sqs_no_contesta_el_trabajo_queda_pendiente_y_no_hay_error(mundo):
    t, _, _ = _encolar(mundo, ColaFalsa(caida=True))
    assert mundo.trabajos.obtener(t.id).estado == "pendiente"


def test_reenviar_manda_los_pendientes_viejos_y_vence_los_en_curso(mundo):
    t, modelo, _ = _encolar(mundo, ColaFalsa(caida=True))
    t2, _, _ = _encolar(mundo, ColaFalsa(), modelo)
    mundo.trabajos.obtener(t2.id).estado = "en_curso"
    cola = ColaFalsa()
    reenviar = ReenviarPendientes(SinEnviarMemoria(mundo.trabajos, mundo.reloj), mundo.estudios, mundo.modelos,
                                  cola, "b-modelos", "b-estudios", minutos=5, vencimiento_minutos=10)

    mundo.reloj.avanzar(60)
    assert reenviar.ejecutar() == 0                     # todavía no pasaron 5 minutos

    mundo.reloj.avanzar(11 * 60)
    assert reenviar.ejecutar() == 1
    assert cola.enviados[0].trabajo_id == t.id
    assert mundo.trabajos.obtener(t2.id).estado == "error"


def test_adaptador_sqs_envia_recibe_borra_y_traduce_errores():
    sqs = boto3.client("sqs", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
    p = PeticionInferencia(uuid4(), "torax", "1.0.0", "bm", "modelos/torax/1.0.0/", "be", "estudios/a.png")
    with Stubber(sqs) as stub:
        stub.add_response("send_message", {"MessageId": "1", "MD5OfMessageBody": "x"},
                          {"QueueUrl": URL, "MessageBody": json.dumps(p.como_mensaje())})
        stub.add_client_error("send_message", "AWS.SimpleQueueService.NonExistentQueue")
        stub.add_response("receive_message", {"Messages": [{"Body": "{}", "ReceiptHandle": "r-1"}]},
                          {"QueueUrl": URL, "MaxNumberOfMessages": 10, "WaitTimeSeconds": 20})
        stub.add_response("delete_message", {}, {"QueueUrl": URL, "ReceiptHandle": "r-1"})
        cola = ColaSqs(sqs, URL)
        cola.enviar(p)
        with pytest.raises(ServicioNoDisponible):
            cola.enviar(p)
        [m] = cola.recibir(20)
        assert m.cuerpo == "{}"
        cola.borrar(m)


def test_config_cada_proceso_exige_su_cola(monkeypatch):
    for k, v in {"DATABASE_URL": "postgresql://x", "BUCKET_MODELOS": "m", "BUCKET_ESTUDIOS": "e"}.items():
        monkeypatch.setenv(k, v)
    for k in ("COLA_INFERENCIAS_URL", "COLA_EVALUACIONES_URL", "COLA_RESULTADOS_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match="cola_inferencias_url"):
        Settings()
    monkeypatch.setenv("COLA_INFERENCIAS_URL", URL)
    s = Settings()
    with pytest.raises(ValueError, match="COLA_EVALUACIONES_URL"):
        s.exigir("cola_evaluaciones_url")                # la API
    with pytest.raises(ValueError, match="COLA_RESULTADOS_URL"):
        s.exigir("cola_resultados_url")                  # el procesador
