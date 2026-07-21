#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sagesse_nouvelles.py — Ajoute les 3 nouvelles strategies au dictionnaire
SAGESSE_STRAT dans test_classement.py pour coherence.

- EMA Crossover:    trend (genre SMA) -> NUANCE 0.95 (comme Dennis Turtle)
- Donchian Breakout: breakout/trend     -> NUANCE 0.95 (comme Bollinger/Dennis)
- Stochastic:       oscillator/contrarian -> VALIDE 1.00 (genre RSI, mean-reversion)
"""
import sys

f = "classement_strategies.py"
src = open(f, encoding="utf-8").read()

ANCHOR = '''    "Bollinger Breakout":  {"trader": "Dennis/Bollinger",      "verdict": "NUANCE",  "mult": 0.95},
}'''
NEW = '''    "Bollinger Breakout":  {"trader": "Dennis/Bollinger",      "verdict": "NUANCE",  "mult": 0.95},
    # Phase 7 - nouvelles strategies (coherence sagesse)
    "EMA Crossover":       {"trader": "Dennis (Turtle)",        "verdict": "NUANCE",  "mult": 0.95},
    "Donchian Breakout":   {"trader": "Dennis/Bollinger",      "verdict": "NUANCE",  "mult": 0.95},
    "Stochastic":          {"trader": "Buffett/Livermore",      "verdict": "VALIDE",  "mult": 1.00},
}'''

if ANCHOR in src:
    src = src.replace(ANCHOR, NEW, 1)
    open(f, "w", encoding="utf-8").write(src)
    print("OK SAGESSE_STRAT mis a jour avec les 3 nouvelles strategies")
    import subprocess
    r = subprocess.run(["grep", "-n", "-A12", "SAGESSE_STRAT =", f], capture_output=True, text=True)
    print(r.stdout)
else:
    print("ERREUR: ancre introuvable - verifie le format")
    sys.exit(1)
