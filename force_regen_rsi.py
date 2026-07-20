#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""force_regen_rsi.py — Supprime les entrees RSI Mean Reversion de
backtests_horaires.json pour forcer le recalcul avec le seuil <35."""
import os, json

DOSSIER = os.path.dirname(os.path.abspath("paper_trading.py")) or "."
f = os.path.join(DOSSIER, "backtests_horaires.json")
if not os.path.exists(f):
    print(f"absent: {f}")
    raise SystemExit(1)

data = json.load(open(f, encoding="utf-8"))
avant = len(data)
# Garde tout sauf RSI Mean Reversion
reste = [r for r in data if r.get("strategie") != "RSI Mean Reversion"]
supp = avant - len(reste)
json.dump(reste, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"OK {f}: {supp} entrees RSI supprimees ({avant} -> {len(reste)})")
print("Maintenant relance: python -u backtest_horaires.py crypto")
print("RSI sera recalcule avec seuil <35 -> classement mis a jour")
