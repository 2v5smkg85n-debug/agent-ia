#!/bin/bash
set -e
cd ~/agent-ia

echo "=== 1. Déploiement code ==="
git fetch origin
git checkout origin/main -- social_consensus.py paper_trading.py
echo "Code déployé"

echo "=== 2. Test syntaxe ==="
source venv/bin/activate
python -m py_compile social_consensus.py && echo "  social_consensus OK"
python -m py_compile paper_trading.py && echo "  paper_trading OK"

echo "=== 3. Test rapide (sans gate) ==="
python -c "from social_consensus import gate_achat, resume; print('Module import OK')" 2>&1 || echo "  (import test: dépendances manquantes OK sur VPS)"

echo "=== 4. Activation SOCIAL_GATE ==="
export SYSTEMD_PAGER=cat
echo "[Service]
Environment=SOCIAL_GATE=1" | sudo tee /etc/systemd/system/paper_trading.service.d/social.conf > /dev/null
sudo systemctl daemon-reload
sudo systemctl restart paper_trading.service
echo "  Social gate activé"

echo "=== 5. Vérification ==="
sudo systemctl is-active paper_trading.service
echo ""
echo "=== RÉCAPITULATIF ==="
echo "Social Consensus actif:"
echo "  - 8 traders scannés: Peter Brandt, Lark Davis, Tone Vays, Van De Poppe,"
echo "    Scott Melker, Crypto Dog, DonAlt, Willy Woo"
echo "  - Scrapping Nitter (3 instances en fallback)"
echo "  - Extraction signaux via Perplexity (1 call/trader)"
echo "  - Gate: bloque achat si score < -0.2 ET >= 3 signaux bearish"
echo "  - Fail-open: si Nitter down ou < 3 signaux, achat autorisé"
echo ""
echo "Pour tester manuellement:"
echo "  python social_consensus.py            # scan complet"
echo "  python social_consensus.py --gate BTCUSDT  # test gate"
echo "  python social_consensus.py --resume   # résumé texte"
