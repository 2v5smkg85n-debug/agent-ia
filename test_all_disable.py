#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test live: coupe MACD Momentum sur TOUS les actifs perdants (mode ALL)."""
import os, json
os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
import sys
sys.path.insert(0, os.getcwd())

import actions_executor as ae

print("=" * 55)
print("STATS MACD Momentum (par actif)")
print("=" * 55)
stats = ae.stats_strategies()
macd = {k: v for k, v in stats.items() if v.get("strategie") == "MACD Momentum"}
if not macd:
    print("  (aucune stratégie MACD Momentum dans les stats live)")
else:
    for cle, s in sorted(macd.items()):
        print(f"  {s.get('actif','?')}: n={s.get('n')} win={s.get('win_rate')} "
              f"pnl={s.get('pnl_total')}€")

print()
print("=" * 55)
print("DÉSACTIVATION MODE ALL (coupe les perdantes)")
print("=" * 55)
ok, msg = ae.desactiver_strategie("MACD Momentum", "ALL",
                                  "MACD Momentum perdante (pnl<0) — reflection répétée")
print(f"  ok={ok}")
print(f"  {msg}")

print()
print("=" * 55)
print("STRATÉGIES DÉSACTIVÉES (après)")
print("=" * 55)
try:
    d = json.load(open(ae.PRUNING_FILE, encoding="utf-8"))
    for cle, v in d.get("desactivees", {}).items():
        print(f"  {cle}: {v.get('source')} | pnl {v.get('stats',{}).get('pnl_total')}€ "
              f"| since {v.get('since')}")
except Exception as e:
    print(f"  err: {e}")
