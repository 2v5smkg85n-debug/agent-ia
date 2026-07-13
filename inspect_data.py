#!/usr/bin/env python3
"""Inspecte la structure des fichiers de donnees de l'agent."""
import json
import os

files = [
    "paper_trading.json", "strategies.json", "backtests_pro.json",
    "backtests_reels.json", "lecons.json", "ml_performances.json",
    "memoire.json", "journal_trades.json", "historique.json",
    "stats_marches.json", "backtests_phase4.json", "backtests_horaires.json",
]

for f in files:
    if not os.path.exists(f):
        print(f"--- {f}: ABSENT")
        continue
    try:
        d = json.load(open(f))
    except Exception as e:
        print(f"--- {f}: ERREUR lecture: {e}")
        continue
    if isinstance(d, dict):
        print(f"--- {f}: dict, {len(d)} cles: {list(d.keys())[:12]}")
        if d:
            k0 = list(d.keys())[0]
            print(f"    sample [{k0}]:", json.dumps(d[k0], default=str)[:200])
    elif isinstance(d, list):
        print(f"--- {f}: list, {len(d)} elements")
        if d:
            print(f"    sample[0]:", json.dumps(d[0], default=str)[:200])
            if len(d) > 1:
                print(f"    sample[-1]:", json.dumps(d[-1], default=str)[:200])
    else:
        print(f"--- {f}: {type(d).__name__}")
