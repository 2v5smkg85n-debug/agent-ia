#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BACKTEST HORAIRE - Phase 5 : donnees plus fines.
=================================================

La feuille de route disait :
  "Certaines strategies marchent mieux en daily, d'autres en hourly.
   Le scalping actuel (TP 1.5%, sortie 45min) correspond a de l'intraday."

Ce module re-backteste les memes strategies sur donnees horaires (1h) et
4h, puis compare avec le daily (backtests_reels.json deja existant).

Pourquoi c'est important :
  - Daily : ~365 points/an -> peu de trades, statistiques faibles
  - 1h    : ~8760 points/an -> 24x plus de trades, stats solides
  - 4h    : ~2190 points/an -> bon compromis bruit/opportunites

ATTENTION coût : Yahoo limite le range. On demande :
  - 1h sur 1 mois   (~720 bougies)
  - 4h sur 3 mois   (~540 bougies)
  - 15m sur 5 jours  (~480 bougies)  [optionnel, tres bruite]
  - 1d sur 1 an      (~365 bougies)  [deja fait dans backtests_reels.json]

Reutilise le moteur deterministe de backtest_moteur.py (simuler + STRATEGIES).
AUCUNE IA : execution bougie par bougie, prix reels, frais 0.1%, TP/SL 1.5%.

Usage:
    python backtest_horaires.py                  # lance 1h + 4h sur tous les actifs
    python backtest_horaires.py crypto           # focus crypto
    python backtest_horaires.py intervalle 1h    # un seul intervalle
    python backtest_horaires.py compare          # compare daily vs 1h vs 4h
    python backtest_horaires.py resultats        # affiche les resultats horaires
"""
import os
import sys
import json
import time
from datetime import datetime

from backtest_moteur import STRATEGIES, simuler, ACTIFS
from indicateurs import historique_ohlcv

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_HORAIRE = os.path.join(DOSSIER, "backtests_horaires.json")
FICHIER_DAILY = os.path.join(DOSSIER, "backtests_reels.json")

# Intervalles a tester en Phase 5 (le daily est compare depuis backtests_reels.json)
INTERVALLES_PHASE5 = ["1h", "4h"]

# Limite de bougies demandees par intervalle
LIMITE = {"1h": 720, "4h": 600, "15m": 500, "1d": 365}
INTERVALLES = ["1h", "4h", "15m"]


# ============================================
# STOCKAGE
# ============================================
def charger(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def sauver(resultats):
    with open(FICHIER_HORAIRE, "w") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)


# ============================================
# EXECUTION
# ============================================
def tester_intervalle(intervalle, categorie=None):
    """Backteste toutes les strategies x actifs sur un intervalle donne."""
    resultats = charger(FICHIER_HORAIRE)
    deja_fait = {(r.get("strategie"), r.get("actif"), r.get("intervalle"))
                 for r in resultats}

    cats = [categorie] if categorie else list(ACTIFS.keys())
    limite = LIMITE.get(intervalle, 500)
    nb_nouveau = 0

    for cat in cats:
        for actif in ACTIFS.get(cat, []):
            for nom_strat, fonc in STRATEGIES.items():
                cle = (nom_strat, actif, intervalle)
                if cle in deja_fait:
                    continue
                print(f"[{intervalle}] [{cat}] {actif} x {nom_strat}...",
                      end=" ", flush=True)
                bougies = historique_ohlcv(actif, intervalle, limite)
                if not bougies or len(bougies) < 60:
                    print("pas assez de donnees")
                    continue
                stats = simuler(bougies, fonc)
                if not stats:
                    print("echec simulation")
                    continue
                entree = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "marche": cat,
                    "actif": actif,
                    "strategie": nom_strat,
                    "intervalle": intervalle,
                    "bougies": len(bougies),
                    **stats,
                }
                resultats.append(entree)
                sauver(resultats)
                nb_nouveau += 1
                print(f"{stats['verdict']} | {stats['retour_pct']:+.2f}% | "
                      f"{stats['gagnes']}G/{stats['perdus']}P | {stats['trades']} trades")
                time.sleep(0.3)

    print(f"\n[{intervalle}] {nb_nouveau} nouveau(x), {len(resultats)} total en base.")
    return resultats


def lancer_tout(categorie=None):
    """Lance tous les intervalles Phase 5."""
    tous = []
    for interv in INTERVALLES_PHASE5:
        print("\n" + "=" * 60)
        print(f"BACKTEST HORAIRE - intervalle {interv}")
        print("=" * 60)
        tous = tester_intervalle(interv, categorie)
    return tous


# ============================================
# COMPARAISON DAILY vs HORAIRE
# ============================================
def comparer():
    """Compare le rendement des strategies selon l'intervalle."""
    daily = charger(FICHIER_DAILY)
    horaire = charger(FICHIER_HORAIRE)

    if not daily:
        print("Aucun backtest daily (backtests_reels.json). "
              "Lance d'abord: python backtest_moteur.py")
        return
    if not horaire:
        print("Aucun backtest horaire. Lance d'abord: python backtest_horaires.py")
        return

    # Index : (strategie, actif) -> {intervalle: retour_pct}
    index = {}
    for r in daily:
        cle = (r.get("strategie"), r.get("actif"))
        index.setdefault(cle, {})["1d"] = r.get("retour_pct", 0)
    for r in horaire:
        cle = (r.get("strategie"), r.get("actif"))
        index.setdefault(cle, {})[r.get("intervalle", "?")] = r.get("retour_pct", 0)

    # Pour chaque cle, quel intervalle gagne ?
    print("=" * 70)
    print("COMPARAISON : DAILY vs HORAIRE (rendement %)")
    print("=" * 70)
    print(f"{'Strategie':<22} {'Actif':<10} {'1d':>8} {'1h':>8} {'4h':>8}  Gagnant")
    print("-" * 70)

    compte_gagnant = {"1d": 0, "1h": 0, "4h": 0}
    meilleures_horaire = []

    for cle, vals in sorted(index.items()):
        strat, actif = cle
        r_d = vals.get("1d")
        r_h = vals.get("1h")
        r_4 = vals.get("4h")
        if r_d is None and r_h is None and r_4 is None:
            continue
        lignes = {
            "1d": r_d if r_d is not None else float("-inf"),
            "1h": r_h if r_h is not None else float("-inf"),
            "4h": r_4 if r_4 is not None else float("-inf"),
        }
        gagnant = max(lignes, key=lignes.get)
        if lignes[gagnant] != float("-inf"):
            compte_gagnant[gagnant] = compte_gagnant.get(gagnant, 0) + 1
            if gagnant in ("1h", "4h") and lignes[gagnant] > 0:
                meilleures_horaire.append((strat, actif, gagnant, lignes[gagnant]))

        def fmt(v):
            return f"{v:+.1f}" if v != float("-inf") and v is not None else "  -  "
        print(f"{strat:<22} {actif:<10} {fmt(r_d):>8} {fmt(r_h):>8} {fmt(r_4):>8}  {gagnant}")

    print("\n" + "=" * 70)
    print("Synthese : nombre de couples ou chaque intervalle gagne")
    for k, v in compte_gagnant.items():
        print(f"  {k} : {v} couple(s)")

    if meilleures_horaire:
        print("\n" + "=" * 70)
        print("STRATEGIES QUI MARCHENT MIEUX EN HORAIRE (et sont positives)")
        print("=" * 70)
        meilleures_horaire.sort(key=lambda x: x[3], reverse=True)
        for strat, actif, interv, ret in meilleures_horaire[:15]:
            print(f"  {actif:<10} x {strat:<22} [{interv}] {ret:+.2f}%")
    else:
        print("\nAucune strategy strictement meilleure en horaire pour l'instant.")


