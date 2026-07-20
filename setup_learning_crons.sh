#!/bin/bash
# setup_learning_crons.sh — Accélère l'apprentissage: 3 crons toutes les 6h
# - reflection_gemini.py : 0 */6 * * *  (au lieu de 0 8 * * * quotidien)
# - backtest_horaires.py crypto : 5 */6 * * *  (regen continu GAGNANTE)
# - auto_sweep.py : 10 */6 * * *  (auto-optimisation seuil RSI)
set -e
DIR="$HOME/agent-ia"
ACT="cd $DIR && source venv/bin/activate"

# Recupere le crontab root actuel
CRON=$(sudo crontab -l 2>/dev/null || true)

# 1. Remplace reflection quotidienne (0 8 * * *) par toutes les 6h
if echo "$CRON" | grep -q "0 8 \* \* .* reflection_gemini"; then
  CRON=$(echo "$CRON" | sed 's|^0 8 \* \* \*.*reflection_gemini.*|0 */6 * * * '"$ACT"' \&\& python -u reflection_gemini.py >> /tmp/reflection_cron.log 2>\&1|')
  echo "reflection: quotidien -> toutes les 6h"
elif ! echo "$CRON" | grep -q "reflection_gemini.*\*/6"; then
  CRON="$CRON
0 */6 * * * $ACT && python -u reflection_gemini.py >> /tmp/reflection_cron.log 2>&1"
  echo "reflection: ajoute toutes les 6h"
fi

# 2. Ajoute backtest_horaires toutes les 6h (si absent)
if ! echo "$CRON" | grep -q "backtest_horaires"; then
  CRON="$CRON
5 */6 * * * $ACT && python -u backtest_horaires.py crypto >> /tmp/backtest_cron.log 2>&1"
  echo "backtest_horaires: ajoute toutes les 6h"
fi

# 3. Ajoute auto_sweep toutes les 6h (si absent)
if ! echo "$CRON" | grep -q "auto_sweep"; then
  CRON="$CRON
10 */6 * * * $ACT && python -u auto_sweep.py >> /tmp/auto_sweep_cron.log 2>&1"
  echo "auto_sweep: ajoute toutes les 6h"
fi

# Ecrit le nouveau crontab
echo "$CRON" | sudo crontab -
echo "=== crontab root mis a jour ==="
sudo crontab -l | grep -E "reflection|backtest_horaires|auto_sweep"
