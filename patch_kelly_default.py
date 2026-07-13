#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PATCH KELLY DEFAULT (Phase 7).
Corrige: quand profit_factor absent (backtests de backtest_moteur.simuler:
backtests_reels.json, backtests_horaires.json), calculer_taille defaultait
profit_factor=1.0 ce qui donnait un ratio gain/perte trop faible -> Kelly≈0
-> montant_trop_petit -> tous les trades skippés.

Fix: quand profit_factor absent, suppose un payoff ratio de 1.0 (réaliste
car TP/SL symétriques +1.5%/-1.5%). Kelly redevient sensé pour les stratégies
à win_rate élevé.

Idempotent. Backup automatique.
"""
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "gestion_risque.py")

ANCIEN = '''    if backtest_stats:
        wr = backtest_stats.get("win_rate", 0)
        pf_val = backtest_stats.get("profit_factor", 1.0)
        if backtest_stats.get("verdict") != "GAGNANTE":
            return 0.0, "strategie_perdante"
        loss_rate = (100 - wr) / 100 if wr < 100 else 0.01
        ratio = pf_val * loss_rate / (wr / 100) if wr > 0 else 0
    else:'''

NOUVEAU = '''    if backtest_stats:
        wr = backtest_stats.get("win_rate", 0)
        if backtest_stats.get("verdict") != "GAGNANTE":
            return 0.0, "strategie_perdante"
        pf_val = backtest_stats.get("profit_factor")
        if pf_val and pf_val > 0:
            # profit_factor present (backtests_pro): ratio derive precis
            loss_rate = (100 - wr) / 100 if wr < 100 else 0.01
            ratio = pf_val * loss_rate / (wr / 100) if wr > 0 else 0
        else:
            # profit_factor absent (backtest_moteur.simuler): TP/SL symetriques
            # +1.5%/-1.5% -> payoff ratio ~1.0 (conservateur, realiste)
            ratio = 1.0
    else:'''


def main():
    if not os.path.exists(FICHIER):
        print(f"ERREUR: {FICHIER} introuvable")
        return
    with open(FICHIER, "r", encoding="utf-8") as f:
        src = f.read()
    if "payoff ratio ~1.0" in src:
        print("Patch Kelly default DÉJÀ appliqué.")
        return
    if ANCIEN not in src:
        print("ERREUR: bloc de calcul introuvable. gestion_risque.py modifié ?")
        return
    bak = FICHIER + ".bak_kd"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(src)
    with open(FICHIER, "w", encoding="utf-8") as f:
        f.write(src.replace(ANCIEN, NOUVEAU, 1))
    print("OK: patch Kelly default appliqué dans gestion_risque.py")
    print(f"Backup: {os.path.basename(bak)}")
    print("\nEffet: profit_factor absent -> payoff ratio 1.0 (au lieu de ~0)")
    print("Kelly redevient positif pour les stratégies gagnantes.")
    print("\nTest: python gestion_risque.py test")


if __name__ == "__main__":
    main()
