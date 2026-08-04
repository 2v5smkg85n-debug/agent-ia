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
    strat_macd_momentum, simuler,
    donchian_series, stochastic_series, ema_simple_series
)

# Phase 4: importe les nouvelles strategies non-correlees
try:
    from strategies_phase4 import NOUVELLES_STRATEGIES
    # Fusionne les strategies originales + nouvelles pour le live
    STRATEGIES_TOUTES = {**STRATEGIES, **NOUVELLES_STRATEGIES}
except Exception:
    NOUVELLES_STRATEGIES = {}
    STRATEGIES_TOUTES = STRATEGIES

# MULTI-STRAT: nb max de signaux ACHAT retournes par actif (top-N par score)
MAX_SIGNAUX_PAR_ACTIF = 2

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BACKTESTS_REELS = os.path.join(DOSSIER, "backtests_reels.json")
FICHIER_BACKTESTS_PRO = os.path.join(DOSSIER, "backtests_pro.json")
FICHIER_BACKTESTS_PHASE4 = os.path.join(DOSSIER, "backtests_phase4.json")
FICHIER_BACKTESTS_HORAIRES = os.path.join(DOSSIER, "backtests_horaires.json")

# Drawdown max acceptable pour qu'une strategie gagnante soit utilisee en live
DRAWDOWN_MAX_ACCEPTABLE = 15.0

# Nombre de bougies a fetcher en live par intervalle (assez pour les indicateurs)
LIMITE_LIVE = {"1h": 200, "4h": 200, "15m": 200, "1d": 365}

# DIP-BUYING-GATE: bloque les entrees sur bougie haussiere confirmee
# (achat dans la force = pire groupe backtest 50% win). Autorise creux+neutre.
DIP_BUYING_GATE = os.getenv("DIP_BUYING_GATE", "0") == "1"  # desactive par defaut

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

def _charger_perf_live():
    """Analyse paper_trading.json pour calculer la performance live par strategie."""
    try:
        import os
        pf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.json")
        pf = json.load(open(pf_path))
        trades = pf.get("trades_fermes", [])
        from collections import defaultdict
        perf = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0})
        for t in trades:
            s = t.get("strategie", "")
            g = t.get("gain_eur", 0)
            if g > 0: perf[s]["wins"] += 1
            else: perf[s]["losses"] += 1
            perf[s]["pnl"] += g
        result = {}
        for s, d in perf.items():
            total = d["wins"] + d["losses"]
            result[s] = {
                "trades": total,
                "wr": 100 * d["wins"] / total if total > 0 else 0,
                "pnl": d["pnl"]
            }
        return result
    except:
        return {}

def strategies_gagnantes_par_actif():
    """Retourne {symbole: [strategies gagnantes triees par retour decroissant]}.
    Chaque entree contient son intervalle (1d, 1h ou 4h)."""
    toutes = charger_strategies_gagnantes()
    gagnantes = {}
    # Charger la performance live pour bloquer les strategies perdantes
    live_perf = _charger_perf_live()
    for r in toutes:
        if r.get("verdict") != "GAGNANTE":
            continue
        if r.get("drawdown_max", 99) > DRAWDOWN_MAX_ACCEPTABLE:
            continue
        wf = r.get("wf_precision")
        if wf is not None and wf < 0.0:
            continue
        sym = r.get("actif")
        if not sym:
            continue
        # FILTRE WIN RATE BACKTEST: minimum 50% (strategies hautement selectives avec confirmations)
        wr_bt = r.get("win_rate", 0)
        if wr_bt < 50:
            continue
        # FILTRE PERFORMANCE LIVE: bloquer strategies perdantes en live (apres 5 trades seulement)
        strat_name = r.get("strategie", "")
        live = live_perf.get(strat_name)
        if live and live.get("trades", 0) >= 5 and live.get("wr", 100) < 40:
            continue  # strategie perdante en live -> bloquee
        # FILTRE TOP 3 STRATEGIES: uniquement les 3 meilleures par nombre de gagnantes
        TOP_3_STRATEGIES = {"RSI Mean Reversion", "SMA Crossover", "EMA Crossover"}
        if strat_name not in TOP_3_STRATEGIES:
            continue
        # AUTO-PRUNING-INSTALLE : skip strategies desactivees en live (auto_pruning)
        try:
            from auto_pruning import est_desactivee
            if est_desactivee(r.get("strategie", ""), r.get("actif", "")):
                continue
        except Exception:
            pass
        gagnantes.setdefault(sym, []).append(r)
    # Trie chaque liste par retour decroissant
    for sym in gagnantes:
        gagnantes[sym].sort(key=lambda r: r.get("retour_pct", 0), reverse=True)
    return gagnantes

