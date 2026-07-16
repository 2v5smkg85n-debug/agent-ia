#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trouve les actifs avec stratégies gagnantes et vérifie s'ils sont dans MARCHES_PAPER (live)."""
import json, os

DOSSIER = os.getcwd()
fichiers = ['backtests_reels.json', 'backtests_pro.json',
            'backtests_phase4.json', 'backtests_horaires.json']
actifs = {}
for f in fichiers:
    p = os.path.join(DOSSIER, f)
    if not os.path.exists(p):
        continue
    try:
        data = json.load(open(p, encoding='utf-8'))
    except Exception:
        continue
    for r in data:
        if isinstance(r, dict) and r.get('verdict') == 'GAGNANTE':
            a = r.get('actif', '?')
            actifs[a] = actifs.get(a, 0) + 1

print("=" * 55)
print("ACTIFS AVEC STRATÉGIES GAGNANTES (fichiers backtest)")
print("=" * 55)
for a, n in sorted(actifs.items(), key=lambda x: -x[1]):
    print(f"  {a}: {n} stratégies")

print()
print("=" * 55)
print("PRÉSENTS DANS MARCHES_PAPER (live) ?")
print("=" * 55)
src = open(os.path.join(DOSSIER, 'paper_trading.py'), encoding='utf-8').read()
manquants = []
for a in sorted(actifs):
    present = ('"%s"' % a) in src
    mark = "✅ live" if present else "❌ MANQUE"
    print(f"  {a}: {mark}")
    if not present:
        manquants.append(a)

print()
if manquants:
    print("=" * 55)
    print(f"À AJOUTER À MARCHES_PAPER ({len(manquants)}):")
    print("  " + ", ".join(manquants))
    print("=" * 55)
else:
    print("Tous les actifs avec stratégies gagnantes sont déjà en live.")
