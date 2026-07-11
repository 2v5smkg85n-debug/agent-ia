#!/bin/bash
# setup_systemd.sh — Convertit paper_trading + protection en services systemd.
# Auto-restart en cas de crash + demarrage au boot.
# A lancer avec: sudo bash setup_systemd.sh

set -e

echo "=== Creation des services systemd ==="

# --- paper_trading.service ---
cat > /etc/systemd/system/paper_trading.service <<'EOF'
[Unit]
Description=Agent IA - Paper Trading boucle
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-ia
ExecStart=/home/ubuntu/agent-ia/venv/bin/python -u paper_trading.py boucle
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/agent-ia/paper_trading.log
StandardError=append:/home/ubuntu/agent-ia/paper_trading.log

[Install]
WantedBy=multi-user.target
EOF
echo "  paper_trading.service cree"

# --- protection.service ---
cat > /etc/systemd/system/protection.service <<'EOF'
[Unit]
Description=Agent IA - Protection BTC (trailing stop)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-ia
ExecStart=/home/ubuntu/agent-ia/venv/bin/python -u protection.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/agent-ia/protection.log
StandardError=append:/home/ubuntu/agent-ia/protection.log

[Install]
WantedBy=multi-user.target
EOF
echo "  protection.service cree"

systemctl daemon-reload
echo "  daemon-reload OK"

# --- Arreter les anciens processus nohup ---
echo ""
echo "=== Arret des anciens processus nohup ==="
pkill -f "paper_trading.py" 2>/dev/null && echo "  paper_trading arrete" || echo "  paper_trading: rien a arreter"
pkill -f "protection.py" 2>/dev/null && echo "  protection arrete" || echo "  protection: rien a arreter"
sleep 2

# --- Activer + demarrer ---
echo ""
echo "=== Activation + demarrage ==="
systemctl enable paper_trading.service protection.service
systemctl restart paper_trading.service protection.service
sleep 3

echo ""
echo "=== Statut ==="
systemctl --no-pager --lines=2 status paper_trading.service protection.service 2>&1 || true

echo ""
echo "============================================="
echo " SUCCES — services systemd actifs"
echo "============================================="
echo " Auto-restart: ON (Restart=always, delai 10s)"
echo " Demarrage au boot: ON (enabled)"
echo ""
echo " Commandes utiles:"
echo "   sudo systemctl status paper_trading"
echo "   sudo systemctl status protection"
echo "   sudo journalctl -u protection -f   (logs live)"
echo "   sudo systemctl restart protection"
