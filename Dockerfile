# OMNIA Praxissoftware - Docker Image
FROM python:3.12-slim

# System-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis
WORKDIR /app

# Dependencies zuerst (fuer Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY . .

# Uploads-Verzeichnis erstellen
RUN mkdir -p /app/uploads && chown -R nobody:nogroup /app/uploads

# Port exponieren
EXPOSE 8000

# Gunicorn starten
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
