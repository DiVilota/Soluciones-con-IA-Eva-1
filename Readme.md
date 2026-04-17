<div align="center">
  <h1>🤖 HardiBot</h1>
  <p><b>Consultor Experto en Hardware (Duoc UC Edition)</b></p>
  
  ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)
  ![Docker](https://img.shields.io/badge/Docker-Production_Ready-2496ED?logo=docker&logoColor=white)
  ![LangChain](https://img.shields.io/badge/LangChain-Enabled-green?logo=chainlink&logoColor=white)
  ![Duoc UC](https://img.shields.io/badge/Duoc_UC-Ingenier%C3%ADa_en_Inform%C3%A1tica-yellow)
</div>

> HardiBot es una solución integral de Inteligencia Artificial diseñada para automatizar la preventa técnica en el mercado de hardware computacional chileno. Utiliza **Razonamiento Lógico (LLM)** mediante modelos de última generación y una arquitectura **Production-Ready** para ofrecer recomendaciones precisas, compatibles y ajustadas a presupuestos locales.

---

## 🛠️ Stack Tecnológico

El proyecto se sustenta en una arquitectura de capas (*Clean Architecture*) integrando las siguientes herramientas:

| Capa Arquitectónica | Tecnología Base | Descripción Técnica |
| :--- | :--- | :--- |
| **Motor de IA** | `GPT-4o` | Inferencia y razonamiento complejo (OpenAI/Azure). |
| **Orquestación** | `LangChain` | Gestión de cadenas de pensamiento y pipeline RAG. |
| **Memoria** | `Window Buffer` | k=4 para control estricto de contexto y ahorro de tokens. |
| **Presentación** | `Rich` | Streaming asíncrono y renderizado Markdown en CLI. |
| **Infraestructura** | `Docker` | Contenedorización inmutable mediante Docker Compose. |
| **Seguridad** | `dotenv` | Enfoque *Zero Trust* para la inyección local de secretos. |

---

## 📂 Arquitectura de Directorios (Scaffolding)

```text
📦 hardibot-core
├── 📁 data/                # Almacenamiento de catálogos y fuentes para RAG (IL1.2)
├── 📁 notebooks/           # Experimentación y laboratorios pedagógicos
│   └── 📄 desarrollo.ipynb # Prototipado inicial de prompts y lógica
├── 📁 src/                 # Código fuente de producción
│   ├── 🐍 config.py        # Validador de variables de entorno y seguridad
│   ├── 🐍 core.py          # Motor asíncrono, gestión de memoria y lógica del LLM
│   └── 🐍 prompts.py       # Repositorio de Master Prompts (Few-Shot, CoT, XML)
├── 🐳 Dockerfile           # Manifiesto de construcción de la imagen Linux-Python
├── ⚙️ docker-compose.yml   # Orquestador de contenedores e inyección de volúmenes
├── 🐍 main.py              # Entrypoint (Punto de entrada) de la aplicación
└── 📄 requirements.txt     # Manifiesto de dependencias del ecosistema
🚀 Guía de Despliegue y Uso
1. Configuración de Entorno (Zero Trust)
⚠️ PRECAUCIÓN DE SEGURIDAD: El archivo .env contendrá credenciales críticas de tu proveedor cloud. Jamás debe ser versionado en tu control de código.

Copia la plantilla y configura tus llaves operativas:

Bash
cp .env.example .env
2. Ejecución Inmutable (Docker Compose)
Para garantizar la paridad de entornos y prevenir fallos de dependencias cruzadas entre sistemas operativos:

Bash
# 1. Construir la imagen aislada de nivel de producción
docker-compose build

# 2. Levantar el CLI interactivo (el contenedor se purga automáticamente al salir)
docker-compose run --rm hardibot-cli
3. Ejecución Local (Entorno de Desarrollo)
Si prefieres iterar directamente sobre tu entorno virtual:

Bash
# Sincronizar el manifiesto de dependencias locales
pip install -r requirements.txt

# Inicializar el orquestador principal
python main.py
🧠 Ingeniería de Prompts (IL1.1 / IL1.2)
HardiBot no solo responde; razona. Se han integrado las 5 técnicas mandatorias del curso de Duoc UC dentro de un Master Prompt consolidado:

🎯 Zero-Shot: Definición estricta de la "Persona" del Ingeniero Senior y restricciones del mercado chileno.

📚 Few-Shot: Inyección de vectores de ejemplo para estandarizar respuestas ante presupuestos inviables o cuellos de botella térmicos.

🔗 Chain-of-Thought (CoT): Desglose matemático y lógico paso a paso previo a la estructuración de la cotización final.

⚙️ Advanced XML Tags: Implementación de la etiqueta <analisis_tecnico> para aislar el proceso cognitivo del output visual del usuario final.

📐 Prompt Optimization: Formateo de salida riguroso en tablas Markdown para reducción de tokens y legibilidad óptima.

📈 Roadmap y Próximos Sprints (Fase 2)
[ ] Implementación RAG: Conexión con base de datos vectorial (FAISS) para ingesta y recuperación de precios reales de tiendas nacionales.

[ ] Observabilidad y Evaluación: Implementación de métricas de desempeño y trazabilidad de inferencia mediante LangSmith.

<div align="center">


<i>Documentación técnica elaborada para Ingeniería de Soluciones con Inteligencia Artificial.</i>
</div>