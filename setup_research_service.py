#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_research_service.py — Cree le service systemd research_loop (24/7)."""
import os, subprocess

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(
    os.path.join(os.getcwd(), "paper_trading.py")) else os.getcwd()
VENV_PY = os.path.join(D, "venv", "bin", "python")
SCRIPT = os.path.join(D, "research_loop.py")

UNIT = f"""[Unit]
Description=Agent IA - Research Loop 24/7 (apprentissage continu)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory={D}
ExecStart={VENV_PY} -u {SCRIPT}
Restart=always
RestartSec=30
StandardOutput=append:/var/log/research_loop.log
StandardError=append:/var/log/research_loop.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

# 1. test compile
r = subprocess.run([VENV_PY, "-c", f"import py_compile; py_compile.compile('{SCRIPT}', doraise=True)"],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("ERREUR compile:\n", r.stderr); raise SystemExit(1)
print("✅ research_loop.py compile OK")

# 2. ecrit le service (sudo)
SERVICE = "/etc/systemd/system/research_loop.service"
subprocess.run(["sudo", "tee", SERVICE], input=UNIT, text=True, check=True)
print(f"✅ service ecrit: {SERVICE}")

# 3. reload + enable + start
for cmd in (["sudo", "systemctl", "daemon-reload"],
            ["sudo", "systemctl", "enable", "research_loop.service"],
            ["sudo", "systemctl", "restart", "research_loop.service"]):
    subprocess.run(cmd, check=True)
print("✅ research_loop.service: enabled + started (24/7)")

# 4. verifie
r = subprocess.run(["systemctl", "is-active", "research_loop.service"],
                   capture_output=True, text=True)
print(f"   statut: {r.stdout.strip()}")
print(f"   log: /var/log/research_loop.log")
print(f"   suivi: sudo journalctl -u research_loop -f  (ou tail /var/log/research_loop.log)")
