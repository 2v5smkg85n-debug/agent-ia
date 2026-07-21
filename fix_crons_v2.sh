#!/bin/bash
# fix_crons_v2.sh — Corrige les 3 crons apprentissage: source -> path python direct
# cron utilise /bin/sh ou source n'existe pas -> les crons ne tournaient pas
set -e
PY=/home/ubuntu/agent-ia/venv/bin/python
DIR=/home/ubuntu/agent-ia
LOGDIR=/home/ubuntu/agent-ia/logs

mkdir -p $LOGDIR

# Recupere crontab root
CRON=$(sudo crontab -l 2>/dev/null || true)

# Supprime les 3 lignes cassees (avec source venv)
CRON=$(echo "$CRON" | grep -v "reflection_gemini.py" | grep -v "backtest_horaires.py crypto" | grep -v "auto_sweep.py")

# Re-ajoute avec path python direct (format qui marchait pour l'ancien cron)
CRON="$CRON
0 */6 * * * cd $DIR && $PY -u reflection_gemini.py >> $LOGDIR/reflection_cron.log 2>&1
5 */6 * * * cd $DIR && $PY -u backtest_horaires.py crypto >> $LOGDIR/backtest_cron.log 2>&1
10 */6 * * * cd $DIR && $PY -u auto_sweep.py >> $LOGDIR/auto_sweep_cron.log 2>&1"

echo "$CRON" | sudo crontab -
echo "=== crons corriges (path python direct) ==="
sudo crontab -l | grep -E "reflection|backtest_horaires|auto_sweep"

# Test immediat: lance auto_sweep + reflection pour valider
echo ""
echo "=== test auto_sweep (valide que le path marche) ==="
cd $DIR && $PY -u auto_sweep.py 2>&1 | tail -8