# ============================================
# AFFICHAGE
# ============================================
def afficher(meilleurs_seulement=False):
    resultats = charger(FICHIER_HORAIRE)
    if not resultats:
        print("Aucun backtest horaire. Lance: python backtest_horaires.py")
        return
    tries = sorted(resultats, key=lambda r: r.get("retour_pct", 0), reverse=True)
    if meilleurs_seulement:
        tries = [r for r in tries if r.get("verdict") == "GAGNANTE"]
    print("=" * 70)
    titre = "TOP HORAIRE" if meilleurs_seulement else "RESULTATS BACKTEST HORAIRE"
    print(f"{titre} ({len(tries)} entrees)")
    print("=" * 70)
    for i, r in enumerate(tries[:25], 1):
        print(f"\n{i}. [{r.get('intervalle','?')}] [{r['marche']}] "
              f"{r['actif']} x {r['strategie']} -> {r['verdict']}")
        print(f"   Retour: {r['retour_pct']:+.2f}% | Trades: {r['trades']} "
              f"({r['gagnes']}G/{r['perdus']}P, WR {r['win_rate']}%) | DD {r['drawdown_max']}%")

    total = len(resultats)
    gagnantes = sum(1 for r in resultats if r.get("verdict") == "GAGNANTE")
    print(f"\nStats: {total} tests | {gagnantes} gagnantes | "
          f"taux succes {gagnantes/total*100:.1f}%")


def aide():
    print("""
BACKTEST HORAIRE (Phase 5)
==========================
Commandes:
  python backtest_horaires.py                Lance 1h + 4h sur tous les actifs
  python backtest_horaires.py crypto          Focus un marche
  python backtest_horaires.py intervalle 1h   Un seul intervalle
  python backtest_horaires.py compare         Compare daily vs 1h vs 4h
  python backtest_horaires.py resultats       Affiche les resultats horaires
  python backtest_horaires.py meilleurs       Top gagnants horaires

Intervalles Phase 5 : 1h, 4h (et 15m si demande explicitement)
Le daily est lu depuis backtests_reels.json pour la comparaison.
""")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "tous"

    print("=" * 60)
    print(f"BACKTEST HORAIRE (PHASE 5) - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    if cmd == "aide":
        aide()
    elif cmd == "resultats":
        afficher()
    elif cmd == "meilleurs":
        afficher(meilleurs_seulement=True)
    elif cmd == "compare":
        comparer()
    elif cmd == "intervalle":
        interv = args[1] if len(args) > 1 else "1h"
        cat = args[2] if len(args) > 2 else None
        tester_intervalle(interv, cat)
    elif cmd in ACTIFS.keys():
        lancer_tout(categorie=cmd)
    else:
        lancer_tout()
