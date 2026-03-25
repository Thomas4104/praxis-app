#!/usr/bin/env bash
# ============================================================================
# OMNIA Praxissoftware - Wiederherstellung eines verschluesselten Backups
# ============================================================================
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
