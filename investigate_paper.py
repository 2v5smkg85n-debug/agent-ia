#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""investigate_paper.py — Pourquoi le portefeuille paper est a 0€ + crons tournent-ils?"""
import os, sys, json, subprocess
from datetime import datetime
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

print("=" * 70)
print(f"INVESTIGATION — {datetime.utcnow():%Y-%m-%d %H:%M} UTC")
print("=" * 70)

# 1. Fichier portefeuille brut
print("\n--- 1. FICHIER PORTEFEUILLE BRUT ---")
for f in ["portefeuille.json", "paper_portefeuille.json", "paper_trading_portefeuille.json"]:
    if os.path.exists(f):
        try:
            d = json.load(open(f, encoding="utf-8"))
            print(f"  {f}: solde={d.get('solde', d.get('capital', '?'))} positions={len(d.get('positions', {}))}")
            print(f"    cles: {list(d.keys())[:10]}")
            # date modif
            mt = datetime.fromtimestamp(os.path.getmtime(f))
            print(f"    modifie: {mt}")
        except Exception as e:
            print(f"  {f} erreur: {e}")
    else:
        print(f"  {f}: absent")

# 2. Lister tous les fichiers portefeuille/paper
print("\n--- 2. FICHIERS PAPER/PORTEFEUILLE ---")
r = subprocess.run(["bash", "-c", "ls -la *portefeuille* *paper* 2>/dev/null | head -20"], capture_output=True, text=True)
print(r.stdout or "  aucun")

# 3. Service paper_trading status
print("\n--- 3. SERVICE paper_trading ---")
r = subprocess.run(["systemctl", "status", "paper_trading.service"], capture_output=True, text=True)
for l in r.stdout.splitlines()[:12]:
    print(f"  {l}")

# 4. Logs paper_trading recents (erreurs?)
print("\n--- 4. LOGS paper_trading (erreurs recentes) ---")
r = subprocess.run(["bash", "-c", "journalctl -u paper_trading.service --since '6h ago' --no-pager 2>/dev/null | tail -25"], capture_output=True, text=True)
print(r.stdout[-1500:] or "  vide")

# 5. Crons: sont-ils presents + ont-ils tourne?
print("\n--- 5. CRONS APPRENTISSAGE ---")
r = subprocess.run(["bash", "-c", "sudo crontab -l 2>/dev/null | grep -E 'reflection|backtest_horaires|auto_sweep'"], capture_output=True, text=True)
print(r.stdout or "  aucun cron trouve")
# logs /tmp
for lf in ["/tmp/reflection_cron.log", "/tmp/backtest_cron.log", "/tmp/auto_sweep_cron.log"]:
    r = subprocess.run(["bash", "-c", f"echo '{lf}:'; ls -la {lf} 2>/dev/null; tail -5 {lf} 2>/dev/null"], capture_output=True, text=True)
    print(r.stdout)

# 6. Reflection log: dernieres entrees avec dates
print("\n--- 6. REFLECTION LOG (dates) ---")
r = subprocess.run(["bash", "-c", "tail -5 reflection_log.jsonl 2>/dev/null | python3 -c \"import sys,json; [print(json.loads(l).get('ts','?')[:16]) for l in sys.stdin if l.strip()]\" 2>/dev/null"], capture_output=True, text=True)
print(r.stdout or "  vide")

# 7. ACHAT Gaz naturel: a-t-il ete execute?
print("\n--- 7. ACHAT GAZ NATUREL (execute?) ---")
r = subprocess.run(["bash", "-c", "grep -i 'gaz\\|natural\\|NG' paper_trading.log 2>/dev/null | tail -8"], capture_output=True, text=True)
print(r.stdout or "  rien")

print("\n" + "=" * 70)
