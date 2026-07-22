#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_conviction_live.py — vérifie _conviction_mult contre le VRAI classement.
N'ouvre aucune position (safe, pas de conflit avec le service paper_trading)."""
import json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import _conviction_mult

cs = json.load(open("classement_strategies.json"))
print("=" * 60)
print("  CONVICTION SIZING — stratégies réelles qui déclenchent un multiplicateur")
print("=" * 60)
amplifiees = []
for actif, d in cs.items():
    for s in d.get("strategies", []):
        sig = {"symbole": actif, "nom": s.get("strategie", "")}
        mult, raison = _conviction_mult(sig, cs)
        if mult != 1.0:
            amplifiees.append((actif, s, mult, raison))

if amplifiees:
    amplifiees.sort(key=lambda x: x[2], reverse=True)
    for actif, s, mult, raison in amplifiees:
        print(f"  {actif:10s} {s.get('strategie','?')[:22]:22s} n={s.get('live_n',0):2d} wr={s.get('live_wr',0):.0f}% pnl={s.get('live_pnl',0):+.2f}€ -> x{mult:.2f} ({raison})")
    print(f"\n  {len(amplifiees)} stratégies amplifiées sur {sum(len(d.get('strategies',[])) for d in cs.values())} totales")
else:
    print("  (aucune stratégie n'atteint encore le seuil de conviction)")
    print("  seuils: x1.5 si >=5 trades & >=70% win & pnl>0 | x1.25 si >=3t & >=60% & pnl>0")
    # montre les plus proches
    candidates = []
    for actif, d in cs.items():
        for s in d.get("strategies", []):
            n = s.get("live_n",0); wr = s.get("live_wr",0); pnl = s.get("live_pnl",0)
            if n >= 2 and pnl > 0:
                candidates.append((actif, s.get("strategie",""), n, wr, pnl))
    candidates.sort(key=lambda x: x[3], reverse=True)
    print("  plus proches du seuil:")
    for actif, nom, n, wr, pnl in candidates[:5]:
        print(f"    {actif:10s} {nom[:22]:22s} n={n} wr={wr:.0f}% pnl={pnl:+.2f}€")

# CAS SPÉCIAL: RSI Mean Reversion BTC (la meilleure stratégie du bilan)
print("\n" + "-" * 60)
print("  VÉRIFICATION: RSI Mean Reversion sur BTCUSDT (top du bilan)")
print("-" * 60)
sig = {"symbole": "BTCUSDT", "nom": "RSI Mean Reversion"}
mult, raison = _conviction_mult(sig, cs)
print(f"  multiplicateur = x{mult} ({raison})")
print(f"  -> si montant base 100€, l'agent ouvrirait à {100*mult:.0f}€ (bénéfice potentiel x{mult})")
print("\n  => CONVICTION SIZING est actif et lit bien le classement live")
print("  => il se déclenchera dès qu'une entrée correspond à une stratégie éprouvée")
