import os
import time
import asyncio
import json
import ast
import operator
import threading
import warnings
from queue import Queue, Empty
from datetime import datetime, timezone
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.live import Live

from src.rag_engine import HardiBotRAG
from src.personas import PERSONAS, obtener_prompt

from langchain_core.tools import tool
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from src.observability import (
    LoggerEstructurado,
    RecolectorMetricas,
    SistemaAlertas,
    observable,
    _sistema_trazas,
)
from src.security import AgenteSeguro
from src.scalability.cache_llm import CacheLLM
from src.scalability.cache_semantico import CacheSemantico
from src.scalability.model_router import seleccionar_modelo
from src.scalability.token_estimator import estimar_tokens
from src.scalability.batch_processor import ProcesadorLotes, Solicitud, PRIORIDAD_NORMAL
from src.scalability.cost_calculator import CalculadorCostos
from src.scalability.resilience import RetryConBackoff, CadenaFallback
from src.scalability.sustainability_report import ReporteSostenibilidad
from src.scalability.system_optimizer import SistemaOptimizado

load_dotenv(override=True)
console = Console()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")

logger_obs = LoggerEstructurado(
    nombre="hardibot",
    log_dir=os.getenv("OBSERVABILITY_LOG_DIR", "logs"),
    nivel=os.getenv("OBSERVABILITY_LOG_LEVEL", "DEBUG"),
)
recolector_obs = RecolectorMetricas()
sistema_alertas = SistemaAlertas()

cache_llm = CacheLLM(max_size=100, cache_file=os.path.join(_CACHE_DIR, "llm_cache.json"))
cache_semantico = CacheSemantico(umbral=0.85, ttl=3600, cache_file=os.path.join(_CACHE_DIR, "semantic_cache.json"))
procesador_lotes = ProcesadorLotes(tamano_lote=5)
calculador_costos = CalculadorCostos(presupuesto_diario=100.0)
reporte_sostenibilidad = ReporteSostenibilidad()
sistema_optimizado = SistemaOptimizado()

MODELO_POR_DEFECTO = os.getenv("MODEL_NAME", "gpt-4o")


class ToolCaptureHandler(BaseCallbackHandler):
    """Captura el uso de herramientas del agente para mostrarlo en la UI."""

    def __init__(self):
        self.tool_calls = []
        self._start_times = {}
        self._current_step = 0

    def on_tool_start(self, serialized, input_str, run_id=None, **kwargs):
        name = serialized.get("name", "unknown")
        self._current_step += 1
        self._start_times[run_id] = time.time()
        self.tool_calls.append({
            "step": self._current_step,
            "name": name,
            "input": str(input_str)[:200],
            "output": None,
            "duration": None,
            "status": "running",
        })

    def on_tool_end(self, output, run_id=None, **kwargs):
        for tc in reversed(self.tool_calls):
            if tc["output"] is None:
                tc["output"] = str(output)[:300]
                tc["duration"] = round(time.time() - self._start_times.get(run_id, time.time()), 2)
                tc["status"] = "complete"
                break


