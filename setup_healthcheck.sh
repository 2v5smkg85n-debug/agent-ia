#!/bin/bash
# setup_healthcheck.sh — Installe le health check (verification toutes les 10 min).
# Detecte les services inactifs OU figes (log pas frais) et les redemarre.
# Lance avec: sudo bash setup_healthcheck.sh
set -e

# 1. Cree le script de health check
cat > /home/ubuntu/health_check.sh <<'EOF'
#!/bin/bash
# Health check : verifie paper_trading + protection. Redemarre si inactif ou fige.
LOG=/home/ubuntu/agent-ia/health.log
TS=$(date '+%Y-%m-%d %H:%M:%S')
SEUIL_FIGE=2700   # 45 min sans nouveau log = process fige

log() { echo "[$TS] $1" >> "$LOG"; }

for svc in paper_trading protection; do
  if systemctl is-active --quiet ${svc}.service; then
    logf=/home/ubuntu/agent-ia/${svc}.log
    if [ -f "$logf" ]; then
      age=$(( $(date +%s) - $(stat -c %Y "$logf") ))
      if [ "$age" -gt "$SEUIL_FIGE" ]; then
        log "ATTENTION: ${svc} actif mais log fige (${age}s > ${SEUIL_FIGE}s) -> restart"
        systemctl restart ${svc}.service
      else
        log "OK: ${svc} actif (log frais ${age}s)"
      fi
    else
      log "OK: ${svc} actif (pas de log encore)"
    fi
  else
    log "ALERTE: ${svc} INACTIF -> restart"
    systemctl restart ${svc}.service
  fi
done
EOF

chmod +x /home/ubuntu/health_check.sh
chown ubuntu:ubuntu /home/ubuntu/health_check.sh

# 2. Cron root toutes les 10 minutes
( crontab -l 2>/dev/null | grep -v health_check.sh ; echo "*/10 * * * * /bin/bash /home/ubuntu/health_check.sh" ) | crontab -

# 3. Premiere verification immediat
bash /home/ubuntu/health_check.sh

echo "============================================="
echo " Health check installe"
echo "============================================="
echo " Verification: toutes les 10 min (cron root)"
echo " Seuil log fige: 45 min"
echo " Log: /home/ubuntu/agent-ia/health.log"
echo ""
echo " Premiere verification :"
cat /home/ubuntu/agent-ia/health.log
