#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_rsi_seuil_v2.py — Fix: change VRAIMENT le seuil 30->35.
Remplacement ciblé du bloc exact dans strat_rsi_reversion."""
import os

f = "backtest_moteur.py"
src = open(f, encoding="utf-8").read()

old = '''    r = d["rsi"][i]
    if r is None:
        return None
    if r < 30:
        return "ACHAT"'''
new = '''    r = d["rsi"][i]
    if r is None:
        return None
    if r < 35:
        return "ACHAT"'''

if old not in src:
    # peut-etre deja 35 (patch v1 partiel) ou format different
    if "if r < 35:\n        return \"ACHAT\"" in src:
        print("deja patche (seuil deja 35) - rien a faire")
    else:
        print("ERREUR: bloc introuvable. Contenu actuel de strat_rsi_reversion:")
        import re
        m = re.search(r'def strat_rsi_reversion.*?(?=\ndef |\Z)', src, re.DOTALL)
        print(m.group(0) if m else "introuvable")
    raise SystemExit(0 if "if r < 35" in src else 1)

nouv = src.replace(old, new, 1)
open(f, "w", encoding="utf-8").write(nouv)
print("OK backtest_moteur.py: seuil RSI 30 -> 35 (bloc exact remplace)")

# Verification: compte les occurrences de "r < 35" et "r < 30"
print(f"  'if r < 35:' occurrences: {nouv.count('if r < 35:')}")
print(f"  'if r < 30:' occurrences restantes: {nouv.count('if r < 30:')}")
