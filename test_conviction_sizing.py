#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_conviction_sizing.py — vérifie les multiplicateurs de conviction."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import _conviction_mult

# fake classement_strategies structure: {actif: {strategies: [{strategie, live_n, live_wr, live_pnl}]}}
cs = {
    "BTCUSDT": {"strategies": [
        {"strategie": "RSI Mean Reversion", "live_n": 5, "live_wr": 75, "live_pnl": 1.32},   # éprouvé
        {"strategie": "Bollinger Breakout", "live_n": 3, "live_wr": 67, "live_pnl": 0.45},   # solide
        {"strategie": "MACD Momentum",      "live_n": 4, "live_wr": 25, "live_pnl": -0.80},  # faible
        {"strategie": "Neuve Strat",        "live_n": 1, "live_wr": 100, "live_pnl": 0.10},  # neutre (n<3)
    ]},
}

cas = [
    ("BTCUSDT", "RSI Mean Reversion", 1.5,  "éprouvé (5t, 75%, +1.32€)"),
    ("BTCUSDT", "Bollinger Breakout", 1.25, "solide (3t, 67%, +0.45€)"),
    ("BTCUSDT", "MACD Momentum",      0.5,  "faible (4t, 25%, -0.80€)"),
    ("BTCUSDT", "Neuve Strat",        1.0,  "neutre (n=1)"),
    ("ETHUSDT", "Inconnue",           1.0,  "nouveau (pas dans classement)"),
    ("btcusdt", "RSI Mean Reversion", 1.5,  "éprouvé (case-insensitive)"),
]
ok = True
for sym, nom, attendu, desc in cas:
    sig = {"symbole": sym, "nom": nom}
    mult, raison = _conviction_mult(sig, cs)
    mark = "OK" if abs(mult - attendu) < 1e-9 else "** FAIL **"
    if abs(mult - attendu) >= 1e-9: ok = False
    print(f"  {sym:8s} {nom:20s} -> x{mult:.2f} ({raison:30s}) attendu x{attendu:.2f} {mark} | {desc}")

# CAS CLÉ: stratégie éprouvée -> taille amplifiée
print("\n>>> CAS CLÉ: RSI Mean Reversion (5 trades, 75% win, +1.32€) sur BTC")
mult, raison = _conviction_mult({"symbole":"BTCUSDT","nom":"RSI Mean Reversion"}, cs)
print(f"    multiplicateur = x{mult} -> si montant base 100€, sizing = {100*mult:.0f}€ (bénéfice potentiel x{mult})")

print("\n" + ("OK - conviction sizing validé" if ok else "** ÉCHEC **"))
