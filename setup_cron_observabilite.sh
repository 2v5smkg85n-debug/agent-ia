#!/bin/bash
# Cron observabilite: snapshot equity toutes les 10 min (non invasif)
# Lit paper_trading.json, ajoute un point de capital a equity_history.jsonl
set -e
CRON="*/10 * * * * cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u observabilite.py snapshot >> /home/ubuntu/agent-ia/observabilite.log 2>&1"

echo "Ajout du cron observabilite (snapshots equity toutes les 10 min)..."

# evite doublon
if sudo crontab -l 2>/dev/null | grep -q "observabilite.py snapshot"; then
    echo "Cron observabilite deja present."
else
    (sudo crontab -l 2>/dev/null; echo "$CRON") | sudo crontab -
    echo "Cron ajoute."
fi

echo ""
echo "Crons actifs:"
sudo crontab -l | grep -E "observabilite|walk_forward|backtest|sauvegarde|backup_github|health" || true
