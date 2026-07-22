#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sortie_temps.py — améliore la sortie par durée.

1) GAGNANT PROTÉGÉ respire: si breakeven armé (variation >= BREAKEVEN_SEUIL),
   la sortie temps passe de 90min à DUREE_GAGNANT_MAX (4h). Le trade ne peut
   plus perdre (SL au breakeven) -> on le laisse atteindre partial TP / TP / trailing.
2) TIME-STOP STALE: position sous le seuil de gain depuis STALE_DUREE_MAX (3h)
   -> ferme pour libérer le capital (fixe le piège EURUSD bloqué à 0%).

Toggle: EXIT_AVANCE=0 désactive la respiration (revert 90min).
Idempotent: skip si DUREE_GAGNANT_MAX déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: constantes ---
if "DUREE_GAGNANT_MAX" not in src:
    src = src.replace(
        "SEUIL_BENEFICE_MIN = 0.30       # 0.30% : couvre les 0.2% de frais + 0.1% de marge nette",
        "SEUIL_BENEFICE_MIN = 0.30       # 0.30% : couvre les 0.2% de frais + 0.1% de marge nette\n"
        "DUREE_GAGNANT_MAX = 240         # gagnant protégé (breakeven armé): respire jusqu'à 4h pour atteindre partial/TP/trailing\n"
        "STALE_DUREE_MAX = 180           # position sous seuil depuis 3h -> time-stop, libère le capital",
    )
    edits += 1
    print("[paper] edit1: constantes DUREE_GAGNANT_MAX + STALE_DUREE_MAX")

# --- Edit 2: logique sortie temps (respiration + stale) ---
ancien = (
    '                # EXTEND: cap duree plus long (8h) pour laisser le TP etendu se realiser\n'
    '                duree_min = EXTEND_DUREE_MAX if extend_actif else SORTIE_DUREE_MIN\n'
    '                seuil_min = EXTEND_SEUIL if extend_actif else SEUIL_BENEFICE_MIN\n'
    '                if age_min >= duree_min and variation >= seuil_min:\n'
    '                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))'
)
nouveau = (
    '                # EXTEND: cap duree plus long (8h) pour laisser le TP etendu se realiser\n'
    '                duree_min = EXTEND_DUREE_MAX if extend_actif else SORTIE_DUREE_MIN\n'
    '                seuil_min = EXTEND_SEUIL if extend_actif else SEUIL_BENEFICE_MIN\n'
    '                # Gagnant protégé (breakeven armé): respire jusqu à DUREE_GAGNANT_MAX\n'
    '                # pour atteindre partial TP / TP / trailing. Le SL est au breakeven -> pas de risque.\n'
    '                if os.getenv("EXIT_AVANCE", "1") != "0" and variation >= BREAKEVEN_SEUIL:\n'
    '                    duree_min = max(duree_min, DUREE_GAGNANT_MAX)\n'
    '                # TIME-STOP STALE: position sous seuil depuis trop longtemps -> libère le capital\n'
    '                # (fixe les positions bloquées plates, ex EURUSD à 0% qui n atteint jamais +0.30%)\n'
    '                if age_min >= STALE_DUREE_MAX and variation < seuil_min:\n'
    '                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS-stale ({variation:+.2f}%)", variation))\n'
    '                elif age_min >= duree_min and variation >= seuil_min:\n'
    '                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))'
)
if ancien in src and "TEMPS-stale" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] edit2: respiration gagnant + time-stop stale")

open(P, "w").write(src)
print(f"\n=== SORTIE TEMPS AMÉLIORÉE ===  ({edits} edits)")
print(f"Gagnant protégé respire jusqu'à {240}min (4h) | Stale time-stop à {180}min (3h)")
print("Toggle EXIT_AVANCE=0 désactive la respiration (revient à 90min)")
