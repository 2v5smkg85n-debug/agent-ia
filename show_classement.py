#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""show_classement.py — Affiche le vrai classement des strategies (aplatit le JSON imbrique)."""
import json

d = json.load(open("classement_strategies.json", encoding="utf-8"))
rows = []
for actif, v in d.items():
    if not isinstance(v, dict):
        continue
    for s in v.get("strategies", []):
        rows.append(s)
rows.sort(key=lambda x: x.get("score", 0), reverse=True)

print("=" * 78)
print(f"CLASSEMENT DES STRATEGIES (score = backtest x regime_fit x live_mult)")
print("=" * 78)
print(f"{'#':<3}{'Actif':<10}{'Strategie':<24}{'Score':>7}{'BTest':>7}{'Fit':>6}{'Live':>7}{'Regime':<8}")
print("-" * 78)
for s in rows[:15]:
    dis = "OFF" if s.get("disabled") else "ON"
    print(f"{str(s.get('rang','?')):<3}{str(s.get('actif','?')):<10}"
          f"{str(s.get('strategie','?')):<24}{s.get('score',0):>7.2f}"
          f"{s.get('backtest',0):>7.2f}{s.get('regime_fit',0):>6.2f}"
          f"x{s.get('live_mult',1.0):>5.2f}  {str(s.get('regime','?')):<8}")
print("-" * 78)
print(f"Total: {len(rows)} strategies classees | "
      f"top: {rows[0].get('actif')}:{rows[0].get('strategie')} (score {rows[0].get('score')})" if rows else "vide")
print(f"\nLecture: Fit>1 = strategie aide en regime QUIET | Fit<1 = strategie nuit en QUIET")
print(f"        Live x1.0 = peu de trades (shrink bayesien), grandira avec l'experience")
