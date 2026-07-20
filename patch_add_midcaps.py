#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_add_midcaps.py — Ajoute 5 mid-caps valides (LDO, AAVE, UNI, PENDLE, ARB)
a l'univers de trading + mapping Revolut X (argent reel).

Backtest valide (TP2/SL2.5/48bar 1h, regime TREND):
  LDO  Bollinger +12.1% / MACD +10.4% / SMA +9.7%
  AAVE MACD +13.1% / SMA +5.9%
  UNI  Bollinger +7.2% / SMA +5.1%
  PENDLE Bollinger +6.6% / RSI +6.5%
  ARB  Bollinger +8.0% / MACD +3.8%
BCH exclu (perdant toutes strategies).
"""
import re

MIDCAPS = [
    ("LDOUSDT", "Lido DAO", "LDO-EUR"),
    ("AAVEUSDT", "Aave", "AAVE-EUR"),
    ("UNIUSDT", "Uniswap", "UNI-EUR"),
    ("PENDLEUSDT", "Pendle", "PENDLE-EUR"),
    ("ARBUSDT", "Arbitrum", "ARB-EUR"),
]
SYMS = [m[0] for m in MIDCAPS]

# --- 1. paper_trading.py: MARCHES_PAPER + EXTEND_CRYPTOS ---
F = "paper_trading.py"
s = open(F, encoding="utf-8").read()

# MARCHES_PAPER: inserer apres la ligne XRPUSDT crypto
anchor_xrp = '    "XRPUSDT": {"nom": "XRP", "marche": "crypto", "source": "binance"},\n'
assert anchor_xrp in s, "ligne XRPUSDT introuvable"
ajout_marches = anchor_xrp + "".join(
    f'    "{sym}": {{"nom": "{nom}", "marche": "crypto", "source": "binance"}},\n'
    for sym, nom, _ in MIDCAPS
)
s = s.replace(anchor_xrp, ajout_marches, 1)

# EXTEND_CRYPTOS
old_ext = 'EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}'
new_ext = 'EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", ' + ", ".join(f'"{x}"' for x in SYMS) + '}'
assert old_ext in s, "EXTEND_CRYPTOS introuvable"
s = s.replace(old_ext, new_ext, 1)
open(F, "w", encoding="utf-8").write(s)
print(f"OK paper_trading.py: +{len(SYMS)} mid-caps (MARCHES_PAPER + EXTEND_CRYPTOS)")

# --- 2. backtest_trailing.py: ACTIFS_TEST ---
F = "backtest_trailing.py"
s = open(F, encoding="utf-8").read()
old_act = 'ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]'
new_act = old_act[:-1] + ", " + ", ".join(f'"{x}"' for x in SYMS) + "]"
assert old_act in s, "ACTIFS_TEST introuvable"
s = s.replace(old_act, new_act, 1)
open(F, "w", encoding="utf-8").write(s)
print(f"OK backtest_trailing.py: +{len(SYMS)} mid-caps (ACTIFS_TEST)")

# --- 3. pont_revolut.py: BINANCE_TO_REVOLUTX ---
F = "pont_revolut.py"
s = open(F, encoding="utf-8").read()
anchor_map = '    "XRPUSDT": "XRP-EUR",\n'
assert anchor_map in s, "ligne XRPUSDT mapping introuvable"
ajout_map = anchor_map + "".join(f'    "{sym}": "{rev}",\n' for sym, _, rev in MIDCAPS)
s = s.replace(anchor_map, ajout_map, 1)
open(F, "w", encoding="utf-8").write(s)
print(f"OK pont_revolut.py: +{len(SYMS)} mappings Revolut X (argent reel)")

print(f"\nMid-caps ajoutes: {', '.join(SYMS)}")
print("Prochaine etape: backtest manuel -> confirm_action -> restart services -> commit")
