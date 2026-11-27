#!/usr/bin/env bash
# Installe le professeur TabPFN (observation seule) sur le VPS. A lancer depuis ~/agent-ia :
#   bash installer_professeur_tabpfn.sh
# Reversible : bash installer_professeur_tabpfn.sh desinstaller   (les notes deja ecrites sont conservees)
# Couper sans desinstaller : PROF_TABPFN=0 dans .env
#
# Ce que fait ce script, et rien d'autre :
#   1. installe torch (version processeur) et tabpfn dans ~/agent-ia/.tabpfn_libs : un dossier a part, les
#      bibliotheques du bot ne sont ni mises a jour ni remplacees ;
#   2. verifie que TabPFN demarre (python3 professeur_tabpfn.py verifier) ; sinon il s'arrete la et retire le dossier ;
#   3. cree un minuteur systemd (toutes les 3 h) a priorite basse, 2 coeurs et 2,5 Go de memoire au plus.
# Le service de trading n'est ni modifie ni redemarre.
set -e
RACINE="$(cd "$(dirname "$0")" && pwd)"
UTILISATEUR="$(id -un)"
PY="$(command -v python3)"
UNITES="${UNITES:-/etc/systemd/system}"
LIBS="$RACINE/.tabpfn_libs"
TORCH="torch==2.14.1+cpu"
TABPFN="tabpfn==10.3.0"

if [ "${1:-}" = "desinstaller" ]; then
  sudo systemctl disable --now professeur-tabpfn.timer 2>/dev/null || true
  sudo rm -f "$UNITES/professeur-tabpfn.service" "$UNITES/professeur-tabpfn.timer"
  sudo systemctl daemon-reload
  rm -rf "$LIBS" "$LIBS.tmp"
  echo "Professeur TabPFN desinstalle (notes conservees dans professeur_tabpfn_notes.jsonl)."
  exit 0
fi

libre_mo="$(df -Pm "$RACINE" | awk 'NR==2 {print $4}')"
mem_mo="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
if [ "${libre_mo:-0}" -lt 4000 ]; then echo "ARRET : moins de 4 Go de disque libres ($libre_mo Mo). Rien n'a ete installe."; exit 1; fi
if [ "${mem_mo:-0}" -lt 2000 ]; then echo "ARRET : moins de 2 Go de memoire disponibles ($mem_mo Mo). Rien n'a ete installe."; exit 1; fi
if ! "$PY" -m pip --version >/dev/null 2>&1; then echo "ARRET : pip est absent (sudo apt install -y python3-pip). Rien n'a ete installe."; exit 1; fi

if [ -d "$LIBS/tabpfn" ] && [ -d "$LIBS/torch" ]; then
  echo "Bibliotheques deja presentes dans .tabpfn_libs : pas de nouveau telechargement."
else
  echo "Telechargement de torch (processeur) et tabpfn dans .tabpfn_libs (1,3 Go, deux a cinq minutes)..."
  rm -rf "$LIBS.tmp"
  if ! "$PY" -m pip install -q --no-warn-script-location --disable-pip-version-check --target "$LIBS.tmp" \
       --extra-index-url https://download.pytorch.org/whl/cpu "$TORCH" "$TABPFN"; then
    rm -rf "$LIBS.tmp"
    echo "ARRET : l'installation des bibliotheques a echoue. Rien d'autre n'a ete touche."
    exit 1
  fi
  if ls "$LIBS.tmp" | grep -qi '^nvidia'; then
    rm -rf "$LIBS.tmp"
    echo "ARRET : pip a choisi la version carte graphique de torch (plusieurs Go inutiles). Rien n'a ete installe."
    exit 1
  fi
  rm -rf "$LIBS"
  mv "$LIBS.tmp" "$LIBS"
fi

cd "$RACINE"
if ! timeout 900 "$PY" professeur_tabpfn.py verifier 2>/dev/null; then
  rm -rf "$LIBS"
  echo "ARRET : TabPFN ne demarre pas sur cette machine. Le dossier .tabpfn_libs a ete retire, rien d'autre n'a ete touche."
  exit 1
fi

sudo tee "$UNITES/professeur-tabpfn.service" >/dev/null <<UNIT
[Unit]
Description=Professeur TabPFN : note les candidats de la porte (observation seule, aucun ordre)
After=network-online.target

[Service]
Type=oneshot
User=$UTILISATEUR
WorkingDirectory=$RACINE
ExecStart=$PY $RACINE/professeur_tabpfn.py noter
Nice=15
IOSchedulingClass=idle
CPUQuota=200%
MemoryMax=2500M
TimeoutStartSec=900
UNIT
sudo tee "$UNITES/professeur-tabpfn.timer" >/dev/null <<UNIT
[Unit]
Description=Minuteur du professeur TabPFN (toutes les 3 h)

[Timer]
OnBootSec=15min
OnUnitActiveSec=3h
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now professeur-tabpfn.timer >/dev/null 2>&1
sudo systemctl start --no-block professeur-tabpfn.service
echo "PROFESSEUR_TABPFN_INSTALLE : premier passage lance en arriere-plan (dix minutes au plus), puis toutes les 3 h."
echo "Voir le bilan : python3 professeur_tabpfn.py"
