#!/bin/bash
# setup_freqtrade_etalon.sh — installe Freqtrade (dry-run Kraken) a cote du bot, comme ETALON de comparaison.
# Ne touche a rien du bot. ~500 Mo de RAM, Python >= 3.11 requis. Lancer : bash setup_freqtrade_etalon.sh
set -e
DIR=/home/ubuntu/freqtrade_etalon
SRC=/home/ubuntu/agent-ia/freqtrade_etalon
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
VER=$($PY -c "import sys;print(sys.version_info.minor)")
if [ "$VER" -lt 11 ]; then echo "Python 3.11+ requis (trouve 3.$VER). Freqtrade n'est pas installable ici : on garde l'etalon en pause."; exit 1; fi
mkdir -p "$DIR" && cd "$DIR"
[ -d venv ] || $PY -m venv venv
./venv/bin/pip install -q --upgrade pip wheel
./venv/bin/pip install -q freqtrade || { echo "pip install freqtrade a echoue (TA-Lib ?). Essayez: sudo apt-get install -y build-essential libta-lib-dev"; exit 1; }
./venv/bin/freqtrade create-userdir --userdir user_data >/dev/null 2>&1 || true
cp "$SRC/EtalonStrategy.py" user_data/strategies/
cp "$SRC/config.json" config.json
echo "Telechargement des bougies 1h Kraken (quelques minutes)..."
./venv/bin/freqtrade download-data --config config.json --timerange 20260601- --timeframe 1h -v >/dev/null 2>&1 || ./venv/bin/freqtrade download-data --config config.json --days 120 --timeframe 1h
echo "Backtest de l'etalon :"
./venv/bin/freqtrade backtesting --config config.json --strategy EtalonStrategy --timerange 20260701- | tail -40
echo
echo "Pour le lancer en dry-run permanent (service) :"
echo "  sudo tee /etc/systemd/system/freqtrade_etalon.service >/dev/null <<EOT
[Unit]
Description=Freqtrade etalon (dry-run Kraken)
After=network-online.target
[Service]
User=ubuntu
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/freqtrade trade --config config.json --strategy EtalonStrategy
Restart=always
MemoryMax=800M
[Install]
WantedBy=multi-user.target
EOT"
echo "  sudo systemctl enable --now freqtrade_etalon && ./venv/bin/freqtrade show-trades ... (ou l'API sur 127.0.0.1:8081)"
