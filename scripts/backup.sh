#!/usr/bin/env bash
# OMNIA Praxissoftware - PostgreSQL Backup Script
set -euo pipefail

BACKUP_DIR="/backups/omnia"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/omnia_${TIMESTAMP}.sql.gz"

# Backup-Verzeichnis erstellen
mkdir -p "$BACKUP_DIR"

# PostgreSQL Dump mit gzip
echo "Starte Backup: ${BACKUP_FILE}"
pg_dump -h "${DB_HOST:-localhost}" -U "${DB_USER:-omnia}" -d "${DB_NAME:-omnia}" | gzip > "$BACKUP_FILE"

echo "Backup erstellt: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"

# Alte Backups loeschen (aelter als 30 Tage)
DELETED=$(find "$BACKUP_DIR" -name "omnia_*.sql.gz" -mtime +30 -delete -print | wc -l)
echo "Alte Backups geloescht: ${DELETED}"
