# OMNIA Praxissoftware - Docker Image (gehaertet)
FROM python:3.12-slim-bookworm

# Sicherheits-Updates und System-Dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
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

# Verzeichnisse erstellen und Berechtigungen setzen
RUN mkdir -p /app/uploads /app/instance && \
    chown -R appuser:appuser /app/uploads /app/instance

# Als non-root User ausfuehren
USER appuser

# Port exponieren
EXPOSE 8000

# Health-Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Gunicorn starten
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
