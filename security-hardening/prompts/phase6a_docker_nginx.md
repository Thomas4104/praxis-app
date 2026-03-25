Du bist ein DevSecOps Engineer. Dein Auftrag: Docker und Nginx in /Users/thomasbalke/praxis-app produktionsreif absichern.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: docker-compose.yml haerten
Datei: /Users/thomasbalke/praxis-app/docker-compose.yml

Lies die Datei zuerst. Dann erstelle eine gehaertete Version:

Anforderungen:
1. **Keine hardcoded Credentials** - Verwende ${VARIABLE:-default} Syntax
2. **Ports nur lokal** - DB und Redis nur ueber internes Netzwerk
3. **Netzwerk-Segmentierung** - frontend + backend Netzwerke
4. **Resource-Limits** - CPU und Memory Limits
5. **Health-Checks** - Fuer alle Services
6. **Restart-Policies** - Mit Limits
7. **Read-Only Filesystems** wo moeglich
8. **Security-Opts** - no-new-privileges

Beispiel-Struktur:
```yaml
version: '3.8'

services:
  web:
    build: .
    environment:
      - DATABASE_URI=postgresql://${DB_USER:-omnia}:${DB_PASSWORD}@db:5432/${DB_NAME:-omnia}
      - SECRET_KEY=${SECRET_KEY}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - FLASK_ENV=${FLASK_ENV:-production}
    ports:
      - "${WEB_PORT:-8000}:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - frontend
      - backend
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    security_opt:
      - no-new-privileges:true
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=${DB_NAME:-omnia}
      - POSTGRES_USER=${DB_USER:-omnia}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    # KEINE ports Sektion - nur intern erreichbar
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-omnia}"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD:-changeme} --maxmemory 256mb --maxmemory-policy allkeys-lru
    networks:
      - backend
    # KEINE ports Sektion
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-changeme}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
    restart: unless-stopped

  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./static:/app/static:ro
    depends_on:
      web:
        condition: service_healthy
    networks:
      - frontend
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
    restart: unless-stopped

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # Kein Internet-Zugang

volumes:
  postgres_data:
```

## Aufgabe 2: Nginx mit TLS konfigurieren
Datei: /Users/thomasbalke/praxis-app/nginx.conf

Erstelle eine produktionsreife Konfiguration. Behalte ALLE bestehenden proxy_pass und gzip Einstellungen bei, fuege hinzu:

```nginx
# Rate-Limiting Zonen
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=general:10m rate=60r/m;

# HTTP -> HTTPS Redirect
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name _;

    # SSL Zertifikate (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/app.omnia-health.ch/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.omnia-health.ch/privkey.pem;

    # Moderne TLS-Konfiguration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "0" always;  # Moderne Browser brauchen das nicht mehr
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    server_tokens off;
    client_max_body_size 16M;

    # Rate-Limiting auf Login
    location /login {
        limit_req zone=login burst=3 nodelay;
        # ... bestehende proxy_pass Konfiguration ...
    }

    # ... bestehende location Bloecke beibehalten ...
}
```

## Aufgabe 3: Dockerfile haerten
Datei: /Users/thomasbalke/praxis-app/Dockerfile

```dockerfile
FROM python:3.12-slim-bookworm

# Sicherheits-Updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies zuerst (Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Applikation
COPY . .

# Non-root User
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser && \
    mkdir -p /app/uploads /app/instance && \
    chown -R appuser:appuser /app/uploads /app/instance

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
```

## Aufgabe 4: .env.example erstellen/aktualisieren
Datei: /Users/thomasbalke/praxis-app/.env.example

```
# === OMNIA Praxissoftware - Umgebungsvariablen ===
# Kopiere diese Datei zu .env und setze ALLE Werte!
# NIEMALS .env in Git committen!

# Flask
FLASK_ENV=production
SECRET_KEY=               # python -c "import secrets; print(secrets.token_hex(32))"

# Datenbank
DB_USER=omnia
DB_PASSWORD=              # openssl rand -base64 24
DB_NAME=omnia
DATABASE_URI=postgresql://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}

# Redis
REDIS_PASSWORD=           # openssl rand -base64 24
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/0

# Verschluesselung
ENCRYPTION_KEY=           # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AUDIT_HMAC_KEY=           # openssl rand -base64 32

# Anthropic KI
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Web
WEB_PORT=8000
```

## Reihenfolge:
1. Lies docker-compose.yml, nginx.conf, Dockerfile KOMPLETT
2. Aktualisiere docker-compose.yml
3. Aktualisiere nginx.conf (bestehende Konfiguration BEIBEHALTEN, nur erweitern)
4. Aktualisiere Dockerfile
5. Erstelle/Aktualisiere .env.example
