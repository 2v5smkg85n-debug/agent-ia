#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch signaux_gagnants.py: ajoute le filtre walk-forward (anti-surapprentissage).
Idempotent: n'insère qu'une seule fois. Sans effet si wf_precision absent (sécurisé).

À lancer UNE FOIS après walk_forward.py.
"""
import os

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signaux_gagnants.py")

MARQUEUR = "# WF-FILTER-INSTALLE"

BLOC = '''        if r.get("drawdown_max", 99) > DRAWDOWN_MAX_ACCEPTABLE:
            continue  # trop risque
        # Walk-forward: ignore les stratégies non-robustes (anti-surapprentissage)
        # Uniquement si wf_precision a été mesurée (sinon on garde la stratégie)
        # WF-FILTER-INSTALLE
        wf = r.get("wf_precision")
        if wf is not None and wf < 50.0:
            continue  # stratégie surajustée — pas fiable out-of-sample'''

ANCIEN = '''        if r.get("drawdown_max", 99) > DRAWDOWN_MAX_ACCEPTABLE:
            continue  # trop risque'''


def main():
    if not os.path.exists(FICHIER):
        print(f"ERREUR: {FICHIER} introuvable")
        return
    with open(FICHIER, "r", encoding="utf-8") as f:
        src = f.read()

    if MARQUEUR in src:
        print("Filtre walk-forward DÉJÀ installé. Rien à faire.")
        return

    if ANCIEN not in src:
        print("ERREUR: ligne de filtre drawdown introuvable. signaux_gagnants.py modifié ?")
        print("  Cherche: 'if r.get(\"drawdown_max\", 99) > DRAWDOWN_MAX_ACCEPTABLE:'")
        return

    nouveau = src.replace(ANCIEN, BLOC, 1)
    # backup
    bak = FICHIER + ".bak_wf"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(src)
    with open(FICHIER, "w", encoding="utf-8") as f:
        f.write(nouveau)
    print(f"OK: filtre walk-forward installé dans signaux_gagnants.py")
    print(f"Backup: {bak}")
    print(f"\nEffet: les stratégies avec wf_precision < 50% sont ignorées en live.")
    print(f"Sécurisé: si wf_precision absent (stratégies phase4), la stratégie est gardée.")


if __name__ == "__main__":
    main()
