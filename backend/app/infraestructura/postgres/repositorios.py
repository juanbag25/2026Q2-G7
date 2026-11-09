"""Repositorios con SQL explícito. Cada método es una transacción corta."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ...dominio.consulta import Consulta
from ...dominio.errores import NoEncontrado
from ...dominio.estudio import Estudio
from ...dominio.modelo import Modelo, ResultadoEvaluacion
from ...dominio.trabajo import ResultadoInferencia, Trabajo


def _float(v: Any) -> float | None:
    return float(v) if isinstance(v, Decimal) else v


# ---- modelo -------------------------------------------------------------------------

COLUMNAS_MODELO = """id, nombre, version, tipo_estudio, tarea, etiquetas, s3_prefix, contrato,
    estado_evaluacion, accuracy, metricas, conjunto, conjunto_version, manifiesto,
    evaluador_id, evaluado_en, error, creado, publicado"""


def _fila_a_modelo(f: dict[str, Any]) -> Modelo:
    return Modelo(
        id=f["id"], nombre=f["nombre"], version=f["version"], tipo_estudio=f["tipo_estudio"],
        tarea=f["tarea"], etiquetas=list(f["etiquetas"]), s3_prefix=f["s3_prefix"], contrato=f["contrato"],
        estado_evaluacion=f["estado_evaluacion"], accuracy=_float(f["accuracy"]), metricas=f["metricas"],
        conjunto=f["conjunto"], conjunto_version=f["conjunto_version"], manifiesto=f["manifiesto"],
        evaluador_id=f["evaluador_id"], evaluado_en=f["evaluado_en"], error=f["error"],
        creado=f["creado"], publicado=f["publicado"],
    )


class RepositorioModelosPostgres:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def guardar(self, m: Modelo) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                f"""
                insert into modelo ({COLUMNAS_MODELO})
                values (%(id)s, %(nombre)s, %(version)s, %(tipo_estudio)s, %(tarea)s, %(etiquetas)s,
                        %(s3_prefix)s, %(contrato)s, %(estado_evaluacion)s, %(accuracy)s, %(metricas)s,
                        %(conjunto)s, %(conjunto_version)s, %(manifiesto)s, %(evaluador_id)s,
                        %(evaluado_en)s, %(error)s, %(creado)s, %(publicado)s)
                on conflict (id) do update set
                    actualizado = now(),
                    tipo_estudio = excluded.tipo_estudio, tarea = excluded.tarea,
                    etiquetas = excluded.etiquetas, contrato = excluded.contrato,
                    estado_evaluacion = excluded.estado_evaluacion, accuracy = excluded.accuracy,
                    metricas = excluded.metricas, conjunto = excluded.conjunto,
                    conjunto_version = excluded.conjunto_version, manifiesto = excluded.manifiesto,
                    evaluador_id = excluded.evaluador_id, evaluado_en = excluded.evaluado_en,
                    error = excluded.error, publicado = excluded.publicado
                """,
                {
                    "id": m.id, "nombre": m.nombre, "version": m.version, "tipo_estudio": m.tipo_estudio,
                    "tarea": m.tarea, "etiquetas": Jsonb(m.etiquetas), "s3_prefix": m.s3_prefix,
                    "contrato": Jsonb(m.contrato), "estado_evaluacion": m.estado_evaluacion,
                    "accuracy": m.accuracy, "metricas": Jsonb(m.metricas) if m.metricas is not None else None,
                    "conjunto": m.conjunto, "conjunto_version": m.conjunto_version,
                    "manifiesto": Jsonb(m.manifiesto) if m.manifiesto is not None else None,
                    "evaluador_id": m.evaluador_id, "evaluado_en": m.evaluado_en, "error": m.error,
                    "creado": m.creado, "publicado": m.publicado,
                },
            )

    def obtener(self, id: UUID) -> Modelo:
        with self._pool.connection() as conn:
            fila = conn.execute(f"select {COLUMNAS_MODELO} from modelo where id = %s", (id,)).fetchone()
        if fila is None:
            raise NoEncontrado(f"no existe el modelo {id}")
        return _fila_a_modelo(fila)

    def buscar(self, nombre: str, version: str) -> Modelo | None:
        with self._pool.connection() as conn:
            fila = conn.execute(
                f"select {COLUMNAS_MODELO} from modelo where nombre = %s and version = %s", (nombre, version)
            ).fetchone()
        return _fila_a_modelo(fila) if fila else None

    def listar(self) -> list[Modelo]:
        with self._pool.connection() as conn:
            filas = conn.execute(f"select {COLUMNAS_MODELO} from modelo order by publicado desc").fetchall()
        return [_fila_a_modelo(f) for f in filas]

    # ---- EvaluacionesSinNoticias (procesador) ----

    def vencer_en_curso(self, minutos: int, motivo: str) -> int:
        with self._pool.connection() as conn:
            return conn.execute(
                """
                update modelo set estado_evaluacion = 'error', error = %s, actualizado = now()
                 where estado_evaluacion = 'en_curso' and actualizado < now() - make_interval(mins => %s)
                """,
                (motivo, minutos),
            ).rowcount


# ---- estudio ------------------------------------------------------------------------

COLUMNAS_ESTUDIO = "id, tipo_estudio, s3_key, content_type, tamano_bytes, estado, creado"


def _fila_a_estudio(f: dict[str, Any]) -> Estudio:
    return Estudio(id=f["id"], tipo_estudio=f["tipo_estudio"], s3_key=f["s3_key"],
                   content_type=f["content_type"], tamano_bytes=f["tamano_bytes"],
                   estado=f["estado"], creado=f["creado"])


class RepositorioEstudiosPostgres:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def guardar(self, e: Estudio) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                f"""
                insert into estudio ({COLUMNAS_ESTUDIO})
                values (%(id)s, %(tipo_estudio)s, %(s3_key)s, %(content_type)s, %(tamano_bytes)s, %(estado)s, %(creado)s)
                on conflict (id) do update set tamano_bytes = excluded.tamano_bytes, estado = excluded.estado
                """,
                {"id": e.id, "tipo_estudio": e.tipo_estudio, "s3_key": e.s3_key, "content_type": e.content_type,
                 "tamano_bytes": e.tamano_bytes, "estado": e.estado, "creado": e.creado},
            )

    def obtener(self, id: UUID) -> Estudio:
        with self._pool.connection() as conn:
            fila = conn.execute(f"select {COLUMNAS_ESTUDIO} from estudio where id = %s", (id,)).fetchone()
        if fila is None:
            raise NoEncontrado(f"no existe el estudio {id}")
        return _fila_a_estudio(fila)


# ---- trabajo ------------------------------------------------------------------------

COLUMNAS_TRABAJO = ("id, estudio_id, modelo_id, estado, intentos, worker_id, resultado, duracion_ms, error, "
                    "creado, actualizado, consulta_id")


def _fila_a_trabajo(f: dict[str, Any]) -> Trabajo:
    return Trabajo(id=f["id"], estudio_id=f["estudio_id"], modelo_id=f["modelo_id"], estado=f["estado"],
                   intentos=f["intentos"], worker_id=f["worker_id"], resultado=f["resultado"],
                   duracion_ms=f["duracion_ms"], error=f["error"], creado=f["creado"], actualizado=f["actualizado"],
                   consulta_id=f["consulta_id"])


def _guardar_trabajo(conn: Connection, t: Trabajo) -> None:
    conn.execute(
        f"""
        insert into trabajo ({COLUMNAS_TRABAJO})
        values (%(id)s, %(estudio_id)s, %(modelo_id)s, %(estado)s, %(intentos)s, %(worker_id)s,
                %(resultado)s, %(duracion_ms)s, %(error)s, %(creado)s, %(actualizado)s, %(consulta_id)s)
        on conflict (id) do update set
            estado = excluded.estado, intentos = excluded.intentos, worker_id = excluded.worker_id,
            resultado = excluded.resultado, duracion_ms = excluded.duracion_ms,
            error = excluded.error, actualizado = excluded.actualizado
        """,
        {"id": t.id, "estudio_id": t.estudio_id, "modelo_id": t.modelo_id, "estado": t.estado,
         "intentos": t.intentos, "worker_id": t.worker_id,
         "resultado": Jsonb(t.resultado) if t.resultado is not None else None,
         "duracion_ms": t.duracion_ms, "error": t.error, "creado": t.creado, "actualizado": t.actualizado,
         "consulta_id": t.consulta_id},
    )


class RepositorioTrabajosPostgres:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def guardar(self, t: Trabajo) -> None:
        with self._pool.connection() as conn:
            _guardar_trabajo(conn, t)

    def obtener(self, id: UUID) -> Trabajo:
        with self._pool.connection() as conn:
            fila = conn.execute(f"select {COLUMNAS_TRABAJO} from trabajo where id = %s", (id,)).fetchone()
        if fila is None:
            raise NoEncontrado(f"no existe el trabajo {id}")
        return _fila_a_trabajo(fila)

    # ---- TrabajosSinEnviar (procesador) ----

    def tomar_para_reenviar(self, minutos: int, limite: int) -> list[Trabajo]:
        """Atómico: tocar `actualizado` hace que otro backend no los reenvíe en la misma vuelta."""
        with self._pool.connection() as conn:
            filas = conn.execute(
                f"""
                update trabajo set actualizado = now()
                 where id in (select id from trabajo
                               where estado = 'pendiente' and actualizado < now() - make_interval(mins => %s)
                               order by actualizado
                               for update skip locked
                               limit %s)
                returning {COLUMNAS_TRABAJO}
                """,
                (minutos, limite),
            ).fetchall()
        return [_fila_a_trabajo(f) for f in filas]

    def vencer_en_curso(self, minutos: int, motivo: str) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute(
                """
                update trabajo set estado = 'error', error = %s, actualizado = now()
                 where estado = 'en_curso' and actualizado < now() - make_interval(mins => %s)
                """,
                (motivo, minutos),
            )
            return cur.rowcount


# ---- consulta (la junta) ------------------------------------------------------------

class RepositorioConsultasPostgres:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def guardar(self, c: Consulta, trabajos: list[Trabajo]) -> None:
        """Una sola transacción: la consulta y todos sus trabajos, o nada."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "insert into consulta (id, estudio_id, creada) values (%s, %s, %s) on conflict (id) do nothing",
                (c.id, c.estudio_id, c.creada),
            )
            for t in trabajos:
                _guardar_trabajo(conn, t)

    def obtener(self, id: UUID) -> Consulta:
        with self._pool.connection() as conn:
            fila = conn.execute("select id, estudio_id, creada from consulta where id = %s", (id,)).fetchone()
        if fila is None:
            raise NoEncontrado(f"no existe la consulta {id}")
        return Consulta(id=fila["id"], estudio_id=fila["estudio_id"], creada=fila["creada"])

    def trabajos_de(self, id: UUID) -> list[Trabajo]:
        with self._pool.connection() as conn:
            filas = conn.execute(
                f"select {COLUMNAS_TRABAJO} from trabajo where consulta_id = %s order by creado, id", (id,)
            ).fetchall()
        return [_fila_a_trabajo(f) for f in filas]


