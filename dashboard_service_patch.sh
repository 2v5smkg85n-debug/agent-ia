#!/bin/bash
# Met a jour le service systemd pour pointer sur dashboard_premium.py
sudo tee /etc/systemd/system/dashboard.service > /dev/null << 'EOL'
[Unit]
Description=Dashboard Premium Agent IA
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-ia
ExecStart=/usr/bin/python3 /home/ubuntu/agent-ia/dashboard_premium.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOL
sudo systemctl daemon-reload
sudo systemctl restart dashboard.service
sleep 2
sudo systemctl status dashboard.service --no-pager | head -10
