#!/bin/bash
set -e
cd ~/agent-ia
git fetch origin
git checkout origin/main -- paper_trading.py
source venv/bin/activate
python -m py_compile paper_trading.py && echo "Code OK"
export SYSTEMD_PAGER=cat
echo "[Service]
Environment=SCALPING=1" | sudo tee /etc/systemd/system/paper_trading.service.d/scalping.conf > /dev/null
sudo systemctl daemon-reload
sudo systemctl restart paper_trading.service
echo "Scalping actif sur paper trading"
echo "TP: 0.5% | SL: 0.3% | Boucle: 2 min | Timeframe: 15m"