def ejecutar_con_visibilidad(user_input: str, history: list = None, session_id: str = "streamlit_session"):
    """Ejecuta el agente y retorna (tool_calls, response_text, metadata).

    history: lista de tuplas ("user"|"assistant", contenido) con el historial de mensajes previos.
    """
    start = time.time()
    handler = ToolCaptureHandler()
    trace_id = f"vis-{int(time.time())}"

    logger_obs.info("ejecutar_con_visibilidad", metadata={"user_input": user_input[:100], "session_id": session_id}, trace_id=trace_id)

    resultado_seguridad = app_state.agente_seguro.procesar(user_input)
    if not resultado_seguridad.es_seguro:
        logger_obs.warning("seguridad_bloqueo", metadata={"razones": [e.detalle for e in resultado_seguridad.eventos]}, trace_id=trace_id)
        return [], resultado_seguridad.error_multi_idioma, {"bloqueado": True, "eventos": [{"tipo": e.tipo, "detalle": e.detalle} for e in resultado_seguridad.eventos]}

    cached = cache_llm.obtener(user_input, os.getenv("MODEL_NAME", "gpt-4o"))
    if cached:
        elapsed = round(time.time() - start, 2)
        logger_obs.info("cache_hit", metadata={"latencia": elapsed}, trace_id=trace_id)
        recolector_obs.registrar_exito(
            modelo=os.getenv("MODEL_NAME", "gpt-4o"),
            tiempo_respuesta_ms=elapsed * 1000,
            tokens_prompt=0,
            tokens_completion=len(cached),
            trace_id=trace_id,
        )
        metadata = {"latencia": elapsed, "cache_hit": True, "timestamp": datetime.now(timezone.utc).isoformat()}
        logger_obs.info("ejecutar_con_visibilidad_completado", metadata=metadata, trace_id=trace_id)
        return handler.tool_calls, cached, metadata

    modelo_config = seleccionar_modelo(user_input)
    tokens_in = estimar_tokens(user_input)

    messages_input = history + [("user", user_input)] if history else [("user", user_input)]
    respuesta = app_state.agent.invoke(
        {"messages": messages_input},
        config={
            "configurable": {"thread_id": session_id},
            "callbacks": [handler],
        },
    )

    _sistema_trazas.finalizar_traza()
    _sistema_trazas.guardar()

    elapsed = round(time.time() - start, 2)
    mensajes = respuesta["messages"]
    textos_ia = []
    for msg in reversed(mensajes):
        if msg.type == "human":
            break
        if msg.type == "ai" and msg.content:
            textos_ia.insert(0, msg.content)

    texto_final = "\n\n---\n\n".join(textos_ia)
    tokens_out = estimar_tokens(texto_final)

    cache_llm.guardar(user_input, modelo_config.nombre, texto_final)
    calculador_costos.registrar(modelo_config.nombre, tokens_in, tokens_out)
    reporte_sostenibilidad.agregar_registro(modelo_config.nombre, tokens_in, tokens_out, elapsed, "exito")

    metadata = {
        "latencia": elapsed,
        "total_mensajes": len(mensajes),
        "herramientas_usadas": len(handler.tool_calls),
        "modelo": modelo_config.nombre,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    recolector_obs.registrar_exito(
        modelo=modelo_config.nombre,
        tiempo_respuesta_ms=elapsed * 1000,
        tokens_prompt=tokens_in,
        tokens_completion=tokens_out,
        trace_id=trace_id,
    )

    alertas = sistema_alertas.evaluar(recolector_obs)
    for alerta in alertas:
        logger_obs.warning("alerta_disparada", metadata={
            "regla": alerta.regla,
            "severidad": alerta.severidad,
            "valor": alerta.valor_actual,
            "umbral": alerta.umbral,
            "mensaje": alerta.mensaje,
        }, trace_id=trace_id)

    costo_alertas = calculador_costos.evaluar_alertas(calculador_costos.total_gastado())
    for alerta in costo_alertas:
        logger_obs.warning("costo_alerta", metadata={"nivel": alerta["nivel"], "mensaje": alerta["mensaje"]}, trace_id=trace_id)

    reporte_sostenibilidad.guardar()
    logger_obs.info("ejecutar_con_visibilidad_completado", metadata=metadata, trace_id=trace_id)
    return handler.tool_calls, texto_final, metadata


def ejecutar_con_streaming(user_input: str, history: list = None, session_id: str = "streamlit_session"):
    """Generador sincrono que emite eventos de streaming en tiempo real.

    history: lista de tuplas ("user"|"assistant", contenido) con el historial de mensajes previos.
    Yields dicts: {"type": "token", "content": str} | {"type": "meta", "tool_calls": [], "metadata": {}} | {"type": "error", "content": str}
    """
    trace_id = f"stream-{int(time.time())}"
    logger_obs.info("ejecutar_con_streaming_inicio", metadata={"user_input": user_input[:100], "session_id": session_id}, trace_id=trace_id)

    resultado_seguridad = app_state.agente_seguro.procesar(user_input)
    if not resultado_seguridad.es_seguro:
        logger_obs.warning("seguridad_bloqueo_stream", metadata={"razones": [e.detalle for e in resultado_seguridad.eventos]}, trace_id=trace_id)
        yield {"type": "meta", "tool_calls": [], "metadata": {"bloqueado": True, "error": resultado_seguridad.error_multi_idioma}}
        return

    cached = cache_llm.obtener(user_input, os.getenv("MODEL_NAME", "gpt-4o"))
    if cached:
        reporte_sostenibilidad.agregar_metricas_cache(hits=1, tokens_ahorrados=estimar_tokens(cached))
        yield {"type": "meta", "tool_calls": [], "metadata": {"cache_hit": True, "texto": cached, "latencia": 0.0}}
        return

    modelo_config = seleccionar_modelo(user_input)
    tokens_in = estimar_tokens(user_input)

    event_queue: Queue = Queue()

    # ── Recortar historial para no exceder 8000 tokens de GitHub Models ──
    MAX_HISTORY_TOKENS = 5500
    try:
        import tiktoken as _tiktoken
        enc = _tiktoken.encoding_for_model("gpt-4o")
    except Exception:
        enc = None

    if history and enc:
        resumen = (
            "Resumen: El usuario pidio una cotizacion de productos. "
            "Usa _ver_carrito si necesitas ver los items actuales en el carrito."
        )
        tokens_resumen = len(enc.encode(resumen))
        disponibles = MAX_HISTORY_TOKENS - tokens_resumen
        recortado = [("system", resumen)]
        for msg in reversed(history):
            tokens_msg = len(enc.encode(msg[1]))
            if tokens_msg > disponibles:
                break
            recortado.insert(1, msg)
            disponibles -= tokens_msg
        history = recortado

    messages_input = history + [("user", user_input)] if history else [("user", user_input)]

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            handler = ToolCaptureHandler()
            start = time.time()

            async def _stream():
                try:
                    async for event in app_state.agent.astream_events(
                        {"messages": messages_input},
                        config={
                            "configurable": {"thread_id": session_id},
                            "callbacks": [handler],
                        },
                        version="v2",
                    ):
                        kind = event.get("event", "")
                        if kind == "on_chat_model_stream":
                            chunk = event.get("data", {}).get("chunk")
                            if chunk and hasattr(chunk, "content") and chunk.content:
                                event_queue.put({"type": "token", "content": str(chunk.content)})
                        elif kind == "on_tool_start":
                            event_queue.put({
                                "type": "tool_start",
                                "name": event.get("name", ""),
                                "input": str(event.get("data", {}).get("input", ""))[:120],
                            })
                        elif kind == "on_tool_end":
                            event_queue.put({
                                "type": "tool_end",
                                "name": event.get("name", ""),
                            })

                    elapsed = round(time.time() - start, 2)
                    _sistema_trazas.finalizar_traza()
                    _sistema_trazas.guardar()

                    calculador_costos.registrar(modelo_config.nombre, tokens_in, 0)
                    reporte_sostenibilidad.agregar_registro(modelo_config.nombre, tokens_in, 0, elapsed, "exito")
                    logger_obs.info("ejecutar_con_streaming_completado", metadata={"latencia": elapsed, "herramientas_usadas": len(handler.tool_calls), "modelo": modelo_config.nombre}, trace_id=trace_id)
                    recolector_obs.registrar_exito(
                        modelo=modelo_config.nombre,
                        tiempo_respuesta_ms=elapsed * 1000,
                        tokens_prompt=tokens_in,
                        tokens_completion=0,
                        trace_id=trace_id,
                    )
                    event_queue.put({
                        "type": "meta",
                        "tool_calls": handler.tool_calls,
                        "metadata": {
                            "latencia": elapsed,
                            "herramientas_usadas": len(handler.tool_calls),
                            "modelo": modelo_config.nombre,
                        },
                    })
                except Exception as e:
                    logger_obs.error("ejecutar_con_streaming_error", metadata={"error": str(e)}, trace_id=trace_id)
                    reporte_sostenibilidad.agregar_registro(modelo_config.nombre, tokens_in, 0, 0, "error")
                    event_queue.put({"type": "error", "content": str(e)})

            loop.run_until_complete(_stream())
        finally:
            loop.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    while True:
        try:
            event = event_queue.get(timeout=90)
            yield event
            if event["type"] in ("meta", "error"):
                break
        except Empty:
            yield {"type": "error", "content": "Timeout"}
            break

    alertas = sistema_alertas.evaluar(recolector_obs)
    for alerta in alertas:
        logger_obs.warning("alerta_disparada", metadata={
            "regla": alerta.regla,
            "severidad": alerta.severidad,
            "valor": alerta.valor_actual,
            "umbral": alerta.umbral,
        }, trace_id=trace_id)
    reporte_sostenibilidad.guardar()


class CarritoCompras:
    def __init__(self):
        self.items = []

    def agregar(self, producto: str, cantidad: int, precio_unitario: float) -> str:
        item = {
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": cantidad * precio_unitario,
        }
        self.items.append(item)
        return json.dumps({
            "accion": "agregado exitosamente",
            "producto": producto,
            "subtotal": item["subtotal"],
            "total_items_en_carrito": len(self.items),
        })

    def ver(self) -> str:
        if not self.items:
            return json.dumps({"mensaje": "El carrito esta vacio en este momento."})
        total = sum(item["subtotal"] for item in self.items)
        return json.dumps({"items": self.items, "precio_total": total})

    def limpiar(self):
        self.items = []

    def total(self) -> float:
        return sum(item["subtotal"] for item in self.items)

    def generar_pdf(self, output_path: str = None) -> bytes:
        try:
            from fpdf import FPDF
        except ImportError:
            return b"Error: fpdf2 no instalado. Ejecuta: pip install fpdf2"

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Cotizacion - HardiBot", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(8)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(80, 8, "Producto", border=1)
        pdf.cell(25, 8, "Cantidad", border=1, align="C")
        pdf.cell(40, 8, "P. Unitario", border=1, align="R")
        pdf.cell(40, 8, "Subtotal", border=1, align="R")
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        for item in self.items:
            precio = f"{item['precio_unitario']:,.0f}".replace(",", ".")
            subtotal = f"{item['subtotal']:,.0f}".replace(",", ".")
            pdf.cell(80, 7, item["producto"][:40], border=1)
            pdf.cell(25, 7, str(item["cantidad"]), border=1, align="C")
            pdf.cell(40, 7, f"${precio}", border=1, align="R")
            pdf.cell(40, 7, f"${subtotal}", border=1, align="R")
            pdf.ln()

        pdf.set_font("Helvetica", "B", 10)
        total = self.total()
        total_str = f"{total:,.0f}".replace(",", ".")
        pdf.cell(145, 8, "TOTAL", border=1, align="R")
        pdf.cell(40, 8, f"${total_str} CLP", border=1, align="R")

        if output_path:
            pdf.output(output_path)
            return output_path
        return bytes(pdf.output())


class HerramientaRobusta:
    """Wrapper resiliente con retry via RetryConBackoff (centralizado en resilience).
    Mantiene compatibilidad hacia atras mientras unifica la logica de reintentos."""

    def __init__(self, nombre: str, funcion, max_reintentos: int = 3):
        self.nombre = nombre
        self.funcion = funcion
        self.max_reintentos = max_reintentos
        self._retry = RetryConBackoff(max_reintentos=max_reintentos, base=0.5, factor=2.0, jitter=True)

    def ejecutar(self, **kwargs) -> str:
        resultado = self._retry.ejecutar(self.funcion, **kwargs)
        if resultado is not None:
            return str(resultado)
        return json.dumps({
            "error": f"La herramienta '{self.nombre}' fallo tras {self.max_reintentos} intentos.",
            "detalle": "Todos los reintentos fallaron.",
            "sugerencia": "Informa al usuario que hubo un problema tecnico al ejecutar esta accion.",
        })


_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_ast(nodo):
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        return nodo.value
    if isinstance(nodo, ast.BinOp):
        op = _OPERADORES.get(type(nodo.op))
        if op is None:
            raise ValueError(f"Operacion no permitida: {type(nodo.op).__name__}")
        return op(_eval_ast(nodo.left), _eval_ast(nodo.right))
    if isinstance(nodo, ast.UnaryOp):
        op = _OPERADORES.get(type(nodo.op))
        if op is None:
            raise ValueError(f"Operacion no permitida: {type(nodo.op).__name__}")
        return op(_eval_ast(nodo.operand))
    raise ValueError(f"Expresion no valida: {type(nodo).__name__}")

def operacion_segura(operacion: str):
    return _eval_ast(ast.parse(operacion, mode="eval").body)


_TOOLS = []


@observable
def _nodo_ejecutar_herramienta(state):
    resultado = app_state.agent.invoke(
        state,
        config={"configurable": {"thread_id": state.get("session_id", "default")}},
    )
    return resultado


class HardiBotAppState:
    """Estado mutable de la aplicacion. Se puede reconfigurar en caliente."""

    def __init__(self, persona_id: str = "hardware"):
        self.persona_id = persona_id
        self.config = PERSONAS[persona_id]
        self.motor_rag = HardiBotRAG(self.config["catalogo"])
        self.motor_rag.construir_indice()
        self.prompt = obtener_prompt(persona_id)
        self.llm = ChatOpenAI(
            base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GITHUB_TOKEN"),
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0.4")),
            max_tokens=int(os.getenv("MODEL_MAX_TOKENS", "4096")),
            streaming=True,
        )
        self.carrito = CarritoCompras()
        self.memoria = MemorySaver()
        self.agent = None
        self.agente_seguro = AgenteSeguro(
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GITHUB_TOKEN", ""),
            modelo=os.getenv("MODEL_NAME", "gpt-4o"),
        )

    def iniciar(self):
        self.agent = create_react_agent(
            model=self.llm,
            tools=_TOOLS,
            prompt=self.prompt,
            checkpointer=self.memoria,
        )
        return self

    def reconfigurar(self, persona_id: str):
        console.print(f"[bold cyan]--- Cambiando a persona: {persona_id} ---[/bold cyan]")
        self.persona_id = persona_id
        self.config = PERSONAS[persona_id]
        self.motor_rag = HardiBotRAG(self.config["catalogo"])
        self.motor_rag.construir_indice()
        self.prompt = obtener_prompt(persona_id)
        self.carrito.limpiar()
        self.memoria = MemorySaver()
        self.agent = create_react_agent(
            model=self.llm,
            tools=_TOOLS,
            prompt=self.prompt,
            checkpointer=self.memoria,
        )
        console.print(f"[bold green]Persona cambiada a: {self.config['nombre']}[/bold green]")

    @property
    def nombre_bot(self) -> str:
        return self.config["nombre"]

    @property
    def titulo_bot(self) -> str:
        return self.config["titulo"]


@tool
def _buscar_catalogo_local(query: str) -> str:
    """Busca en el INVENTARIO LOCAL de HardiBot (catalogo FAISS interno).
    NO busca en internet, Knasta, SoloTodo ni tiendas externas.
    Usa esta herramienta para consultar productos disponibles en nuestro propio stock interno."""
    logger_obs.info("tool_buscar_catalogo_local", metadata={"query": query[:100]})
    env = HerramientaRobusta("RAG_Catalogo", app_state.motor_rag.recuperar_contexto)
    resultado = env.ejecutar(query=query, top_k=15)
    logger_obs.info("tool_buscar_catalogo_local_completado", metadata={"query": query[:100], "resultado_len": len(resultado)})
    return resultado


@tool
def _buscar_web(query: str) -> str:
    """
    Busca en internet precios de la competencia, ofertas actuales, especificaciones
    de productos o cualquier informacion actualizada del mercado chileno.
    DEBES usar esta herramienta CUANDO:
    - El usuario te pida comparar precios con la competencia.
    - El usuario pregunte por precios de mercado actuales.
    - Necesites validar si tu cotizacion es competitiva.
    - El producto no este en tu catalogo y quieras investigar.
    """
    logger_obs.info("tool_buscar_web", metadata={"query": query[:100]})
    api_key = os.getenv("TAVILY_API_KEY")
    if api_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            resultados = client.search(query=query, search_depth="advanced", max_results=5)
            if resultados and "results" in resultados:
                fragments = []
                for r in resultados["results"][:5]:
                    fragments.append(f"**{r.get('title', '')}**\n{r.get('content', '')}\nFuente: {r.get('url', '')}")
                return "\n\n".join(fragments)
            return "No se encontraron resultados en la busqueda web."
        except Exception as e:
            console.print(f"[dim yellow]Tavily fallo: {e}. Usando fallback DuckDuckGo...[/dim yellow]")

    try:
        from duckduckgo_search import DDGS
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            resultados = DDGS().text(query, max_results=5)
        fragments = []
        for r in resultados:
            fragments.append(f"**{r.get('title', '')}**\n{r.get('body', '')}\nFuente: {r.get('href', '')}")
        return "\n\n".join(fragments) if fragments else "No se encontraron resultados en la busqueda web."
    except Exception as e:
        return json.dumps({
            "error": "No se pudo realizar la busqueda web.",
            "detalle": str(e),
            "sugerencia": "Informa al usuario que no hay conectividad a internet en este momento.",
        })


@tool
def _calcular_presupuesto(operacion: str) -> str:
    """Usa esta herramienta para sumar o multiplicar los precios de los componentes. Ingresa SOLO la operacion matematica."""
    logger_obs.info("tool_calcular_presupuesto", metadata={"operacion": operacion[:100]})
    env = HerramientaRobusta("Calculadora", operacion_segura, max_reintentos=2)
    resultado = env.ejecutar(operacion=operacion)
    logger_obs.info("tool_calcular_presupuesto_completado", metadata={"operacion": operacion[:100], "resultado": resultado[:200]})
    return resultado


@tool
def _buscar_foto_componente(query: str) -> str:
    """Busca la URL de una imagen de un producto. Primero intenta con Knasta.cl, luego DuckDuckGo."""
    logger_obs.info("tool_buscar_foto_componente", metadata={"query": query[:100]})
    try:
        import json as _json
        import re as _re
        import requests as _requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/120.0",
            "Accept": "text/html",
        }
        url = f"https://knasta.cl/results?q={_requests.utils.quote(query)}&page=1"
        r = _requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        m = _re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            r.text,
            _re.DOTALL,
        )
        if m:
            data = _json.loads(m.group(1))
            init = data.get("props", {}).get("pageProps", {}).get("initialData", {})
            products = init.get("products", [])
            for p in products[:5]:
                img = p.get("image") or p.get("thumbnail_image") or ""
                if img:
                    return img
    except Exception as e:
        logger_obs.warning("tool_buscar_foto_knasta_fallo", metadata={"error": str(e)})
    try:
        from duckduckgo_search import DDGS
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            resultados = DDGS().images(query, max_results=1)
        if resultados:
            return resultados[0]["image"]
        return "No se encontro imagen. Indica al usuario que puede buscar una foto manualmente del producto en knasta.cl."
    except Exception as e:
        logger_obs.error("tool_buscar_foto_componente_error", metadata={"error": str(e)})
        return f"No se pudo buscar imagen debido a un error. Sugiere al usuario buscar una foto manualmente del producto en knasta.cl."


