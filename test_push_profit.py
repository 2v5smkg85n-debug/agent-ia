#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_push_profit.py — vérifie les nouveaux multiplicateurs de conviction."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import _conviction_mult

cs = {
    "BTCUSDT": {"strategies": [
        {"strategie": "RSI Mean Reversion", "live_n": 5, "live_wr": 75, "live_pnl": 1.32},   # éprouvé x2.0
        {"strategie": "Bollinger Breakout", "live_n": 3, "live_wr": 67, "live_pnl": 0.45},   # solide x1.5
        {"strategie": "MACD Momentum",      "live_n": 4, "live_wr": 25, "live_pnl": -0.80},  # faible x0.5
        {"strategie": "Elite Strat",        "live_n": 8, "live_wr": 80, "live_pnl": 3.50},   # élite x2.5
        {"strategie": "Neuve",              "live_n": 1, "live_wr": 100, "live_pnl": 0.10},   # neutre x1.0
    ]},
}

cas = [
    ("BTCUSDT", "RSI Mean Reversion", 2.0,  "éprouvé -> x2.0"),
    ("BTCUSDT", "Bollinger Breakout", 1.5,  "solide -> x1.5"),
    ("BTCUSDT", "MACD Momentum",      0.5,  "faible -> x0.5"),
    ("BTCUSDT", "Elite Strat",        2.5,  "élite -> x2.5"),
    ("BTCUSDT", "Neuve",              1.0,  "neutre -> x1.0"),
    ("ETHUSDT", "Inconnue",           1.0,  "nouveau -> x1.0"),
]
ok = True
for sym, nom, attendu, desc in cas:
    mult, raison = _conviction_mult({"symbole": sym, "nom": nom}, cs)
    mark = "OK" if abs(mult - attendu) < 1e-9 else "** FAIL **"
    if abs(mult - attendu) >= 1e-9: ok = False
    print(f"  {nom:20s} -> x{mult:.2f} ({raison:28s}) attendu x{attendu:.2f} {mark} | {desc}")

# CAS CLÉ: stratégie élite -> taille x2.5
print("\n>>> CAS CLÉ: stratégie élite (8t, 80% win, +3.50€)")
mult, raison = _conviction_mult({"symbole":"BTCUSDT","nom":"Elite Strat"}, cs)
print(f"    x{mult} -> si base 100€, sizing = {100*mult:.0f}€ (bénéfice x{mult} sur chaque gagnant)")
print(f"    un trade à +1.5% qui rapportait +1.50€ rapporte maintenant +{1.50*mult:.2f}€")

print("\n" + ("OK - conviction push validé" if ok else "** ÉCHEC **"))
