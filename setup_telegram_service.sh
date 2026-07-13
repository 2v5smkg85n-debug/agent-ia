#!/bin/bash
# setup_telegram_service.sh
# Crée et démarre le service systemd telegram_monitor.service.
# À lancer APRÈS config_telegram.py (token + chat_id dans .env).

set -e
DOSSIER=/home/ubuntu/agent-ia
SERVICE=telegram_monitor.service
FICHIER_SERVICE=/etc/systemd/system/$SERVICE

# Vérifie que .env a le token
if ! grep -q "TELEGRAM_BOT_TOKEN" $DOSSIER/.env || [ -z "$(grep TELEGRAM_BOT_TOKEN $DOSSIER/.env | cut -d= -f2)" ]; then
    echo "ERREUR: TELEGRAM_BOT_TOKEN absent du .env"
    echo "Lance d'abord: python config_telegram.py"
    exit 1
fi

# Vérifie les dépendances
$DOSSIER/venv/bin/python -c "import requests, dotenv" 2>/dev/null || {
    echo "Installation des dépendances..."
    $DOSSIER/venv/bin/pip install -q requests python-dotenv
}

# Crée le service systemd
sudo tee $FICHIER_SERVICE > /dev/null <<EOF
[Unit]
Description=Telegram Monitor - alertes push iPhone
After=network-online.target paper_trading.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$DOSSIER
ExecStart=$DOSSIER/venv/bin/python -u telegram_monitor.py
Restart=always
RestartSec=30
EnvironmentFile=$DOSSIER/.env
StandardOutput=append:$DOSSIER/telegram_monitor.log
StandardError=append:$DOSSIER/telegram_monitor.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE
sudo systemctl restart $SERVICE

sleep 3
echo "=== Statut $SERVICE ==="
sudo systemctl is-active $SERVICE
echo ""
echo "=== Log (dernières lignes) ==="
tail -10 $DOSSIER/telegram_monitor.log 2>/dev/null || echo "(log vide encore)"
echo ""
echo "OK. Le moniteur tourne. Tu recevras les alertes sur Telegram."
echo "Logs: tail -f $DOSSIER/telegram_monitor.log"
