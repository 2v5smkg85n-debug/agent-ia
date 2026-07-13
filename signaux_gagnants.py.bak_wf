#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIGNAUX BASES SUR LES STRATEGIES GAGNANTES DU BACKTEST.
L'agent n'utilise plus des signaux generiques: il applique uniquement les
strategies qui ont PROUVE qu'elles marchent en backtest reel (deterministe).

Phase 5 : support MULTI-TIMEFRAMES.
  - Charge aussi backtests_horaires.json (intervalles 1h et 4h)
  - Chaque strategie gagnante est testee sur SON intervalle backteste
    (ex: MACD Momentum sur NG=F en 4h, Bollinger sur SOL en 1h)
  - Un actif peut avoir plusieurs strategies gagnantes a des intervalles
    differents : on regroupe par intervalle, on fetch une fois par
    intervalle, on teste chaque strategie.

Comment ca marche:
1. Charge backtests_reels.json + backtests_pro.json + backtests_phase4.json
   + backtests_horaires.json
2. Garde seulement les strategies GAGNANTES (et filtre le drawdown trop eleve)
3. Pour chaque actif du paper trading, regarde s'il a une strategie gagnante
4. Pour chaque intervalle represente parmi ses strategies gagnantes,
   recupere l'historique recent a CET intervalle
