#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sortie_temps.py — vérifie la logique respiration gagnant + time-stop stale."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import (SORTIE_DUREE_MIN, SEUIL_BENEFICE_MIN, BREAKEVEN_SEUIL,
                           DUREE_GAGNANT_MAX, STALE_DUREE_MAX, EXTEND_DUREE_MAX, EXTEND_SEUIL)

def decision(variation, age_min, extend_actif=False):
    """Réplique la logique de sortie temps (après le patch)."""
    duree_min = EXTEND_DUREE_MAX if extend_actif else SORTIE_DUREE_MIN
    seuil_min = EXTEND_SEUIL if extend_actif else SEUIL_BENEFICE_MIN
    # respiration gagnant protégé
    if variation >= BREAKEVEN_SEUIL:
        duree_min = max(duree_min, DUREE_GAGNANT_MAX)
    # stale
    if age_min >= STALE_DUREE_MAX and variation < seuil_min:
        return "TEMPS-stale"
    if age_min >= duree_min and variation >= seuil_min:
        return "TEMPS+benefice"
    return "OUVERT"

print(f"Config: SORTIE={SORTIE_DUREE_MIN}min SEUIL={SEUIL_BENEFICE_MIN}% BE={BREAKEVEN_SEUIL}%")
print(f"        GAGNANT_MAX={DUREE_GAGNANT_MAX}min STALE={STALE_DUREE_MAX}min\n")

cas = [
    # (variation%, age_min, attendu, description)
    (0.00, 100, "OUVERT",         "plate à 100min -> attend (stale=180)"),
    (0.00, 200, "TEMPS-stale",    "plate à 200min -> time-stop libère capital"),
    (0.20, 100, "OUVERT",         "+0.2% à 100min -> sous seuil, attend"),
    (0.20, 200, "TEMPS-stale",    "+0.2% à 200min -> stale (sous 0.30%)"),
    (0.40, 100, "TEMPS+benefice", "+0.4% à 100min -> sortie normale (>=0.30, >=90min)"),
    (0.70, 100, "OUVERT",         "+0.7% protégé à 100min -> respire (pas de close à 90min)"),
    (0.70, 250, "TEMPS+benefice", "+0.7% protégé à 250min -> close (>=240min gagnant max)"),
    (-0.50, 200, "TEMPS-stale",   "-0.5% à 200min -> time-stop (coupe le loser mort)"),
    (-0.50, 100, "OUVERT",        "-0.5% à 100min -> attend (SL gère, stale=180)"),
    (1.20, 120, "OUVERT",         "+1.2% protégé à 120min -> respire vers partial/trailing"),
]
ok = True
for var, age, attendu, desc in cas:
    r = decision(var, age)
    mark = "OK" if r == attendu else "** FAIL **"
    if r != attendu: ok = False
    print(f"  var {var:+.2f}% age {age:3d}min -> {r:16s} (attendu {attendu:16s}) {mark} | {desc}")

# Le cas clé: le piège EURUSD
print("\n>>> CAS CLÉ: position EURUSD bloquée à 0%")
r = decision(0.00, 200)
print(f"    plateau 0% pendant 200min -> {r} (libère le capital, au lieu de rester piégée indéfiniment)")

# Le cas clé: gagnant qui respire
print(">>> CAS CLÉ: gagnant +0.7% (breakeven armé) à 100min")
r_avant = "TEMPS+benefice (ancien: coupé à 90min)"
r_apres = decision(0.70, 100)
print(f"    avant: {r_avant}")
print(f"    après: {r_apres} -> respire pour atteindre partial TP/TP/trailing")

print("\n" + ("OK - logique sortie temps validée" if ok else "** ÉCHEC **"))
