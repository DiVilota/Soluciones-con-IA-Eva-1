import os
import time
import asyncio
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.live import Live

from src.prompts import HARDIBOT_SYSTEM_PROMPT
from src.rag_engine import HardiBotRAG

# --- Importaciones Modernas (LangGraph + LangChain Core) ---
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

load_dotenv(override=True)
console = Console()

# ── 1. Inicialización de RAG ─────────
motor_rag = HardiBotRAG()
motor_rag.construir_indice()

# ── 2. Configuración del Modelo ─────────
llm = ChatOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("GITHUB_TOKEN"),
    model="gpt-4o",
    temperature=0.4,
    max_tokens=800,
    streaming=True,
)


# ── 3. Definición de Herramientas (Tools) ─────────
@tool
def buscar_catalogo(query: str) -> str:
    """
    Usa esta herramienta SIEMPRE que el usuario pregunte por componentes,
    precios, stock o compatibilidad de hardware.
    """
    return motor_rag.recuperar_contexto(query, top_k=5)


@tool
def calcular_presupuesto(operacion: str) -> str:
    """
    Usa esta herramienta para sumar o multiplicar los precios de los componentes.
    Ingresa SOLO la operación matemática en formato Python (ejemplo: 145000 + 55000).
    """
    try:
        return str(eval(operacion, {"__builtins__": None}, {}))
    except Exception as e:
        return f"Error en cálculo: {e}"


herramientas = [buscar_catalogo, calcular_presupuesto]
# ── 4. Construcción del Agente (LangGraph) ─────────
memoria = MemorySaver()

agent_executor = create_react_agent(
    model=llm,
    tools=herramientas,
    prompt=HARDIBOT_SYSTEM_PROMPT,  # <--- SOLUCIONADO
    checkpointer=memoria,
)


# ── 5. Interfaz y Streaming ─────────
async def chat_hardibot(user_input: str, session_id: str = "eval_session"):
    console.print(Rule(title="🤖 HardiBot", style="bold blue", align="left"))
    start_time = time.time()

    try:
        with Live(
            Markdown("⏳ *Analizando y ejecutando herramientas...*"),
            console=console,
            refresh_per_second=15,
        ) as live:
            # LangGraph usa un formato de "messages" y agrupa el historial por "thread_id"
            respuesta = agent_executor.invoke(
                {"messages": [("user", user_input)]},
                config={"configurable": {"thread_id": session_id}},
            )
            # Imprime el último mensaje (la respuesta final del bot)
            live.update(Markdown(respuesta["messages"][-1].content))
    except Exception as e:
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")

    total_time = time.time() - start_time
    console.print(Rule(style="dim"))
    console.print(f"[dim]⚡ Inferencia completada en {total_time:.2f}s[/dim]")


def iniciar_loop():
    print("=" * 60)
    print(" 🖥️  HardiBot CLI - Modo Producción (LangGraph Agent)")
    print("=" * 60)
    while True:
        try:
            user_input = input("\n👤 Tú: ").strip()
            if user_input.lower() in ["salir", "exit"]:
                break
            asyncio.run(chat_hardibot(user_input))
        except KeyboardInterrupt:
            break


def chat_hardibot_stream_sync(user_input: str, session_id: str = "streamlit_session"):
    """
    Generador sincrono para Streamlit adaptado a LangGraph.
    """
    respuesta = agent_executor.invoke(
        {"messages": [("user", user_input)]},
        config={"configurable": {"thread_id": session_id}},
    )

    texto_final = respuesta["messages"][-1].content

    # Efecto de escritura para Streamlit
    for palabra in texto_final.split(" "):
        yield palabra + " "
        time.sleep(0.02)
