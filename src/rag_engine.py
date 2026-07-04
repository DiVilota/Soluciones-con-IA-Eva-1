import os
import pandas as pd
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from rich.console import Console

console = Console(no_color=True, force_terminal=False)
load_dotenv(override=True)

CATALOGO_POR_DEFECTO = "data/catalogo_hardware.csv"
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
FAISS_INDEX_DIR = os.path.join(_DATA_DIR, "faiss_index")


class HardiBotRAG:
    def __init__(self, data_path: str = CATALOGO_POR_DEFECTO):
        self.data_path = data_path
        self.vector_store = None

        try:
            self.embeddings = OpenAIEmbeddings(
                base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
                api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GITHUB_TOKEN"),
                model="text-embedding-3-small"
            )
        except Exception as e:
            console.print(f"[red]Error al cargar Embeddings: {e}[/red]")

    def _indice_guardado_valido(self):
        return os.path.isdir(FAISS_INDEX_DIR) and os.path.exists(os.path.join(FAISS_INDEX_DIR, "index.faiss"))

    def _cargar_indice_guardado(self):
        if not self._indice_guardado_valido():
            return False
        try:
            self.vector_store = FAISS.load_local(
                FAISS_INDEX_DIR, self.embeddings, allow_dangerous_deserialization=True
            )
            console.print(f"[bold green]Indice FAISS cargado desde disco: {FAISS_INDEX_DIR}[/bold green]")
            return True
        except Exception as e:
            console.print(f"[yellow]No se pudo cargar indice FAISS guardado: {e}. Reconstruyendo...[/yellow]")
            return False

    def _guardar_indice(self):
        if self.vector_store is None:
            return
        try:
            os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
            self.vector_store.save_local(FAISS_INDEX_DIR)
            console.print(f"[dim]Indice FAISS guardado en: {FAISS_INDEX_DIR}[/dim]")
        except Exception as e:
            console.print(f"[yellow]No se pudo guardar indice FAISS: {e}[/yellow]")

    def construir_indice(self):
        if self._cargar_indice_guardado():
            return True

        console.print("[dim]Iniciando ingesta de datos (RAG)...[/dim]")

        if not os.path.exists(self.data_path):
            console.print(f"[red]No se encontro el catalogo en: {self.data_path}[/red]")
            return False

        df = pd.read_csv(self.data_path)
        documents = []

        for _, row in df.iterrows():
            precio_formateado = f"{int(row['Precio_CLP']):,}".replace(",", ".")
            chunk_content = (
                f"Componente: {row['Categoria']}\n"
                f"Producto: {row['Marca']} {row['Modelo']}\n"
                f"Especificaciones Técnicas: {row['Especificaciones']}\n"
                f"Precio: {precio_formateado} CLP\n"
                f"Disponibilidad de Stock: {row['Stock']}"
            )

            doc = Document(
                page_content=chunk_content,
                metadata={"categoria": row['Categoria'], "marca": row['Marca']}
            )
            documents.append(doc)

        try:
            self.vector_store = FAISS.from_documents(documents, self.embeddings)
            console.print(f"[bold green]Indice Vectorial FAISS creado: {len(documents)} productos indexados.[/bold green]")
            self._guardar_indice()
            return True
        except Exception as e:
            console.print(f"[bold red]Error al vectorizar: {e}[/bold red]")
            return False

    def recargar(self, data_path: str = None):
        if data_path:
            self.data_path = data_path
        return self.construir_indice()

    def recuperar_contexto(self, query: str, top_k: int = 15) -> str:
        if not self.vector_store:
            console.print("[yellow]Indice vacio. Construyendo indice primero...[/yellow]")
            self.construir_indice()

        query_lower = query.lower()
        palabras_clave = [p.strip() for p in query_lower.replace(",", "").split() if len(p.strip()) > 2]

        coincidencias = []
        try:
            df = pd.read_csv(self.data_path)
            for _, row in df.iterrows():
                texto = f"{row['Marca']} {row['Modelo']} {row['Especificaciones']}".lower()
                coinciden = sum(1 for p in palabras_clave if p in texto)
                if coinciden > 0:
                    coincidencias.append((coinciden, row))
            coincidencias.sort(key=lambda x: -x[0])
        except Exception:
            pass

        if coincidencias:
            fragmentos = []
            for _, row in coincidencias[:top_k]:
                precio_formateado = f"{int(row['Precio_CLP']):,}".replace(",", ".")
                frag = (
                    f"Componente: {row['Categoria']}\n"
                    f"Producto: {row['Marca']} {row['Modelo']}\n"
                    f"Especificaciones Técnicas: {row['Especificaciones']}\n"
                    f"Precio: {precio_formateado} CLP\n"
                    f"Disponibilidad de Stock: {row['Stock']}"
                )
                fragmentos.append(frag)
            console.print(f"[dim]Busqueda por keyword: {len(coincidencias)} coincidencias[/dim]")
            return "\n---\n".join(fragmentos)

        console.print("[dim]Sin coincidencias directas, usando FAISS...[/dim]")
        resultados = self.vector_store.similarity_search(query, k=top_k)

        contexto = "\n---\n".join([doc.page_content for doc in resultados])
        return contexto

    @property
    def total_productos(self) -> int:
        if os.path.exists(self.data_path):
            return sum(1 for _ in open(self.data_path)) - 1
        return 0


if __name__ == "__main__":
    motor = HardiBotRAG()
    exito = motor.construir_indice()

    if exito:
        print("\n--- TEST DE RECUPERACIÓN ---")
        busqueda = "Quiero una tarjeta de video barata para jugar en 1080p"
        print(f"Query: '{busqueda}'\n")

        resultados = motor.recuperar_contexto(busqueda)
        print("Resultados recuperados por FAISS:")
        print(resultados)
