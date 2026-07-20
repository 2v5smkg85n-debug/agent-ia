#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_rsi_seuil.py — Teste le VRAI levier: le seuil RSI.
RSI<30 (actuel) vs RSI<35 vs RSI<40. Plus de trades = plus d'opportunites."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from indicateurs import historique_ohlcv
from backtest_moteur import simuler, rsi_series, sma_series, bollinger_series, _macd_full, CAPITAL_DEPART
from bougies_patterns import analyser_patterns

CRYPTOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]

def make_rsi(seuil):
    """Strategie RSI Mean Reversion avec seuil parametrable.
    Achat si RSI < seuil; vente si RSI > 70."""
    def f(i, d):
        r = d["rsi"][i]
        if r is None:
            return None
        if r < seuuil:
            return "ACHAT"
        if r > 70:
            return "VENTE"
        return None
    return f

def make_rsi(seuil):
    def f(i, d):
        r = d["rsi"][i]
        if r is None:
            return None
        if r < seuil:
            return "ACHAT"
        if r > 70:
            return "VENTE"
        return None
    return f

SEUILS = [30, 35, 40, 45]
print("=" * 90)
print("BACKTEST SEUIL RSI (RSI Mean Reversion, 1h, ~500 bougies, 10 cryptos)")
print("=" * 90)
hdr = f"{'ACTIF':<10}"
for s in SEUILS:
    hdr += f" | RSI<{s:<2} trades/PnL/Win%"
print(hdr)
print("-" * 90)

tot = {s: [0, 0.0, 0, 0] for s in SEUILS}  # trades, pnl, gagnes, perdus

for sym in CRYPTOS:
    bougies = historique_ohlcv(sym, "1h", 500)
    if not bougies or len(bougies) < 60:
        print(f"{sym:<10} | pas de donnees")
        continue
    row = f"{sym:<10}"
    for s in SEUILS:
        try:
            stats = simuler(bougies, make_rsi(s))
            if not stats:
                row += " | KO"
                continue
            n = stats.get("trades", 0)
            pnl = stats.get("retour_pct", 0)
            g = stats.get("gagnes", 0)
            p = stats.get("perdus", 0)
            win = stats.get("win_rate", 0)
            row += f" | {n:>3}t {pnl:>+6.1f}% {win:>4.0f}%"
            tot[s][0] += n; tot[s][1] += pnl; tot[s][2] += g; tot[s][3] += p
        except Exception as e:
            row += f" | err"
    print(row)

print("-" * 90)
print("TOTAL (10 cryptos):")
for s in SEUILS:
    t, pnl, g, p = tot[s]
    win = (100*g/t) if t else 0
    print(f"  RSI<{s:<2}: {t:>4} trades, PnL cumul {pnl:>+7.1f}%, win% {win:>4.0f}%  (g={g} p={p})")

print("=" * 90)
print("LECTURE:")
print("  Plus le seuil est haut, plus de trades (entrees moins profondes)")
print("  Trade-off: plus de trades vs qualite (win% / PnL)")
print("  -> On cherche le seuil qui maximise le PnL total SANS effondrer win%")
print("=" * 90)
