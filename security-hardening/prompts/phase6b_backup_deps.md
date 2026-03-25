Du bist ein Reliability Engineer. Dein Auftrag: Backup-System und Dependencies in /Users/thomasbalke/praxis-app haerten.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: Backup-Script mit Verschluesselung
Datei: /Users/thomasbalke/praxis-app/scripts/backup.sh

Lies das bestehende Script und erstelle eine gehaertete Version:

```bash
#!/usr/bin/env bash
# ============================================================================
# OMNIA Praxissoftware - Verschluesseltes Datenbank-Backup
# Medizinische Daten erfordern verschluesselte Backups (DSG Art. 7)
# ============================================================================
set -euo pipefail

# Konfiguration
BACKUP_DIR="${BACKUP_DIR:-/backups/omnia}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-omnia}"
DB_NAME="${DB_NAME:-omnia}"
RETENTION_DAYS="${RETENTION_DAYS:-90}"     # 90 Tage lokale Retention
ARCHIVE_DAYS="${ARCHIVE_DAYS:-2555}"       # 7 Jahre Archiv (med. Aufbewahrungspflicht)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/omnia_${TIMESTAMP}.sql.gz.enc"
CHECKSUM_FILE="${BACKUP_DIR}/omnia_${TIMESTAMP}.sha256"
LOG_FILE="${BACKUP_DIR}/backup.log"

# Encryption Key aus Umgebung oder Datei
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
if [ -z "$BACKUP_ENCRYPTION_KEY" ] && [ -f "/run/secrets/backup_key" ]; then
    BACKUP_ENCRYPTION_KEY=$(cat /run/secrets/backup_key)
fi

if [ -z "$BACKUP_ENCRYPTION_KEY" ]; then
    echo "FEHLER: BACKUP_ENCRYPTION_KEY nicht gesetzt!" | tee -a "$LOG_FILE"
    exit 1
fi

# Verzeichnis erstellen
mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Backup gestartet ==="

# 1. Datenbank-Dump erstellen und verschluesseln
log "Erstelle verschluesselten Datenbank-Dump..."
PGPASSWORD="${DB_PASSWORD}" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=custom \
    --compress=9 \
    | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
    -pass env:BACKUP_ENCRYPTION_KEY \
    -out "$BACKUP_FILE"

if [ $? -ne 0 ]; then
    log "FEHLER: Datenbank-Dump fehlgeschlagen!"
    exit 1
fi

# 2. Checksum erstellen
log "Erstelle Checksum..."
sha256sum "$BACKUP_FILE" > "$CHECKSUM_FILE"

# 3. Backup-Groesse pruefen (Minimum 1KB als Sanity-Check)
BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat --printf="%s" "$BACKUP_FILE" 2>/dev/null)
if [ "$BACKUP_SIZE" -lt 1024 ]; then
    log "WARNUNG: Backup ungewoehnlich klein ($BACKUP_SIZE Bytes). Moeglicherweise fehlerhaft."
fi

log "Backup erstellt: $BACKUP_FILE ($BACKUP_SIZE Bytes)"

# 4. Upload-Verzeichnis sichern (Patientendokumente)
UPLOADS_DIR="/app/uploads"
if [ -d "$UPLOADS_DIR" ]; then
    UPLOADS_BACKUP="${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz.enc"
    log "Sichere Uploads-Verzeichnis..."
    tar czf - -C "$UPLOADS_DIR" . \
        | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -pass env:BACKUP_ENCRYPTION_KEY \
        -out "$UPLOADS_BACKUP"
    sha256sum "$UPLOADS_BACKUP" >> "$CHECKSUM_FILE"
    log "Uploads-Backup erstellt: $UPLOADS_BACKUP"
fi

# 5. Alte lokale Backups aufraemen (Retention)
log "Bereinige Backups aelter als $RETENTION_DAYS Tage..."
find "$BACKUP_DIR" -name "omnia_*.sql.gz.enc" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "uploads_*.tar.gz.enc" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "*.sha256" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

# 6. Backup-Integritaet verifizieren
log "Verifiziere Backup-Integritaet..."
if sha256sum -c "$CHECKSUM_FILE" > /dev/null 2>&1; then
    log "Checksum-Verifizierung erfolgreich"
else
    log "FEHLER: Checksum-Verifizierung fehlgeschlagen!"
    exit 1
fi

log "=== Backup abgeschlossen ==="
log "Datei: $BACKUP_FILE"
log "Checksum: $CHECKSUM_FILE"
echo ""
echo "Zum Wiederherstellen:"
echo "  openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -pass env:BACKUP_ENCRYPTION_KEY -in $BACKUP_FILE | pg_restore -d $DB_NAME"
```

