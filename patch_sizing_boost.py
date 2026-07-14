#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch: augmente le sizing (Half Kelly + cap actif 15%)."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "gestion_risque.py")
MARKER = "SIZING-BOOST-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch sizing-boost deja installe.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.sizing")
print("[i] Backup: gestion_risque.py.bak.sizing")

# 1. Quarter Kelly (0.25) -> Half Kelly (0.50)
old1 = "KELLY_FRACTION = 0.25        # Quarter Kelly (conservateur). Passer a 0.50 apres 30 trades live gagnants"
new1 = "KELLY_FRACTION = 0.50        # Half Kelly (plus agressif) - " + MARKER
if old1 not in code:
    print("[ECHEC] ancrage KELLY_FRACTION introuvable")
    raise SystemExit(1)
code = code.replace(old1, new1, 1)

# 2. Cap par actif 10% -> 15%
old2 = "CAP_ACTIF = 0.10             # max 10% du capital sur un seul actif"
new2 = "CAP_ACTIF = 0.15             # max 15% du capital sur un seul actif"
if old2 not in code:
    print("[ECHEC] ancrage CAP_ACTIF introuvable")
    raise SystemExit(1)
code = code.replace(old2, new2, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Sizing booste: KELLY_FRACTION 0.25->0.50 (Half Kelly), CAP_ACTIF 0.10->0.15")
print("     Les positions seront ~2x plus grandes (drawdown aussi).")
