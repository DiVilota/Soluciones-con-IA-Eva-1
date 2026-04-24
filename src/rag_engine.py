import os
import pandas as pd
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from rich.console import Console

console = Console()
load_dotenv(override=True)

class HardiBotRAG:
    def __init__(self, data_path: str = "data/catalogo_hardware.csv"):
        self.data_path = data_path
        self.vector_store = None
        
        # Inicialización del modelo de Embeddings 
        try:
            self.embeddings = OpenAIEmbeddings(
                base_url=os.getenv("OPENAI_BASE_URL"),
                api_key=os.getenv("GITHUB_TOKEN"),
                model="text-embedding-3-small" # Modelo optimizado para RAG
            )
        except Exception as e:
            console.print(f"[red]Error al cargar Embeddings: {e}[/red]")

    def construir_indice(self):
        """Lee el CSV, genera los Chunks semánticos y los vectoriza en FAISS."""
        console.print("[dim]⚙️ Iniciando ingesta de datos (RAG)...[/dim]")
        
        if not os.path.exists(self.data_path):
            console.print(f"[red]❌ No se encontró el catálogo en: {self.data_path}[/red]")
            return False

        # 1. Ingesta
        df = pd.read_csv(self.data_path)
        documents = []

        # 2. Semantic Chunking (Transformar filas a lenguaje natural)
        for _, row in df.iterrows():
            # Construimos un string semántico que el LLM entienda perfectamente
            chunk_content = (
                f"Componente: {row['Categoria']}\n"
                f"Producto: {row['Marca']} {row['Modelo']}\n"
                f"Especificaciones Técnicas: {row['Especificaciones']}\n"
                f"Precio: ${row['Precio_CLP']} CLP\n"
                f"Disponibilidad de Stock: {row['Stock']}"
            )
            
            # Agregamos metadata por si queremos filtrar luego
            doc = Document(
                page_content=chunk_content, 
                metadata={"categoria": row['Categoria'], "marca": row['Marca']}
            )
            documents.append(doc)

        # 3. Vectorización y almacenamiento en FAISS
        try:
            self.vector_store = FAISS.from_documents(documents, self.embeddings)
            console.print(f"[bold green]✅ Índice Vectorial FAISS creado: {len(documents)} productos indexados.[/bold green]")
            return True
        except Exception as e:
            console.print(f"[bold red]❌ Error al vectorizar: {e}[/bold red]")
            return False

    def recuperar_contexto(self, query: str, top_k: int = 3) -> str:
        """Busca los K productos más relevantes para la consulta del usuario."""
        if not self.vector_store:
            console.print("[yellow]⚠️ Índice vacío. Construyendo índice primero...[/yellow]")
            self.construir_indice()

        # Búsqueda de similitud vectorial
        resultados = self.vector_store.similarity_search(query, k=top_k)
        
        # Consolidar los resultados en un solo string para inyectar al LLM
        contexto = "\n---\n".join([doc.page_content for doc in resultados])
        return contexto

# Bloque de prueba unitaria (Smoke Test)
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