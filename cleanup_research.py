#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_research.py — Nettoie les artefacts du bug regime_watch + reset + restart.

1. Retire les lecons regime_shift bidons (hypothese contenant "{'" = artefact dict-string).
2. Reset regime_history.json (clean slate, evite faux shifts au prochain cycle).
3. Restart research_loop.service (charge le code fixe).
"""
import os, json, subprocess, datetime

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(
    os.path.join(os.getcwd(), "paper_trading.py")) else os.getcwd()
LECONS = os.path.join(D, "lecons_apprises.jsonl")
HIST = os.path.join(D, "regime_history.json")

# 1. nettoie les lecons artefact
lines = open(LECONS, encoding="utf-8").read().splitlines()
kept, removed = [], 0
for ln in lines:
    ln = ln.strip()
    if not ln:
        continue
    try:
        e = json.loads(ln)
    except Exception:
        kept.append(ln); continue
    # artefact: regime_shift avec un dict-string dans l'hypothese (vrai shift = labels courts)
    if (e.get("source") == "research_loop (24/7)" and e.get("type") == "regime_shift"
            and "{'" in e.get("hypothese", "")):
        removed += 1
        continue
    kept.append(ln)
with open(LECONS, "w", encoding="utf-8") as f:
    for ln in kept:
        f.write(ln + "\n")
print(f"✅ lecons nettoyees: {removed} artefact(s) retire(s), {len(kept)} conservees")

# 2. reset regime_history (clean slate)
with open(HIST, "w", encoding="utf-8") as f:
    json.dump({"_reset": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, f, ensure_ascii=False)
print(f"✅ regime_history.json reset (clean slate)")

# 3. restart service (charge le code fixe)
subprocess.run(["sudo", "systemctl", "restart", "research_loop.service"], check=True)
import time; time.sleep(3)
r = subprocess.run(["systemctl", "is-active", "research_loop.service"],
                   capture_output=True, text=True)
print(f"✅ research_loop.service restarte -> {r.stdout.strip()}")
print(f"   (charge maintenant le code fixe; historique clean = plus de faux shifts)")
