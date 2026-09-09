# ==============================================================================
# DOCKERFILE - RESTAURANTE RYU (SISTEMA DE TELEFONIA IA Y RECEPCIONISTA EN VIVO)
# Optimizado para baja latencia, códecs de audio y ejecución rápida en CPU (CTranslate2)
# ==============================================================================

FROM python:3.11-slim-bookworm

# 1. Configurar variables de entorno globales de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HUB_ENABLE_HF_TRANSFER=0

# 2. Instalar dependencias esenciales de sistema para audio, códecs y OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    sox \
    libsox-fmt-all \
    libgomp1 \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. Directorio de trabajo en el contenedor
WORKDIR /app

# 4. Instalar dependencias de Python (aprovechando caché de capas de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 5. Pre-descargar el modelo faster-whisper 'base' dentro de la imagen
# Esto garantiza que el contenedor arranque en frío en menos de 2 segundos sin esperar descargas
RUN python -c "from faster_whisper import WhisperModel; print('Pre-descargando modelo faster-whisper base...'); WhisperModel('base', device='cpu', compute_type='int8')"

# 6. Copiar el código fuente y archivos de configuración
COPY . .

# 7. Crear directorio para logs persistentes
RUN mkdir -p /app/logs

# 8. Exponer puertos estándar de SIP y API
EXPOSE 5060/udp
EXPOSE 5061/udp
EXPOSE 8000/tcp

# 9. Comando de inicio predeterminado (Servicio telefónico SIP de alta fidelidad)
CMD ["python", "-u", "sip_telephony_service.py"]
