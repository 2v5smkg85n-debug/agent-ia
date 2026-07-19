#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_signal_live.py — Genere un signal ACHAT live et affiche le dip.

Lance la vraie selection d'entree (generer_signaux_gagnants) sur les prix
live actuels. Montre les ACHAT avec le biais bougies (dip) affiche, et les
'neutre' sinon (normal: gate dip-buying restrictif + regime QUIET).
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

import paper_trading as pt
import signaux_gagnants as sg

print("Recuperation des prix live...")
prix = pt.tous_les_prix()
print(f"  {len(prix)} prix charges")
print(f"  DIP_BUYING_GATE = {getattr(sg, 'DIP_BUYING_GATE', '?')}")
print()
print("=== SELECTION D'ENTREE LIVE (regime gate + classement + dip-buying) ===")
signaux = sg.generer_signaux_gagnants(prix, pt.MARCHES_PAPER)
print()
print(f"=== {len(signaux)} signal(x) ACHAT genere(s) ===")
for s in signaux:
    bs = s.get("backtest_stats", {})
    print(f"  -> {s['symbole']} | {s.get('strategie','?')} | "
          f"dip {bs.get('biais_bougies', 0):+.2f} | "
          f"regime_fit {bs.get('regime_fit',0)} | "
          f"live x{bs.get('live_mult',1.0):.2f}")
if not signaux:
    print("  (aucun ACHAT maintenant: regime QUIET + gate dip-buying restrictif = normal)")
