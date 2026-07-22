#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_push_profit.py — pousse le conviction sizing pour viser plus de bénéfices.

Monte les multiplicateurs de conviction (justifié par l'exit stack qui protège
les gagnants via breakeven/partial/trailing):
  - élite (>=8t, >=75% win, pnl>0):     x2.5  (nouveau tier)
  - éprouvé (>=5t, >=70% win, pnl>0):    x2.0  (était x1.5)
  - solide (>=3t, >=60% win, pnl>0):     x1.5  (était x1.25)
  - faible (>=3t, pnl<0):                x0.5  (inchangé)
  - neuf/neutre:                         x1.0  (inchangé)

=> Un gagnant prouvé rapporte 2x plus (éprouvé) à 2.5x (élite). Le breakeven
   garantit qu'un gagnant ne redevient pas une perte, donc l'amplification est
   justifiée. La fuite reste le SL avant breakeven (les stratégies prouvées à
   70%+ win ont peu de chance de le toucher).

Idempotent: skip si 'élite' déjà présent dans _conviction_mult.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

ancien = (
    '            if _n >= 5 and _wr >= 70 and _pnl > 0:\n'
    '                return 1.5, f"éprouvé ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"\n'
    '            if _n >= 3 and _wr >= 60 and _pnl > 0:\n'
    '                return 1.25, f"solide ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"'
)
nouveau = (
    '            if _n >= 8 and _wr >= 75 and _pnl > 0:\n'
    '                return 2.5, f"élite ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"\n'
    '            if _n >= 5 and _wr >= 70 and _pnl > 0:\n'
    '                return 2.0, f"éprouvé ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"\n'
    '            if _n >= 3 and _wr >= 60 and _pnl > 0:\n'
    '                return 1.5, f"solide ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"'
)
if ancien in src and "élite" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] conviction: élite x2.5 + éprouvé x2.0 + solide x1.5")
else:
    print("[paper] ancre introuvable ou déjà appliqué")

open(P, "w").write(src)
print(f"\n=== CONVICTION PUSH APPLIQUÉ ===  ({edits} edits)")
print("élite x2.5 | éprouvé x2.0 | solide x1.5 | faible x0.5 | neuf x1.0")