@tool
def _buscar_knasta(producto: str) -> str:
    """Busca productos en Knasta.cl (tienda online chilena) con precios actualizados del mercado.
    USA esta herramienta CUANDO el usuario te pida comparar precios de mercado,
    buscar productos en tiendas online, o cuando no encuentres el producto en tu catalogo local.
    Hace una busqueda en tiempo real en Knasta.cl."""
    logger_obs.info("tool_buscar_knasta", metadata={"producto": producto[:100]})
    import re as _re
    import json as _json
    import requests as _requests
    from urllib.parse import quote as _url_quote
    import time as _time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    url = f"https://knasta.cl/results?q={_url_quote(producto)}&page=1&page_size=8"

    last_error = None
    for intento in range(3):
        try:
            r = _requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            m = _re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                r.text,
                _re.DOTALL,
            )
            if not m:
                last_error = RuntimeError("__NEXT_DATA__ no encontrado en la pagina")
                _time.sleep(1)
                continue
            data = _json.loads(m.group(1))
            init = data.get("props", {}).get("pageProps", {}).get("initialData", {})
            products = init.get("products", [])
            if not products:
                return f"No se encontraron productos en Knasta para: {producto}"
            resultados = []
            for p in products[:8]:
                title = p.get("title", "Sin titulo")
                precio = p.get("current_price", 0)
                tienda = p.get("retail_label", "")
                url_p = p.get("url", "")
                img = p.get("image") or p.get("thumbnail_image") or ""
                precio_str = f"${int(precio):,}".replace(",", ".") if precio else "Consultar"
                img_line = f"  Imagen: {img}" if img else ""
                resultados.append(f"- {title}\n  Precio: {precio_str} CLP | Tienda: {tienda}\n  URL: {url_p}\n{img_line}".rstrip())
            return "Resultados de Knasta.cl:\n\n" + "\n\n".join(resultados)
        except Exception as e:
            last_error = e
            logger_obs.warning("tool_buscar_knasta_retry", metadata={"intento": intento + 1, "error": str(e)[:200]})
            _time.sleep(1)

    logger_obs.warning("tool_buscar_knasta_fallback_solotodo", metadata={"producto": producto[:100], "error": str(last_error)[:200]})
    try:
        resultado_st = _buscar_solotodo.invoke({"producto": producto})
        return f"[Knasta.cl no disponible en este momento. Resultados alternativos desde SoloTodo:]\n\n{resultado_st}"
    except Exception as fallback_error:
        logger_obs.error("tool_buscar_knasta_fallback_error", metadata={"error": str(fallback_error)[:200]})
        return _json.dumps({
            "error": "No se pudo buscar en Knasta ni en SoloTodo.",
            "detalle": f"Knasta: {str(last_error)[:100]} | SoloTodo: {str(fallback_error)[:100]}",
            "sugerencia": "Sugiere al usuario intentar mas tarde o buscar manualmente en estas tiendas.",
        })


