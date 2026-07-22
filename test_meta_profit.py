#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_meta_profit.py — vérifie _diagnostic_profit identifie la plus grosse fuite."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from meta_evolver import _diagnostic_profit

# fake trades: 3 STOP-LOSS (grosse perte) + quelques TAKE-PROFIT + TEMPS
trades = [
    {"raison": "STOP-LOSS", "gain_eur": -1.30, "strategie": "MACD Momentum", "source": ""},
    {"raison": "STOP-LOSS", "gain_eur": -1.40, "strategie": "MACD Momentum", "source": ""},
    {"raison": "STOP-LOSS", "gain_eur": -1.20, "strategie": "Bollinger Breakout", "source": ""},
    {"raison": "TAKE-PROFIT", "gain_eur": +1.62, "strategie": "RSI Mean Reversion", "source": ""},
    {"raison": "TEMPS+benefice (+0.27%)", "gain_eur": +0.27, "strategie": "RSI Mean Reversion", "source": ""},
    {"raison": "TEMPS+benefice (+0.50%)", "gain_eur": +0.50, "strategie": "RSI Mean Reversion", "source": ""},
    {"raison": "PARTIAL-TP", "gain_eur": +0.45, "strategie": "RSI Mean Reversion", "source": "rsi_PARTIAL"},
    {"raison": "STOP-BREAKEVEN", "gain_eur": +0.01, "strategie": "Bollinger Breakout", "source": ""},
]
diag = _diagnostic_profit(trades)
print(diag)
print("\n" + "=" * 60)

# vérifications
assert "DIAGNOSTIC RENTABILITÉ" in diag
assert "CIBLE PRIORITAIRE" in diag, "doit identifier la plus grosse fuite"
assert "STOP-LOSS" in diag, "STOP-LOSS doit apparaître comme la fuite"
# la fuite STOP-LOSS = -3.90€ (3 trades)
assert "CIBLE PRIORITAIRE (plus grosse fuite): STOP-LOSS" in diag
# PARTIAL-TP bien regroupé (pas de doublon _PARTIAL)
assert "rsi_PARTIAL" not in diag, "le suffixe _PARTIAL doit être nettoyé"
print("OK - diagnostic profit validé: STOP-LOSS identifié comme cible prioritaire")
