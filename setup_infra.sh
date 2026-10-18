#!/bin/bash
# setup_infra.sh — infrastructure du VPS (a lancer une fois : sudo bash setup_infra.sh)
#  1. zram (swap compressee en RAM, zstd, 50 %) : evite l'OOM quand Ollama + bot + dashboard tournent ensemble
#  2. heure exacte (NTP) : les bougies et les fenetres horaires en dependent
#  3. journald : les erreurs du bot vont AUSSI dans journalctl (le log fichier reste)
#  4. service optionnel ws_kraken (prix temps reel) — active seulement si le module websockets est installe
#  5. cron : copie SQLite horaire, battement de coeur healthchecks.io (si HEALTHCHECK_URL dans .env), bilan quotidien
#  6. logrotate pour paper_trading.log
set -e
DIR=/home/ubuntu/agent-ia
cd "$DIR"
# Python reellement utilise par le service (venv ou systeme)
PY=$(systemctl show -p ExecStart paper_trading.service 2>/dev/null | grep -oE '/[^ ;]*python[0-9.]*' | head -1)
[ -x "$PY" ] || PY=$(command -v python3)
echo "Python du bot : $PY"

echo "== 1. zram (swap compressee) =="
if ! swapon --show | grep -q zram; then
  apt-get install -y -q zram-tools >/dev/null 2>&1 || true
  if [ -f /etc/default/zramswap ]; then
    sed -i 's/^#\?ALGO=.*/ALGO=zstd/; s/^#\?PERCENT=.*/PERCENT=50/; s/^#\?PRIORITY=.*/PRIORITY=100/' /etc/default/zramswap
    systemctl enable --now zramswap >/dev/null 2>&1 || systemctl restart zramswap || true
  fi
  # si une swap disque existe, elle devient le second niveau (priorite 10)
  grep -q "vm.swappiness" /etc/sysctl.conf || echo "vm.swappiness=100" >> /etc/sysctl.conf
  grep -q "vm.page-cluster" /etc/sysctl.conf || echo "vm.page-cluster=0" >> /etc/sysctl.conf
  sysctl -p >/dev/null 2>&1 || true
fi
swapon --show || true
free -h | head -2

echo "== 2. heure exacte (NTP) =="
timedatectl set-ntp true 2>/dev/null || true
timedatectl | grep -E "Time zone|synchronized" || true

echo "== 3. journald : erreurs du bot visibles dans journalctl =="
mkdir -p /etc/systemd/system/paper_trading.service.d
cat > /etc/systemd/system/paper_trading.service.d/override.conf <<'EOF'
[Service]
# stdout reste dans paper_trading.log ; stderr (tracebacks) part dans le journal ET dans le fichier via tee
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=OLLAMA_KEEP_ALIVE=30m
MemoryHigh=2500M
EOF
systemctl daemon-reload

echo "== 4. service ws_kraken (prix temps reel, optionnel) =="
if $PY -c "import websockets" 2>/dev/null; then
cat > /etc/systemd/system/ws_kraken.service <<EOF
[Unit]
Description=Agent IA - flux prix Kraken WebSocket
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$DIR
ExecStart=$PY -u ws_kraken.py
Restart=always
RestartSec=5
StandardOutput=append:$DIR/ws_kraken.log
StandardError=append:$DIR/ws_kraken.log
MemoryMax=200M

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now ws_kraken.service
  echo "  ws_kraken.service actif"
else
  echo "  module websockets absent -> $PY -m pip install websockets (ou pip3 install --user websockets) puis relancer ce script"
fi

echo "== 5. cron (SQLite horaire, heartbeat, bilan) =="
HC=$(grep -E "^HEALTHCHECK_URL=" $DIR/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
CRON_TMP=$(mktemp)
crontab -u ubuntu -l 2>/dev/null | grep -v "etat_sqlite.py\|healthchecks\|hc-ping\|registre_strategies.py rapport" > "$CRON_TMP" || true
echo "17 * * * * cd $DIR && $PY etat_sqlite.py migrer >> $DIR/etat_sqlite.log 2>&1" >> "$CRON_TMP"
echo "5 7 * * * cd $DIR && $PY registre_strategies.py rapport >> $DIR/registre.log 2>&1" >> "$CRON_TMP"
if [ -n "$HC" ]; then
  # battement de coeur : OK seulement si les 3 services tournent et que le log a bouge depuis 15 min
  echo "*/5 * * * * systemctl is-active --quiet paper_trading && systemctl is-active --quiet dashboard && [ \$(find $DIR/paper_trading.log -mmin -15 | wc -l) -gt 0 ] && curl -fsS -m 10 --retry 3 $HC >/dev/null 2>&1 || curl -fsS -m 10 $HC/fail >/dev/null 2>&1" >> "$CRON_TMP"
  echo "  heartbeat healthchecks.io installe"
else
  echo "  (pas de HEALTHCHECK_URL dans .env : creez un check gratuit sur https://healthchecks.io et ajoutez HEALTHCHECK_URL=https://hc-ping.com/xxxx dans .env)"
fi
crontab -u ubuntu "$CRON_TMP"; rm -f "$CRON_TMP"

echo "== 6. logrotate =="
cat > /etc/logrotate.d/agent-ia <<EOF
$DIR/*.log {
  daily
  rotate 7
  compress
  missingok
  notifempty
  copytruncate
}
EOF

echo "== 7. redemarrage des services =="
systemctl restart paper_trading.service chat_naturel.service dashboard.service
sleep 3
systemctl is-active paper_trading chat_naturel dashboard ws_kraken 2>/dev/null | paste -sd' '
echo "Termine. Verifier : journalctl -u paper_trading --since -5min --no-pager | tail ; tail -20 $DIR/paper_trading.log"
