import { useCallback, useEffect, useRef, useState } from "react";
import { mensajeDeError } from "../api/cliente";
import { listarDisponibles, listarPublicados } from "../api/modelos";
import type { Modelo, ModeloDisponible } from "../api/tipos";
import { useSesion } from "./useSesion";
import { get } from "../api/cliente";

export interface EstadoDemo {
  activo: boolean;
  estado: "desactivado" | "preparando" | "parcial" | "ok" | "error";
  esperados: number;
  listos: number;
  errores: number;
  pendientes: number;
  modelos: {
    nombre: string;
    version: string;
    nombre_visible: string;
    estado: "desactivado" | "preparando" | "pendiente" | "en_curso" | "ok" | "error";
    modelo_id: string | null;
  }[];
}

export interface EstadoModelos {
  publicados: Modelo[];
  disponibles: ModeloDisponible[];
  cargando: boolean;
  error: string | null;
  demo: EstadoDemo | null;
  /** Vuelve a pedir las dos listas. */
  refrescar: () => Promise<void>;
  /** Reemplaza (o agrega al frente) un modelo en la lista de publicados. */
  actualizarModelo: (modelo: Modelo) => void;
}

/**
 * Carga el catálogo y, si hay sesión, los modelos disponibles en el bucket.
 *
 * El catálogo es público, así que la portada lo muestra a quien no ingresó. Lo del bucket pide
 * token y una cuenta que publica: pedirlo sin sesión devolvía 401 (la portada se llenaba de «tu
 * sesión venció»), y con una cuenta de institución, 403.
 */
export function useModelos(): EstadoModelos {
  // En local (sin login) se puede todo; con login, hace falta una sesión de una cuenta que publica.
  const { puedePublicar: pedirDisponibles } = useSesion();
  const [publicados, setPublicados] = useState<Modelo[]>([]);
  const [disponibles, setDisponibles] = useState<ModeloDisponible[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<EstadoDemo | null>(null);
  const consultando = useRef(false);
  const montado = useRef(true);

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const refrescar = useCallback(async () => {
    if (consultando.current) return;
    consultando.current = true;
    setCargando(true);
    setError(null);
    try {
      const [p, d, estadoDemo] = await Promise.all([
        listarPublicados(),
        pedirDisponibles ? listarDisponibles() : Promise.resolve<ModeloDisponible[]>([]),
        get<EstadoDemo>("/publico/demo"),
      ]);
      if (!montado.current) return;
      setPublicados(p);
      setDisponibles(d);
      setDemo(estadoDemo);
    } catch (e) {
      if (!montado.current) return;
      setError(mensajeDeError(e));
    } finally {
      if (montado.current) setCargando(false);
      consultando.current = false;
    }
  }, [pedirDisponibles]);

  useEffect(() => {
    void refrescar();
  }, [refrescar]);

  useEffect(() => {
    const preparando = demo === null || (demo.activo && demo.pendientes > 0);
    if (!preparando) return;
    const timer = window.setInterval(() => void refrescar(), 5000);
    return () => window.clearInterval(timer);
  }, [demo, refrescar]);

  const actualizarModelo = useCallback((modelo: Modelo) => {
    setPublicados((previos) =>
      previos.some((m) => m.id === modelo.id)
        ? previos.map((m) => (m.id === modelo.id ? modelo : m))
        : [modelo, ...previos],
    );
  }, []);

  return { publicados, disponibles, cargando, error, demo, refrescar, actualizarModelo };
}
