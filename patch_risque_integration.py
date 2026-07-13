#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PATCH INTÉGRATION RISQUE (Phase 7).
Corrige le bug: les signaux signaux_gagnants n'avaient pas de champ 'strategie',
donc gestion_risque.calculer_taille ne trouvait pas l'edge -> skip des trades.

Applique 2 corrections idempotentes:
  1. signaux_gagnants.py: ajoute 'strategie' + 'backtest_stats' au signal
  2. paper_trading.py: passe backtest_stats à calculer_taille (4e arg)

À lancer UNE FOIS. Backup automatique.
"""
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def patch_fichier(fichier, ancien, nouveau, marqueur):
    chemin = os.path.join(DOSSIER, fichier)
    if not os.path.exists(chemin):
        print(f"ERREUR: {fichier} introuvable")
        return False
    with open(chemin, "r", encoding="utf-8") as f:
        src = f.read()
    if marqueur in src:
        print(f"  {fichier}: déjà patché")
        return True
    if ancien not in src:
        print(f"  {fichier}: ancrage introuvable — fichier modifié ?")
        return False
    # backup
    bak = chemin + ".bak_ri"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(src)
    nouveau_src = src.replace(ancien, nouveau, 1)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(nouveau_src)
    print(f"  {fichier}: patch appliqué (backup {os.path.basename(bak)})")
    return True


def main():
    print("=" * 60)
    print("PATCH INTÉGRATION RISQUE (Phase 7)")
    print("=" * 60)

    # 1. signaux_gagnants.py: ajoute strategie + backtest_stats au signal
    print("\n1. signaux_gagnants.py — ajout champ strategie + backtest_stats")
    ancien1 = '''                "source": "backtest-gagnant",
                "score": 2,'''
    nouveau1 = '''                "source": "backtest-gagnant",
                "score": 2,
                "strategie": meilleure_strat.get("strategie", ""),
                "backtest_stats": meilleure_strat,'''
    patch_fichier("signaux_gagnants.py", ancien1, nouveau1, "backtest_stats")

    # 2. paper_trading.py: passe backtest_stats à calculer_taille
    print("\n2. paper_trading.py — passage backtest_stats à calculer_taille")
    ancien2 = "        montant, raison = calculer_taille(pf, signal, prix_actuel)"
    nouveau2 = "        montant, raison = calculer_taille(pf, signal, prix_actuel, signal.get(\"backtest_stats\"))"
    patch_fichier("paper_trading.py", ancien2, nouveau2, "signal.get(\"backtest_stats\")")

    print("\n" + "=" * 60)
    print("Effet: les signaux gagnants portent maintenant leurs stats backtest.")
    print("gestion_risque appliquera Kelly + vol + corrélation + caps CORRECTEMENT.")
    print("\nProchaine étape: redémarre paper_trading.service + tick de test")
    print("  sudo systemctl restart paper_trading.service")
    print("  python paper_trading.py tick 2>&1 | grep -iE 'SIZING|SKIP|ACHAT'")


if __name__ == "__main__":
    main()
