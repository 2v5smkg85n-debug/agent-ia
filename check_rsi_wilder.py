#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_rsi_wilder.py — Affiche le VRAI RSI (Wilder, rsi_series) que la
strategie voit, pour savoir quels cryptos declencheraient ACHAT (<35)."""
import os, sys
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from indicateurs import historique_ohlcv
from backtest_moteur import rsi_series, strat_rsi_reversion
from signaux_gagnants import calculer_donnees, signal_strategie

CRYPTOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]

print(f"{'ACTIF':<12} {'RSI Wilder':>10} {'<35?':>6} {'signal':>8}")
print("-" * 42)
for sym in CRYPTOS:
    bougies = historique_ohlcv(sym, "1h", 100)
    if not bougies or len(bougies) < 60:
        print(f"{sym:<12} pas de donnees")
        continue
    closes = [b["cloture"] for b in bougies]
    rsi = rsi_series(closes, 14)
    rsi_actuel = rsi[-1] if rsi else None
    # signal via la vraie fonction (seuil <35 maintenant)
    donnees = calculer_donnees(closes)
    sig = signal_strategie("RSI Mean Reversion", donnees)
    rsi_str = f"{rsi_actuel:.1f}" if rsi_actuel is not None else "N/A"
    decl = "OUI" if (rsi_actuel is not None and rsi_actuel < 35) else "non"
    print(f"{sym:<12} {rsi_str:>10} {decl:>6} {str(sig):>8}")

print("-" * 42)
print("Si 'OUI' mais signal != ACHAT -> autre filtre bloque (gate/classement)")
print("Si tout 'non' -> marche pas assez oversold, attendre")
