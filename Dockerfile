FROM python:3.11-slim

# System packages: FFmpeg + Coral runtime support
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Coral Edge TPU runtime (optional — only activated when /dev/apex_0 present)
# Installs libedgetpu1-std so the delegate loads automatically if a Coral is attached
RUN echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" \
    > /etc/apt/sources.list.d/coral-edgetpu.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - \
    && apt-get update \
    && apt-get install -y --no-install-recommends libedgetpu1-std \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Coral runtime not available on this arch — skipping"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install AI inference backend (ai-edge-litert, Python 3.11 compatible)
RUN pip install --no-cache-dir ai-edge-litert || \
    pip install --no-cache-dir tflite-runtime || \
    echo "No TFLite backend installed — Coral detection will be unavailable"

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY models/ ./models/ 2>/dev/null || true

RUN mkdir -p recordings/hls config models

EXPOSE 8765

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
