#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_gate_relax.py — Compare 3 variantes du dip-buying gate.
V1 (actuel): RSI<30 ET biais<0 (bloque bougies haussieres)
V2 (relaxe) : RSI<30 seul (autorise bougie haussiere oversold)
V3 (smart)  : RSI<30 ET (biais<0 OU pattern retournement haussier)
Objectif: plus de trades SANS baisser la qualite."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from indicateurs import historique_ohlcv
from backtest_moteur import simuler, strat_rsi_reversion, CAPITAL_DEPART
from bougies_patterns import analyser_patterns

PATTERNS_HAUSSIER = {"marteau_haussier", "engulfing_haussier", "marubozu_haussier",
                     "etoile_du_matin", "morning_star", "pirole_haussier", "avalement_haussier"}

CRYPTOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]

def _patterns(bougies, i):
    """Patterns sur les 3 dernieres bougies jusqu'a i."""
    window = bougies[max(0, i-2):i+1]
    if len(window) < 3:
        return []
    return set(analyser_patterns(window).get("patterns", []))

def _biais(bougies, i):
    window = bougies[max(0, i-2):i+1]
    if len(window) < 3:
        return 0.0
    return analyser_patterns(window).get("biais", 0.0)

def make_v1(bougies):
    """Gate actuel: RSI<30 ET biais<0."""
    def f(i, d):
        sig = strat_rsi_reversion(i, d)
        if sig != "ACHAT":
            return sig
        if _biais(bougies, i) > 0:
            return None
        return "ACHAT"
    return f

def make_v2(bougies):
    """Relaxe: RSI<30 seul (autorise bougie haussiere oversold)."""
    return strat_rsi_reversion

def make_v3(bougies):
    """Smart: RSI<30 ET (biais<0 OU retournement haussier)."""
    def f(i, d):
        sig = strat_rsi_reversion(i, d)
        if sig != "ACHAT":
            return sig
        biais = _biais(bougies, i)
        if biais > 0:
            # autoriser seulement si pattern de retournement haussier present
            pats = _patterns(bougies, i)
            if not (pats & PATTERNS_HAUSSIER):
                return None
        return "ACHAT"
    return f

print("=" * 80)
print("BACKTEST COMPARATIF DU DIP-BUYING GATE (RSI Mean Reversion, 1h, ~500 bougies)")
print("=" * 80)
print(f"{'ACTIF':<10} | {'V1 trades/PnL/Win%':<26} | {'V2 trades/PnL/Win%':<26} | {'V3 trades/PnL/Win%':<26}")
print("-" * 80)

tot = {"V1": [0,0.0,0,0], "V2": [0,0.0,0,0], "V3": [0,0.0,0,0]}  # trades, pnl, gagnes, perdus

for sym in CRYPTOS:
    bougies = historique_ohlcv(sym, "1h", 500)
    if not bougies or len(bougies) < 60:
        print(f"{sym:<10} | pas de donnees")
        continue
    row = [sym]
    for name, mk in [("V1", make_v1), ("V2", make_v2), ("V3", make_v3)]:
        try:
            stats = simuler(bougies, mk(bougies))
            if not stats:
                row.append("KO")
                continue
            n = stats.get("nb_trades", stats.get("trades", 0))
            pnl = stats.get("pnl_pct", stats.get("rendement", 0))
            g = stats.get("gagnes", 0)
            p = stats.get("perdus", 0)
            win = (100*g/n) if n else 0
            row.append(f"{n:>3}t {pnl:>+6.1f}% {win:>4.0f}%")
            tot[name][0] += n; tot[name][1] += pnl; tot[name][2] += g; tot[name][3] += p
        except Exception as e:
            row.append(f"err:{e}"[:24])
    print(f"{row[0]:<10} | {row[1]:<26} | {row[2]:<26} | {row[3]:<26}")

print("-" * 80)
print("TOTAL (10 cryptos):")
for name in ["V1", "V2", "V3"]:
    t, pnl, g, p = tot[name]
    win = (100*g/t) if t else 0
    print(f"  {name}: {t:>3} trades, PnL cumul {pnl:>+7.1f}%, win% {win:>4.0f}%  (gagnes={g} perdus={p})")

print("=" * 80)
print("LECTURE:")
print("  V1 = gate actuel (bloque bougies haussieres)")
print("  V2 = relaxe totale (autorise toutes entrees oversold)")
print("  V3 = relaxe smart (autorise bougie haussiere si pattern retournement)")
print("  -> Si V2 ou V3 a PLUS de trades ET win% >= V1 => deployer la relaxe")
print("=" * 80)