## Aufgabe 2: Restore-Script erstellen
Erstelle: /Users/thomasbalke/praxis-app/scripts/restore.sh

```bash
#!/usr/bin/env bash
# Wiederherstellung eines verschluesselten Backups
set -euo pipefail

BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    echo "Verwendung: $0 <backup-datei.sql.gz.enc>"
    echo ""
    echo "Verfuegbare Backups:"
    ls -la /backups/omnia/omnia_*.sql.gz.enc 2>/dev/null || echo "  Keine Backups gefunden"
    exit 1
fi

if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
    echo "FEHLER: BACKUP_ENCRYPTION_KEY muss gesetzt sein!"
    exit 1
fi

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-omnia}"
DB_NAME="${DB_NAME:-omnia}"

echo "WARNUNG: Dies ueberschreibt die aktuelle Datenbank '$DB_NAME'!"
echo "Druecken Sie ENTER um fortzufahren oder CTRL+C zum Abbrechen."
read

echo "Stelle Backup wieder her: $BACKUP_FILE"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
    -pass env:BACKUP_ENCRYPTION_KEY \
    -in "$BACKUP_FILE" \
    | PGPASSWORD="${DB_PASSWORD}" pg_restore \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --clean \
    --if-exists

echo "Wiederherstellung abgeschlossen!"
```

## Aufgabe 3: Dependencies aktualisieren
Datei: /Users/thomasbalke/praxis-app/requirements.txt

Lies die aktuelle Datei und aktualisiere auf die neuesten Patch-Versionen.
Fuege fehlende Security-relevante Packages hinzu:

```
# Web Framework
Flask==3.1.1
Flask-Login==0.6.3
Flask-WTF==1.2.2
Flask-SQLAlchemy==3.1.1
flask-migrate==4.1.0
Flask-Limiter==3.12

# Database
SQLAlchemy==2.0.38
psycopg2-binary==2.9.10

# Security
cryptography>=43.0.0
pyotp>=2.9.0

# Server
gunicorn==23.0.0

# Utilities
reportlab==4.2.5
qrcode==8.0
Pillow==11.1.0
python-dotenv==1.0.1

# AI
anthropic==0.42.0
```

HINWEIS: Pruefe die tatsaechlichen aktuellen Versionen auf pypi.org oder via pip. Die Versionen oben sind Beispiele. Verwende die Versionen die bereits in der Datei stehen falls du nicht sicher bist, aendere nur offensichtlich veraltete.

## Aufgabe 4: Deploy-Script haerten
Datei: /Users/thomasbalke/praxis-app/scripts/deploy.sh

Lies das bestehende Script und erweitere es:

1. Vor dem Deploy: Automatisches Backup erstellen
2. Health-Check nach Deploy
3. Rollback bei Fehler

```bash
# Am Anfang:
echo "Erstelle Pre-Deploy Backup..."
bash /app/scripts/backup.sh || { echo "Backup fehlgeschlagen! Deploy abgebrochen."; exit 1; }

# Nach flask db upgrade:
echo "Pruefe Health..."
sleep 5
curl -sf http://localhost:8000/health > /dev/null || {
    echo "FEHLER: Health-Check fehlgeschlagen nach Deploy!"
    echo "Rollback empfohlen."
    exit 1
}
```

## Reihenfolge:
1. Lies backup.sh, deploy.sh, requirements.txt KOMPLETT
2. Aktualisiere backup.sh
3. Erstelle restore.sh
4. Aktualisiere requirements.txt
5. Aktualisiere deploy.sh
