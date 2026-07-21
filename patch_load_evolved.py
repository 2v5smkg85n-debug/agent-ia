#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_load_evolved.py — backtest_moteur charge strategies_evolved.py (import dynamique)."""
import sys

f = "backtest_moteur.py"
src = open(f, encoding="utf-8").read()

ANCHOR = '''    "EMA Crossover":      strat_ema_crossover,
}'''
NEW = '''    "EMA Crossover":      strat_ema_crossover,
}

# Phase 7b: charge les stratégies générées par strategy_evolver.py (auto-déploiement)
try:
    from strategies_evolved import EVOLVED_STRATEGIES
    STRATEGIES.update(EVOLVED_STRATEGIES)
except Exception:
    pass'''

if "from strategies_evolved import EVOLVED_STRATEGIES" in src:
    print("deja patche - skip")
elif ANCHOR in src:
    src = src.replace(ANCHOR, NEW, 1)
    open(f, "w", encoding="utf-8").write(src)
    print("OK backtest_moteur charge strategies_evolved.py")
else:
    print("ERREUR: ancre STRATEGIES introuvable")
    sys.exit(1)
