from __future__ import annotations

import copy

import pytest

from app.aplicacion.casos_uso.estudios import CrearEstudio
from app.aplicacion.casos_uso.inferencias import ConsultarTrabajo, EncolarInferencia
from app.aplicacion.casos_uso.modelos import (
    ListarModelosDisponibles, PrepararSubidaModelo, PublicarModelo,
)
from app.dominio.errores import Conflicto, EntradaInvalida, NoEncontrado, SinPermiso
from app.dominio.usuario import Usuario

from .fakes import (
    ADMIN, INSTITUCION, MEDICO_A, MEDICO_B, PUBLICADOR_A, PUBLICADOR_B, AlmacenMemoria, CatalogoMemoria,
    ColaFalsa, RelojFijo, RepoEstudiosMemoria, RepoModelosMemoria, RepoTrabajosMemoria,
)

CONTRATO = {
    "nombre": "torax", "version": "1.0.0", "tipo_estudio": "torax-rx", "tarea": "clasificacion",
    "entrada": {"layout": "NCHW", "forma": [1, 3, 224, 224], "espacio_color": "RGB"},
    "salida": {"tipo": "logits", "etiquetas": ["NORMAL", "PNEUMONIA"], "positiva": "PNEUMONIA"},
}
PREFIX = "modelos/torax/1.0.0/"


@pytest.fixture
def mundo():
    class Mundo:
        reloj = RelojFijo()
        modelos = RepoModelosMemoria()
        estudios = RepoEstudiosMemoria()
        trabajos = RepoTrabajosMemoria()
        almacen = AlmacenMemoria()
        catalogo = CatalogoMemoria({PREFIX: copy.deepcopy(CONTRATO)})
        inferencias = ColaFalsa()
        evaluaciones = ColaFalsa()

        def publicar(self, usuario=PUBLICADOR_A):
            return PublicarModelo(self.catalogo, self.modelos, self.reloj, "modelos/",
                                  self.evaluaciones).ejecutar(usuario, "torax", "1.0.0")

        def preparar_subida(self, nombre="torax-nuevo", version="2.0.0", tamano=16_000_000,
                            max_bytes=512_000_000):
            return PrepararSubidaModelo(self.catalogo, max_bytes, "modelos/").ejecutar(nombre, version, tamano)

        def publicar_subido(self, contrato, nombre=None, version=None, usuario=PUBLICADOR_A):
            """El camino de la interfaz: el ONNX ya está en el bucket y el contrato viaja en el pedido."""
            return PublicarModelo(self.catalogo, self.modelos, self.reloj, "modelos/", self.evaluaciones).ejecutar(
                usuario, nombre or contrato["nombre"], version or contrato["version"], contrato,
            )

        def crear_estudio(self, tipo="torax-rx", subido=True, usuario=MEDICO_A):
            c = CrearEstudio(self.estudios, self.almacen, self.reloj, 20_000_000, "estudios/").ejecutar(
                usuario, tipo, "image/png", 1234)
            if subido:
                self.almacen.objetos[c.estudio.s3_key] = 1234
            return c.estudio

        def encolar(self, estudio, modelo, usuario=MEDICO_A):
            return EncolarInferencia(self.estudios, self.modelos, self.trabajos, self.almacen, self.reloj,
                                     self.inferencias, "b-modelos", "b-estudios").ejecutar(usuario, estudio.id, modelo.id)

        def consultar(self, trabajo, usuario=MEDICO_A):
            return ConsultarTrabajo(self.trabajos).ejecutar(usuario, trabajo.id)

    return Mundo()


# ---- publicar -----------------------------------------------------------------------

def test_publicar_da_de_alta_en_pendiente(mundo):
    m = mundo.publicar()
    assert m.estado_evaluacion == "pendiente" and m.etiquetas == ["NORMAL", "PNEUMONIA"]
    assert m.s3_prefix == PREFIX and m.accuracy is None