# ---- resultados (procesador) --------------------------------------------------------

SIN_TERMINAR = "('pendiente', 'en_curso')"


class RegistroResultadosPostgres:
    """Cada update lleva la condición de estado: un resultado repetido o tardío no pisa nada."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def _aplicar(self, sql: str, params: tuple) -> bool:
        with self._pool.connection() as conn:
            return conn.execute(sql, params).rowcount == 1

    def inferencia_en_curso(self, trabajo_id: UUID, worker: str, intento: int) -> bool:
        return self._aplicar(
            f"""update trabajo set estado = 'en_curso', intentos = greatest(intentos, %s), worker_id = %s,
                       actualizado = now()
                 where id = %s and estado in {SIN_TERMINAR}""",
            (intento, worker, trabajo_id),
        )

    def inferencia_terminada(self, trabajo_id: UUID, r: ResultadoInferencia) -> bool:
        return self._aplicar(
            f"""update trabajo set estado = 'ok', resultado = %s, worker_id = %s, duracion_ms = %s,
                       error = null, actualizado = now()
                 where id = %s and estado in {SIN_TERMINAR}""",
            (Jsonb(r.como_dict()), r.worker_id, r.duracion_ms, trabajo_id),
        )

    def inferencia_fallida(self, trabajo_id: UUID, motivo: str) -> bool:
        return self._aplicar(
            f"update trabajo set estado = 'error', error = %s, actualizado = now() where id = %s and estado in {SIN_TERMINAR}",
            (motivo, trabajo_id),
        )

    def evaluacion_en_curso(self, modelo_id: UUID, evaluador: str) -> bool:
        return self._aplicar(
            f"""update modelo set estado_evaluacion = 'en_curso', evaluador_id = %s, actualizado = now()
                 where id = %s and estado_evaluacion in {SIN_TERMINAR}""",
            (evaluador, modelo_id),
        )

    def evaluacion_terminada(self, modelo_id: UUID, r: ResultadoEvaluacion) -> bool:
        return self._aplicar(
            f"""update modelo set estado_evaluacion = 'ok', accuracy = %s, metricas = %s, conjunto = %s,
                       conjunto_version = %s, manifiesto = %s, evaluador_id = %s, evaluado_en = %s,
                       error = null, actualizado = now()
                 where id = %s and estado_evaluacion in {SIN_TERMINAR}""",
            (r.accuracy, Jsonb(r.metricas), r.conjunto, r.conjunto_version, Jsonb(r.manifiesto),
             r.evaluador_id, r.evaluado_en, modelo_id),
        )

    def evaluacion_fallida(self, modelo_id: UUID, evaluador: str, motivo: str) -> bool:
        return self._aplicar(
            f"""update modelo set estado_evaluacion = 'error', error = %s, evaluador_id = %s, evaluado_en = now(),
                       actualizado = now()
                 where id = %s and estado_evaluacion in {SIN_TERMINAR}""",
            (motivo, evaluador, modelo_id),
        )
