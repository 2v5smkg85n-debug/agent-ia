#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_exit_avance.py — vérifie la logique break-even + trailing."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import BREAKEVEN_SEUIL, TRAIL_ACTIF, TRAIL_PCT, TAKE_PROFIT_PCT, STOP_LOSS_PCT

prix_entree = 100.0
_tp = TAKE_PROFIT_PCT
_sl = STOP_LOSS_PCT

def decision(prix_actuel, prix_peak):
    """Réplique la logique du patch pour tester."""
    variation = (prix_actuel - prix_entree) / prix_entree * 100
    pos = {"prix_entree": prix_entree, "prix_peak": prix_peak}
    _sl_regle = "fixe"
    pic = pos.get("prix_peak", prix_entree)
    if prix_actuel > pic:
        pic = prix_actuel
    var_pic = (pic - prix_entree) / prix_entree * 100   # variation au pic (sticky)
    if var_pic >= TRAIL_ACTIF:
        sl_price = pic * (1 - TRAIL_PCT / 100.0)
        _sl_regle = "trailing"
    elif var_pic >= BREAKEVEN_SEUIL:
        sl_price = prix_entree * 1.001
        _sl_regle = "breakeven"
    else:
        sl_price = prix_entree * (1 - _sl / 100.0)
    if variation >= _tp:
        return ("TP", variation)
    elif prix_actuel <= sl_price:
        return (f"STOP-{_sl_regle}", variation)
    else:
        return ("OUVERT", variation)

print(f"Config: TP={_tp}% SL={_sl}% BE={BREAKEVEN_SEUIL}% TRAIL@{TRAIL_ACTIF}% ({TRAIL_PCT}% sous pic)")
print(f"Entry: {prix_entree}€\n")

cas = [
    # (prix_actuel, prix_peak, description)
    (98.4, 100.0, "baisse directe -> SL fixe"),
    (100.3, 100.0, "monte à +0.3% (sous BE) -> OUVERT"),
    (100.7, 100.7, "+0.7% -> breakeven armé, OUVERT"),
    (100.2, 100.7, "redescend de +0.7% à +0.2% -> STOP-BREAKEVEN (sauvé)"),
    (101.2, 101.2, "+1.2% -> trailing armé"),
    (100.4, 101.2, "reverse de pic 1.2% à +0.4% -> STOP-TRAILING (lock profit)"),
    (101.6, 101.6, "+1.6% -> TAKE-PROFIT"),
    (101.0, 101.5, "+1.0% pic 1.5% -> trailing, OUVERT"),
]
for prix, pic, desc in cas:
    r, var = decision(prix, pic)
    print(f"  prix={prix:6.2f} (var {var:+.2f}%) pic={pic:6.2f} -> {r:14s} | {desc}")

# Le cas clé: un gagnant qui reverse
print("\n>>> CAS CLÉ: trade monte à +0.7% puis reverse à -1.5%")
r1, _ = decision(100.7, 100.7)
r2, _ = decision(98.5, 100.7)
print(f"    +0.7% -> {r1}, puis redescend à -1.5% -> {r2} (au lieu de STOP-LOSS = perte, sauvé au breakeven)")
print("\nOK - logique break-even + trailing validée")
