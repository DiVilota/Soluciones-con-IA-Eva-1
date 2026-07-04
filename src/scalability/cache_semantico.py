import json
import os
import re
import time
from collections import Counter


class EntradaCache:
    def __init__(self, consulta: str, respuesta: str, timestamp: float, ttl: int):
        self.consulta = consulta
        self.respuesta = respuesta
        self.timestamp = timestamp
        self.ttl = ttl
        self.tokens_ahorrados = max(len(respuesta) // 4, 1)
        self.accesos = 0

    def to_dict(self):
        return {
            "consulta": self.consulta,
            "respuesta": self.respuesta,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "tokens_ahorrados": self.tokens_ahorrados,
            "accesos": self.accesos,
        }

    @classmethod
    def from_dict(cls, d):
        e = cls(d["consulta"], d["respuesta"], d["timestamp"], d["ttl"])
        e.tokens_ahorrados = d.get("tokens_ahorrados", e.tokens_ahorrados)
        e.accesos = d.get("accesos", 0)
        return e


class CacheSemantico:
    def __init__(self, umbral: float = 0.85, ttl: int = 3600, cache_file: str = None):
        self.umbral = umbral
        self.ttl = ttl
        self.entradas: dict[str, EntradaCache] = {}
        self._cache_file = cache_file
        if cache_file:
            self._cargar_desde_disco()

    def _normalizar(self, texto: str) -> str:
        texto = texto.lower()
        texto = re.sub(r"[^a-záéíóúñü0-9\s]", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto

    def _frecuencia_palabras(self, texto: str) -> Counter:
        return Counter(self._normalizar(texto).split())

    def _similitud_coseno(self, texto1: str, texto2: str) -> float:
        freq1 = self._frecuencia_palabras(texto1)
        freq2 = self._frecuencia_palabras(texto2)
        todas = set(freq1.keys()) | set(freq2.keys())
        v1 = [freq1.get(p, 0) for p in todas]
        v2 = [freq2.get(p, 0) for p in todas]
        dot = sum(a * b for a, b in zip(v1, v2))
        mag1 = sum(a * a for a in v1) ** 0.5
        mag2 = sum(b * b for b in v2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    def _expirado(self, entrada: EntradaCache) -> bool:
        return (time.time() - entrada.timestamp) >= entrada.ttl

    def buscar(self, consulta: str):
        mejor_sim = 0.0
        mejor_clave = None
        ahora = time.time()
        expiradas = []

        for clave, entrada in self.entradas.items():
            if (ahora - entrada.timestamp) >= entrada.ttl:
                expiradas.append(clave)
                continue
            sim = self._similitud_coseno(consulta, entrada.consulta)
            if sim > mejor_sim:
                mejor_sim = sim
                mejor_clave = clave

        for clave in expiradas:
            del self.entradas[clave]

        if mejor_clave and mejor_sim >= self.umbral:
            entrada = self.entradas[mejor_clave]
            entrada.accesos += 1
            self._persistir()
            return entrada.respuesta
        return None

    def guardar(self, consulta: str, respuesta: str):
        clave = self._normalizar(consulta)
        self.entradas[clave] = EntradaCache(
            consulta=consulta,
            respuesta=respuesta,
            timestamp=time.time(),
            ttl=self.ttl,
        )
        self._persistir()

    def limpiar_expirados(self):
        ahora = time.time()
        self.entradas = {
            k: v for k, v in self.entradas.items()
            if (ahora - v.timestamp) < v.ttl
        }

    def estadisticas(self) -> dict:
        self.limpiar_expirados()
        total_accesos = sum(e.accesos for e in self.entradas.values())
        total_tokens = sum(e.tokens_ahorrados for e in self.entradas.values())
        return {
            "entradas_activas": len(self.entradas),
            "total_accesos": total_accesos,
            "total_tokens_ahorrados": total_tokens,
        }

    def _cargar_desde_disco(self):
        if not os.path.exists(self._cache_file):
            return
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            ahora = time.time()
            for item in data.get("entries", []):
                entrada = EntradaCache.from_dict(item)
                if ahora - entrada.timestamp < entrada.ttl:
                    self.entradas[self._normalizar(entrada.consulta)] = entrada
        except Exception:
            pass

    def _persistir(self):
        if not self._cache_file:
            return
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            data = {
                "entries": [e.to_dict() for e in self.entradas.values()],
            }
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
