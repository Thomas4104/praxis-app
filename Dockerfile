# OMNIA Praxissoftware - Docker Image
FROM python:3.12-slim-bookworm

# System-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root User erstellen
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Arbeitsverzeichnis
WORKDIR /app

# Dependencies zuerst (fuer Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY . .

# Uploads-Verzeichnis erstellen und Berechtigungen setzen
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app

# Als non-root User ausfuehren
USER appuser

# Port exponieren
EXPOSE 8000

# Gunicorn starten
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
