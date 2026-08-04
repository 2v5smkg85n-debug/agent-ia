#!/usr/bin/env python3
"""Affiche uniquement les strategies utilisees par l'agent (top 3 + WR >= 65%)"""
import json

TOP_3 = {"RSI Mean Reversion", "SMA Crossover", "EMA Crossover"}
WR_MIN = 65

with open("backtests_horaires.json") as f:
    data = json.load(f)

filtered = []
for r in data:
    if r.get("verdict") != "GAGNANTE":
        continue
    if r.get("strategie") not in TOP_3:
        continue
    if r.get("win_rate", 0) < WR_MIN:
        continue
    filtered.append(r)

filtered.sort(key=lambda x: x.get("rendement", 0), reverse=True)

print(f"\n=== STRATEGIES ACTIVES (top 3 + WR >= {WR_MIN}%) ===")
print(f"Total: {len(filtered)} strategies actives\n")

# Par strategie
from collections import defaultdict
par_strat = defaultdict(list)
for r in filtered:
    par_strat[r["strategie"]].append(r)

print(f"{'Strategie':<22} {'Nb':>4} {'WR moy':>8} {'Best WR':>8} {'Best R':>8}")
print("-" * 55)
for strat in sorted(par_strat.keys()):
    items = par_strat[strat]
    wrs = [x.get("win_rate", 0) for x in items]
    rends = [x.get("rendement", 0) for x in items]
    print(f"{strat:<22} {len(items):>4} {sum(wrs)/len(wrs):>7.1f}% {max(wrs):>7.1f}% {max(rends):>+7.1f}%")

print(f"\n--- Details ({len(filtered)} strategies) ---")
for r in filtered:
    print(f"  {r.get('actif','?'):<12} {r.get('strategie','?'):<22} WR={r.get('win_rate',0):>5.1f}% R={r.get('rendement',0):>+7.1f}% {r.get('intervalle','?')}")
