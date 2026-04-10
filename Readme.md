# 🤖 HardiBot - Asistente Técnico RAG (Mercado Chileno)

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![LangChain](https://img.shields.io/badge/LangChain-Enabled-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-black.svg)
![DuocUC](https://img.shields.io/badge/DuocUC-Ingeniería_en_Informática-navy.svg)

## 📌 Descripción del Proyecto
HardiBot es un asistente conversacional de alto rendimiento diseñado para cotizar y armar presupuestos de hardware de PC. Este proyecto fue desarrollado como parte de la **Evaluación Parcial N°1** de la asignatura **Ingeniería de Soluciones con IA (ISY0101)**, correspondiente al 5to semestre de Ingeniería en Informática (Mención Desarrollo de Software) en Duoc UC.

El bot opera bajo una arquitectura **RAG (Retrieval-Augmented Generation)**, lo que le permite consultar un inventario local simulado de componentes de hardware en tiempo real, evitando alucinaciones y entregando presupuestos precisos en **Pesos Chilenos (CLP)**.

## 🏗️ Arquitectura y Tecnologías
Esta solución implementa patrones de diseño modernos utilizados en el sector retail y banca en Chile para asistentes virtuales:
* **Core LLM:** `gpt-4o` configurado con baja temperatura (`0.2`) para respuestas analíticas y deterministas.
* **Orquestación:** LangChain.
* **Base Vectorial en Memoria:** `FAISS` (Facebook AI Similarity Search).
* **Embeddings:** `text-embedding-3-small` de OpenAI.
* **UX/UI:** Implementación de **Streaming** de tokens para reducir la latencia percibida (Time To First Token) y uso de la biblioteca `rich` para formateo en consola.

## 📂 Estructura del Repositorio
```text
📦 soluciones-con-ia-eva-1
 ┣ 📜 desarrollo.ipynb       # Script principal con la implementación del Pipeline RAG y HardiBot.
 ┣ 📜 bibliotecas.ipynb      # Pruebas y validación de entornos/dependencias.
 ┣ 📜 requirements.txt       # Dependencias exactas del proyecto.
 ┣ 📜 .env.example           # Plantilla de variables de entorno (No exponer credenciales reales).
 ┗ 📜 .gitignore             # Exclusión de archivos temporales y entornos virtuales.

⚙️ Requisitos Previos
Python 3.10 o superior.

Una cuenta de GitHub para acceder a los modelos vía GitHub Models (o directamente una API Key de OpenAI).

⚙️ Requisitos Previos
Python 3.10 o superior.

Una cuenta de GitHub para acceder a los modelos vía GitHub Models (o directamente una API Key de OpenAI).
git clone [https://github.com/tu-usuario/soluciones-con-ia-eva-1.git](https://github.com/tu-usuario/soluciones-con-ia-eva-1.git)
cd soluciones-con-ia-eva-1

2. Crear y activar un entorno virtual (Recomendado):
# En Windows
python -m venv venv
venv\Scripts\activate

# En macOS/Linux
python3 -m venv venv
source venv/bin/activate

3. Instalar dependencias:
pip install -r requirements.txt

4. Configurar variables de entorno:

Copia el archivo .env.example y renómbralo a .env.

Inserta tus credenciales:
OPENAI_BASE_URL="[https://models.inference.ai.azure.com](https://models.inference.ai.azure.com)"
GITHUB_TOKEN="tu_token_aqui"

### Integrantes
Diego Villota
Ignacio Chacón