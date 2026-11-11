"""Elegir el tipo de cuenta (institución o publicador) una sola vez, con fakes de Cognito y de la base."""

from __future__ import annotations

import pytest

from app.aplicacion.casos_uso.cuenta import ElegirTipoCuenta, TipoElegido
from app.dominio.cuenta import GRUPO_POR_TIPO
from app.dominio.errores import Conflicto, EntradaInvalida, NoAutenticado, ServicioNoDisponible
from app.dominio.usuario import ADMIN_INSTITUCION, ADMIN_PLATAFORMA, MEDICO, PUBLICADOR, Usuario

from .fakes import SIN_ROL, DirectorioMemoria, RelojFijo, RepoCuentasMemoria

USERNAME = SIN_ROL.username     # "usuario-sin-rol": no es el sub


@pytest.fixture
def mundo():
    class Mundo:
        cuentas = RepoCuentasMemoria()
        directorio = DirectorioMemoria({USERNAME: []})
        reloj = RelojFijo()

        def elegir(self, tipo, usuario=SIN_ROL):
            return ElegirTipoCuenta(self.cuentas, self.directorio, self.reloj).ejecutar(usuario, tipo)

        @property
        def grupos(self):
            return self.directorio.cuentas[USERNAME]

    return Mundo()


class DirectorioDesfasado(DirectorioMemoria):
    """Lee los grupos como estaban antes de que nadie eligiera: lo que ve un pedido que arrancó a la
    vez que otro (dos pestañas, dos clics)."""

    def grupos_de(self, username):
        super().grupos_de(username)
        return ()


# ---- la primera vez -------------------------------------------------------------------

@pytest.mark.parametrize("tipo, grupo", [("institucion", ADMIN_INSTITUCION), ("publicador", PUBLICADOR)])
def test_la_primera_eleccion_fija_el_tipo_y_da_el_grupo(mundo, tipo, grupo):
    assert mundo.elegir(tipo) == TipoElegido(tipo, grupo)
    assert mundo.cuentas.tipos == {SIN_ROL.sub: tipo}                    # la base, por sub
    assert mundo.cuentas.elegidas[SIN_ROL.sub] == mundo.reloj.ahora()
    assert mundo.directorio.agregados == [(USERNAME, grupo)]             # Cognito, por username
    assert mundo.grupos == [grupo]


def test_repetir_la_misma_no_cambia_nada(mundo):
    mundo.elegir("publicador")
    primera = mundo.reloj.ahora()
    mundo.reloj.avanzar(60)
    assert mundo.elegir("publicador") == TipoElegido("publicador", PUBLICADOR)
    assert mundo.directorio.agregados == [(USERNAME, PUBLICADOR)]        # una sola vez
    assert mundo.cuentas.elegidas[SIN_ROL.sub] == primera


def test_una_eleccion_distinta_es_409_y_no_cambia_nada(mundo):
    mundo.elegir("institucion")
    with pytest.raises(Conflicto, match="ya es de institución: el tipo se elige una sola vez"):
        mundo.elegir("publicador")
    assert mundo.grupos == [ADMIN_INSTITUCION]
    assert mundo.cuentas.tipos == {SIN_ROL.sub: "institucion"}


# ---- lo que ya hay en Cognito ---------------------------------------------------------

@pytest.mark.parametrize("tipo, grupo", [("institucion", ADMIN_INSTITUCION), ("publicador", PUBLICADOR)])
def test_con_ese_mismo_grupo_ya_en_cognito_no_hay_nada_que_hacer(mundo, tipo, grupo):
    """Se registró por «crear cuenta» (la Lambda le dio el grupo) y el token que trae es de antes."""
    mundo.directorio.cuentas[USERNAME] = [grupo]
    assert mundo.elegir(tipo) == TipoElegido(tipo, grupo)
    assert mundo.directorio.agregados == [] and mundo.cuentas.tipos == {}


@pytest.mark.parametrize("grupos, tipo, dice", [
    ([PUBLICADOR], "institucion", "ya es de publicador"),
    ([ADMIN_INSTITUCION], "publicador", "ya es de institución"),
    ([MEDICO], "institucion", "ya es de médico"),                            # lo invitó una institución
    ([ADMIN_PLATAFORMA], "publicador", "ya es de administración de Ateneo"),
    ([PUBLICADOR, MEDICO], "publicador", "ya es de publicador y médico"),    # el mismo y otro: tampoco
])
def test_con_otro_grupo_en_cognito_es_409_y_no_cambia_nada(mundo, grupos, tipo, dice):
    mundo.directorio.cuentas[USERNAME] = list(grupos)
    with pytest.raises(Conflicto, match=dice):
        mundo.elegir(tipo)
    assert mundo.grupos == grupos
    assert mundo.directorio.agregados == [] and mundo.cuentas.tipos == {}


