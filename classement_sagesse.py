#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classement_sagesse.py — Classement des strategies avec la sagesse des traders integree.

Lit classement_strategies.json + mappe chaque strategie a son maitre trader
+ verdict du backtest. Affiche score_sagesse = score x sagesse_mult.

Sagesse_mult (validé par backtest_sagesse.py):
  - RSI Mean Reversion (contrarian creux modere): VALIDE -> 1.00 (regime_fit recompense deja)
  - MACD/SMA/Bollinger (trend/breakout): NUANCE -> 0.95 (principe regime-conditionnel,
    le Turtle test a montre expectancy positive mais qualite inferieure en QUIET)
"""
import json

# Mapping strategie -> sagesse du maitre trader
SAGESSE_STRAT = {
    "RSI Mean Reversion": {
        "trader": "Buffett/Rogers/Soros",
        "principe": "Contrarian (creux modere)",
        "verdict": "VALIDE",
        "mult": 1.00,
        "lecon": "RSI 20-30 gagne 83% (creux modere rebondit). RSI<20 = couteau tombant (rejete).",
    },
    "MACD Momentum": {
        "trader": "Dennis/PTJ",
        "principe": "Trend/momentum",
        "verdict": "NUANCE",
        "mult": 0.95,
        "lecon": "Trend aide en regime TREND, nuit en QUIET (Fit 0.60). Turtle: 55% win tous regimes mais qualite 4x inferieure.",
    },
    "SMA Crossover": {
        "trader": "Dennis (Turtle)",
        "principe": "Trend-following",
        "verdict": "NUANCE",
        "mult": 0.95,
        "lecon": "Breakout/trend regime-conditionnel. Rejete en QUIET (ADX/trailing/EXTEND-breakeven tous rejetes).",
    },
    "Bollinger Breakout": {
        "trader": "Dennis/Bollinger",
        "principe": "Breakout volatilite",
        "verdict": "NUANCE",
        "mult": 0.95,
        "lecon": "Breakout = trend, regime-conditionnel. Fit 0.70 en QUIET.",
    },
}

d = json.load(open("classement_strategies.json", encoding="utf-8"))
rows = []
for actif, v in d.items():
    if not isinstance(v, dict):
        continue
    for s in v.get("strategies", []):
        nom = s.get("strategie", "")
        sag = SAGESSE_STRAT.get(nom, {"trader": "?", "principe": "?", "verdict": "?", "mult": 1.0, "lecon": ""})
        s2 = dict(s)
        s2["sagesse_trader"] = sag["trader"]
        s2["sagesse_principe"] = sag["principe"]
        s2["sagesse_verdict"] = sag["verdict"]
        s2["sagesse_mult"] = sag["mult"]
        s2["score_sagesse"] = s.get("score", 0) * sag["mult"]
        rows.append(s2)

rows.sort(key=lambda x: x.get("score_sagesse", 0), reverse=True)

print("=" * 92)
print("CLASSEMENT AVEC SAGESSE DES TRADERS (score_sagesse = score x sagesse_mult)")
print("=" * 92)
print(f"{'#':<3}{'Actif':<10}{'Strategie':<20}{'Score':>6}{'Sag':>6}{'Fit':>5}{'Live':>6}  {'Maitre':<22}{'Verdict':<8}")
print("-" * 92)
for s in rows[:13]:
    v = s.get("sagesse_verdict", "?")
    mark = "OK" if v == "VALIDE" else ("~" if v == "NUANCE" else "X")
    print(f"{str(s.get('rang','?')):<3}{str(s.get('actif','?')):<10}"
          f"{str(s.get('strategie','?')):<20}{s.get('score_sagesse',0):>6.2f}"
          f"x{s.get('sagesse_mult',1.0):>4.2f}{s.get('regime_fit',0):>5.2f}"
          f"x{s.get('live_mult',1.0):>5.2f}  {str(s.get('sagesse_trader','?')):<22}{mark:<8}")
print("-" * 92)
print("\nLecture par strategie (sagesse du maitre + lecon):")
seen = set()
for s in rows:
    nom = s.get("strategie", "")
    if nom in seen:
        continue
    seen.add(nom)
    print(f"\n  {nom} [{s.get('sagesse_trader')}] — verdict: {s.get('sagesse_verdict')} (x{s.get('sagesse_mult')})")
    print(f"    {s.get('sagesse_principe')}")
    lc = SAGESSE_STRAT.get(nom, {}).get("lecon", "")
    if lc:
        print(f"    lecon: {lc}")
print("\n" + "=" * 92)
print("Bilan: la sagesse des 10 maitres est maintenant reliee a chaque strategie.")
print("RSI = contrarian valide (Buffett/Rogers). MACD/SMA/Bollinger = trend regime-conditionnel.")
print("La reflection Gemini peut citer ces liens pour generer des hypotheses.")
print("=" * 92)
