"""El consenso de la junta (spec funcional §6.5): números hechos a mano, sin IO."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.dominio.consenso import UMBRAL_ACUERDO, Peso, Voto, calcular_consenso, peso_de
from app.dominio.modelo import Modelo

from .fakes import RelojFijo


def voto(peso: float, prediccion: str, p_neumonia: float) -> Voto:
    return Voto(peso, prediccion, {"NORMAL": 1 - p_neumonia, "PNEUMONIA": p_neumonia})


def modelo(estado="ok", accuracy=0.9, metricas=None) -> Modelo:
    t = RelojFijo().ahora()
    return Modelo(id=uuid4(), nombre="m", version="1", tipo_estudio="torax-rx", tarea="clasificacion",
                  etiquetas=["NORMAL", "PNEUMONIA"], s3_prefix="modelos/m/1/", contrato={},
                  estado_evaluacion=estado, creado=t, publicado=t, accuracy=accuracy,
                  metricas=metricas if metricas is not None else {"accuracy": accuracy})


# ---- el peso ------------------------------------------------------------------------

def test_el_peso_es_el_auc_verificado_si_esta():
    assert peso_de(modelo(accuracy=0.9, metricas={"accuracy": 0.9, "auc": 0.97})) == Peso("auc", 0.97)


def test_sin_auc_pesa_la_accuracy_como_en_multiclase():
    assert peso_de(modelo(accuracy=0.88, metricas={"accuracy": 0.88, "f1_macro": 0.87})) == Peso("accuracy", 0.88)


def test_un_auc_que_no_es_numero_cae_en_la_accuracy():
    assert peso_de(modelo(accuracy=0.8, metricas={"auc": float("nan")})) == Peso("accuracy", 0.8)


@pytest.mark.parametrize("estado", ["pendiente", "en_curso", "error"])
def test_sin_evaluacion_verificada_no_hay_peso(estado):
    assert peso_de(modelo(estado=estado, accuracy=None, metricas={})) is None


# ---- el consenso --------------------------------------------------------------------

def test_unanimes_acuerdo_total_sin_revision():
    c = calcular_consenso([voto(0.99, "PNEUMONIA", 0.9), voto(0.95, "PNEUMONIA", 0.8), voto(0.9, "PNEUMONIA", 0.7)])
    assert c.prediccion == "PNEUMONIA" and c.votos == 3
    assert c.acuerdo == pytest.approx(1.0) and not c.revision_prioritaria


def test_promedio_ponderado_de_las_probabilidades():
    # (0.9 · 0.9 + 0.6 · 0.4) / 1.5 = 0.70 de neumonía
    c = calcular_consenso([voto(0.9, "PNEUMONIA", 0.9), voto(0.6, "NORMAL", 0.4)])
    assert c.probabilidades["PNEUMONIA"] == pytest.approx(0.70)
    assert c.probabilidades["NORMAL"] == pytest.approx(0.30)
    assert c.prediccion == "PNEUMONIA"
    assert c.acuerdo == pytest.approx(0.9 / 1.5)          # 0,60: solo coincide el primero


def test_dos_de_tres_parecidos_es_revision_prioritaria():
    c = calcular_consenso([voto(0.98, "PNEUMONIA", 0.9), voto(0.97, "PNEUMONIA", 0.8), voto(0.99, "NORMAL", 0.2)])
    assert c.prediccion == "PNEUMONIA"
    assert c.acuerdo == pytest.approx(1.95 / 2.94)        # 0,66 < 0,70
    assert c.revision_prioritaria


def test_cuatro_de_cinco_alcanzan_el_umbral():
    votos = [voto(0.9, "NORMAL", 0.1)] * 4 + [voto(0.9, "PNEUMONIA", 0.95)]
    c = calcular_consenso(votos)
    assert c.prediccion == "NORMAL" and c.acuerdo == pytest.approx(0.8) and not c.revision_prioritaria


def test_el_promedio_puede_contradecir_a_la_mayoria_y_eso_se_marca():
    # Dos dudan hacia neumonía (0,55) y uno está seguro de normal (0,01): gana normal por el promedio.
    c = calcular_consenso([voto(1, "PNEUMONIA", 0.55), voto(1, "PNEUMONIA", 0.55), voto(1, "NORMAL", 0.01)])
    assert c.prediccion == "NORMAL"
    assert c.acuerdo == pytest.approx(1 / 3) and c.revision_prioritaria


def test_con_menos_de_dos_votos_no_hay_consenso():
    assert calcular_consenso([]) is None
    assert calcular_consenso([voto(0.9, "PNEUMONIA", 0.9)]) is None


def test_si_ningun_modelo_pesa_valen_todos_lo_mismo():
    c = calcular_consenso([voto(0, "PNEUMONIA", 0.9), voto(0, "NORMAL", 0.3)])
    assert c.probabilidades["PNEUMONIA"] == pytest.approx(0.6) and c.acuerdo == pytest.approx(0.5)


def test_multiclase_con_las_cuatro_etiquetas():
    a = Voto(0.9, "glioma", {"glioma": 0.7, "meningioma": 0.1, "notumor": 0.1, "pituitary": 0.1})
    b = Voto(0.8, "meningioma", {"glioma": 0.3, "meningioma": 0.5, "notumor": 0.1, "pituitary": 0.1})
    c = calcular_consenso([a, b])
    assert list(c.probabilidades) == ["glioma", "meningioma", "notumor", "pituitary"]
    assert sum(c.probabilidades.values()) == pytest.approx(1.0)
    assert c.prediccion == "glioma" and c.acuerdo == pytest.approx(0.9 / 1.7)


def test_el_umbral_es_el_de_la_spec():
    assert UMBRAL_ACUERDO == 0.70
