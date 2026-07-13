#!/usr/bin/env python3
"""Dump complet des structures cles pour le rapport de performance."""
import json

print("=" * 60)
print("TRADES FERMES (paper trading live)")
print("=" * 60)
pt = json.load(open("paper_trading.json"))
tf = pt.get("trades_fermes", [])
print(f"Nombre: {len(tf)}")
if tf:
    print("Sample complet [0]:")
    print(json.dumps(tf[0], indent=2, ensure_ascii=False, default=str)[:600])
    if len(tf) > 1:
        print("Sample [1]:")
        print(json.dumps(tf[1], indent=2, ensure_ascii=False, default=str)[:600])

print()
print("=" * 60)
print("BACKTEST PRO [0] complet")
print("=" * 60)
bp = json.load(open("backtests_pro.json"))
print(json.dumps(bp[0], indent=2, ensure_ascii=False, default=str)[:800])

print()
print("=" * 60)
print("STATS MARCHES (complet)")
print("=" * 60)
sm = json.load(open("stats_marches.json"))
print(json.dumps(sm, indent=2, ensure_ascii=False, default=str)[:800])

print()
print("=" * 60)
print("ML PERFORMANCES (BTCUSDT + AAPL)")
print("=" * 60)
ml = json.load(open("ml_performances.json"))
for k in ("BTCUSDT", "AAPL"):
    if k in ml:
        print(f"--- {k}:")
        print(json.dumps(ml[k], indent=2, ensure_ascii=False, default=str)[:500])
