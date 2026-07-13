#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALK-FORWARD VALIDATION (Phase 3) — filtre les stratégies robustes.
Anti-surapprentissage: teste chaque stratégie sur 4 fenêtres OUT-OF-SAMPLE.

Valide TOUTES les stratégies (canoniques + phase4) sur TOUS les fichiers
de backtest lus par signaux_gagnants:
  - backtests_reels.json     (daily, canoniques)
  - backtests_pro.json       (daily, canoniques)
  - backtests_phase4.json    (daily, phase4: Volatility Squeeze, Z-Score, Trend Filter, Dual TF)
  - backtests_horaires.json  (1h/4h, toutes stratégies)

Une stratégie est ROBUSTE si:
  - retour_pct > 0 (rentable sur la période complète)
  - wf_precision >= 50% (rentable sur au moins 2 folds out-of-sample)

Usage:
    python walk_forward.py            # calcule wf_precision pour tous les backtests
    python walk_forward.py crypto     # focus un marché
    python walk_forward.py resultats  # affiche le classement robuste
"""
import os
import sys
import json
from datetime import datetime

from backtest_moteur import (
    STRATEGIES, simuler, ACTIFS,
    FICHIER_RESULTATS, charger_resultats, sauver_resultats,
)
from indicateurs import historique_ohlcv

# Phase 4: stratégies non-corrélées (mêmes indicateurs -> validables par simuler)
try:
    from strategies_phase4 import NOUVELLES_STRATEGIES
except Exception:
    NOUVELLES_STRATEGIES = {}
STRATEGIES_ALL = {**STRATEGIES, **NOUVELLES_STRATEGIES}

N_FOLDS = 4
WF_SEUIL = 50.0  # % de folds rentables requis pour "robuste"

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIERS = [
    os.path.join(DOSSIER, "backtests_reels.json"),
    os.path.join(DOSSIER, "backtests_pro.json"),
    os.path.join(DOSSIER, "backtests_phase4.json"),
    os.path.join(DOSSIER, "backtests_horaires.json"),
]


def walk_forward(bougies, fonction_strat, n_folds=N_FOLDS):
    """Découpe l'historique en n_folds+1 segments. Pour chaque fold k,
    teste la stratégie sur le segment k (out-of-sample).
    Retourne (precision %, liste des retours par fold)."""
    n = len(bougies)
    if n < 120:
        return 0.0, []
    fold = n // (n_folds + 1)
    if fold < 30:
        return 0.0, []
    retours = []
    for k in range(1, n_folds + 1):
        start = k * fold
        end = (k + 1) * fold if k < n_folds else n
        if end - start < 30:
            continue
        seg = bougies[start:end]
        stats = simuler(seg, fonction_strat)
        if stats:
            retours.append(stats.get("retour_pct", 0))
    if not retours:
        return 0.0, []
    gagnes = sum(1 for r in retours if r > 0)
    precision = gagnes / len(retours) * 100
    return precision, [round(r, 2) for r in retours]


def _charger(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _sauver(fichier, data):
    with open(fichier, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calculer_fichier(fichier, categorie=None):
    """Calcule wf_precision pour chaque entrée d'un fichier de backtest.
    Cache les bougies par (actif, intervalle). Valide toutes les stratégies
    connues (canoniques + phase4)."""
    resultats = _charger(fichier)
    nom_fich = os.path.basename(fichier)
    if not resultats:
        print(f"  {nom_fich}: vide ou absent")
        return 0
    print(f"  {nom_fich}: {len(resultats)} entrées")

    cache = {}  # (actif, intervalle) -> bougies
    maj = 0
    sautes = 0

    for entry in resultats:
        if categorie and entry.get("marche") != categorie:
            continue
        nom = entry.get("strategie")
        fonc = STRATEGIES_ALL.get(nom)
        if not fonc:
            sautes += 1  # stratégie inconnue (non validable)
            continue
        actif = entry.get("actif")
        interv = entry.get("intervalle", "1d")
        if not actif:
            continue
        key = (actif, interv)
        if key not in cache:
            limite = 365 if interv == "1d" else 500
            print(f"    [{actif} {interv}] fetch...", end=" ", flush=True)
            bougies = historique_ohlcv(actif, interv, limite)
            cache[key] = bougies
            print(f"{len(bougies) if bougies else 0} bougies")
        bougies = cache[key]
        if not bougies or len(bougies) < 120:
            continue
        wf, folds = walk_forward(bougies, fonc)
        entry["wf_precision"] = round(wf, 1)
        entry["wf_folds"] = folds
        entry["robuste"] = (entry.get("retour_pct", 0) > 0 and wf >= WF_SEUIL)
        maj += 1

    _sauver(fichier, resultats)
    print(f"    -> {maj} mises à jour, {sautes} sautées (stratégie inconnue)")
    return maj


def calculer_tous(categorie=None):
    print(f"Calcul walk-forward (4 folds out-of-sample) — {len(STRATEGIES_ALL)} stratégies connues")
    print("=" * 60)
    total = 0
    for fich in FICHIERS:
        total += calculer_fichier(fich, categorie)
    print("=" * 60)
    print(f"Total: {total} entrées mises à jour.")
    print(f"Seuil robuste: retour>0 ET wf_precision>={WF_SEUIL}%")
    print(f"\nRelance: python signaux_gagnants.py  (les non-robustes sont filtrées)")


def afficher_resultats():
    robustes = []
    total = 0
    for fich in FICHIERS:
        data = _charger(fich)
        for r in data:
            if "wf_precision" in r:
                total += 1
                if r.get("robuste"):
                    r["_fich"] = os.path.basename(fich)
                    robustes.append(r)
    if not robustes:
        print("Aucune stratégie robuste. Lance: python walk_forward.py")
        return
    print("=" * 65)
    print(f"CLASSEMENT WALK-FORWARD — {len(robustes)} stratégies robustes / {total} testées")
    print("=" * 65)
    robustes.sort(key=lambda r: r.get("wf_precision", 0), reverse=True)
    for r in robustes:
        wf = r.get("wf_precision", 0)
        ret = r.get("retour_pct", 0)
        wr = r.get("win_rate", 0)
        dd = r.get("drawdown_max", 0)
        folds = r.get("wf_folds", [])
        folds_str = " ".join(f"{f:+.1f}" for f in folds)
        interv = r.get("intervalle", "1d")
        print(f"\n  [{r.get('marche','?')}] {r.get('actif','?')} {interv} x {r.get('strategie','?')}")
        print(f"    WF {wf:.0f}% (folds: {folds_str}) | retour {ret:+.2f}% | win {wr}% | DD {dd}%")
    print("\n" + "=" * 65)
    by_marche = {}
    for r in robustes:
        by_marche[r.get("marche", "?")] = by_marche.get(r.get("marche", "?"), 0) + 1
    print("Robustes par marché:")
    for m, c in sorted(by_marche.items()):
        print(f"  {m}: {c}")
    print(f"\nTotal: {len(robustes)} stratégies robustes (priorisées en live)")


def aide():
    print("""
WALK-FORWARD VALIDATION - Aide
===========================================
Commandes:
  python walk_forward.py            Calcule wf_precision (4 fichiers: reels, pro, phase4, horaires)
  python walk_forward.py crypto     Focus sur un marché
  python walk_forward.py resultats  Affiche le classement des stratégies robustes

Logique:
  - Découpe l'historique en 5 segments
  - Teste la stratégie sur 4 fenêtres out-of-sample
  - wf_precision = % de fenêtres rentables
  - ROBUSTE = retour>0 ET wf_precision >= 50%
""")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "tous"
    print("=" * 60)
    print(f"WALK-FORWARD VALIDATION - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    if cmd == "resultats":
        afficher_resultats()
    elif cmd == "aide":
        aide()
    elif cmd in ACTIFS.keys():
        calculer_tous(categorie=cmd)
    else:
        calculer_tous()
