#!/bin/bash
set -e
cd ~/agent-ia

echo "=== 1. Déploiement code ==="
git fetch origin
git checkout origin/main -- digest_quotidien.py reflection_action.py auto_tuning_oos.py revolut_live_render.py pont_revolut.py dashboard_server.py
echo "Code déployé"

echo "=== 2. Test syntaxe ==="
source venv/bin/activate
for f in digest_quotidien.py reflection_action.py auto_tuning_oos.py revolut_live_render.py pont_revolut.py dashboard_server.py; do
    python -m py_compile "$f" && echo "  $f OK" || echo "  $f ERREUR"
done

echo "=== 3. Redémarrage services ==="
export SYSTEMD_PAGER=cat
sudo systemctl restart pont_revolut.service 2>/dev/null && echo "  pont_revolut OK" || echo "  pont_revolut: déjà arrêté ou inexistant"
sudo systemctl restart dashboard.service 2>/dev/null && echo "  dashboard OK" || echo "  dashboard: restart via autre nom"
# dashboard pourrait être nommé différemment
sudo systemctl restart dashboard_server.service 2>/dev/null && echo "  dashboard_server OK" || true

echo "=== 4. Crons ==="
# Digest quotidien à 06:00 UTC (08:00 CEST)
(crontab -l 2>/dev/null | grep -v digest_quotidien; echo "0 6 * * * /home/ubuntu/agent-ia/venv/bin/python /home/ubuntu/agent-ia/digest_quotidien.py") | crontab -
# Réflexion → Action: 10 min après chaque réflexion (toutes les 6h à :05)
(crontab -l 2>/dev/null | grep -v reflection_action; echo "10 */6 * * * /home/ubuntu/agent-ia/venv/bin/python /home/ubuntu/agent-ia/reflection_action.py") | crontab -
# Auto-tuning OOS: 10 min après le génétique (03:40 UTC)
(crontab -l 2>/dev/null | grep -v auto_tuning_oos; echo "40 3 * * * /home/ubuntu/agent-ia/venv/bin/python /home/ubuntu/agent-ia/auto_tuning_oos.py") | crontab -
echo "  Crons installés"

echo "=== 5. Tests rapides ==="
echo "--- Backfill preview ( positions existantes ) ---"
python pont_revolut.py backfill-preview 2>&1 | head -20
echo ""
echo "--- Digest (dry) ---"
python digest_quotidien.py 2>&1 | head -30
echo ""
echo "--- Reflection action (dry-run) ---"
python reflection_action.py --dry-run 2>&1 | head -15
echo ""
echo "--- Auto-tuning OOS (dry-run) ---"
python auto_tuning_oos.py --dry-run 2>&1 | head -15

echo ""
echo "=== DÉPLOIEMENT TERMINÉ ==="
echo "Dashboard live: http://51.255.192.58:8765/live?token=LlVcM309UvV0aZMsUGl4FA"
echo "Pour backfill réel: python pont_revolut.py backfill"
