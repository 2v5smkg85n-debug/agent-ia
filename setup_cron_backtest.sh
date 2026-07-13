#!/bin/bash
# setup_cron_backtest.sh — cron quotidien du moteur de backtest (track record)
set -e
DIR=/home/ubuntu/agent-ia
PY=$DIR/venv/bin/python
LOG=$DIR/backtest.log
CRON_LINE="0 3 * * * cd $DIR && $PY -u backtest_engine.py >> $LOG 2>&1"

echo "=== Setup cron backtest quotidien ==="

# Verifier yfinance
if ! $PY -c "import yfinance" 2>/dev/null; then
    echo "Installation yfinance..."
    $PY -m pip install yfinance -q
fi

# Verifier backtest_engine.py
if [ ! -f "$DIR/backtest_engine.py" ]; then
    echo "ERREUR: $DIR/backtest_engine.py absent. Telecharge-le d'abord."
    exit 1
fi

# Retirer l'ancienne ligne backtest si presente, puis ajouter
crontab -l 2>/dev/null | grep -v "backtest_engine.py" | crontab -
( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -

echo "Cron ajoute: $CRON_LINE"
echo ""
echo "=== Crontab actuel (entrees backtest) ==="
crontab -l 2>/dev/null | grep backtest_engine || echo "(aucune)"
echo ""
echo "Le backtest tournera chaque jour a 03:00 UTC (05:00 CEST)."
echo "Log: $LOG"
echo "Historique track record: $DIR/backtests_history.jsonl"
echo ""
echo "Pour lancer un test immediat:"
echo "  cd $DIR && $PY backtest_engine.py"