# ============================================
# CALCUL DES SIGNAUX EN LIVE
# ============================================
def calculer_donnees(clotures):
    """Pre-calcule TOUS les indicateurs sur une serie de clotures.
    Doit matcher le dict d du backtest (sinon KeyError live sur strat evolved/Phase7)."""
    bb_haut, bb_bas = bollinger_series(clotures, 20, 2)
    macd_line, macd_signal = _macd_full(clotures)
    donch_haut, donch_bas = donchian_series(clotures, 20)
    stoch_k, stoch_d = stochastic_series(clotures, 14, 3)
    return {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": bb_haut,
        "bb_bas": bb_bas,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "donchian_haut": donch_haut,
        "donchian_bas": donch_bas,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "ema12": ema_simple_series(clotures, 12),
        "ema26": ema_simple_series(clotures, 26),
    }

def signal_strategie(nom_strat, donnees):
    """Applique une strategie sur la DERNIERE bougie. Retourne 'ACHAT'/'VENTE'/None."""
    fonc = STRATEGIES_TOUTES.get(nom_strat)
    if not fonc:
        return None
    i = len(donnees["clotures"]) - 1
    try:
        return fonc(i, donnees)
    except Exception as e:
        # une strategie qui crash (ex: indicateur absent) ne doit pas casser
        # la generation de signaux -> on log et on ignore cette strat
        try:
            print(f"    [signal_strategie] {nom_strat} crash: {e}", flush=True)
        except Exception:
            pass
        return None

# ============================================
# GENERATION DES SIGNAUX POUR LE PAPER TRADING
# ============================================
_CLASSEMENT_CACHE = {"data": None, "mtime": 0.0}


