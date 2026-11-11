import { useCallback, useEffect, useRef, useState } from "react";
import { mensajeDeError } from "../api/cliente";
import { crear as crearConsulta, obtener as obtenerConsulta } from "../api/consultas";
import { crear as crearEstudio } from "../api/estudios";
import { subirArchivoAS3 } from "../api/s3";
import type { Consulta, Modelo } from "../api/tipos";
import type { EtapaInferencia } from "./useInferencia";

const INTERVALO_MS = 1500;
const TIEMPO_MAXIMO_MS = 5 * 60 * 1000;

/** Las mismas etapas que una consulta individual: así se reusa el indicador de pasos. */
export type EtapaJunta = EtapaInferencia;

export interface EstadoJunta {
  etapa: EtapaJunta;
  consulta: Consulta | null;
  error: string | null;
  /** true mientras hay una corrida en marcha (subiendo, encolando o esperando). */
  enCurso: boolean;
  ejecutar: (archivo: File, modelos: Modelo[]) => Promise<void>;
  reiniciar: () => void;
}

const terminada = (c: Consulta) => c.estado === "completa" || c.estado === "parcial" || c.estado === "error";

/**
 * La junta, de punta a punta:
 *  1. POST /estudios y la imagen a S3 una sola vez,
 *  2. POST /consultas con los modelos elegidos (un trabajo por modelo),
 *  3. polling de GET /consultas/{id} cada 1,5 s hasta que terminen todos (máx. 5 min).
 * Cada modelo muestra su resultado apenas llega; el consenso, cuando están todos.
 */
export function useJunta(): EstadoJunta {
  const [etapa, setEtapa] = useState<EtapaJunta>("idle");
  const [consulta, setConsulta] = useState<Consulta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idConsulta, setIdConsulta] = useState<string | null>(null);

  const montado = useRef(true);
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const ejecutar = useCallback(async (archivo: File, modelos: Modelo[]) => {
    setError(null);
    setConsulta(null);
    setIdConsulta(null);
    try {
      setEtapa("subiendo");
      const estudio = await crearEstudio({
        tipo_estudio: modelos[0].tipo_estudio,
        nombre_archivo: archivo.name,
        content_type: archivo.type,
        tamano_bytes: archivo.size,
      });
      await subirArchivoAS3(estudio.subida, archivo);
      if (!montado.current) return;

      setEtapa("encolando");
      const creada = await crearConsulta({
        estudio_id: estudio.estudio_id,
        modelo_ids: modelos.map((m) => m.id),
      });
      if (!montado.current) return;

      setConsulta(creada);
      setEtapa("esperando");
      setIdConsulta(creada.id);
    } catch (e) {
      if (!montado.current) return;
      setError(mensajeDeError(e));
      setEtapa("error");
    }
  }, []);

  const reiniciar = useCallback(() => {
    setIdConsulta(null);
    setConsulta(null);
    setError(null);
    setEtapa("idle");
  }, []);

  // Polling de la consulta; se cancela al terminar, al reiniciar o al desmontar.
  useEffect(() => {
    if (idConsulta === null) return;
    const id = idConsulta;
    const inicio = Date.now();
    let activo = true;
    let temporizador: ReturnType<typeof setInterval> | undefined;

    const terminar = () => {
      activo = false;
      if (temporizador !== undefined) clearInterval(temporizador);
    };

    const consultar = async () => {
      if (!activo) return;
      if (Date.now() - inicio > TIEMPO_MAXIMO_MS) {
        terminar();
        setError("La junta no terminó en 5 minutos. Probá de nuevo más tarde.");
        setEtapa("error");
        return;
      }
      try {
        const actual = await obtenerConsulta(id);
        if (!activo) return;
        setConsulta(actual);
        if (terminada(actual)) {
          terminar();
          if (actual.estado === "error") {
            setError("Ningún modelo de la junta pudo analizar la imagen.");
            setEtapa("error");
          } else {
            setEtapa("ok");
          }
        }
      } catch (e) {
        if (!activo) return;
        terminar();
        setError(mensajeDeError(e));
        setEtapa("error");
      }
    };

    temporizador = setInterval(() => void consultar(), INTERVALO_MS);
    void consultar();

    return terminar;
  }, [idConsulta]);

  const enCurso = etapa === "subiendo" || etapa === "encolando" || etapa === "esperando";

  return { etapa, consulta, error, enCurso, ejecutar, reiniciar };
}
