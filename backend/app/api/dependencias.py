"""Composition root de la API: el único módulo que instancia adaptadores para ella.

`Contenedor` arma el grafo una vez por proceso; las funciones `Depends` de abajo
son lo que reciben los routers. Los tests reemplazan estas funciones con
`app.dependency_overrides`. El procesador tiene su propio armado (procesador.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request

from ..aplicacion.casos_uso.consultas import ConsultarConsulta, CrearConsulta
from ..aplicacion.casos_uso.cuenta import ConsultarTipoCuenta, ElegirTipoCuenta
from ..aplicacion.casos_uso.estudios import CrearEstudio
from ..aplicacion.casos_uso.inferencias import ConsultarTrabajo, EncolarInferencia
from ..aplicacion.casos_uso.modelos import (
    ConsultarModelo, ListarModelos, ListarModelosDisponibles, PrepararSubidaModelo, PublicarModelo,
)
from ..aplicacion.puertos import DirectorioCuentas, VerificadorTokens
from ..config import Settings
from ..dominio.errores import NoAutenticado
from ..dominio.usuario import Usuario
from ..infraestructura.aws import cliente_cognito, cliente_s3, cliente_sqs
from ..infraestructura.cognito.directorio import DirectorioCognito
from ..infraestructura.cognito.verificador import VerificadorCognito
from ..infraestructura.postgres.conexion import crear_pool
from ..infraestructura.postgres.repositorios import (
    RepositorioConsultasPostgres, RepositorioCuentasPostgres, RepositorioEstudiosPostgres,
    RepositorioModelosPostgres, RepositorioTrabajosPostgres,
)
from ..infraestructura.reloj import RelojSistema
from ..infraestructura.s3.almacen_estudios import AlmacenEstudiosS3
from ..infraestructura.s3.catalogo_modelos import CatalogoModelosS3
from ..infraestructura.sqs.colas import ColaSqs


@dataclass
class Contenedor:
    settings: Settings
    listar_disponibles: ListarModelosDisponibles
    preparar_subida: PrepararSubidaModelo
    publicar_modelo: PublicarModelo
    listar_modelos: ListarModelos
    consultar_modelo: ConsultarModelo
    crear_estudio: CrearEstudio
    encolar_inferencia: EncolarInferencia
    consultar_trabajo: ConsultarTrabajo
    crear_consulta: CrearConsulta
    consultar_consulta: ConsultarConsulta
    elegir_tipo_cuenta: ElegirTipoCuenta
    consultar_tipo_cuenta: ConsultarTipoCuenta
    pool: object
    verificador: VerificadorTokens | None      # None = sin Cognito: todos anónimos

    def abrir(self) -> None:
        self.pool.open()          # type: ignore[attr-defined]

    def cerrar(self) -> None:
        self.pool.close()         # type: ignore[attr-defined]


def armar(settings: Settings) -> Contenedor:
    settings.exigir("cola_evaluaciones_url")
    pool = crear_pool(settings.database_url)
    s3 = cliente_s3(settings.aws_region)
    sqs = cliente_sqs(settings.aws_region)
    reloj = RelojSistema()

    modelos = RepositorioModelosPostgres(pool)
    estudios = RepositorioEstudiosPostgres(pool)
    trabajos = RepositorioTrabajosPostgres(pool)
    consultas = RepositorioConsultasPostgres(pool)
    almacen = AlmacenEstudiosS3(s3, settings.bucket_estudios, settings.s3_url_publica)
    catalogo = CatalogoModelosS3(s3, settings.bucket_modelos, settings.prefijo_modelos, settings.s3_url_publica)
    inferencias = ColaSqs(sqs, settings.cola_inferencias_url)
    evaluaciones = ColaSqs(sqs, settings.cola_evaluaciones_url)

    verificador: VerificadorTokens | None = None
    directorio: DirectorioCuentas | None = None    # sin Cognito nadie elige tipo: el anónimo ya puede todo
    if settings.cognito_user_pool_id:
        verificador = VerificadorCognito(settings.aws_region, settings.cognito_user_pool_id,
                                         settings.clientes_cognito)
        directorio = DirectorioCognito(cliente_cognito(settings.aws_region), settings.cognito_user_pool_id)

    return Contenedor(
        settings=settings,
        listar_disponibles=ListarModelosDisponibles(catalogo, modelos),
        preparar_subida=PrepararSubidaModelo(catalogo, settings.max_bytes_modelo, settings.prefijo_modelos),
        publicar_modelo=PublicarModelo(catalogo, modelos, reloj, settings.prefijo_modelos, evaluaciones),
        listar_modelos=ListarModelos(modelos),
        consultar_modelo=ConsultarModelo(modelos),
        crear_estudio=CrearEstudio(estudios, almacen, reloj, settings.max_bytes_estudio, settings.prefijo_estudios),
        encolar_inferencia=EncolarInferencia(estudios, modelos, trabajos, almacen, reloj, inferencias,
                                             settings.bucket_modelos, settings.bucket_estudios),
        consultar_trabajo=ConsultarTrabajo(trabajos),
        crear_consulta=CrearConsulta(estudios, modelos, consultas, almacen, reloj, inferencias,
                                     settings.bucket_modelos, settings.bucket_estudios),
        consultar_consulta=ConsultarConsulta(consultas, modelos),
        elegir_tipo_cuenta=ElegirTipoCuenta(RepositorioCuentasPostgres(pool), directorio, reloj),
        consultar_tipo_cuenta=ConsultarTipoCuenta(directorio),
        pool=pool,
        verificador=verificador,
    )


# ---- lo que reciben los routers -----------------------------------------------------

def contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


def dep_listar_disponibles(request: Request) -> ListarModelosDisponibles:
    return contenedor(request).listar_disponibles


def dep_preparar_subida(request: Request) -> PrepararSubidaModelo:
    return contenedor(request).preparar_subida


def dep_publicar_modelo(request: Request) -> PublicarModelo:
    return contenedor(request).publicar_modelo


def dep_listar_modelos(request: Request) -> ListarModelos:
    return contenedor(request).listar_modelos


def dep_consultar_modelo(request: Request) -> ConsultarModelo:
    return contenedor(request).consultar_modelo


def dep_crear_estudio(request: Request) -> CrearEstudio:
    return contenedor(request).crear_estudio


def dep_encolar_inferencia(request: Request) -> EncolarInferencia:
    return contenedor(request).encolar_inferencia


def dep_consultar_trabajo(request: Request) -> ConsultarTrabajo:
    return contenedor(request).consultar_trabajo


def dep_crear_consulta(request: Request) -> CrearConsulta:
    return contenedor(request).crear_consulta


def dep_consultar_consulta(request: Request) -> ConsultarConsulta:
    return contenedor(request).consultar_consulta


def dep_elegir_tipo_cuenta(request: Request) -> ElegirTipoCuenta:
    return contenedor(request).elegir_tipo_cuenta


def dep_consultar_tipo_cuenta(request: Request) -> ConsultarTipoCuenta:
    return contenedor(request).consultar_tipo_cuenta


def dep_verificador(request: Request) -> VerificadorTokens | None:
    return contenedor(request).verificador


def usuario_actual(request: Request, verificador: VerificadorTokens | None = Depends(dep_verificador)) -> Usuario:
    """El usuario del access token de Cognito (Authorization: Bearer …). Sin Cognito, anónimo."""
    if verificador is None:
        return Usuario.anonimo()
    tipo, _, token = request.headers.get("authorization", "").partition(" ")
    if tipo.lower() != "bearer" or not token.strip():
        raise NoAutenticado("falta el token: ingresá de nuevo")
    return verificador.verificar(token.strip())


def exigir_grupos(*grupos: str) -> Callable[..., Usuario]:
    """Para el `dependencies=` de un router: sin token, 401; sin ninguno de `grupos`, 403
    `sin_permiso`. Sin Cognito, el anónimo trae todos los grupos y pasa (Usuario.anonimo)."""
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        usuario.exigir(grupos)
        return usuario
    return dependencia
