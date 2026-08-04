#!/bin/bash
set -e
cd ~/agent-ia

echo "=== 1. Déploiement code (3 fichiers) ==="
git fetch origin
git checkout origin/main -- indicateurs.py paper_trading.py pont_revolut.py
echo "Code déployé"

echo "=== 2. Test syntaxe ==="
source venv/bin/activate
for f in indicateurs.py paper_trading.py pont_revolut.py; do
    python -m py_compile "$f" && echo "  $f OK" || echo "  $f ERREUR"
done

echo "=== 3. Relaxation paramètres runtime ==="
echo "--- RSI 35 -> 40 (plus de signaux en QUIET) ---"
python -c "
import json
sp = json.load(open('strat_params.json'))
sp['rsi_achat'] = 40
json.dump(sp, open('strat_params.json','w'), indent=2, ensure_ascii=False)
print('  RSI achat:', sp['rsi_achat'])
"
echo "--- BB ecart 1.55 -> 1.2 (bandes plus serrées) ---"
python -c "
import json
sp = json.load(open('strat_params.json'))
sp['bb_ecart'] = 1.2
json.dump(sp, open('strat_params.json','w'), indent=2, ensure_ascii=False)
print('  BB ecart:', sp['bb_ecart'])
"

echo "=== 4. Consensus quorum 2 -> 1 ==="
export SYSTEMD_PAGER=cat
sudo tee /etc/systemd/system/paper_trading.service.d/quorum.conf > /dev/null << 'EOF'
[Service]
Environment=CONSENSUS_QUORUM=1
EOF
sudo systemctl daemon-reload
echo "  Quorum: 1"

echo "=== 5. Redémarrage services ==="
sudo systemctl restart paper_trading.service && echo "  paper_trading OK"
sudo systemctl restart pont_revolut.service && echo "  pont_revolut OK"

echo "=== 6. Vérification ==="
echo "--- strat_params ---"
python -c "import json; sp=json.load(open('strat_params.json')); print(f'  RSI achat: {sp[\"rsi_achat\"]} | BB ecart: {sp[\"bb_ecart\"]}')"
echo "--- systemd env ---"
sudo systemctl show paper_trading.service -p Environment | grep -o 'CONSENSUS[^ ]*\|SENTIMENT[^ ]*'
echo "--- services ---"
sudo systemctl is-active paper_trading.service pont_revolut.service

echo ""
echo "=== RÉCAPITULATIF ==="
echo "Code déployé (commit 776d98f):"
echo "  - indicateurs.py: seuils dynamiques + signal range + RSI<50 achat faible"
echo "  - paper_trading.py: anti-corrélation 30min (avant 60min)"
echo "  - pont_revolut.py: 16 paires Revolut (avant 10)"
echo ""
echo "Runtime:"
echo "  - RSI achat: 35 -> 40"
echo "  - BB ecart: 1.55 -> 1.2"
echo "  - Consensus quorum: 2 -> 1"
echo ""
echo "Effet attendu: 3-5x plus de signaux d'achat crypto en marché QUIET"
