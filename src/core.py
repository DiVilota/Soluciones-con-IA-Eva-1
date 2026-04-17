import os
import time
import asyncio
from typing import Dict, List
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from rich.live import Live

from src.prompts import HARDIBOT_SYSTEM_PROMPT
from src.rag_engine import HardiBotRAG  # <-- Importamos el Motor RAG

load_dotenv(override=True)

console = Console()

# ── 1. Inicialización de RAG ─────────
motor_rag = HardiBotRAG()
motor_rag.construir_indice() # Crea el FAISS local al arrancar

# ── 2. Configuración del Modelo ─────────
llm = ChatOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("GITHUB_TOKEN"),
    model="gpt-4o",
    temperature=0.4,
    max_tokens=800,
    streaming=True 
)

# ── 3. Gestión de Memoria ─────────
class WindowChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, k: int = 4):
        self.k = k
        self._messages = []
    
    @property
    def messages(self):
        return self._messages[-(self.k * 2):]
    
    def add_message(self, message):
        self._messages.append(message)
    
    def clear(self):
        self._messages.clear()

store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = WindowChatMessageHistory(k=4)
    return store[session_id]

# ── 4. Construcción de la Cadena ─────────
prompt = ChatPromptTemplate.from_messages([
    ("system", HARDIBOT_SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}")
])

chain = prompt | llm
conversation = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="chat_history"
)

# ── 5. Interfaz y Streaming ─────────
async def chat_hardibot(user_input: str, session_id: str = "eval_session"):
    console.print(Rule(title="🤖 HardiBot", style="bold blue", align="left"))
    respuesta_completa = ""
    start_time = time.time()
    
    try:
        # Primero recupera el contexto de la base de datos antes de pensar
        contexto_recuperado = motor_rag.recuperar_contexto(user_input, top_k=15)
        
        with Live(Markdown("⏳ *Pensando y buscando en catálogo...*"), console=console, refresh_per_second=15) as live:
            # Segundo, Inyectar la pregunta + el contexto RAG + historial
            async for chunk in conversation.astream(
                {
                    "input": user_input,
                    "context": contexto_recuperado  
                },
                config={"configurable": {"session_id": session_id}}
            ):
                respuesta_completa += chunk.content
                live.update(Markdown(respuesta_completa))
    except Exception as e:
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")

    total_time = time.time() - start_time
    console.print(Rule(style="dim"))
    console.print(f"[dim]⚡ Inferencia completada en {total_time:.2f}s[/dim]")

def iniciar_loop():
    print("=" * 60)
    print(" 🖥️  HardiBot CLI - Modo Producción (RAG Activado)")
    print("=" * 60)
    while True:
        try:
            user_input = input("\n👤 Tú: ").strip()
            if user_input.lower() in ["salir", "exit"]: break
            asyncio.run(chat_hardibot(user_input))
        except KeyboardInterrupt: break