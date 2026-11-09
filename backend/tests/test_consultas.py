"""La junta: crearla con fakes en memoria y leer el informe mientras el procesador aplica resultados."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.aplicacion.casos_uso.consultas import ConsultarConsulta, CrearConsulta
from app.aplicacion.casos_uso.estudios import CrearEstudio
from app.dominio.errores import Conflicto, EntradaInvalida, NoEncontrado
from app.dominio.modelo import Modelo

from .fakes import (
    AlmacenMemoria, ColaFalsa, RelojFijo, RepoConsultasMemoria, RepoEstudiosMemoria, RepoModelosMemoria,
    RepoTrabajosMemoria,
)

TORAX = ["NORMAL", "PNEUMONIA"]


@pytest.fixture
def mundo():
    class Mundo:
        reloj = RelojFijo()
        modelos = RepoModelosMemoria()
        estudios = RepoEstudiosMemoria()
        trabajos = RepoTrabajosMemoria()
        consultas = RepoConsultasMemoria(trabajos)
        almacen = AlmacenMemoria()
        cola = ColaFalsa()

        def modelo(self, nombre, auc=0.95, tipo="torax-rx", etiquetas=TORAX, estado="ok"):
            t = self.reloj.ahora()
            metricas = {"accuracy": 0.9, "auc": auc} if estado == "ok" else None
            m = Modelo(id=uuid4(), nombre=nombre, version="1.0.0", tipo_estudio=tipo, tarea="clasificacion",
                       etiquetas=list(etiquetas), s3_prefix=f"modelos/{nombre}/1.0.0/", contrato={},
                       estado_evaluacion=estado, creado=t, publicado=t,
                       accuracy=0.9 if estado == "ok" else None, metricas=metricas)
            self.modelos.guardar(m)
            return m

        def estudio(self, tipo="torax-rx", subido=True):
            c = CrearEstudio(self.estudios, self.almacen, self.reloj, 20_000_000, "estudios/").ejecutar(
                tipo, "image/png", 1234)
            if subido:
                self.almacen.objetos[c.estudio.s3_key] = 1234
            return c.estudio

        def crear(self, estudio, modelos):
            return CrearConsulta(self.estudios, self.modelos, self.consultas, self.almacen, self.reloj, self.cola,
                                 "b-modelos", "b-estudios").ejecutar(estudio.id, [m.id for m in modelos])

        def leer(self, consulta_id):
            return ConsultarConsulta(self.consultas, self.modelos).ejecutar(consulta_id)

        def resultado(self, informe, modelo, p_neumonia=None, error=None):
            """Lo que haría el procesador al llegar el resultado de ese modelo."""
            t = next(i.trabajo for i in informe.inferencias if i.modelo.id == modelo.id)
            if error:
                t.estado, t.error = "error", error
            else:
                t.estado = "ok"
                t.resultado = {"prediccion": "PNEUMONIA" if p_neumonia >= 0.5 else "NORMAL",
                               "probabilidades": {"NORMAL": 1 - p_neumonia, "PNEUMONIA": p_neumonia}}

    return Mundo()


def tres(mundo):
    return mundo.modelo("mediscan", 0.99), mundo.modelo("densenet", 0.97), mundo.modelo("efficientnet", 0.95)


# ---- crear --------------------------------------------------------------------------

def test_una_junta_de_tres_crea_un_trabajo_y_un_mensaje_por_modelo(mundo):
    modelos = tres(mundo)
    e = mundo.estudio()
    informe = mundo.crear(e, modelos)

    assert informe.estado == "en_cola" and informe.consenso is None
    trabajos = mundo.consultas.trabajos_de(informe.consulta.id)
    assert len(trabajos) == 3
    assert all(t.estado == "pendiente" and t.consulta_id == informe.consulta.id for t in trabajos)
    assert {t.modelo_id for t in trabajos} == {m.id for m in modelos}
    # El mismo mensaje que una consulta individual: el worker no se entera de la junta.
    mensajes = [p.como_mensaje() for p in mundo.cola.enviados]
    assert {m["trabajo_id"] for m in mensajes} == {str(t.id) for t in trabajos}
    assert {m["modelo"]["nombre"] for m in mensajes} == {"mediscan", "densenet", "efficientnet"}
    assert all(m["estudio"] == {"bucket": "b-estudios", "key": e.s3_key} for m in mensajes)
    assert mundo.estudios.obtener(e.id).estado == "subido"


def test_con_la_cola_caida_la_junta_queda_pendiente_para_el_reenviador(mundo):
    mundo.cola.caida = True
    informe = mundo.crear(mundo.estudio(), tres(mundo))
    assert informe.estado == "en_cola"
    assert all(t.estado == "pendiente" for t in mundo.consultas.trabajos_de(informe.consulta.id))


@pytest.mark.parametrize("cuantos", [1, 6])
def test_una_junta_lleva_de_dos_a_cinco_modelos(mundo, cuantos):
    modelos = [mundo.modelo(f"m{i}") for i in range(cuantos)]
    with pytest.raises(EntradaInvalida):
        mundo.crear(mundo.estudio(), modelos)


def test_un_modelo_repetido_no_vale_doble(mundo):
    a, b, _ = tres(mundo)
    with pytest.raises(EntradaInvalida):
        mundo.crear(mundo.estudio(), [a, b, a])


def test_todos_del_tipo_del_estudio(mundo):
    a, _, _ = tres(mundo)
    cerebro = mundo.modelo("cnn", tipo="cerebro-rm", etiquetas=["glioma", "meningioma", "notumor", "pituitary"])
    with pytest.raises(EntradaInvalida):
        mundo.crear(mundo.estudio(), [a, cerebro])


def test_todos_con_las_mismas_etiquetas(mundo):
    a, _, _ = tres(mundo)
    otro = mundo.modelo("covid", etiquetas=["NORMAL", "COVID"])
    with pytest.raises(EntradaInvalida):
        mundo.crear(mundo.estudio(), [a, otro])


@pytest.mark.parametrize("estado", ["pendiente", "en_curso", "error"])
def test_todos_con_evaluacion_verificada(mundo, estado):
    a, b, _ = tres(mundo)
    sin_evaluar = mundo.modelo("nuevo", estado=estado)
    with pytest.raises(Conflicto):
        mundo.crear(mundo.estudio(), [a, b, sin_evaluar])


def test_el_estudio_tiene_que_estar_subido(mundo):
    with pytest.raises(Conflicto):
        mundo.crear(mundo.estudio(subido=False), tres(mundo))


def test_un_modelo_que_no_existe_es_404(mundo):
    a, _, _ = tres(mundo)
    fantasma = replace(a, id=uuid4())               # nunca se guardó
    with pytest.raises(NoEncontrado):
        mundo.crear(mundo.estudio(), [a, fantasma])


def test_si_la_junta_no_vale_no_queda_nada(mundo):
    a, b, _ = tres(mundo)
    with pytest.raises(Conflicto):
        mundo.crear(mundo.estudio(), [a, b, mundo.modelo("nuevo", estado="pendiente")])
    assert mundo.consultas.datos == {} and mundo.trabajos.datos == {} and mundo.cola.enviados == []


# ---- leer el informe ----------------------------------------------------------------

def test_sin_consenso_hasta_que_terminan_todos(mundo):
    a, b, c = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b, c])
    mundo.resultado(informe, a, 0.9)
    mundo.resultado(informe, b, 0.8)
    leido = mundo.leer(informe.consulta.id)
    assert leido.estado == "procesando" and leido.consenso is None
    assert all(i.coincide is None for i in leido.inferencias)


def test_completa_con_consenso_ponderado_y_marcas(mundo):
    a, b, c = tres(mundo)                                   # pesos AUC 0,99 · 0,97 · 0,95
    informe = mundo.crear(mundo.estudio(), [a, b, c])
    mundo.resultado(informe, a, 0.9)
    mundo.resultado(informe, b, 0.8)
    mundo.resultado(informe, c, 0.1)
    leido = mundo.leer(informe.consulta.id)

    assert leido.estado == "completa"
    assert leido.consenso.prediccion == "PNEUMONIA" and leido.consenso.votos == 3
    assert leido.consenso.acuerdo == pytest.approx(1.96 / 2.91)
    assert leido.consenso.revision_prioritaria                       # 0,67 < 0,70
    por_nombre = {i.modelo.nombre: i for i in leido.inferencias}
    assert por_nombre["mediscan"].coincide and por_nombre["densenet"].coincide
    assert por_nombre["efficientnet"].coincide is False
    assert por_nombre["mediscan"].peso.metrica == "auc" and por_nombre["mediscan"].peso.valor == 0.99
    assert [i.modelo.nombre for i in leido.inferencias] == ["mediscan", "densenet", "efficientnet"]


def test_unanimes_no_piden_revision(mundo):
    a, b, c = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b, c])
    for m in (a, b, c):
        mundo.resultado(informe, m, 0.1)
    leido = mundo.leer(informe.consulta.id)
    assert leido.consenso.prediccion == "NORMAL" and leido.consenso.acuerdo == pytest.approx(1.0)
    assert not leido.consenso.revision_prioritaria


def test_parcial_con_un_modelo_caido_consensua_los_otros_dos(mundo):
    """Criterio de aceptación 5 de la spec: junta de 3 con uno caído, informe de los otros dos."""
    a, b, c = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b, c])
    mundo.resultado(informe, a, 0.9)
    mundo.resultado(informe, b, 0.7)
    mundo.resultado(informe, c, error="el worker no respondió tras 3 intentos")
    leido = mundo.leer(informe.consulta.id)
    assert leido.estado == "parcial"
    assert leido.consenso.votos == 2 and leido.consenso.prediccion == "PNEUMONIA"
    caido = next(i for i in leido.inferencias if i.modelo.id == c.id)
    assert caido.coincide is None and caido.trabajo.error


def test_con_una_sola_ok_no_hay_consenso(mundo):
    a, b, _ = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b])
    mundo.resultado(informe, a, 0.9)
    mundo.resultado(informe, b, error="imagen ilegible")
    leido = mundo.leer(informe.consulta.id)
    assert leido.estado == "parcial" and leido.consenso is None


def test_si_fallan_todas_la_consulta_es_error(mundo):
    a, b, _ = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b])
    mundo.resultado(informe, a, error="x")
    mundo.resultado(informe, b, error="y")
    leido = mundo.leer(informe.consulta.id)
    assert leido.estado == "error" and leido.consenso is None


def test_un_modelo_que_se_esta_reevaluando_no_vota(mundo):
    a, b, c = tres(mundo)
    informe = mundo.crear(mundo.estudio(), [a, b, c])
    for m in (a, b, c):
        mundo.resultado(informe, m, 0.9)
    c.estado_evaluacion, c.accuracy, c.metricas = "pendiente", None, None      # lo volvieron a publicar
    leido = mundo.leer(informe.consulta.id)
    assert leido.consenso.votos == 2
    reevaluado = next(i for i in leido.inferencias if i.modelo.id == c.id)
    assert reevaluado.peso is None and reevaluado.coincide is None
    assert leido.inferencias[-1].modelo.id == c.id                             # sin peso, al final


def test_consulta_inexistente_es_404(mundo):
    with pytest.raises(NoEncontrado):
        mundo.leer(uuid4())
