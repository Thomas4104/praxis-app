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