def test_republicar_mientras_esta_pendiente_es_conflicto(mundo):
    mundo.publicar()
    with pytest.raises(Conflicto):
        mundo.publicar()


def test_republicar_un_modelo_evaluado_lo_reencola(mundo):
    m = mundo.publicar()
    m.estado_evaluacion, m.accuracy, m.metricas = "ok", 0.9, {"accuracy": 0.9}
    m2 = mundo.publicar()
    assert m2.id == m.id and m2.estado_evaluacion == "pendiente" and m2.accuracy is None


def test_publicar_deja_el_pedido_en_la_cola_de_evaluaciones(mundo):
    m = mundo.publicar()
    assert [p.como_mensaje() for p in mundo.evaluaciones.enviados] == [{
        "tipo": "evaluar_modelo", "modelo_id": str(m.id), "nombre": "torax", "version": "1.0.0",
        "tipo_estudio": "torax-rx", "prefix": PREFIX, "etiquetas": ["NORMAL", "PNEUMONIA"],
    }]


def test_publicar_sin_cola_deja_el_modelo_en_error_y_se_puede_republicar(mundo):
    mundo.evaluaciones.caida = True
    m = mundo.publicar()
    assert m.estado_evaluacion == "error" and "volvé a publicar" in m.error
    mundo.evaluaciones.caida = False
    assert mundo.publicar().estado_evaluacion == "pendiente"


def test_publicar_contrato_invalido(mundo):
    mundo.catalogo.contratos[PREFIX]["salida"]["etiquetas"] = ["A"]
    with pytest.raises(EntradaInvalida):
        mundo.publicar()
    assert mundo.modelos.listar() == []


def test_publicar_inexistente(mundo):
    with pytest.raises(NoEncontrado):
        PublicarModelo(mundo.catalogo, mundo.modelos, mundo.reloj, "modelos/", mundo.evaluaciones).ejecutar(
            PUBLICADOR_A, "otro", "1")


def test_disponibles_marca_publicados(mundo):
    antes = ListarModelosDisponibles(mundo.catalogo, mundo.modelos).ejecutar()
    assert antes[0].publicado is False and antes[0].tipo_estudio == "torax-rx"
    m = mundo.publicar()
    despues = ListarModelosDisponibles(mundo.catalogo, mundo.modelos).ejecutar()
    assert despues[0].publicado is True and despues[0].modelo_id == m.id



# ---- subir el modelo desde la interfaz ----------------------------------------------

NUEVO = "modelos/torax-nuevo/2.0.0/"


def contrato_nuevo():
    c = copy.deepcopy(CONTRATO)
    c["nombre"], c["version"] = "torax-nuevo", "2.0.0"
    return c


def test_preparar_subida_firma_el_prefijo_pedido(mundo):
    s = mundo.preparar_subida()
    assert s.prefix == NUEVO and mundo.catalogo.firmadas == [NUEVO]
    assert s.subida.campos["key"] == f"{NUEVO}modelo.onnx"


def test_preparar_subida_no_pisa_una_version_que_ya_existe(mundo):
    with pytest.raises(Conflicto):
        mundo.preparar_subida("torax", "1.0.0")


def test_preparar_subida_rechaza_un_archivo_fuera_de_rango(mundo):
    with pytest.raises(EntradaInvalida):
        mundo.preparar_subida(tamano=2, max_bytes=1)


def test_publicar_subido_escribe_el_contrato_al_lado_del_onnx(mundo):
    mundo.catalogo.onnx.add(NUEVO)
    m = mundo.publicar_subido(contrato_nuevo())
    assert m.estado_evaluacion == "pendiente" and m.s3_prefix == NUEVO
    assert mundo.catalogo.contratos[NUEVO]["nombre"] == "torax-nuevo"


def test_publicar_subido_sin_el_onnx_no_escribe_el_contrato(mundo):
    with pytest.raises(NoEncontrado):
        mundo.publicar_subido(contrato_nuevo())
    assert NUEVO not in mundo.catalogo.contratos