@tool
def _buscar_solotodo(producto: str) -> str:
    """Busca productos en SoloTodo.com (API oficial) con precios actualizados del mercado chileno.
    Usa esta herramienta CUANDO el usuario te pida EXPRESAMENTE buscar en SoloTodo,
    o quiera comparar precios de proveedores chilenos en SoloTodo.
    Retorna productos con precio, tienda, link e imagen."""
    logger_obs.info("tool_buscar_solotodo", metadata={"producto": producto[:100]})
    import json as _json
    import requests as _requests
    import time as _time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    API_BASE = "https://api.solotodo.com"

    CATEGORY_KEYWORDS = {
        3: ["procesador", "cpu", "ryzen", "intel", "core i", "amd"],
        5: ["placa", "motherboard", "mother"],
        2: ["tarjeta", "grafica", "gpu", "video", "rtx", "gtx", "radeon"],
        7: ["ram", "memoria", "ddr4", "ddr5"],
        39: ["ssd", "disco", "almacenamiento", "nvm", "hdd", "nvme"],
        9: ["fuente", "psu", "poder", "power"],
        10: ["gabinete", "case", "torre"],
        4: ["monitor", "pantalla"],
        12: ["cooler", "ventilador", "refrigeracion"],
    }

    CATEGORY_NAMES = {
        3: "Procesador", 5: "Placa Madre", 2: "Tarjeta Video",
        7: "Memoria RAM", 39: "Almacenamiento", 9: "Fuente Poder",
        10: "Gabinete", 4: "Monitor", 12: "Cooler CPU",
    }

    query_lower = producto.lower()
    cat_ids = [cid for cid, keywords in CATEGORY_KEYWORDS.items() if any(kw in query_lower for kw in keywords)]
    if not cat_ids:
        cat_ids = list(CATEGORY_KEYWORDS.keys())

    all_results = []
    seen_ids = set()
    cat_str = ",".join(str(c) for c in cat_ids[:3])
    url = f"{API_BASE}/products/?categories={cat_str}&page_size=8&format=json"

    try:
        r = _requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        products = data.get("results", [])

        for p in products[:8]:
            prod_id = p.get("id")
            if prod_id in seen_ids:
                continue
            seen_ids.add(prod_id)

            name = p.get("name", "Sin nombre")

            precio = "Consultar"
            tienda = "SoloTodo"
            product_url = f"https://www.solotodo.com/products/{prod_id}"

            try:
                ent_url = f"{API_BASE}/entities/?products={prod_id}&is_visible=True&page_size=1&format=json"
                ent_r = _requests.get(ent_url, headers=headers, timeout=10)
                if ent_r.status_code == 200:
                    ent_data = ent_r.json()
                    entities = ent_data.get("results", [])
                    if entities:
                        ent = entities[0]
                        # Solo incluir si tiene external_url real (no URL de API)
                        external = ent.get("external_url", "")
                        if not external or "api.solotodo.com" in external:
                            _time.sleep(0.2)
                            continue
                        store_info = ent.get("store", {})
                        tienda = store_info.get("name", "SoloTodo") if isinstance(store_info, dict) else "SoloTodo"
                        registry = ent.get("active_registry")
                        precio = "Consultar"
                        if registry and registry.get("offer_price"):
                            precio = f"${int(float(registry['offer_price'])):,}".replace(",", ".")
                            all_results.append({
                                "name": name,
                                "precio": precio,
                                "tienda": tienda,
                                "url": external,
                            })
                        elif registry and registry.get("normal_price"):
                            precio = f"${int(float(registry['normal_price'])):,}".replace(",", ".")
                            all_results.append({
                                "name": name,
                                "precio": precio,
                                "tienda": tienda,
                                "url": external,
                            })
                _time.sleep(0.2)
            except Exception:
                pass

        if all_results:
            lineas = []
            for r in all_results:
                lineas.append(f"**{r['name']}**\nPrecio: {r['precio']} CLP | Tienda: {r['tienda']}\n[Comprar en {r['tienda']}]({r['url']})")
            return "Resultados de SoloTodo:\n\n" + "\n\n".join(lineas)
        return f"No se encontraron productos con precios disponibles en SoloTodo para: {producto}"

    except Exception as e:
        logger_obs.error("tool_buscar_solotodo_error", metadata={"error": str(e)})
        return _json.dumps({
            "error": "No se pudo buscar en SoloTodo.",
            "detalle": str(e)[:200],
            "sugerencia": "Sugiere usar _buscar_knasta o _buscar_web como alternativa.",
        })


