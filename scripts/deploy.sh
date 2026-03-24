#!/usr/bin/env bash
# OMNIA Praxissoftware - Deployment Script
set -euo pipefail

APP_DIR="/home/ubuntu/praxis-app"
cd "$APP_DIR"

echo "=== OMNIA Deploy ==="

# Code aktualisieren
echo "1/4 Git pull..."
git pull

# Dependencies installieren
echo "2/4 pip install..."
pip install -r requirements.txt

# Datenbank-Migrationen
echo "3/4 Flask DB upgrade..."
flask db upgrade

# Service neu starten
echo "4/4 Neustart..."
sudo systemctl restart praxis-app

# Health Check nach 3 Sekunden
sleep 3
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "=== Deploy erfolgreich ==="
else
    echo "=== WARNUNG: Health Check fehlgeschlagen ==="
    exit 1
fi
