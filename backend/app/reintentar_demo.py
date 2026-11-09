"""Recuperación explícita de la demo; nunca borra otros modelos ni resultados válidos."""
import argparse

from tools.demo_assets import seleccionar

from .aplicacion.casos_uso.modelos import PublicarModelo
from .aplicacion.puertos import PeticionEvaluacion
from .config import Settings
from .demo import ConexionPrestada, InicializarModelo, OutboxDemo
from .dominio.usuario import Usuario
from .infraestructura.aws import cliente_s3, cliente_sqs
from .infraestructura.postgres.conexion import crear_pool
from .infraestructura.postgres.repositorios import RepositorioModelosPostgres
from .infraestructura.reloj import RelojSistema
from .infraestructura.s3.catalogo_modelos import CatalogoModelosS3


def reintentar(s, pool, s3, sqs, md):
    with pool.connection() as conn:
        conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (md.clave,))
        repo = RepositorioModelosPostgres(ConexionPrestada(conn))
        m = repo.buscar(md.nombre, md.version)
        if m is None:
            raise SystemExit("Primero completá la preparación de artefactos")
        contrato = md.contrato()
        if m.contrato != contrato:
            raise SystemExit("El contrato existente pertenece a otro modelo")
        if m.estado_evaluacion in ("ok", "en_curso"):
            raise SystemExit("La demo está lista o evaluándose: no se modifica")
        conn.execute("delete from demo_inicializacion where clave=%s", (md.clave,))
        outbox = OutboxDemo(conn, md.clave)
        if m.estado_evaluacion == "error":
            PublicarModelo(CatalogoModelosS3(s3, s.bucket_modelos), repo, RelojSistema(),
                           s.prefijo_modelos, outbox).ejecutar(Usuario.plataforma(), md.nombre, md.version)
        else:
            outbox.enviar(PeticionEvaluacion.de(m))
    InicializarModelo(pool, s3, sqs, s, md).ejecutar()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--version", default="1.0.0")
    a = parser.parse_args()
    md = seleccionar(a.nombre, a.version)
    s = Settings()
    if not s.datos_demo:
        raise SystemExit("La demo está desactivada")
    pool = crear_pool(s.database_url)
    pool.open(wait=True)
    s3, sqs = cliente_s3(s.aws_region), cliente_sqs(s.aws_region)
    try:
        reintentar(s, pool, s3, sqs, md)
        print("Recuperación solicitada. Usá tools/esperar_modelo.py para verificar.")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
