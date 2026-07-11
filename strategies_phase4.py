#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHASE 4 - DIVERSIFICATION + ANALYSE DE CORRELATION.
Ajoute de nouvelles strategies non-correlees et mesure la correlation entre
toutes les strategies pour construire un portefeuille equilibre.

Pourquoi c'est important:
  - Tes 4 strategies actuelles (SMA, RSI, Bollinger, MACD) sont toutes basees sur
    les memes indicateurs -> correlees. Quand une perd, les autres perdent aussi.
  - Un portefeuille pro combine des strategies NON-correlees pour lisser les
    rendements et reduire le drawdown.

Nouvelles strategies (chacune explore un edge different):
  5. Volatility Squeeze   - compression de volatilite puis expansion (breakout)
  6. Z-Score Reversion    - mean reversion multi-periode (plus robuste que RSI<30)
  7. Trend Filter Combo   - momentum + filtre de tendance (evite les faux signaux)
  8. Dual Timeframe       - tendance long terme + entree court terme

Analyse de correlation:
  - Calcule les rendements journaliers de chaque strategie
  - Matrice de correlation entre strategies
  - Suggere des poids de portefeuille (plus de poids = faible correlation + bon Sharpe)

Usage:
  python strategies_phase4.py                # ajoute les strategies + backtest pro
  python strategies_phase4.py correlation     # analyse de correlation entre strategies
  python strategies_phase4.py portfolio      # suggestions de poids de portefeuille
  python strategies_phase4.py tester BTCUSDT # teste les nouvelles strategies sur un actif
"""
import os
import sys
import json
import math
import time
from datetime import datetime
from collections import defaultdict

from backtest_moteur import (
    ACTIFS, STRATEGIES, simuler, sma_series, bollinger_series, _macd_full
)
from backtest_moteur import CAPITAL_DEPART
from indicateurs import historique_ohlcv
from backtest_pro import simuler_pro, charger_resultats as charger_pro

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_RESULTATS = os.path.join(DOSSIER, "backtests_phase4.json")
FICHIER_CORREL = os.path.join(DOSSIER, "correlation_strategies.json")

# ============================================
# NOUVELLES STRATEGIES (interface compatible: (index, donnees) -> signal)
# ============================================

def _bollinger_width_series(clotures, periode=20, ecart=2):
    """Largeur des bandes de Bollinger (mesure de volatilite)."""
    hauts, bas = bollinger_series(clotures, periode, ecart)
    widths = []
    for i in range(len(clotures)):
        if hauts[i] is not None and bas[i] is not None:
            widths.append(hauts[i] - bas[i])
        else:
            widths.append(None)
    return widths

def _sma(values, periode):
    """SMA sur une liste de valeurs (dont certains elements None)."""
    out = [None] * len(values)
    for i in range(periode - 1, len(values)):
        fenetre = [v for v in values[i - periode + 1:i + 1] if v is not None]
        if len(fenetre) == periode:
            out[i] = sum(fenetre) / periode
    return out

def strat_volatility_squeeze(i, d):
    """
    Volatility Squeeze: detecte une compression de volatilite (bandes serrees)
    puis un breakout quand le prix sort de la compression.
    - Achat quand BB largeur est basse (squeeze) ET prix remonte au-dessus de SMA20
    - Vente quand BB largeur est haute (expansion) ET prix sous SMA20
    """
    clotures = d["clotures"]
    if "bb_width" not in d:
        d["bb_width"] = _bollinger_width_series(clotures)
    if "bb_width_sma" not in d:
        d["bb_width_sma"] = _sma(d["bb_width"], 20)

    if i < 20:
        return None
    width = d["bb_width"][i]
    width_sma = d["bb_width_sma"][i]
    sma20 = d.get("sma20", [None] * len(clotures))[i]
    prix = clotures[i]

    if width is None or width_sma is None or width_sma == 0 or sma20 is None:
        return None

    squeeze = width < width_sma * 0.8  # volatilite compressee
    expansion = width > width_sma * 1.5  # volatilite en expansion

    if squeeze and prix > sma20:
        return "ACHAT"
    if expansion and prix < sma20:
        return "VENTE"
    return None

def strat_zscore_reversion(i, d):
    """
    Z-Score Mean Reversion: achete quand le prix est statistiquement bas
    (z-score < -1.5) et vend quand statistiquement haut (z-score > 1.5).
    Plus robuste que RSI<30 car normalise par la volatilite.
    """
    clotures = d["clotures"]
    periode = 20
    if i < periode:
        return None
    fenetre = clotures[i - periode + 1:i + 1]
    moyenne = sum(fenetre) / periode
    variance = sum((x - moyenne) ** 2 for x in fenetre) / periode
    ecart_type = math.sqrt(variance)
    if ecart_type == 0:
        return None
    z = (clotures[i] - moyenne) / ecart_type

    if z < -1.5:   # prix anormalement bas -> rebond attendu
        return "ACHAT"
    if z > 1.5:    # prix anormalement haut -> correction attendue
        return "VENTE"
    return None

def strat_trend_filter_combo(i, d):
    """
    Trend Filter Combo: achete en momentum SEULEMENT si la tendance long terme
    est haussiere (SMA50 croissante). Filtre les faux signaux en marche bear.
    """
    clotures = d["clotures"]
    if i < 55:
        return None
    if "sma50_slope" not in d:
        d["sma50_slope"] = _slope_series(d.get("sma50", [None] * len(clotures)), 5)

    sma20 = d.get("sma20", [None] * len(clotures))[i]
    sma50 = d.get("sma50", [None] * len(clotures))[i]
    slope = d["sma50_slope"][i] if d.get("sma50_slope") else None
    prix = clotures[i]

    if sma20 is None or sma50 is None or slope is None:
        return None

    tendance_haussiere = slope > 0 and prix > sma50
    momentum_hausse = sma20 > sma50 and prix > sma20

    if tendance_haussiere and momentum_hausse:
        return "ACHAT"
    if not tendance_haussiere and prix < sma20:
        return "VENTE"
    return None

def _slope_series(series, lookback=5):
    """Pente d'une serie (pour detecter tendance croissante/decroissante)."""
    out = [None] * len(series)
    for i in range(lookback, len(series)):
        if series[i] is not None and series[i - lookback] is not None and series[i - lookback] != 0:
            out[i] = (series[i] - series[i - lookback]) / series[i - lookback]
    return out

