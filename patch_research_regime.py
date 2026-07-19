#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_research_regime.py — Fix regime_watch: extraire juste le label REGIME.

regime_actif() retourne un dict avec TREND_STRENGTH/SMA qui changent chaque heure.
Comparaison string du dict entier -> faux shift chaque cycle. Fix: extraire REGIME.
"""
import os
D = os.getcwd()
F = os.path.join(D, "research_loop.py")
src = open(F, encoding="utf-8").read()

old = '''    regimes = {}
    for sym in CRYPTO:
        try:
            r = regime_actif(sym)
            regimes[sym] = str(r).upper()
        except Exception:
            regimes[sym] = "?"'''

new = '''    regimes = {}
    for sym in CRYPTO:
        try:
            r = regime_actif(sym)
            # regime_actif retourne un dict avec TREND_STRENGTH/SMA qui changent
            # chaque heure -> extraire juste le label REGIME pour eviter les faux
            # shifts (QUIET/TREND/RANGE/VOL change rarement = vrai signal).
            if isinstance(r, dict):
                regimes[sym] = str(r.get("REGIME", r.get("regime", "?"))).upper()
            else:
                regimes[sym] = str(r).upper()
        except Exception:
            regimes[sym] = "?"'''

assert old in src, "ancrage regime_watch introuvable"
src = src.replace(old, new, 1)
open(F, "w", encoding="utf-8").write(src)
import py_compile
py_compile.compile(F, doraise=True)
print("✅ research_loop.py: regime_watch fixe (extrait juste le label REGIME)")
print("✅ compile OK")
