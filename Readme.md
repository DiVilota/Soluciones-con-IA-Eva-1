<div align="center">
  <h1>🤖 HardiBot v3.0 (Fase IL2.1)</h1>
  <p><b>Arquitectura de Agentes Inteligentes con LangGraph & Streamlit</b></p>
  
  ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)
  ![Docker](https://img.shields.io/badge/Docker-Production_Ready-2496ED?logo=docker&logoColor=white)
  ![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_AI-orange?logo=langchain&logoColor=white)
  ![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B?logo=streamlit&logoColor=white)
  ![Duoc UC](https://img.shields.io/badge/Duoc_UC-Ingenier%C3%ADa_en_Inform%C3%A1tica-yellow)
</div>

> **Actualización IL2.1:** HardiBot ha evolucionado de una cadena estática a un **Agente Inteligente**. Ahora utiliza el ciclo de razonamiento ReAct impulsado por **LangGraph**, es capaz de decidir cuándo usar herramientas externas (Búsqueda en Catálogo FAISS o Calculadora de Presupuestos) y cuenta con una interfaz web moderna mediante **Streamlit**.

---

## 🛠️ Stack Tecnológico Actualizado

| Capa Arquitectónica      | Tecnología Base    | Descripción Técnica                                                             |
| :----------------------- | :----------------- | :------------------------------------------------------------------------------ |
| **Motor de IA**          | `GPT-4o`           | Inferencia y razonamiento complejo vía GitHub Models API.                       |
| **Orquestación Agentic** | `LangGraph`        | Máquina de estados para control de flujo y ciclo ReAct.                         |
| **Herramientas (Tools)** | `Function Calling` | Herramientas de RAG (`buscar_catalogo`) y matemáticas (`calcular_presupuesto`). |
| **Presentación**         | `Streamlit`        | Interfaz gráfica web con streaming de texto asíncrono.                          |
| **Observabilidad**       | `LangSmith`        | Trazabilidad completa de _tokens_, latencia y uso de herramientas en _backend_. |
| **Infraestructura**      | `Docker`           | Contenedorización inmutable mapeada al puerto 8501.                             |

---

## 🚀 Guía de Despliegue Rápido (Para Colaboradores)

### 1. Configuración de Entorno (Requisito Crítico)

Para esta versión, es **obligatorio** configurar las variables de LangSmith en tu archivo `.env` para poder monitorear los "pensamientos" del agente.

Asegúrate de que tu archivo `.env` contenga lo siguiente:

```env
# --- GitHub Models API ---
OPENAI_BASE_URL="[https://models.inference.ai.azure.com](https://models.inference.ai.azure.com)"
GITHUB_TOKEN="tu_token_aqui"

# --- LangSmith (Observabilidad) ---
LANGCHAIN_TRACING_V2="true"
LANGCHAIN_API_KEY="tu_api_key_de_langsmith_aqui"
LANGCHAIN_PROJECT="ingenieria_soluciones_con_ia"
LANGCHAIN_ENDPOINT="[https://api.smith.langchain.com](https://api.smith.langchain.com)"
2. Ejecución Inmutable (Docker Compose)
Dado que actualizamos drásticamente las versiones en requirements.txt (Migración a LangChain/LangGraph 0.3.x), la primera vez debes construir la imagen sin usar caché local:

Bash
# 1. Construir la imagen asegurando dependencias limpias
docker-compose build --no-cache

# 2. Levantar el servidor web
docker-compose up
3. Acceso a la Aplicación
Una vez que la terminal indique que el contenedor está corriendo, abre tu navegador web e ingresa a:
👉 http://localhost:8501

🔬 ¿Cómo evaluar a HardiBot en esta fase?
Dado que la consola ahora es silenciosa (LangGraph procesa los estados internamente), el testing se realiza mediante LangSmith.

Hazle una pregunta en la interfaz de Streamlit (Ej: "Cotízame un Ryzen 5 5600G y una placa Asus A320M-K y dame el total").

Ve a tu cuenta de LangSmith -> Proyecto ingenieria_soluciones_con_ia.

Haz clic en el Run más reciente para visualizar el Trace.

Podrás ver en tiempo real:

El ahorro de tokens cuando no usa herramientas (ej. al saludar).

Cómo invoca la herramienta RAG y qué fragmentos del CSV extrae.

Cómo invoca la herramienta de cálculo matemático para asegurar una suma exacta.
Documentación técnica elaborada para Ingeniería de Soluciones con Inteligencia Artificial.
Integrantes: Diego Villota e Ignacio Chacón
```
