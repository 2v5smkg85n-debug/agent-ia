#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_moteur_midcaps.py — Ajoute les 5 mid-caps a ACTIFS["crypto"] dans
backtest_moteur.py (source utilisee par backtest_horaires.py qui genere
backtests_horaires.json, le fichier lu par le classement live)."""
F = "backtest_moteur.py"
s = open(F, encoding="utf-8").read()

old = '    "crypto":   ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],'
new = ('    "crypto":   ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",\n'
       '                  "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"],')
assert old in s, "ligne ACTIFS crypto introuvable"
s = s.replace(old, new, 1)
open(F, "w", encoding="utf-8").write(s)
print("OK backtest_moteur.py: +5 mid-caps dans ACTIFS['crypto']")
print("  LDOUSDT, AAVEUSDT, UNIUSDT, PENDLEUSDT, ARBUSDT")