@tool
def _agregar_al_carrito(producto: str, cantidad: int, precio_unitario: float) -> str:
    """Agrega un producto al carrito de compras del usuario."""
    logger_obs.info("tool_agregar_al_carrito", metadata={"producto": producto[:50], "cantidad": cantidad, "precio_unitario": precio_unitario})
    resultado = app_state.carrito.agregar(producto, cantidad, precio_unitario)
    logger_obs.info("tool_agregar_al_carrito_completado", metadata={"producto": producto[:50], "resultado": resultado[:200]})
    return resultado


@tool
def _ver_carrito() -> str:
    """Muestra los productos actuales en el carrito de compras y el precio total."""
    logger_obs.info("tool_ver_carrito")
    resultado = app_state.carrito.ver()
    logger_obs.info("tool_ver_carrito_completado", metadata={"resultado": resultado[:200]})
    return resultado


_TOOLS[:] = [_buscar_catalogo_local, _buscar_web, _buscar_knasta, _buscar_solotodo, _calcular_presupuesto, _buscar_foto_componente, _agregar_al_carrito, _ver_carrito]

app_state = HardiBotAppState(os.getenv("PERSONA_ID", "hardware")).iniciar()


def reconfigurar_agente(persona_id: str) -> dict:
    """Cambia la personalidad del bot en caliente. Usado desde la UI."""
    app_state.reconfigurar(persona_id)
    return {"persona_id": persona_id, "nombre": app_state.nombre_bot, "titulo": app_state.titulo_bot}


