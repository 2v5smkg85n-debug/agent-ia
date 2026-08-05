#!/bin/bash
# Restauration complete de l'agent IA sur nouveau VPS
set -e
cd ~/agent-ia
source venv/bin/activate

echo "=== 1. Creation du .env ==="
cat > ~/agent-ia/.env <<'ENVEOF'
# === API KEYS (A REMPLIR) ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
REVOLUT_X_API_KEY=
REVOLUT_X_PRIVATE_KEY=
REVOLUT_X_PRIVATE_KEY_PEM=
GEMINI_API_KEY=
PPLX_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# === DASHBOARD ===
DASHBOARD_TOKEN=LlVcM309UvV0aZMsUGl4FA
DASHBOARD_PORT=8765

# === SCALPING MODE ===
SCALPING=1

# === STRATEGIES ===
TOP_3_STRATEGIES=1
WR_THRESHOLD=75

# === CONSENSUS IA ===
CONSENSUS_IA=1
CONSENSUS_MODELES=perplexity,gemini
CONSENSUS_QUORUM=1

# === SENTIMENT ===
SENTIMENT_GATE=1
SENTIMENT_FILTER=1

# === MACRO ===
MACRO_GATE=1
MACRO_GATE_HEURES=2

# === SOCIAL ===
SOCIAL_GATE=1

# === RISK MANAGEMENT ===
PROTECTION_CAPITAL=0
META_IA=0
BOUGIE_GATE=0
CONF_MULTI_TF=0
PLUGINS_ACTIVE=0

# === ANTI-CORRELATION ===
ANTI_CORR=1

# === CONVICTION SIZING ===
CONVICTION_SIZING=1

# === EXIT AVANCE ===
EXIT_AVANCE=1
SMART_EXIT=1

# === REGIME FILTER ===
REGIME_FILTER=1

# === PAPER TRADING ===
PAPER_CAPITAL=1000
MAX_POSITIONS=15
RISK_PAR_TRADE=0.065
ENVEOF
echo "  .env cree (API keys a remplir)"

echo "=== 2. Creation paper_trading.json (1000 EUR) ==="
python3 -c "
import json
data = {
    'capital_initial': 1000.0,
    'capital': 1000.0,
    'positions': [],
    'trades': [],
    'date_debut': None,
    'perte_journaliere': 0.0,
    'trades_aujourdhui': 0,
    'circuit_breaker_actif': False,
    'compound_base': 1000.0
}
with open('paper_trading.json', 'w') as f:
    json.dump(data, f, indent=2)
print('  paper_trading.json cree (1000 EUR)')
"

echo "=== 3. Creation systemd paper_trading.service ==="
sudo tee /etc/systemd/system/paper_trading.service > /dev/null <<'SVCEOF'
[Unit]
Description=Agent IA - Paper Trading boucle
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-ia
EnvironmentFile=/home/ubuntu/agent-ia/.env
ExecStart=/home/ubuntu/agent-ia/venv/bin/python -u paper_trading.py boucle
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/agent-ia/paper_trading.log
StandardError=append:/home/ubuntu/agent-ia/paper_trading.log

[Install]
WantedBy=multi-user.target
SVCEOF
echo "  paper_trading.service cree"

echo "=== 4. Creation systemd dashboard.service ==="
sudo tee /etc/systemd/system/dashboard.service > /dev/null <<'SVCEOF'
[Unit]
Description=Agent IA - Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-ia
EnvironmentFile=/home/ubuntu/agent-ia/.env
ExecStart=/home/ubuntu/agent-ia/venv/bin/python -u dashboard_server.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/agent-ia/dashboard.log
StandardError=append:/home/ubuntu/agent-ia/dashboard.log

[Install]
WantedBy=multi-user.target
SVCEOF
echo "  dashboard.service cree"

echo "=== 5. Activation des services ==="
sudo systemctl daemon-reload
sudo systemctl enable paper_trading.service dashboard.service
echo "  Services actives (demarrage auto au boot)"

echo "=== 6. Ouverture des ports firewall ==="
sudo ufw allow 8765/tcp 2>/dev/null || true
echo "  Port 8765 (dashboard) ouvert"

echo "=== 7. Installation des crons ==="
(crontab -l 2>/dev/null | grep -v "agent-ia"; echo "0 6 * * * cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u digest_quotidien.py >> /home/ubuntu/agent-ia/cron_digest.log 2>&1"; echo "10 */6 * * * cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u reflection_action.py >> /home/ubuntu/agent-ia/cron_reflection.log 2>&1"; echo "40 3 * * * cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u auto_tuning_oos.py >> /home/ubuntu/agent-ia/cron_tuning.log 2>&1"; echo "*/30 * * * * cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u apprentissage_continu.py >> /home/ubuntu/agent-ia/cron_apprentissage.log 2>&1") | crontab -
echo "  4 crons installes"

echo "=== 8. Demarrage du dashboard ==="
sudo systemctl start dashboard.service
sleep 3
sudo systemctl status dashboard.service --no-pager 2>&1 | head -5

echo ""
echo "============================================="
echo " RESTAURATION TERMINEE"
echo "============================================="
echo ""
echo " Dashboard: http://$(hostname -I | awk '{print $1}'):8765/?token=LlVcM309UvV0aZMsUGl4FA"
echo ""
echo " IMPORTANT: Remplis tes cles API dans .env:"
echo "   nano ~/agent-ia/.env"
echo ""
echo " Puis demarre le trading:"
echo "   sudo systemctl start paper_trading.service"
echo "   sudo systemctl status paper_trading.service"
echo ""
echo " Verifier le dashboard:"
echo "   curl -s http://localhost:8765/?token=LlVcM309UvV0aZMsUGl4FA | head -5"