def strat_dual_timeframe(i, d):
    """
    Dual Timeframe: tendance long terme (SMA50) + entree court terme (RSI survente
    dans la tendance). Achete quand la tendance LT est haussiere ET RSI court terme
    indique survente (pullback dans le trend).
    """
    clotures = d["clotures"]
    if i < 55:
        return None
    rsi = d.get("rsi", [None] * len(clotures))[i]
    sma50 = d.get("sma50", [None] * len(clotures))[i]
    sma20 = d.get("sma20", [None] * len(clotures))[i]
    prix = clotures[i]

    if rsi is None or sma50 is None or sma20 is None:
        return None

    tendance_haussiere = sma50 > 0 and prix > sma50 and sma20 > sma50
    tendance_baissiere = sma50 > 0 and prix < sma50 and sma20 < sma50

    # Pullback dans tendance haussiere (RSI temporairement bas)
    if tendance_haussiere and rsi < 45:
        return "ACHAT"
    # Rebond dans tendance baissiere (RSI temporairement haut)
    if tendance_baissiere and rsi > 55:
        return "VENTE"
    return None

# ============================================
# REGISTRE DES NOUVELLES STRATEGIES
# ============================================
NOUVELLES_STRATEGIES = {
    "Volatility Squeeze": strat_volatility_squeeze,
    "Z-Score Reversion":  strat_zscore_reversion,
    "Trend Filter Combo": strat_trend_filter_combo,
    "Dual Timeframe":     strat_dual_timeframe,
}