async def chat_hardibot(user_input: str, session_id: str = "eval_session"):
    console.print(Rule(title=f"HardiBot ({app_state.persona_id})", style="bold blue", align="left"))
    start_time = time.time()
    trace_id = f"chat-{int(time.time())}"
    logger_obs.info("chat_hardibot_inicio", metadata={"user_input": user_input[:100], "session_id": session_id}, trace_id=trace_id)

    resultado_seguridad = app_state.agente_seguro.procesar(user_input)
    if not resultado_seguridad.es_seguro:
        logger_obs.warning("seguridad_bloqueo_chat", metadata={"razones": [e.detalle for e in resultado_seguridad.eventos]}, trace_id=trace_id)
        console.print(f"\n[bold red]Seguridad:[/bold red] {resultado_seguridad.error_multi_idioma}")
        return

    cached = cache_llm.obtener(user_input, os.getenv("MODEL_NAME", "gpt-4o"))
    if cached:
        total_time = time.time() - start_time
        logger_obs.info("cache_hit_chat", metadata={"latencia": round(total_time, 2)}, trace_id=trace_id)
        console.print(Markdown(cached))
        console.print(Rule(style="dim"))
        console.print(f"[dim]Cache hit en {total_time:.2f}s[/dim]")
        reporte_sostenibilidad.agregar_metricas_cache(hits=1, tokens_ahorrados=estimar_tokens(cached))
        return

    modelo_config = seleccionar_modelo(user_input)
    tokens_in = estimar_tokens(user_input)

    try:
        with Live(Markdown("Analizando y ejecutando herramientas..."), console=console, refresh_per_second=15) as live:
            respuesta = app_state.agent.invoke(
                {"messages": [("user", user_input)]},
                config={"configurable": {"thread_id": session_id}},
            )
            live.update(Markdown(respuesta["messages"][-1].content))
        _sistema_trazas.finalizar_traza()
        _sistema_trazas.guardar()
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        logger_obs.error("chat_hardibot_error", metadata={"error": str(e)}, trace_id=trace_id)
    total_time = time.time() - start_time
    tokens_out = estimar_tokens(str(respuesta["messages"][-1].content)) if "messages" in locals() and respuesta["messages"] else 0
    logger_obs.info("chat_hardibot_completado", metadata={"duracion_s": round(total_time, 2)}, trace_id=trace_id)

    cache_llm.guardar(user_input, modelo_config.nombre, str(respuesta["messages"][-1].content) if "messages" in locals() and respuesta["messages"] else "")
    calculador_costos.registrar(modelo_config.nombre, tokens_in, tokens_out)
    reporte_sostenibilidad.agregar_registro(modelo_config.nombre, tokens_in, tokens_out, total_time, "exito" if "messages" in locals() else "error")

    recolector_obs.registrar_exito(
        modelo=modelo_config.nombre,
        tiempo_respuesta_ms=total_time * 1000,
        tokens_prompt=tokens_in,
        tokens_completion=tokens_out,
        trace_id=trace_id,
    )

    alertas = sistema_alertas.evaluar(recolector_obs)
    for alerta in alertas:
        logger_obs.warning("alerta_disparada", metadata={
            "regla": alerta.regla,
            "severidad": alerta.severidad,
            "valor": alerta.valor_actual,
            "umbral": alerta.umbral,
        }, trace_id=trace_id)

    costo_alertas = calculador_costos.evaluar_alertas(calculador_costos.total_gastado())
    for alerta in costo_alertas:
        logger_obs.warning("costo_alerta", metadata={"nivel": alerta["nivel"], "mensaje": alerta["mensaje"]}, trace_id=trace_id)

    reporte_sostenibilidad.guardar()
    console.print(Rule(style="dim"))
    console.print(f"[dim]Inferencia completada en {total_time:.2f}s | Modelo: {modelo_config.nombre}[/dim]")


def iniciar_loop():
    print("=" * 60)
    print(f"  {app_state.nombre_bot} CLI - Modo Produccion")
    print("=" * 60)
    while True:
        try:
            user_input = input("\nTu: ").strip()
            if user_input.lower() in ["salir", "exit"]:
                break
            asyncio.run(chat_hardibot(user_input))
        except KeyboardInterrupt:
            break


def chat_hardibot_stream_sync(user_input: str, session_id: str = "streamlit_session"):
    respuesta = app_state.agent.invoke(
        {"messages": [("user", user_input)]},
        config={"configurable": {"thread_id": session_id}},
    )
    mensajes = respuesta["messages"]
    textos_ia = []
    for msg in reversed(mensajes):
        if msg.type == "human":
            break
        if msg.type == "ai" and msg.content:
            textos_ia.insert(0, msg.content)
    texto_final = "\n\n---\n\n".join(textos_ia)
    for palabra in texto_final.split(" "):
        yield palabra + " "
        time.sleep(0.02)


