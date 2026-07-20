#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_midcaps.py — Backteste les 4 strategies sur les mid-caps Revolut
en hausse (LDO, AAVE, UNI, PENDLE, BCH, ARB) vs les 5 majors actuels.

TP=2.0%, SL=2.5%, max 48 barres (1h). Identifie quelles strategies marchent
sur quels mid-caps avant ajout au mapping Revolut X (argent reel).
"""
import os, sys, logging
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING)

from signaux_gagnants import signal_strategie, calculer_donnees
from indicateurs import historique_ohlcv

TP = 2.0; SL = 2.5; MAX_BARS = 48; DEBUT = 60
STRATEGIES = ["RSI Mean Reversion", "MACD Momentum", "SMA Crossover", "Bollinger Breakout"]
MIDCAPS = ["LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "BCHUSDT", "ARBUSDT"]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def backtest(symbole, strategie, bougies):
    closes = [b["cloture"] for b in bougies]
    if len(closes) < DEBUT + MAX_BARS + 10:
        return None
    trades = []; ouvert = None
    for i in range(DEBUT, len(closes)):
        px = closes[i]
        if ouvert:
            var = (px - ouvert["px"]) / ouvert["px"] * 100
            age = i - ouvert["bar"]
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                trades.append(var)
                ouvert = None
            elif age >= MAX_BARS:
                trades.append(var)
                ouvert = None
        if ouvert:
            continue
        try:
            donnees = calculer_donnees(closes[:i+1])
            if signal_strategie(strategie, donnees) == "ACHAT":
                ouvert = {"bar": i, "px": px}
        except Exception:
            pass
    if ouvert:
        trades.append((closes[-1] - ouvert["px"]) / ouvert["px"] * 100)
    if not trades:
        return {"n": 0, "pnl": 0, "wr": 0, "avg": 0}
    n = len(trades); wins = sum(1 for t in trades if t > 0)
    return {"n": n, "pnl": sum(trades), "wr": 100*wins/n, "avg": sum(trades)/n}


print("=" * 92)
print("BACKTEST MID-CAPS REVOLUT vs MAJORS (TP2%/SL2.5%/48bar 1h)")
print("=" * 92)

for label, syms in [("MID-CAPS (Revolut, en hausse)", MIDCAPS), ("MAJORS (actuels)", MAJORS)]:
    print(f"\n=== {label} ===")
    print(f"{'Symbole':<10}{'Strategie':<22}{'N':>5}{'Win%':>6}{'PnL%':>8}{'Avg%':>7}  Verdict")
    print("-" * 92)
    best = []
    for sym in syms:
        try:
            bougies = historique_ohlcv(sym, "1h", 500)
        except Exception as e:
            print(f"{sym:<10} fetch KO: {e}")
            continue
        if not bougies or len(bougies) < 100:
            print(f"{sym:<10} historique insuffisant")
            continue
        for strat in STRATEGIES:
            r = backtest(sym, strat, bougies)
            if r is None:
                continue
            v = "OK" if r["pnl"] > 0 and r["n"] >= 3 else ("~" if r["n"] < 3 else "X")
            print(f"{sym:<10}{strat:<22}{r['n']:>5}{r['wr']:>5.0f}%{r['pnl']:>8.1f}{r['avg']:>7.2f}  {v}")
            if r["pnl"] > 0 and r["n"] >= 3:
                best.append((sym, strat, r["pnl"], r["wr"], r["n"]))
    print(f"\n  --> Gagnants (PnL>0, n>=3): {len(best)}")
    for sym, strat, pnl, wr, n in sorted(best, key=lambda x: -x[2])[:5]:
        print(f"      {sym:<10} {strat:<22} PnL {pnl:+.1f}% win {wr:.0f}% n={n}")

print("\n" + "=" * 92)
print("CONCLUSION:")
print("- Si les mid-caps ont des gagnants -> candidats pour le mapping Revolut X")
print("- Regime TREND sur ces mid-caps -> les strategies trend (MACD/SMA/Bollinger)")
print("  pourraient mieux y marcher que sur les majors en QUIET")
print("=" * 92)
