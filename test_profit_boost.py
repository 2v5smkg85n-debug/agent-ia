#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_profit_boost.py - valide les 4 leviers profit."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import paper_trading
importlib.reload(paper_trading)

ok = True

# === Lever 1: durees + partial TP ===
assert paper_trading.DUREE_PETIT_GAIN == 180, f"DUREE_PETIT_GAIN={paper_trading.DUREE_PETIT_GAIN}"
assert paper_trading.DUREE_GAIN_PROGRESS == 240, f"DUREE_GAIN_PROGRESS={paper_trading.DUREE_GAIN_PROGRESS}"
assert paper_trading.DUREE_GAGNANT_MAX == 360, f"DUREE_GAGNANT_MAX={paper_trading.DUREE_GAGNANT_MAX}"
assert paper_trading.PARTIAL_TP_SEUIL == 0.8, f"PARTIAL_TP_SEUIL={paper_trading.PARTIAL_TP_SEUIL}"
print(f"OK Lever1: DUREE petit/progress/gagnant = {paper_trading.DUREE_PETIT_GAIN}/{paper_trading.DUREE_GAIN_PROGRESS}/{paper_trading.DUREE_GAGNANT_MAX}, partial TP {paper_trading.PARTIAL_TP_SEUIL}")

# === Lever 2: conviction multipliers ===
# on appelle _conviction_mult avec un signal dont la strat est "élite" (mock classement)
cs = {"ARBUSDT": {"strategies": [{"strategie": "EliteStrat", "live_n": 10, "live_wr": 80, "live_pnl": 5.0}]}}
m, r = paper_trading._conviction_mult({"symbole": "ARBUSDT", "strategie": "EliteStrat", "nom": "EliteStrat"}, cs)
assert m == 3.0, f"élite mult={m} (attendu 3.0)"
print(f"OK Lever2: conviction élite x{m} ({r})")

cs2 = {"X": {"strategies": [{"strategie": "S", "live_n": 6, "live_wr": 72, "live_pnl": 1.0}]}}
m2, _ = paper_trading._conviction_mult({"symbole": "X", "strategie": "S", "nom": "S"}, cs2)
assert m2 == 2.5, f"éprouvé mult={m2} (attendu 2.5)"
print(f"OK Lever2: conviction éprouvé x{m2}")

# === Lever 4: TP ===
assert paper_trading.TAKE_PROFIT_PCT == 2.0, f"TP={paper_trading.TAKE_PROFIT_PCT}"
print(f"OK Lever4: TAKE_PROFIT_PCT = {paper_trading.TAKE_PROFIT_PCT} (EXTEND crypto reste {paper_trading.EXTEND_TP_PCT})")

# === Lever 3: nouveaux actifs ===
nouveaux = ["DOGEUSDT", "AVAXUSDT", "LINKUSDT", "OPUSDT", "INJUSDT", "NEARUSDT"]
for s in nouveaux:
    assert s in paper_trading.MARCHES_PAPER, f"{s} absent de MARCHES_PAPER"
    assert paper_trading.MARCHES_PAPER[s]["source"] == "binance", f"{s} source != binance"
    assert s in paper_trading.EXTEND_CRYPTOS, f"{s} absent de EXTEND_CRYPTOS"
print(f"OK Lever3: {len(nouveaux)} nouveaux actifs dans MARCHES_PAPER + EXTEND_CRYPTOS")
print(f"  Total actifs MARCHES_PAPER: {len(paper_trading.MARCHES_PAPER)}")

print("\n=== TOUS LES LEVIERS PROFIT VALIDÉS ===")