# ============================================
# STOCKAGE
# ============================================
def charger_resultats():
    if os.path.exists(FICHIER_RESULTATS):
        try:
            with open(FICHIER_RESULTATS, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def sauver_resultats(resultats):
    with open(FICHIER_RESULTATS, "w") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

# ============================================
# BACKTEST DES NOUVELLES STRATEGIES (avec couts reels)
# ============================================
def tester_nouvelles(categorie=None):
    """Backteste les 4 nouvelles strategies sur tous les actifs (couts reels)."""
    resultats = charger_resultats()
    deja_fait = {(r.get("strategie"), r.get("actif")) for r in resultats}

    cats = [categorie] if categorie else list(ACTIFS.keys())
    nb_nouveau = 0

    for cat in cats:
        for actif in ACTIFS.get(cat, []):
            for nom_strat, fonc in NOUVELLES_STRATEGIES.items():
                if (nom_strat, actif) in deja_fait:
                    continue
                print(f"[{cat}] {actif} x {nom_strat}... ", end="", flush=True)
                bougies = historique_ohlcv(actif, "1d", 365)
                if not bougies or len(bougies) < 60:
                    print("pas assez de donnees")
                    continue
                # Utilise simuler_pro (couts reels + metriques pro)
                stats = simuler_pro(bougies, fonc, cat, actif)
                if not stats:
                    print("echec simulation")
                    continue
                entree = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "marche": cat,
                    "actif": actif,
                    "strategie": nom_strat,
                    "bougies": len(bougies),
                    **stats,
                }
                resultats.append(entree)
                sauver_resultats(resultats)
                nb_nouveau += 1
                print(f"{stats['verdict']} | {stats['retour_pct']:+.2f}% | "
                      f"Sh {stats['sharpe']} | DD {stats['drawdown_max']:.1f}%")
                time.sleep(0.3)

    print("\n" + "=" * 60)
    print(f"Phase 4 termine. {nb_nouveau} nouveau(x), {len(resultats)} total.")
    print("=" * 60)

