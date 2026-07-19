#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_classement_sagesse.py — Cable la sagesse des traders dans classement_strategies.py.

score = backtest × regime_fit × live_mult × sagesse_mult
+ ajoute sagesse_mult, sagesse_trader, sagesse_verdict dans chaque entree.

SAGESSE_STRAT (validé par backtest_sagesse.py):
  - RSI Mean Reversion (contrarian, Buffett/Rogers/Soros): VALIDE -> 1.00
  - MACD/SMA/Bollinger (trend, Dennis): NUANCE regime TREND -> 0.95
"""
import os

F = "classement_strategies.py"
s = open(F, encoding="utf-8").read()

# 1) Ajout de la SAGESSE_STRAT avant calculer_classement
anchor = "def calculer_classement():"
assert anchor in s, "def calculer_classement introuvable"
sagesse_dict = '''# SAGESSE DES TRADERS: multiplieur de principe (validé par backtest_sagesse.py)
# RSI=contrarian valide (x1.00), trend/breakout=regime-conditionnel (x0.95 leger penalite)
SAGESSE_STRAT = {
    "RSI Mean Reversion":  {"trader": "Buffett/Rogers/Soros", "verdict": "VALIDE",  "mult": 1.00},
    "MACD Momentum":       {"trader": "Dennis/PTJ",            "verdict": "NUANCE",  "mult": 0.95},
    "SMA Crossover":       {"trader": "Dennis (Turtle)",        "verdict": "NUANCE",  "mult": 0.95},
    "Bollinger Breakout":  {"trader": "Dennis/Bollinger",      "verdict": "NUANCE",  "mult": 0.95},
}


'''
s = s.replace(anchor, sagesse_dict + anchor, 1)

# 2) Recup sagesse_mult apres nom = s.get("strategie", "")
old2 = '            nom = s.get("strategie", "")\n            backtest = float(s.get("retour_pct", 0) or 0)\n'
new2 = ('            nom = s.get("strategie", "")\n'
        '            backtest = float(s.get("retour_pct", 0) or 0)\n'
        '            # sagesse du maitre trader (principe valide/nuance)\n'
        '            _sag = SAGESSE_STRAT.get(nom, {})\n'
        '            sagesse_mult = float(_sag.get("mult", 1.0))\n')
assert old2 in s, "bloc nom/backtest introuvable"
s = s.replace(old2, new2, 1)

# 3) Score: ajouter * sagesse_mult
old3 = '                score = backtest * fit_avg * live_mult\n'
new3 = '                score = backtest * fit_avg * live_mult * sagesse_mult\n'
assert old3 in s, "formule score introuvable"
s = s.replace(old3, new3, 1)

# 4) Ajout champs sagesse dans le row dict (apres live_mult)
old4 = '                "live_mult": round(live_mult, 2),\n'
new4 = ('                "live_mult": round(live_mult, 2),\n'
        '                "sagesse_mult": round(sagesse_mult, 2),\n'
        '                "sagesse_trader": _sag.get("trader", ""),\n'
        '                "sagesse_verdict": _sag.get("verdict", ""),\n')
assert old4 in s, "bloc live_mult row introuvable"
s = s.replace(old4, new4, 1)

open(F, "w", encoding="utf-8").write(s)
print("OK sagesse cablee dans classement_strategies.py")
print("  - SAGESSE_STRAT ajoutee (RSI x1.00, trend x0.95)")
print("  - score = backtest * fit * live * sagesse_mult")
print("  - champs sagesse_mult/trader/verdict dans le JSON")
