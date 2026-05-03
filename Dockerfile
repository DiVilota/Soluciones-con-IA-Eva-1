FROM python:3.12-slim

# Configuraciones de optimización para Python en contenedores
# Evita la creación de archivos .pyc y fuerza a que stdout/stderr no tengan buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKDIR=/app

WORKDIR $WORKDIR

# Patrón de caché de capas: Instalar dependencias primero
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar exclusivamente los binarios de producción
COPY src/ ./src/
COPY main.py .
COPY app.py .

# Comando de ejecución para Streamlit, exponiendo el puerto 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]