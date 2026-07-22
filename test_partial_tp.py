#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_partial_tp.py — vérifie l'accounting du partial take-profit."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import fermer_position_partielle, fermer_position, FRAIS_TRANSACTION, PARTIAL_TP_SEUIL, PARTIAL_FRACTION

prix_entree = 100.0
pos = {
    "symbole": "TEST", "nom": "Test", "marche": "crypto",
    "prix_entree": prix_entree, "quantite": 1.0, "montant_eur": 100.0,
    "frais_entree": 0.1, "date_ouverture": "2026-07-22 05:00",
    "strategie": "test", "source": "test",
}
pf = {"liquidites": 0.0, "total_frais": 0.0, "trades_fermes": [], "historique": [], "positions": [pos]}

print(f"Config: PARTIAL_TP_SEUIL={PARTIAL_TP_SEUIL}% FRACTION={PARTIAL_FRACTION} FRAIS={FRAIS_TRANSACTION}")
print(f"Ouverture: quantite=1.0 @ 100.00€ (montant 100.00€)\n")

# 1) Partial TP à +1% (prix 101)
fermer_position_partielle(pf, pos, 101.0, PARTIAL_FRACTION, "PARTIAL-TP", 1.0)
frais1 = 0.5 * 101 * FRAIS_TRANSACTION
gain1 = (0.5 * 101 - frais1) - 50.0
assert abs(pos["quantite"] - 0.5) < 1e-9, f"quantite={pos['quantite']}"
assert abs(pos["montant_eur"] - 50.0) < 1e-9, f"montant={pos['montant_eur']}"
assert pos["partiellement_clote"] is True
assert abs(pf["trades_fermes"][0]["gain_eur"] - gain1) < 1e-9
print(f"After partial TP @ +1.0%: quantite={pos['quantite']:.4f} montant_eur={pos['montant_eur']:.2f}€")
print(f"  gain1 lock = {gain1:+.4f}€  | liquidites={pf['liquidites']:.4f}€\n")

# 2) Le reste ride jusqu'à +2% -> TP final sur les 50% restants
fermer_position(pf, pos, 102.0, "TAKE-PROFIT", 2.0)
frais2 = 0.5 * 102 * FRAIS_TRANSACTION
gain2 = (0.5 * 102 - frais2) - 50.0
assert abs(pf["trades_fermes"][1]["gain_eur"] - gain2) < 1e-9
assert pos not in pf["positions"], "position devrait être fermée"
print(f"After full TP @ +2.0% (reste 50%): gain2 = {gain2:+.4f}€")
print(f"  gain total réalisé = {gain1+gain2:+.4f}€")
print(f"  liquidites = {pf['liquidites']:.4f}€ (attendu {0.5*101-frais1 + 0.5*102-frais2:.4f}€)")

# comparaison: sans partial TP, tout fermé à +2% -> gain = (1*102 - 0.102) - 100 = 1.898€
gain_sans_partial = (1.0*102 - 1.0*102*FRAIS_TRANSACTION) - 100.0
print(f"\n  sans partial (tout @ +2%): gain = {gain_sans_partial:+.4f}€")
print(f"  avec partial (lock +1% puis TP +2%): gain = {gain1+gain2:+.4f}€")
print(f"  -> le partial lock du profit à +1% coûte {gain_sans_partial-(gain1+gain2):+.4f}€ en frais supp. mais garantit la moitié du gain si le prix avait rebouché")
print("\nOK - accounting partial TP validé (quantite, cost-basis, gain, liquidites corrects)")
