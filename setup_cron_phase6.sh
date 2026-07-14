#!/bin/bash
# setup_cron_phase6.sh — installe les crons Phase 6 (auto-pruning + reflection)
# Idempotent: verifie si le cron existe deja avant de l'ajouter.
set -e
cd ~/agent-ia
source venv/bin/activate 2>/dev/null
VENVPY="$HOME/agent-ia/venv/bin/python"
BASE="$HOME/agent-ia"

# Recupere le crontab actuel (root ou user)
CRON_EXISTANT=$(sudo crontab -l 2>/dev/null || crontab -l 2>/dev/null || true)

add_cron() {
    local ligne="$1"
    if echo "$CRON_EXISTANT" | grep -qF "$ligne"; then
        echo "[OK] deja present: $ligne"
    else
        (echo "$CRON_EXISTANT"; echo "$ligne") | (sudo crontab - 2>/dev/null || crontab -) 2>/dev/null
        echo "[+] ajoute: $ligne"
        CRON_EXISTANT=$(sudo crontab -l 2>/dev/null || crontab -l 2>/dev/null || true)
    fi
}

echo "=== Installation crons Phase 6 ==="

# Auto-pruning toutes les 30 min (desactive/reactive les strategies selon perf live)
add_cron "*/30 * * * * $VENVPY $BASE/auto_pruning.py >> $BASE/logs/pruning_cron.log 2>&1"

# Reflexion quotidienne a 08:00 UTC (analyse LLM + digest Telegram)
add_cron "0 8 * * * $VENVPY $BASE/reflection_gemini.py >> $BASE/logs/reflection_cron.log 2>&1"

echo ""
echo "=== Crontab final ==="
sudo crontab -l 2>/dev/null || crontab -l 2>/dev/null
echo ""
echo "[OK] Phase 6 crons installes:"
echo "  - auto_pruning: toutes les 30 min"
echo "  - reflection_gemini: 08:00 UTC quotidien"
