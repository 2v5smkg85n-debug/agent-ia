#!/usr/bin/env bash
# Installe et lance le rejeu historique (observation seule) sur le VPS. A lancer depuis ~/agent-ia :
#   bash installer_rejeu.sh
# Reversible : bash installer_rejeu.sh desinstaller     (les resultats deja calcules sont conserves)
# Couper sans desinstaller : REJEU=0 dans .env
#
# Ce que fait ce script, et rien d'autre :
#   1. choisit l'interpreteur Python qui sait charger les modules du bot (celui du service de trading en premier) ;
#   2. installe numpy, LightGBM et Optuna dans ~/agent-ia/.rejeu_libs : un dossier a part (environ 250 Mo), les
#      bibliotheques du bot ne sont ni mises a jour ni remplacees. Si LightGBM ne demarre pas faute de la bibliotheque
#      systeme libgomp1, il tente « sudo apt-get install -y libgomp1 » (bibliotheque standard de calcul parallele) ;
#      si cette etape echoue, le rejeu tourne quand meme, sans le filtre LightGBM ni Optuna ;
#   3. cree le service rejeu-historique (un seul passage, priorite la plus basse, 2 coeurs et 2,5 Go au plus) et le
#      lance en arriere-plan : il telecharge les bougies Kraken (environ 220 Mo sur le disque), rejoue, puis ecrit le bilan.
# Le service de trading n'est ni modifie ni redemarre. Aucun reglage du bot n'est change.
# Relancer plus tard : sudo systemctl start --no-block rejeu-historique.service
set -e
RACINE="$(cd "$(dirname "$0")" && pwd)"
UTILISATEUR="$(id -un)"
UNITES="${UNITES:-/etc/systemd/system}"
LIBS="$RACINE/.rejeu_libs"
PAQUETS="lightgbm==4.7.0 optuna==5.1.0"

if [ "${1:-}" = "desinstaller" ]; then
  sudo systemctl stop rejeu-historique.service 2>/dev/null || true
  sudo rm -f "$UNITES/rejeu-historique.service"
  sudo systemctl daemon-reload
  rm -rf "$LIBS" "$LIBS.tmp"
  echo "Rejeu historique desinstalle. Resultats conserves (rejeu_bilan.txt) ; pour liberer le disque : rm -rf $RACINE/rejeu_data"
  exit 0
fi

cd "$RACINE"
libre_mo="$(df -Pm "$RACINE" | awk 'NR==2 {print $4}')"
mem_mo="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
if [ "${libre_mo:-0}" -lt 2000 ]; then echo "ARRET : moins de 2 Go de disque libres ($libre_mo Mo). Rien n'a ete installe."; exit 1; fi
if [ "${mem_mo:-0}" -lt 1500 ]; then echo "ARRET : moins de 1,5 Go de memoire disponibles ($mem_mo Mo). Rien n'a ete installe."; exit 1; fi

PY=""
DU_SERVICE="$(systemctl show -p ExecStart paper_trading.service 2>/dev/null | grep -oE '/[^ ;]*python[0-9.]*' | head -1 || true)"
for candidat in "$DU_SERVICE" "$(command -v python3 || true)" "$RACINE/venv/bin/python" "$RACINE/.venv/bin/python"; do
  if [ -n "$candidat" ] && [ -x "$candidat" ] && "$candidat" -c "import indicateurs, stop_atr, strategies_tendance" >/dev/null 2>&1; then PY="$candidat"; break; fi
done
if [ -z "$PY" ]; then echo "ARRET : aucun interpreteur Python ne charge les modules du bot (indicateurs, stop_atr, strategies_tendance). Rien n'a ete installe."; exit 1; fi
echo "Interpreteur : $PY"

if [ -d "$LIBS/lightgbm" ] && [ -d "$LIBS/optuna" ]; then
  echo "Bibliotheques deja presentes dans .rejeu_libs : pas de nouveau telechargement."
else
  PIP=""
  if "$PY" -m pip --version >/dev/null 2>&1; then PIP="$PY"
  elif command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1 \
       && [ "$(python3 -c 'import sys; print(sys.version_info[:2])')" = "$("$PY" -c 'import sys; print(sys.version_info[:2])')" ]; then PIP="$(command -v python3)"; fi
  if [ -z "$PIP" ]; then
    echo "pip est absent : le rejeu tournera sans LightGBM ni Optuna (sudo apt install -y python3-pip puis relancer ce script)."
  else
    echo "Telechargement de numpy, LightGBM et Optuna dans .rejeu_libs (environ 250 Mo, une a deux minutes)..."
    rm -rf "$LIBS.tmp"
    if "$PIP" -m pip install -q --no-warn-script-location --disable-pip-version-check --target "$LIBS.tmp" $PAQUETS; then
      rm -rf "$LIBS"
      mv "$LIBS.tmp" "$LIBS"
    else
      rm -rf "$LIBS.tmp"
      echo "L'installation des bibliotheques a echoue : le rejeu tournera sans LightGBM ni Optuna. Rien d'autre n'a ete touche."
    fi
  fi
fi
if [ -d "$LIBS/numpy" ]; then
  if ! timeout 300 "$PY" rejeu_modeles.py verifier; then
    if [ -d "$LIBS/lightgbm" ] && ! ldconfig -p 2>/dev/null | grep -q 'libgomp.so.1'; then
      echo "LightGBM a besoin de la bibliotheque systeme libgomp1 : installation..."
      sudo apt-get install -y -q libgomp1 >/dev/null 2>&1 || echo "  (installation de libgomp1 impossible)"
      timeout 300 "$PY" rejeu_modeles.py verifier || echo "LightGBM ou Optuna ne demarre pas : cette partie du bilan dira « absent », le reste tourne."
    else
      echo "LightGBM ou Optuna ne demarre pas : cette partie du bilan dira « absent », le reste tourne."
    fi
  fi
fi

sudo tee "$UNITES/rejeu-historique.service" >/dev/null <<UNIT
[Unit]
Description=Rejeu historique : rejoue les strategies du bot sur les bougies Kraken (observation seule, aucun ordre)
After=network-online.target

[Service]
Type=oneshot
User=$UTILISATEUR
WorkingDirectory=$RACINE
ExecStart=$PY -u $RACINE/rejeu_historique.py tout
StandardOutput=append:$RACINE/rejeu_journal.log
StandardError=append:$RACINE/rejeu_journal.log
Nice=19
IOSchedulingClass=idle
CPUQuota=200%
MemoryMax=2500M
TimeoutStartSec=6h
UNIT
sudo systemctl daemon-reload
sudo systemctl start --no-block rejeu-historique.service
echo "REJEU_INSTALLE : le rejeu tourne en arriere-plan (une dizaine de minutes). Vous pouvez fermer Termius."
echo "Avancement : python3 rejeu_historique.py etat     Bilan a la fin : python3 rejeu_historique.py bilan"
