#!/bin/bash
# Script de securisation VPS - Agent IA Trading
# A lancer en root: sudo bash securite_vps.sh

echo "🔐 SECURISATION VPS - Agent IA Trading"
echo "======================================"

# 1. Firewall UFW
echo ""
echo "📡 1/5 Configuration du firewall UFW..."
apt-get install -y ufw > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8765/tcp comment 'Dashboard'
ufw --force enable
echo "✅ Firewall actif (SSH + Dashboard autorises)"

# 2. Fail2ban
echo ""
echo "🛡️ 2/5 Installation fail2ban..."
apt-get install -y fail2ban > /dev/null 2>&1
cat > /etc/fail2ban/jail.local << 'JAIL'
[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 3600
findtime = 600
JAIL
systemctl enable fail2ban
systemctl restart fail2ban
echo "✅ Fail2ban actif (ban apres 3 tentatives SSH)"

# 3. Sauvegarde automatique
echo ""
echo "💾 3/5 Configuration sauvegardes auto..."
mkdir -p /home/ubuntu/backups
cat > /home/ubuntu/agent-ia/backup.sh << 'BACKUP'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M)
cd /home/ubuntu
tar -czf backups/agent-ia_$DATE.tar.gz agent-ia/ --exclude='venv' --exclude='__pycache__'
# Garder seulement les 7 derniers
ls -t backups/agent-ia_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null
echo "Backup $DATE cree"
BACKUP
chmod +x /home/ubuntu/agent-ia/backup.sh
# Cron backup quotidien a 3h
(crontab -l 2>/dev/null; echo "0 3 * * * /home/ubuntu/agent-ia/backup.sh >> /home/ubuntu/backups/backup.log 2>&1") | crontab -
echo "✅ Sauvegarde quotidienne 3h installee"

# 4. Monitoring systeme
echo ""
echo "📊 4/5 Installation monitoring..."
cat > /home/ubuntu/agent-ia/monitor.sh << 'MONITOR'
#!/bin/bash
CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
MEM=$(free | awk '/Mem/ {printf("%.1f", $3/$2*100)}')
DISK=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
LOAD=$(cat /proc/loadavg | awk '{print $1}')
AGENT=$(pgrep -f "agent_os.py" | wc -l)
PAPER=$(systemctl is-active paper_trading.service 2>/dev/null || echo "inactive")

# Alerte si problemes
ALERT=""
if (( $(echo "$CPU > 80" | bc -l) )); then ALERT="$ALERT ⚠️ CPU: ${CPU}%"; fi
if (( $(echo "$MEM > 80" | bc -l) )); then ALERT="$ALERT ⚠️ RAM: ${MEM}%"; fi
if (( DISK > 85 )); then ALERT="$ALERT ⚠️ DISK: ${DISK}%"; fi
if [ "$AGENT" -eq 0 ]; then ALERT="$ALERT 🔴 Agent OS arrete!"; fi
if [ "$PAPER" != "active" ]; then ALERT="$ALERT 🔴 Paper trading arrete!"; fi

if [ -n "$ALERT" ]; then
  cd /home/ubuntu/agent-ia && source venv/bin/activate
  python3 -c "
import requests
TOKEN='8842392968:AAFtjbMxfzCt7fPp0zvU1mNRED7nsEnMnj4'
CHAT='7732199571'
msg='🚨 ALERTE SYSTEME VPS\n$ALERT\n\nCPU: ${CPU}% | RAM: ${MEM}%\nDisk: ${DISK}% | Load: ${LOAD}\nAgent: ${AGENT} | Paper: ${PAPER}'
requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json={'chat_id': CHAT, 'text': msg})
"
fi
MONITOR
chmod +x /home/ubuntu/agent-ia/monitor.sh
# Cron monitoring toutes les 30 min
(crontab -l 2>/dev/null; echo "*/30 * * * * /home/ubuntu/agent-ia/monitor.sh >> /home/ubuntu/agent-ia/monitor.log 2>&1") | crontab -
echo "✅ Monitoring toutes les 30min installe"

# 5. SSH hardening
echo ""
echo "🔒 5/5 Hardening SSH..."
SSH_CONFIG="/etc/ssh/sshd_config"
# Desactive root login
if grep -q "^#*PermitRootLogin" "$SSH_CONFIG"; then
  sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSH_CONFIG"
fi
# Garde la connexion active
if grep -q "^#*ClientAliveInterval" "$SSH_CONFIG"; then
  sed -i 's/^#*ClientAliveInterval.*/ClientAliveInterval 60/' "$SSH_CONFIG"
else
  echo "ClientAliveInterval 60" >> "$SSH_CONFIG"
fi
systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null
echo "✅ SSH durci (root desactive, keepalive 60s)"

echo ""
echo "======================================"
echo "✅ SECURISATION TERMINEE!"
echo ""
echo "Services installes:"
echo "  📡 Firewall UFW (SSH + Dashboard)"
echo "  🛡️ Fail2ban (3 tentatives max)"
echo "  💾 Sauvegarde auto quotidienne 3h"
echo "  📊 Monitoring 30min + alertes Telegram"
echo "  🔒 SSH hardening"
echo ""
echo "Crons installes:"
crontab -l