5. Calcule les indicateurs et applique la strategie -> signal ACHAT/VENTE/NONE
6. Retourne les signaux au format attendu par paper_trading.py
"""
import os
import sys
import json
import time
from datetime import datetime

from indicateurs import historique_ohlcv
from backtest_moteur import (
    STRATEGIES, sma_series, rsi_series, bollinger_series, _macd_full,
    strat_sma_crossover, strat_rsi_reversion, strat_bollinger_breakout,
    strat_macd_momentum, simuler
)

# Phase 4: importe les nouvelles strategies non-correlees
try:
    from strategies_phase4 import NOUVELLES_STRATEGIES
    # Fusionne les strategies originales + nouvelles pour le live
    STRATEGIES_TOUTES = {**STRATEGIES, **NOUVELLES_STRATEGIES}
except Exception:
    NOUVELLES_STRATEGIES = {}
    STRATEGIES_TOUTES = STRATEGIES

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BACKTESTS_REELS = os.path.join(DOSSIER, "backtests_reels.json")
FICHIER_BACKTESTS_PRO = os.path.join(DOSSIER, "backtests_pro.json")
FICHIER_BACKTESTS_PHASE4 = os.path.join(DOSSIER, "backtests_phase4.json")
FICHIER_BACKTESTS_HORAIRES = os.path.join(DOSSIER, "backtests_horaires.json")

# Drawdown max acceptable pour qu'une strategie gagnante soit utilisee en live
DRAWDOWN_MAX_ACCEPTABLE = 15.0

# Nombre de bougies a fetcher en live par intervalle (assez pour les indicateurs)
LIMITE_LIVE = {"1h": 200, "4h": 200, "15m": 200, "1d": 365}

# ============================================
# CHARGER LES STRATEGIES GAGNANTES
# ============================================
def charger_strategies_gagnantes():
    """Retourne la liste des strategies gagnantes depuis tous les fichiers de backtest.
    Combine: backtests_reels.json (daily), backtests_pro.json (daily couts reels),
    backtests_phase4.json (daily nouvelles), backtests_horaires.json (1h/4h)."""
    tous_resultats = []
    fichiers = [
        FICHIER_BACKTESTS_REELS,
        FICHIER_BACKTESTS_PRO,
        FICHIER_BACKTESTS_PHASE4,
        FICHIER_BACKTESTS_HORAIRES,
    ]
    for fich in fichiers:
        if os.path.exists(fich):
            try:
                with open(fich, "r") as f:
                    data = json.load(f)
                # Normalise le champ intervalle (les anciens fichiers n'en ont pas -> 1d)
                for r in data:
                    if "intervalle" not in r:
                        r["intervalle"] = "1d"
                tous_resultats.extend(data)
            except Exception:
                pass

    # Deduplique par (strategie, actif, intervalle) : si plusieurs fichiers
    # contiennent le meme couple, garde la version la plus fiable
    # (backtest avec couts reels / phase4 / horaire > reels naif).
    vus = {}
    for r in tous_resultats:
        cle = (r.get("strategie"), r.get("actif"), r.get("intervalle", "1d"))
        existant = vus.get(cle)
        if not existant:
            vus[cle] = r
        else:
            # Heuristique: un resultat avec champ 'sharpe' (pro/phase4) est plus fiable
            if "sharpe" in r and "sharpe" not in existant:
                vus[cle] = r
    return list(vus.values())

def strategies_gagnantes_par_actif():
    """Retourne {symbole: [strategies gagnantes triees par retour decroissant]}.
    Chaque entree contient son intervalle (1d, 1h ou 4h)."""
    toutes = charger_strategies_gagnantes()
    gagnantes = {}
    for r in toutes:
        if r.get("verdict") != "GAGNANTE":
            continue
        if r.get("drawdown_max", 99) > DRAWDOWN_MAX_ACCEPTABLE:
            continue  # trop risque
        sym = r.get("actif")
        if not sym:
            continue
        gagnantes.setdefault(sym, []).append(r)
    # Trie chaque liste par retour decroissant
    for sym in gagnantes:
        gagnantes[sym].sort(key=lambda r: r.get("retour_pct", 0), reverse=True)
    return gagnantes

# ============================================
# CALCUL DES SIGNAUX EN LIVE
# ============================================
def calculer_donnees(clotures):
    """Pre-calcule tous les indicateurs sur une serie de clotures."""
    bb_haut, bb_bas = bollinger_series(clotures, 20, 2)
    macd_line, macd_signal = _macd_full(clotures)
    return {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": bb_haut,
        "bb_bas": bb_bas,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
    }

def signal_strategie(nom_strat, donnees):
    """Applique une strategie sur la DERNIERE bougie. Retourne 'ACHAT'/'VENTE'/None."""
    fonc = STRATEGIES_TOUTES.get(nom_strat)
    if not fonc:
        return None
    i = len(donnees["clotures"]) - 1
    return fonc(i, donnees)

# ============================================
# GENERATION DES SIGNAUX POUR LE PAPER TRADING
# ============================================
def generer_signaux_gagnants(prix_actuels, marches_paper):
    """Genere des signaux d'achat bases sur les strategies gagnantes du backtest.

    Phase 5: chaque strategie est testee sur SON intervalle backteste.
    On regroupe les strategies gagnantes d'un actif par intervalle, on fetch
    une fois l'historique par intervalle, puis on teste chaque strategie.

    Arguments:
        prix_actuels: dict {symbole: prix}
        marches_paper: dict {symbole: config} depuis paper_trading.MARCHES_PAPER

    Retourne: liste de signaux au format attendu par paper_trading.ouvrir_position
    """
    gagnantes = strategies_gagnantes_par_actif()
    if not gagnantes:
        print("    (aucune strategie gagnante en base -> lance backtest_moteur.py)")
        return []

    signaux = []
    for symbole, config in marches_paper.items():
        if symbole not in prix_actuels:
            continue
        if symbole not in gagnantes:
            continue  # aucune strategie gagnante pour cet actif

        print(f"    {config['nom']}... ", end="", flush=True)

        # Regroupe les strategies gagnantes par intervalle
        par_intervalle = {}
        for strat in gagnantes[symbole]:
            interv = strat.get("intervalle", "1d")
            par_intervalle.setdefault(interv, []).append(strat)

        meilleur_signal = None
        meilleure_strat = None
        meilleur_retour = -999

        # Pour chaque intervalle, fetch l'historique une fois et teste les strategies
        for interv, strats in par_intervalle.items():
            # Le daily n'est pas utilise pour le live intraday (trop lent a bouger),
            # mais on garde quand meme les stratégies daily en fallback sur 1h
            # si elles n'existent qu'en daily.
            interv_live = interv if interv in ("1h", "4h", "15m") else "1h"
            bougies = historique_ohlcv(symbole, interv_live, LIMITE_LIVE.get(interv_live, 200))
            if not bougies or len(bougies) < 60:
                continue
            clotures = [b["cloture"] for b in bougies]
            donnees = calculer_donnees(clotures)

            for strat in strats:
                nom = strat.get("strategie")
                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    if strat.get("retour_pct", 0) > meilleur_retour:
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = {**strat, "intervalle_live": interv_live}

        if meilleur_signal == "ACHAT":
            interv_aff = meilleure_strat.get("intervalle", "?")
            print(f"ACHAT ({meilleure_strat['strategie']} [{interv_aff}], "
                  f"backtest {meilleur_retour:+.1f}%)")
            signaux.append({
                "symbole": symbole,
                "prix_entree": prix_actuels[symbole],
                "nom": config["nom"],
                "marche": config["marche"],
                "source": "backtest-gagnant",
                "score": 2,
                "raison": (f"strategie gagnante backtest "
                           f"({meilleure_strat['strategie']} [{interv_aff}], "
                           f"retour {meilleur_retour:+.1f}%, "
                           f"win rate {meilleure_strat.get('win_rate',0)}%)"),
            })
        else:
            print("neutre")
        time.sleep(0.3)

    return signaux

# ============================================
# TEST UNITAIRE
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("STRATEGIES GAGNANTES DISPONIBLES POUR LE PAPER TRADING (multi-TF)")
    print("=" * 60)
    gagnantes = strategies_gagnantes_par_actif()
    total = 0
    for sym, strats in sorted(gagnantes.items()):
        print(f"\n{sym}:")
        for s in strats:
            interv = s.get("intervalle", "1d")
            print(f"  - [{interv}] {s['strategie']}: {s['retour_pct']:+.2f}% | "
                  f"win {s.get('win_rate',0)}% | DD {s.get('drawdown_max',0)}%")
            total += 1
    print(f"\n{total} strategies gagnantes utilisables en live "
          f"(drawdown < {DRAWDOWN_MAX_ACCEPTABLE}%).")
