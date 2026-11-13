#!/usr/bin/env bash
# Installe les outils de revenus sur le VPS (timers systemd). À lancer depuis ~/agent-ia :
#   bash revenus/installer.sh
# Réversible : bash revenus/installer.sh desinstaller
set -e
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
UTILISATEUR="$(id -un)"
PY="$(command -v python3)"
UNITES=/etc/systemd/system

if [ "${1:-}" = "desinstaller" ]; then
  for u in revenus-leads.timer revenus-veilleur.timer revenus-veilleur-rapport.timer revenus-veilleur-serveur.service revenus-ombre.service; do
    sudo systemctl disable --now "$u" 2>/dev/null || true
  done
  sudo rm -f $UNITES/revenus-*.service $UNITES/revenus-*.timer
  sudo systemctl daemon-reload
  echo "Outils de revenus désinstallés (les données dans revenus/donnees sont conservées)."
  exit 0
fi

# Jetons d'accès pour les deux petits serveurs HTTP (ajoutés au .env s'ils manquent)
touch "$RACINE/.env"
for cle in VEILLEUR_TOKEN OMBRE_TOKEN; do
  if ! grep -q "^$cle=" "$RACINE/.env"; then
    echo "$cle=$($PY -c 'import secrets;print(secrets.token_urlsafe(18))')" >> "$RACINE/.env"
    echo "→ $cle généré dans .env"
  fi
done

unite_simple() { # nom, description, commande
  sudo tee "$UNITES/$1.service" >/dev/null <<UNIT
[Unit]
Description=$2
After=network-online.target

[Service]
Type=oneshot
User=$UTILISATEUR
WorkingDirectory=$RACINE
ExecStart=$PY $3
UNIT
}
unite_timer() { # nom, OnCalendar/OnUnitActiveSec
  sudo tee "$UNITES/$1.timer" >/dev/null <<UNIT
[Unit]
Description=Timer $1

[Timer]
$2
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
UNIT
}
unite_service() { # nom, description, commande
  sudo tee "$UNITES/$1.service" >/dev/null <<UNIT
[Unit]
Description=$2
After=network-online.target

[Service]
User=$UTILISATEUR
WorkingDirectory=$RACINE
ExecStart=$PY $3
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
}

unite_simple revenus-leads "Scanner de leads (Codeur, Adzuna, France Travail)" "$RACINE/revenus/leads/scanner_leads.py"
unite_timer revenus-leads "OnBootSec=3min
OnUnitActiveSec=2h"
unite_simple revenus-veilleur "Veilleur : passe de contrôle des agents IA" "$RACINE/revenus/veilleur/veilleur.py"
unite_timer revenus-veilleur "OnBootSec=2min
OnUnitActiveSec=5min"
unite_simple revenus-veilleur-rapport "Veilleur : rapport quotidien" "$RACINE/revenus/veilleur/veilleur.py rapport"
unite_timer revenus-veilleur-rapport "OnCalendar=*-*-* 08:00:00"
unite_service revenus-veilleur-serveur "Veilleur : battements et état (port 8791)" "$RACINE/revenus/veilleur/veilleur.py serveur"
unite_service revenus-ombre "Mode ombre : webhooks des marchands (port 8790)" "$RACINE/revenus/audit_regles/regles_ombre.py serveur"

[ -f "$RACINE/revenus/veilleur/clients.json" ] || cp "$RACINE/revenus/veilleur/clients.exemple.json" "$RACINE/revenus/veilleur/clients.json"
sudo systemctl daemon-reload
sudo systemctl enable --now revenus-leads.timer revenus-veilleur.timer revenus-veilleur-rapport.timer revenus-veilleur-serveur.service revenus-ombre.service
echo
systemctl list-timers --no-pager | grep revenus || true
echo
echo "Installé. Première passe : python3 revenus/leads/scanner_leads.py && python3 revenus/veilleur/veilleur.py test"
