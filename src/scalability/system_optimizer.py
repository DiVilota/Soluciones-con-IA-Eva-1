import time
import os
import pandas as pd

from src.scalability.cache_llm import CacheLLM
from src.scalability.cache_semantico import CacheSemantico
from src.scalability.model_router import seleccionar_modelo
from src.scalability.token_estimator import estimar_tokens
from src.scalability.resilience import RetryConBackoff
from src.scalability.cost_calculator import CalculadorCostos
from src.scalability.sustainability_report import ReporteSostenibilidad

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")


class SistemaOptimizado:
    def __init__(self):
        self.cache_llm = CacheLLM(max_size=100, cache_file=os.path.join(_CACHE_DIR, "optimizer_llm_cache.json"))
        self.cache_semantico = CacheSemantico(umbral=0.85, ttl=3600, cache_file=os.path.join(_CACHE_DIR, "optimizer_semantic_cache.json"))
        self.calculador_costos = CalculadorCostos(presupuesto_diario=100.0)
        self.reporte = ReporteSostenibilidad()
        self.retry = RetryConBackoff(max_reintentos=3, base=0.5)
        self._no_optimizado_costos = []
        self._optimizado_costos = []

    def procesar(self, consulta: str) -> dict:
        start = time.time()

        if not consulta or not consulta.strip():
            return {"texto": "", "optimizado": False, "error": "consulta vacia"}

        cache_hit = self.cache_llm.obtener(consulta, "gpt-4o")
        if cache_hit:
            latencia = round(time.time() - start, 4)
            self.reporte.agregar_metricas_cache(hits=1, tokens_ahorrados=estimar_tokens(cache_hit))
            self.reporte.agregar_registro("gpt-4o", 0, 0, latencia, "cache_hit")
            self._optimizado_costos.append(0.0)
            return {"texto": cache_hit, "optimizado": True, "fuente": "cache_llm", "latencia": latencia}

        cache_sem = self.cache_semantico.buscar(consulta)
        if cache_sem:
            latencia = round(time.time() - start, 4)
            self.reporte.agregar_metricas_cache(hits=1, tokens_ahorrados=estimar_tokens(cache_sem))
            self.reporte.agregar_registro("gpt-4o", 0, 0, latencia, "cache_hit_semantico")
            self._optimizado_costos.append(0.0)
            return {"texto": cache_sem, "optimizado": True, "fuente": "cache_semantico", "latencia": latencia}

        modelo_config = seleccionar_modelo(consulta)
        tokens_estimados = estimar_tokens(consulta)
        costo_estimado = (tokens_estimados / 1000) * modelo_config.costo_por_1k

        self._optimizado_costos.append(costo_estimado)
        self._no_optimizado_costos.append((tokens_estimados / 1000) * 5.0)

        resultado_simulado = f"Resultado simulado para: {consulta[:50]}"

        latencia = round(time.time() - start, 4)
        self.reporte.agregar_registro(modelo_config.nombre, tokens_estimados, tokens_estimados // 2, latencia, "exito")
        self.reporte.agregar_metricas_cache(misses=1)
        ahorro = max(round(((tokens_estimados / 1000) * 5.0) - costo_estimado, 4), 0)
        self.reporte.agregar_metricas_enrutamiento(costo_ahorrado=ahorro)

        return {
            "texto": resultado_simulado,
            "optimizado": True,
            "modelo": modelo_config.nombre,
            "latencia": latencia,
            "tokens_estimados": tokens_estimados,
            "costo_estimado": costo_estimado,
        }

    def generar_reporte_comparativo(self) -> pd.DataFrame:
        max_len = max(len(self._optimizado_costos), len(self._no_optimizado_costos))
        opt = self._optimizado_costos + [0.0] * (max_len - len(self._optimizado_costos))
        no_opt = self._no_optimizado_costos + [0.0] * (max_len - len(self._no_optimizado_costos))
        df = pd.DataFrame({
            "consulta": range(1, max_len + 1),
            "optimizado": opt,
            "no_optimizado": no_opt,
            "ahorro": [round(n - o, 4) for o, n in zip(opt, no_opt)],
        })
        return df

    def generar_reporte_sostenibilidad(self) -> dict:
        self.reporte.guardar()
        return self.reporte.metricas