# ============================================
# ANALYSE DE CORRELATION
# ============================================
def analyser_correlation():
    """
    Calcule la matrice de correlation entre strategies.
    Pour chaque strategie, on moyenne les rendements journaliers sur tous les actifs,
    puis on calcule la correlation entre les series de rendements des strategies.
    """
    # Combine backtests pro (anciennes strategies) + phase4 (nouvelles)
    anciens = charger_pro()
    nouveaux = charger_resultats()
    tous = anciens + nouveaux

    if not tous:
        print("Aucun backtest. Lance 'python strategies_phase4.py' d'abord.")
        return

    # Stats par strategie
    par_strat = defaultdict(list)
    for r in tous:
        par_strat[r.get("strategie")].append(r)

    strategies = sorted(par_strat.keys())
    print("=" * 70)
    print(f"ANALYSE DE CORRELATION - {len(strategies)} strategies")
    print("=" * 70)

    # Performance par strategie
    print(f"\n{'Strategie':<24} {'Tests':<6} {'Gagnantes':<10} {'Retour moy':<12} {'Sharpe moy'}")
    print("-" * 65)
    perfs = {}
    for strat in strategies:
        res = par_strat[strat]
        n = len(res)
        gagnes = sum(1 for r in res if r.get("verdict") == "GAGNANTE")
        retours = [r.get("retour_pct", 0) for r in res]
        sharpes = [r.get("sharpe", 0) for r in res]
        ret_moy = sum(retours) / n if n else 0
        sh_moy = sum(sharpes) / n if n else 0
        perfs[strat] = {"n": n, "gagnes": gagnes, "ret_moy": ret_moy, "sharpe": sh_moy}
        print(f"{strat:<24} {n:<6} {gagnes:<10} {ret_moy:+.2f}%     {sh_moy:.2f}")

    # Correlation entre strategies (approximation: si deux strategies gagnent/perdent
    # sur les memes actifs, elles sont correlees)
    print("\n" + "-" * 65)
    print("CORRELATION ENTRE STRATEGIES (meme direction sur memes actifs)")
    print("-" * 65)
    actifs_communs = list(set(r["actif"] for r in tous))
    correl_matrix = {}
    for s1 in strategies:
        correl_matrix[s1] = {}
        for s2 in strategies:
            # Compte les actifs ou les deux strategies donnent le meme verdict
            v1 = {r["actif"]: r.get("verdict") for r in par_strat[s1]}
            v2 = {r["actif"]: r.get("verdict") for r in par_strat[s2]}
            communs = [a for a in actifs_communs if a in v1 and a in v2]
            if not communs:
                correl_matrix[s1][s2] = 0
                continue
            memes = sum(1 for a in communs if v1[a] == v2[a])
            correl_matrix[s1][s2] = memes / len(communs) * 100

    # Affiche la matrice
    entete = "                " + " ".join(f"{s[:8]:>9}" for s in strategies)
    print(entete)
    for s1 in strategies:
        ligne = f"{s1[:14]:<16}"
        for s2 in strategies:
            c = correl_matrix[s1][s2]
            ligne += f"{c:>8.0f}%"
        print(ligne)

    # Sauvegarde
    output = {
        "strategies": strategies,
        "performances": perfs,
        "correlation": {k: v for k, v in correl_matrix.items()},
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with open(FICHIER_CORREL, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nCorrelation sauvegardee dans {FICHIER_CORREL}")

# ============================================
# SUGGESTIONS DE PORTEFEUILLE
# ============================================
def suggerer_portefeuille():
    """Suggere des poids de portefeuille base sur Sharpe et correlation."""
    if not os.path.exists(FICHIER_CORREL):
        analyser_correlation()

    try:
        with open(FICHIER_CORREL, "r") as f:
            data = json.load(f)
    except Exception:
        print("Analyse de correlation impossible.")
        return

    perfs = data["performances"]
    correl = data["correlation"]

    print("=" * 70)
    print("SUGGESTIONS DE POIDS DE PORTEFEUILLE")
    print("=" * 70)
    print("\nScore = Sharpe moyen * (1 - correlation moyenne avec les autres)")
    print("Plus le score est eleve, plus la strategie merite du poids.\n")

    scores = {}
    for strat in data["strategies"]:
        sharpe = perfs[strat].get("sharpe", 0)
        # correlation moyenne avec les autres strategies
        autres = [correl[strat][s] for s in data["strategies"] if s != strat]
        corr_moy = sum(autres) / len(autres) / 100 if autres else 0
        # Score: bon Sharpe + faible correlation = score eleve
        score = sharpe * (1 - corr_moy)
        scores[strat] = {
            "sharpe": sharpe,
            "corr_moy": corr_moy * 100,
            "score": round(score, 3),
        }

    # Poids proportionnel au score (seulement si score positif)
    total_positif = sum(max(0, s["score"]) for s in scores.values())
    for strat in sorted(scores.keys(), key=lambda x: scores[x]["score"], reverse=True):
        s = scores[strat]
        poids = (max(0, s["score"]) / total_positif * 100) if total_positif > 0 else 0
        print(f"  {strat:<24} Sharpe {s['sharpe']:.2f} | corr {s['corr_moy']:.0f}% | "
              f"score {s['score']:.3f} -> poids {poids:.0f}%")

    print("\nInterpretation:")
    print("  - Poids eleve = bonne strategie, peu correlee aux autres (diversifie)")
    print("  - Poids 0 = score negatif (Sharpe negatif) -> a exclure")
    print("  - Objectif: combiner des strategies avec poids > 0 pour lisser le risque")

# ============================================
# COMMANDES
# ============================================
def aide():
    print("""
PHASE 4 - DIVERSIFICATION + CORRELATION
========================================
Commandes:
  python strategies_phase4.py                Backteste les 4 nouvelles strategies
  python strategies_phase4.py crypto         Focus sur un marche
  python strategies_phase4.py correlation    Matrice de correlation entre strategies
  python strategies_phase4.py portfolio      Suggestions de poids de portefeuille

Nouvelles strategies:
  5. Volatility Squeeze   Compression de vol puis breakout
  6. Z-Score Reversion    Mean reversion normalisee (plus robuste que RSI)
  7. Trend Filter Combo    Momentum filtre par tendance long terme
  8. Dual Timeframe        Tendance LT + entree sur pullback court terme

Ces strategies explorent des edges differents des 4 originales.
L'analyse de correlation identifie les strategies redondantes vs diversifiantes.
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        aide()
        sys.exit(0)
    cmd = sys.argv[1].lower()
    if cmd == "correlation":
        analyser_correlation()
    elif cmd == "portfolio":
        suggerer_portefeuille()
    elif cmd in ACTIFS.keys():
        tester_nouvelles(categorie=cmd)
    elif cmd == "tester":
        if len(sys.argv) > 2:
            actif = sys.argv[2]
            print(f"Test des nouvelles strategies sur {actif}:")
            bougies = historique_ohlcv(actif, "1d", 365)
            if bougies:
                for nom, fonc in NOUVELLES_STRATEGIES.items():
                    stats = simuler_pro(bougies, fonc, "test", actif)
                    if stats:
                        print(f"  {nom}: {stats['verdict']} {stats['retour_pct']:+.2f}%")
        else:
            print("Usage: python strategies_phase4.py tester <actif>")
    else:
        tester_nouvelles()
