FROM python:3.11-slim

# System deps for soundfile/librosa
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY server.py config.py generator.py voice.py archive.py display.py player.py main.py synthesis.py storage.py card.py ./
COPY static/ static/

# EFS mount points (created at runtime, these are fallback defaults)
RUN mkdir -p /app/output /app/reference_audio /app/transcripts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