def test_publicar_subido_con_contrato_invalido_no_escribe_nada(mundo):
    mundo.catalogo.onnx.add(NUEVO)
    malo = contrato_nuevo()
    malo["salida"]["etiquetas"] = ["UNA_SOLA"]
    with pytest.raises(EntradaInvalida):
        mundo.publicar_subido(malo)
    assert NUEVO not in mundo.catalogo.contratos


def test_publicar_subido_con_un_contrato_de_otro_modelo(mundo):
    mundo.catalogo.onnx.add(NUEVO)
    with pytest.raises(EntradaInvalida):
        mundo.publicar_subido(contrato_nuevo(), version="9.9.9")


# ---- estudios e inferencias ---------------------------------------------------------

def test_crear_estudio_firma_subida(mundo):
    c = CrearEstudio(mundo.estudios, mundo.almacen, mundo.reloj, 20_000_000, "estudios/").ejecutar(
        MEDICO_A, "torax-rx", "image/jpeg", 10)
    assert c.estudio.s3_key.startswith("estudios/") and c.estudio.s3_key.endswith(".jpg")
    assert c.subida.campos["key"] == c.estudio.s3_key


def test_crear_estudio_mime_o_tamano_invalido(mundo):
    caso = CrearEstudio(mundo.estudios, mundo.almacen, mundo.reloj, 100, "estudios/")
    with pytest.raises(EntradaInvalida):
        caso.ejecutar(MEDICO_A, "torax-rx", "image/gif", 10)
    with pytest.raises(EntradaInvalida):
        caso.ejecutar(MEDICO_A, "torax-rx", "image/png", 101)


def test_encolar_confirma_y_deja_pendiente(mundo):
    m = mundo.publicar()
    e = mundo.crear_estudio()
    t = mundo.encolar(e, m)
    assert t.estado == "pendiente" and t.intentos == 0
    assert mundo.estudios.obtener(e.id).estado == "subido"


def test_encolar_sin_archivo_subido_es_conflicto(mundo):
    m = mundo.publicar()
    e = mundo.crear_estudio(subido=False)
    with pytest.raises(Conflicto):
        mundo.encolar(e, m)


def test_encolar_tipo_distinto(mundo):
    m = mundo.publicar()
    e = mundo.crear_estudio(tipo="cerebro-mri")
    with pytest.raises(EntradaInvalida):
        mundo.encolar(e, m)


# ---- autoría: de quién es cada cosa -------------------------------------------------

def test_cada_cosa_guarda_el_sub_de_quien_la_creo(mundo):
    m = mundo.publicar(PUBLICADOR_A)
    e = mundo.crear_estudio(usuario=MEDICO_A)
    t = mundo.encolar(e, m, MEDICO_A)
    assert m.publicado_por == PUBLICADOR_A.sub
    assert mundo.estudios.obtener(e.id).creado_por == MEDICO_A.sub
    assert mundo.trabajos.obtener(t.id).creado_por == MEDICO_A.sub


def test_cada_uno_ve_su_trabajo(mundo):
    m = mundo.publicar()
    t = mundo.encolar(mundo.crear_estudio(usuario=INSTITUCION), m, INSTITUCION)
    assert mundo.consultar(t, INSTITUCION).id == t.id


def test_el_trabajo_ajeno_da_el_mismo_404_que_uno_que_no_existe(mundo):
    """Tener el UUID no alcanza, y el mensaje no confirma que el trabajo exista."""
    t = mundo.encolar(mundo.crear_estudio(), mundo.publicar())
    with pytest.raises(NoEncontrado) as ajeno:
        mundo.consultar(t, MEDICO_B)
    mundo.trabajos.datos.clear()
    with pytest.raises(NoEncontrado) as inexistente:
        mundo.consultar(t, MEDICO_B)
    assert ajeno.value.detalle == inexistente.value.detalle == f"no existe el trabajo {t.id}"


