"""Registro interno de la demo; outbox transaccional y candado entre procesadores."""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager

from psycopg.types.json import Jsonb

from tools.demo_assets import (catalogo, comprobar, escribir_json, leer)


from .aplicacion.casos_uso.modelos import PublicarModelo
from .dominio.usuario import Usuario
from .infraestructura.postgres.repositorios import RepositorioModelosPostgres
from .infraestructura.reloj import RelojSistema
from .infraestructura.s3.catalogo_modelos import CatalogoModelosS3

log = logging.getLogger(__name__)


class ConexionPrestada:
    """Los repositorios participan de una única transacción de inicialización."""
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


class OutboxDemo:
    def __init__(self, conn, clave):
        self.conn = conn
        self.clave = clave

    def enviar(self, peticion):
        self.conn.execute("insert into demo_inicializacion (clave, mensaje) values (%s, %s)",
                          (self.clave, Jsonb(peticion.como_mensaje())))


class InicializarModelo:
    def __init__(self, pool, s3, sqs, settings, modelo):
        self.pool, self.s3, self.sqs, self.settings = pool, s3, sqs, settings
        self.modelo = modelo
        self.verificado = False
        self.terminado = False
        self.errores = 0

    def ejecutar(self):
        if self.terminado:
            return
        try:
            self._ejecutar()
            self.errores = 0
        except Exception:
            self.errores += 1
            if self.errores >= 3:
                escribir_json(self.s3, self.settings.bucket_modelos, self.modelo.estado, {"estado": "error"})
                self.terminado = True
            raise

    def _ejecutar(self):
        s = self.settings
        md = self.modelo
        if not self.verificado:
            marca = leer(self.s3, s.bucket_modelos, md.listo)
            if marca is None:
                return
            ref = md.metadata()["archivos"]["modelo.onnx"]
            if json.loads(marca)["modelo_sha256"] != ref["sha256"]:
                raise ValueError("La marca de demo pertenece a otro modelo")
            datos = leer(self.s3, s.bucket_modelos, md.prefijo + "modelo.onnx")
            if datos is None:
                return
            comprobar(datos, ref)
            contrato = leer(self.s3, s.bucket_modelos, md.prefijo + "modelo.json")
            if contrato is None or json.loads(contrato) != md.contrato():
                raise ValueError("El contrato de demo no coincide")
            self.verificado = True

        with self.pool.connection() as conn:
            if not conn.execute("select pg_try_advisory_xact_lock(hashtextextended(%s, 0)) as tomado", (md.clave,)).fetchone()["tomado"]:
                return
            modelos = RepositorioModelosPostgres(ConexionPrestada(conn))
            modelo = modelos.buscar(md.nombre, md.version)
            if modelo is not None:
                if modelo.contrato != md.contrato():
                    raise ValueError("El catálogo contiene otro contrato para la versión de demo")
                if modelo.estado_evaluacion in ("ok", "error"):
                    self.terminado = modelo.estado_evaluacion == "ok"
                    return
                if modelo.estado_evaluacion == "en_curso":
                    return
            else:
                caso = PublicarModelo(CatalogoModelosS3(self.s3, s.bucket_modelos), modelos,
                                      RelojSistema(), s.prefijo_modelos, OutboxDemo(conn, md.clave))
                modelo = caso.ejecutar(Usuario.plataforma(), md.nombre, md.version)
                log.info("demo registrada: %s; evaluación pendiente de envío", modelo.id)
            # Una publicación manual pendiente puede no tener outbox: esperar antes de recuperar.
            from .aplicacion.puertos import PeticionEvaluacion
            conn.execute("""insert into demo_inicializacion (clave, mensaje, intentos, enviado)
                            values (%s, %s, 1, now()) on conflict (clave) do nothing""",
                         (md.clave, Jsonb(PeticionEvaluacion.de(modelo).como_mensaje())))
        # La fila del modelo y su mensaje ya están confirmados antes de enviar a SQS.
        with self.pool.connection() as conn:
            conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (md.clave,))
            fila = conn.execute("""select *, enviado is null or
                enviado < now() - make_interval(secs => %s) as vencido
                from demo_inicializacion where clave = %s for update""",
                (s.demo_reenvio_segundos, md.clave)).fetchone()
            estado = conn.execute("select estado_evaluacion from modelo where nombre=%s and version=%s",
                                  (md.nombre, md.version)).fetchone()["estado_evaluacion"]
            if estado != "pendiente" or not (fila["vencido"] or fila["error"]):
                return
            if fila["intentos"] >= 3:
                conn.execute("update demo_inicializacion set error=true where clave=%s", (md.clave,))
                return
            try:
                self.sqs.send_message(QueueUrl=s.cola_evaluaciones_url, MessageBody=json.dumps(fila["mensaje"]))
                error = False
                log.info("evaluación demo encolada")
            except Exception:
                error = True
                log.exception("falló el envío de demo; reintento limitado")
            conn.execute("""update demo_inicializacion set intentos=intentos+1, enviado=now(), error=%s
                            where clave=%s""", (error, md.clave))


class InicializarDemo:
    def __init__(self, pool, s3, sqs, settings):
        self.tareas = [InicializarModelo(pool, s3, sqs, settings, m) for m in catalogo()]

    def ejecutar(self):
        for tarea in self.tareas:
            try:
                tarea.ejecutar()
            except Exception:
                log.exception("error inicializando %s; continúo con los otros modelos", tarea.modelo.clave)


def estado_demo(settings, pool, s3) -> dict:
    registro = catalogo()
    existentes = {(m.nombre, m.version): m for m in RepositorioModelosPostgres(pool).listar()}
    with pool.connection() as conn:
        envios = {f["clave"]: f for f in conn.execute("select clave, intentos, error from demo_inicializacion").fetchall()}
    estados = []
    for md in registro:
        m = existentes.get((md.nombre, md.version))
        estado = m.estado_evaluacion if m else "preparando"
        if not settings.datos_demo and m is None:
            estado = "desactivado"
        elif estado not in ("ok", "en_curso", "error"):
            envio = envios.get(md.clave)
            marca = leer(s3, settings.bucket_modelos, md.estado)
            if (envio and envio["intentos"] >= 3 and envio["error"]) or (marca and json.loads(marca).get("estado") == "error"):
                estado = "error"
        estados.append({"nombre": md.nombre, "version": md.version, "nombre_visible": md.nombre_visible,
                        "estado": estado, "modelo_id": str(m.id) if m else None})
    listos = sum(m["estado"] == "ok" for m in estados)
    errores = sum(m["estado"] == "error" for m in estados)
    pendientes = sum(m["estado"] in ("preparando", "pendiente", "en_curso") for m in estados)
    if not settings.datos_demo:
        global_ = "desactivado"
    elif listos == len(registro):
        global_ = "ok"
    elif listos:
        global_ = "parcial"
    elif pendientes:
        global_ = "preparando"
    else:
        global_ = "error"
    return {"activo": settings.datos_demo, "estado": global_, "esperados": len(registro),
            "listos": listos, "errores": errores, "pendientes": pendientes, "modelos": estados}