def test_decide_con_los_grupos_de_cognito_y_no_con_los_del_token(mundo):
    """El token dice «sin grupos» porque se emitió antes de que otra pestaña eligiera."""
    mundo.directorio.cuentas[USERNAME] = [ADMIN_INSTITUCION]
    assert SIN_ROL.grupos == ()
    with pytest.raises(Conflicto):
        mundo.elegir("publicador", usuario=SIN_ROL)
    assert mundo.grupos == [ADMIN_INSTITUCION]


# ---- carreras y fallas a mitad de camino ----------------------------------------------

def test_dos_pedidos_a_la_vez_dejan_un_solo_tipo(mundo):
    """Los dos ven Cognito sin grupos; en la base entra uno solo, y el otro recibe 409."""
    mundo.directorio = DirectorioDesfasado({USERNAME: []})
    assert mundo.elegir("institucion").grupo == ADMIN_INSTITUCION
    with pytest.raises(Conflicto, match="ya se eligió como institución"):
        mundo.elegir("publicador")
    assert mundo.grupos == [ADMIN_INSTITUCION]
    assert all(grupo == ADMIN_INSTITUCION for _, grupo in mundo.directorio.agregados)


def test_si_cognito_falla_al_agregar_repetir_la_misma_lo_completa(mundo):
    mundo.directorio.falla_al_agregar = True
    with pytest.raises(ServicioNoDisponible):
        mundo.elegir("publicador")
    assert mundo.cuentas.tipos == {SIN_ROL.sub: "publicador"} and mundo.grupos == []   # la elección ya quedó
    mundo.directorio.falla_al_agregar = False
    assert mundo.elegir("publicador").grupo == PUBLICADOR
    assert mundo.grupos == [PUBLICADOR]


def test_despues_de_esa_falla_otra_eleccion_es_409_y_completa_la_primera(mundo):
    """Así, después de un 409 el login siempre trae un grupo: el sitio no queda dando vueltas."""
    mundo.directorio.falla_al_agregar = True
    with pytest.raises(ServicioNoDisponible):
        mundo.elegir("publicador")
    mundo.directorio.falla_al_agregar = False
    with pytest.raises(Conflicto, match="ya se eligió como publicador"):
        mundo.elegir("institucion")
    assert mundo.grupos == [PUBLICADOR]


def test_con_cognito_caido_es_502_y_no_fija_nada(mundo):
    mundo.directorio.caido = True
    with pytest.raises(ServicioNoDisponible):
        mundo.elegir("institucion")
    assert mundo.cuentas.tipos == {}


# ---- lo que no se elige ---------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["medico", "admin_plataforma", "admin_institucion", "admin", "", "Publicador",
                                  "institución", " publicador"])
def test_un_tipo_que_no_se_elige_es_422_y_no_toca_nada(mundo, tipo):
    with pytest.raises(EntradaInvalida, match="«institucion» o «publicador»"):
        mundo.elegir(tipo)
    assert mundo.cuentas.tipos == {} and mundo.directorio.agregados == [] and mundo.grupos == []


def test_nunca_se_puede_elegir_medico_ni_admin():
    """Los únicos grupos que da esta ruta: los demás llegan por invitación o con la infraestructura."""
    assert GRUPO_POR_TIPO == {"institucion": ADMIN_INSTITUCION, "publicador": PUBLICADOR}
    assert not {MEDICO, ADMIN_PLATAFORMA} & set(GRUPO_POR_TIPO.values())


def test_sin_cognito_el_anonimo_ya_tiene_todos_los_roles_y_es_409():
    caso = ElegirTipoCuenta(RepoCuentasMemoria(), None, RelojFijo())
    with pytest.raises(Conflicto, match="sin Cognito"):
        caso.ejecutar(Usuario.anonimo(), "publicador")


def test_un_token_sin_username_es_401_y_no_fija_nada(mundo):
    with pytest.raises(NoAutenticado):
        mundo.elegir("publicador", usuario=Usuario(SIN_ROL.sub))
    assert mundo.cuentas.tipos == {}


def test_una_cuenta_que_ya_no_esta_en_cognito_es_401(mundo):
    with pytest.raises(NoAutenticado):
        mundo.elegir("publicador", usuario=Usuario("sub-borrado", username="borrado"))
    assert mundo.cuentas.tipos == {}
