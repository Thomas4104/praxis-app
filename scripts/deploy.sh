#!/usr/bin/env bash
# ============================================================================
# OMNIA Praxissoftware - Deployment Script (gehaertet)
# Pre-Deploy Backup, Health-Check, Rollback bei Fehler
# ============================================================================
set -euo pipefail

APP_DIR="/home/ubuntu/praxis-app"
cd "$APP_DIR"

echo "=== OMNIA Deploy ==="

# Aktuellen Commit merken fuer Rollback
PREVIOUS_COMMIT=$(git rev-parse HEAD)
echo "Aktueller Commit: $PREVIOUS_COMMIT"

# Pre-Deploy Backup
echo "0/5 Erstelle Pre-Deploy Backup..."
bash /app/scripts/backup.sh || {
    echo "FEHLER: Backup fehlgeschlagen! Deploy abgebrochen."
    exit 1
}

# Code aktualisieren
echo "1/5 Git pull..."
git pull

NEW_COMMIT=$(git rev-parse HEAD)
echo "Neuer Commit: $NEW_COMMIT"

# Dependencies installieren
echo "2/5 pip install..."
pip install -r requirements.txt

# Datenbank-Migrationen
echo "3/5 Flask DB upgrade..."
flask db upgrade

# Service neu starten
echo "4/5 Neustart..."
sudo systemctl restart praxis-app

# Health Check nach 5 Sekunden
echo "5/5 Health Check..."
sleep 5
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "=== Deploy erfolgreich ==="
    echo "Commit: $NEW_COMMIT"
else
    echo "=== FEHLER: Health Check fehlgeschlagen ==="
    echo "Starte Rollback auf $PREVIOUS_COMMIT..."

    git checkout "$PREVIOUS_COMMIT"
    pip install -r requirements.txt
    flask db upgrade
    sudo systemctl restart praxis-app

    sleep 5
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "Rollback erfolgreich auf $PREVIOUS_COMMIT"
    else
        echo "KRITISCH: Rollback ebenfalls fehlgeschlagen! Manueller Eingriff noetig."
    fi
    exit 1
fi
