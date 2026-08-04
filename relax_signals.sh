#!/bin/bash
set -e
cd ~/agent-ia
source venv/bin/activate

echo "=== AVANT ==="
python -c "import json; sp=json.load(open('strat_params.json')); print(f'RSI achat: {sp[\"rsi_achat\"]} | BB ecart: {sp[\"bb_ecart\"]}')"

echo "=== 1. RSI 35 -> 40 (plus de signaux en marché QUIET) ==="
python -c "
import json
sp = json.load(open('strat_params.json'))
sp['rsi_achat'] = 40
json.dump(sp, open('strat_params.json','w'), indent=2, ensure_ascii=False)
print('RSI achat: 35 -> 40')
"

echo "=== 2. BB ecart 1.55 -> 1.2 (bandes plus serrées) ==="
python -c "
import json
sp = json.load(open('strat_params.json'))
sp['bb_ecart'] = 1.2
json.dump(sp, open('strat_params.json','w'), indent=2, ensure_ascii=False)
print('BB ecart: 1.55 -> 1.2')
"

echo "=== 3. Consensus quorum 2 -> 1 (un seul modele suffit) ==="
export SYSTEMD_PAGER=cat
sudo tee /etc/systemd/system/paper_trading.service.d/quorum.conf > /dev/null << 'EOF'
[Service]
Environment=CONSENSUS_QUORUM=1
EOF
sudo systemctl daemon-reload
echo "Quorum: 2 -> 1"

echo "=== 4. Redemarrage paper_trading ==="
sudo systemctl restart paper_trading.service
echo "Paper trading redemarré"

echo "=== APRES ==="
python -c "import json; sp=json.load(open('strat_params.json')); print(f'RSI achat: {sp[\"rsi_achat\"]} | BB ecart: {sp[\"bb_ecart\"]}')"
echo "Quorum: 1 (via systemd drop-in)"
echo ""
echo "=== VERIFICATION ==="
sudo systemctl status paper_trading.service --no-pager | head -5
echo ""
echo "Changes:"
echo "  RSI: 35 -> 40 (plus de signaux d'achat en QUIET)"
echo "  BB: 1.55 -> 1.2 (bandes plus serrées, plus de touchers)"
echo "  Quorum: 2 -> 1 (un seul modele IA suffit pour valider un achat)"
