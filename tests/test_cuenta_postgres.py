"""Integración optativa: el tipo de cuenta contra Postgres de verdad, con pedidos a la vez. Usa la
misma base exclusiva de pruebas que test_demo_postgres.py, nunca la del usuario."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

from app.infraestructura.postgres import migraciones
from app.infraestructura.postgres.conexion import crear_pool
from app.infraestructura.postgres.repositorios import RepositorioCuentasPostgres

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DEMO_DATABASE_URL"), reason="requiere base exclusiva de integración")

AHORA = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    url = os.environ["TEST_DEMO_DATABASE_URL"]
    migraciones.aplicar(url, Path("migraciones"))
    pool = crear_pool(url, maximo=8)
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute("delete from cuenta where sub like 'prueba-%'")
    yield RepositorioCuentasPostgres(pool)
    pool.close()


def test_el_primero_fija_el_tipo_y_los_demas_lo_leen(repo):
    assert repo.fijar_tipo("prueba-1", "institucion", AHORA) == "institucion"
    assert repo.fijar_tipo("prueba-1", "publicador", AHORA) == "institucion"
    assert repo.fijar_tipo("prueba-1", "institucion", AHORA) == "institucion"


def test_a_la_vez_entra_uno_solo_y_todos_leen_ese(repo):
    tipos = ["institucion", "publicador"] * 8
    with ThreadPoolExecutor(max_workers=8) as hilos:
        vistos = list(hilos.map(lambda tipo: repo.fijar_tipo("prueba-carrera", tipo, AHORA), tipos))
    assert len(set(vistos)) == 1


def test_la_base_no_acepta_medico_ni_admin(repo):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.fijar_tipo("prueba-2", "medico", AHORA)
