#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EVALUATION REELLE via BACKTEST.
Remplace l'evaluation IA (biaisee, juge sans donnees) par un vrai test sur
l'historique reel des prix (365 jours Binance pour la crypto).

Comment ca marche:
- Pour chaque strategie non evaluee, on lance backtester_strategie()
- Le backtest recupere l'historique reel, simule la strategie dessus
- On lit le verdict (GAGNANTE/PERDANTE/NEUTRE) et on met a jour strategies.json
- L'IA ne "devine" plus: elle simule sur des donnees reelles

Usage (depuis evolution.py automatiquement, ou manuel):
    python evaluation_reelle.py            # evalue les strategies non evaluees
    python evaluation_reelle.py --stats    # affiche les performances reelles
"""
import os
import sys
import json
import time
from datetime import datetime

from strategies import (
    charger_strategies, sauver_strategies
)
from backtest import (
    backtester_strategie, extraire_backtest
)

# ============================================
# MAPAGE VERDICT BACKTEST -> RESULTAT STRATEGIE
# ============================================
def _verdict_vers_resultat(verdict_brut):
    """Convertit le verdict du backtest en resultat de strategie."""
    v = (verdict_brut or "").upper()
    if "GAGNANTE" in v:
        return "gagne"
    if "PERDANTE" in v:
        return "perdu"
    return "neutre"

# ============================================
# EVALUATION D'UNE STRATEGIE VIA BACKTEST REEL
# ============================================
def evaluer_une_par_backtest(strat):
    """Evalue une strategie via le backtest sur historique reel. Retourne le dict maj ou None."""
    print(f"    Backtest strategie {strat.get('marche','?')}...", end=" ", flush=True)
    resultat = backtester_strategie(strat)
    if not resultat:
        print("echec")
        return None
    print("OK")
    chiffres = extraire_backtest(resultat["resultat_brut"])
    verdict = chiffres.get("verdict", "NEUTRE")
    resultat_strat = _verdict_vers_resultat(verdict)

    # Met a jour la strategie avec les vraies perf
    strat["evaluee"] = True
    strat["resultat"] = resultat_strat
    strat["evaluations"] = strat.get("evaluations", 0) + 1
    if resultat_strat == "gagne":
        strat["gagnes"] = strat.get("gagnes", 0) + 1
    else:
        strat["gagnes"] = strat.get("gagnes", 0)
    evals = strat["evaluations"]
    strat["win_rate"] = strat["gagnes"] / evals if evals else 0
    # Raison detaillee avec les vrais chiffres du backtest
    strat["raison_eval"] = (
        f"[BACKTEST REEL] verdict={verdict} | win_rate={chiffres.get('win_rate','?')} "
        f"| retour={chiffres.get('retour','?')} | trades={chiffres.get('trades','?')} "
        f"| drawdown={chiffres.get('drawdown','?')} | note={chiffres.get('note','?')[:150]}"
    )[:300]
    strat["methode_evaluation"] = "backtest_reel"
    return strat

# ============================================
# CYCLE D'EVALUATION REELLE
# ============================================
def evaluer_par_backtest(limite=5):
    """Evalue jusqu'a `limite` strategies non evaluees via le backtest reel."""
    strategies = charger_strategies()
    non_evaluees = [s for s in strategies if not s.get("evaluee")]

    if not non_evaluees:
        print("Toutes les strategies ont deja ete evaluees.")
        return 0

    a_evaluer = non_evaluees[-limite:]
    print(f"{len(non_evaluees)} strategie(s) a evaluer, traitement de {len(a_evaluer)} ce cycle.")
    print("Evaluation par BACKTEST REEL (historique 365j Binance pour crypto)...")

    compte = 0
    for strat in a_evaluer:
        if evaluer_une_par_backtest(strat):
            compte += 1
        time.sleep(2)

    sauver_strategies(strategies)
    print(f"\nEvaluation terminee. {compte} strategie(s) evaluee(s) par backtest reel.")
    return compte

# ============================================
# STATS
# ============================================
def afficher_stats():
    strategies = charger_strategies()
    evaluees = [s for s in strategies if s.get("evaluee")]
    if not evaluees:
        print("Aucune strategie evaluee pour le moment.")
        return

    print("=" * 60)
    print(f"PERFORMANCES REELLES (via backtest) - {len(evaluees)} strategies")
    print("=" * 60)

    # Stats par marche
    marches = {}
    for s in evaluees:
        m = s.get("marche", "?")
        if m not in marches:
            marches[m] = {"gagne": 0, "perdu": 0, "neutre": 0}
        r = s.get("resultat", "neutre")
        if r in marches[m]:
            marches[m][r] += 1

    print("\nPar marche:")
    for m in sorted(marches.keys()):
        s = marches[m]
        total = s["gagne"] + s["perdu"] + s["neutre"]
        wr = s["gagne"] / total * 100 if total else 0
        print(f"  {m:10}: {s['gagne']}G/{s['perdu']}P/{s['neutre']}N (win rate {wr:.0f}%, {total} evals)")

    # Strategie d'origine vs amelioree
    ameliorees = [s for s in evaluees if s.get("amelioree_de")]
    if ameliorees:
        print(f"\nStrategies ameliorees re-evaluees: {len(ameliorees)}")
        for s in ameliorees[-5:]:
            print(f"  [{s.get('marche','?')}] {s.get('resultat','?')} "
                  f"(action: {s.get('action_amelioration','?')})")
            print(f"    origine: {s.get('strategie_origine_resultat','?')} -> maintenant: {s.get('resultat','?')}")

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--stats" in args:
        afficher_stats()
    else:
        evaluer_par_backtest()