def _classement_lookup():
    """{(actif, strategie): entry} depuis classement_strategies.json (cache par mtime).
    Mis a jour chaque heure par research_loop. Retourne {} si absent/erreur."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "classement_strategies.json")
        mt = os.path.getmtime(p)
        if _CLASSEMENT_CACHE["data"] is None or mt != _CLASSEMENT_CACHE["mtime"]:
            import json
            d = json.load(open(p, encoding="utf-8"))
            lookup = {}
            for actif, info in d.items():
                for s in info.get("strategies", []):
                    lookup[(actif, s.get("strategie"))] = s
            _CLASSEMENT_CACHE["data"] = lookup
            _CLASSEMENT_CACHE["mtime"] = mt
        return _CLASSEMENT_CACHE["data"]
    except Exception:
        return {}


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
        meilleur_score = -999  # REGIME-FIT-INSTALLE
        candidats_achat = []  # MULTI-STRAT: collecte tous les ACHAT (score, retour, strat)

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
            # DIP-BUYING-GATE: biais des chandeliers (achat de creux).
            # Backtest: biais>0 (force) = 50% win (pire), biais<=0 (creux) = 68.4%.
            _biais_bougies = 0.0
            try:
                from bougies_patterns import biais_bougies as _bb_fn
                _biais_bougies = _bb_fn(bougies)
            except Exception:
                _biais_bougies = 0.0
            if DIP_BUYING_GATE and _biais_bougies > 0:
                continue  # bougie haussiere confirmee -> achat dans la force -> skip
            # REGIME-MTF-GATE : gate multi-timeframe (1h+4h) - valide backtest +1.66% PnL
            try:
                from regime import fit_multi_tf
                _mtf_ok = True
            except Exception:
                _mtf_ok = False

            for strat in strats:
                nom = strat.get("strategie")
                # FILTRE TENDANCE: n'acheter qu'en tendance haussiere (prix > SMA50)
                # Evite d'acheter dans une baisse de marche
                sma50 = donnees.get("sma50", [None])[-1] if donnees.get("sma50") else None
                prix_courant = clotures[-1] if clotures else None
                if sma50 and prix_courant and prix_courant < sma50 * 0.98:
                    continue  # prix > 2% sous SMA50 = baisse -> skip
                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    if _mtf_ok:
                        try:
                            _fit_avg, _r1h, _r4h = fit_multi_tf(nom, clotures)
                        except Exception:
                            _fit_avg, _r1h, _r4h = 1.0, {"regime": "INCONNU"}, {"regime": "INCONNU"}
                        if _fit_avg < 1.0:
                            continue  # regime defavorable en moyenne -> skip
                    else:
                        _fit_avg, _r1h, _r4h = 1.0, {"regime": "INCONNU"}, {"regime": "INCONNU"}
                    # CLASSEMENT-INSTALLE: enrichit le score avec live_mult (perf
                    # live bayesienne depuis classement_strategies.json). Effet
                    # faible avec peu de trades (shrink vers 1.0), grandit ensuite.
                    _live_mult = 1.0
                    try:
                        _cl = _classement_lookup().get((symbole, nom))
                        if _cl:
                            _live_mult = _cl.get("live_mult", 1.0)
                    except Exception:
                        pass
                    _score = strat.get("retour_pct", 0) * _fit_avg * _live_mult
                    _strat_full = {**strat, "intervalle_live": interv_live,
                                   "regime_1h": _r1h.get("regime"),
                                   "regime_4h": _r4h.get("regime"),
                                   "regime_fit": round(_fit_avg, 3),
                                   "live_mult": round(_live_mult, 3),
                                   "biais_bougies": round(_biais_bougies, 2)}
                    candidats_achat.append((_score, strat.get("retour_pct", 0), _strat_full))
                    if _score > meilleur_score:
                        meilleur_score = _score
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = _strat_full

        if meilleur_signal == "ACHAT" and candidats_achat:
            # MULTI-STRAT: top-N strategies ACHAT par score (pas juste la meilleure)
            candidats_achat.sort(key=lambda c: c[0], reverse=True)
            # CONFLUENCE: si 2+ strategies signalent ACHAT, score plus eleve + position plus grosse
            nb_confluence = len(candidats_achat)
            score_confluence = min(2 + nb_confluence, 5)  # 2 strats=3, 3 strats=4, 4+=5
            for _sc, _retour, _strat in candidats_achat[:MAX_SIGNAUX_PAR_ACTIF]:
                interv_aff = _strat.get("intervalle", "?")
                _lm = _strat.get("live_mult", 1.0)
                _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""
                _bb_s = _strat.get("biais_bougies", 0.0)
                _bb_str = f", dip {_bb_s:+.2f}" if _bb_s != 0 else ""
                print(f"ACHAT ({_strat['strategie']} [{interv_aff}], "
                      f"backtest {_retour:+.1f}%{_lm_str}{_bb_str})")
                signaux.append({
                    "symbole": symbole,
                    "prix_entree": prix_actuels[symbole],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "backtest-gagnant",
                    "score": score_confluence,
                    "strategie": _strat.get("strategie", ""),
                    "confluence": nb_confluence,
                    "backtest_stats": _strat,
                    "raison": (f"strategie gagnante backtest "
                               f"({_strat['strategie']} [{interv_aff}], "
                               f"retour {_retour:+.1f}%, "
                               f"win rate {_strat.get('win_rate',0)}%)"),
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