def test_encolar_sobre_un_estudio_ajeno_es_404_y_no_toca_nada(mundo):
    m = mundo.publicar()
    e = mundo.crear_estudio(usuario=MEDICO_A)
    with pytest.raises(NoEncontrado, match=f"^no existe el estudio {e.id}$"):
        mundo.encolar(e, m, MEDICO_B)
    assert mundo.estudios.obtener(e.id).estado == "pendiente_subida"      # no se confirmó la subida
    assert mundo.trabajos.datos == {} and mundo.inferencias.enviados == []


def test_el_admin_de_plataforma_ve_y_usa_lo_de_todos(mundo):
    m = mundo.publicar()
    e = mundo.crear_estudio(usuario=MEDICO_A)
    t = mundo.encolar(e, m, MEDICO_A)
    assert mundo.consultar(t, ADMIN).id == t.id
    t_admin = mundo.encolar(e, m, ADMIN)
    assert t_admin.creado_por == ADMIN.sub
    with pytest.raises(NoEncontrado):                       # y el suyo es suyo: el médico no lo ve
        mundo.consultar(t_admin, MEDICO_A)


def test_lo_anterior_a_la_migracion_no_es_de_nadie(mundo):
    """Las filas sin `creado_por` solo las ve un admin."""
    t = mundo.encolar(mundo.crear_estudio(), mundo.publicar())
    mundo.trabajos.obtener(t.id).creado_por = None
    with pytest.raises(NoEncontrado):
        mundo.consultar(t, MEDICO_A)
    assert mundo.consultar(t, ADMIN).id == t.id


def test_sin_cognito_el_anonimo_ve_todo_como_antes(mundo):
    t = mundo.encolar(mundo.crear_estudio(usuario=MEDICO_A), mundo.publicar())
    assert mundo.consultar(t, Usuario.anonimo()).id == t.id


def test_republicar_no_cambia_quien_lo_publico(mundo):
    m = mundo.publicar(PUBLICADOR_A)
    m.estado_evaluacion = "ok"
    assert mundo.publicar(PUBLICADOR_B).publicado_por == PUBLICADOR_A.sub


def test_cualquier_publicador_puede_volver_a_evaluarlo_sin_contrato(mundo):
    """El botón «Reevaluar»: no cambia nada del modelo, solo lo vuelve a medir."""
    m = mundo.publicar(PUBLICADOR_A)
    m.estado_evaluacion = "ok"
    assert mundo.publicar(PUBLICADOR_B).estado_evaluacion == "pendiente"


def test_cambiarle_el_contrato_a_un_modelo_ajeno_es_sin_permiso_y_no_escribe_nada(mundo):
    mundo.catalogo.onnx.add(NUEVO)
    m = mundo.publicar_subido(contrato_nuevo(), usuario=PUBLICADOR_A)
    m.estado_evaluacion = "ok"
    otro = contrato_nuevo()
    otro["salida"]["etiquetas"] = ["PNEUMONIA", "NORMAL"]          # las etiquetas al revés
    with pytest.raises(SinPermiso):
        mundo.publicar_subido(otro, usuario=PUBLICADOR_B)
    assert mundo.catalogo.contratos[NUEVO]["salida"]["etiquetas"] == ["NORMAL", "PNEUMONIA"]
    assert mundo.modelos.obtener(m.id).estado_evaluacion == "ok"


def test_el_autor_y_el_admin_si_le_cambian_el_contrato(mundo):
    mundo.catalogo.onnx.add(NUEVO)
    m = mundo.publicar_subido(contrato_nuevo(), usuario=PUBLICADOR_A)
    for quien in (PUBLICADOR_A, ADMIN):
        m.estado_evaluacion = "ok"
        assert mundo.publicar_subido(contrato_nuevo(), usuario=quien).estado_evaluacion == "pendiente"
