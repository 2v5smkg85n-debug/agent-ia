#!/bin/bash
# setup_cron_walkforward.sh
# Ajoute le cron quotidien walk_forward (03:30 UTC) — auto-validation des stratégies.
# Tourne après le cron backtest (03:00 UTC). Idempotent.

set -e
CRON_LINE="30 3 * * * cd /home/ubuntu/agent-ia && venv/bin/python -u walk_forward.py >> walk_forward.log 2>&1"

# Vérifie qu'on a bien le script
if [ ! -f /home/ubuntu/agent-ia/walk_forward.py ]; then
    echo "ERREUR: walk_forward.py introuvable dans ~/agent-ia"
    exit 1
fi

# Récupère le cron actuel
CRON_ACTUEL=$(sudo crontab -l 2>/dev/null || echo "")

# Évite les doublons
if echo "$CRON_ACTUEL" | grep -q "walk_forward.py"; then
    echo "Cron walk_forward DÉJÀ présent. Aucun changement."
else
    (echo "$CRON_ACTUEL"; echo "$CRON_LINE") | sudo crontab -
    echo "Cron walk_forward ajouté."
fi

echo ""
echo "=== Cron root actuel ==="
sudo crontab -l
echo ""
echo "Le walk-forward tournera chaque jour à 03:30 UTC (05:30 CEST)."
echo "Log: ~/agent-ia/walk_forward.log"
echo ""
echo "Vérifier le log après 03:30 UTC: tail -20 ~/agent-ia/walk_forward.log"
