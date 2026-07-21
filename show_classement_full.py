#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""show_classement_full.py — Regénère le classement (7 stratégies) et l'affiche complet."""
import json
from classement_strategies import calculer_classement

NOUVELLES = {"Donchian Breakout", "Stochastic", "EMA Crossover"}

# 1. Regénère le classement avec les nouveaux backtests (7 strategies)
result = None
try:
    result = calculer_classement()
except Exception as e:
    print(f"(regen via calculer_classement: {e})")
    result = None

# calculer_classement peut retourner un dict {actif: {strategies:[...]}} ou une liste
rows = []
if isinstance(result, dict):
    for actif, v in result.items():
        if isinstance(v, dict):
            rows.extend(v.get("strategies", []))
elif isinstance(result, list):
    rows = result

# fallback: lit le JSON si vide
if not rows:
    d = json.load(open("classement_strategies.json", encoding="utf-8"))
    for actif, v in d.items():
        if isinstance(v, dict):
            rows.extend(v.get("strategies", []))

rows.sort(key=lambda x: x.get("score", 0), reverse=True)

# compte par strategie
par_strat = {}
for r in rows:
    s = r.get("strategie", "?")
    par_strat.setdefault(s, {"n": 0, "gagnantes": 0, "top_score": -999})
    par_strat[s]["n"] += 1
    if not r.get("disabled") and r.get("score", 0) > 0:
        par_strat[s]["gagnantes"] += 1
    par_strat[s]["top_score"] = max(par_strat[s]["top_score"], r.get("score", 0))

print("=" * 90)
print(f"CLASSEMENT COMPLET — {len(rows)} entrees | 7 strategies | *=nouvelle (Phase 7)")
print("score = backtest_edge x regime_fit x live_mult x sagesse_mult")
print("=" * 90)
print(f"{'#':<4}{'Actif':<11}{'Strategie':<23}{'Score':>8}{'BTest':>7}{'Fit':>6}{'Live':>7}{'Sages':>7}{'Regime':<9}")
print("-" * 90)
for i, r in enumerate(rows[:30], 1):
    strat = str(r.get("strategie", "?"))
    star = " *" if strat in NOUVELLES else "  "
    dis = " (OFF)" if r.get("disabled") else ""
    print(f"{i:<4}{str(r.get('actif','?')):<11}{strat+star+dis:<23}"
          f"{r.get('score',0):>8.2f}{r.get('backtest',0):>7.2f}"
          f"{r.get('regime_fit',0):>6.2f}x{r.get('live_mult',1.0):>5.2f}"
          f"{r.get('sagesse_mult',1.0):>6.2f}x  {str(r.get('regime','?')):<9}")
print("-" * 90)

print("\n=== STATS PAR STRATEGIE ===")
print(f"{'Strategie':<24}{'Entrees':>8}{'Gagnantes':>10}{'Top score':>11}")
print("-" * 55)
for s in sorted(par_strat.keys(), key=lambda k: par_strat[k]["top_score"], reverse=True):
    st = par_strat[s]
    star = " *" if s in NOUVELLES else ""
    print(f"{s+star:<24}{st['n']:>8}{st['gagnantes']:>10}{st['top_score']:>11.2f}")

print(f"\nTop actuel: {rows[0].get('actif')} x {rows[0].get('strategie')} (score {rows[0].get('score')})")
nb_nouvelles = sum(1 for r in rows if r.get("strategie") in NOUVELLES and not r.get("disabled") and r.get("score",0) > 0)
print(f"Strategies nouvelles rentrees au classement (score>0): {nb_nouvelles} entrees")
