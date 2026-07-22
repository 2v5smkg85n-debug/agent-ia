#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memoire_marche.py — Mémoire du marché: apprend l'évolution du marché crypto
sur ~7 ans et l'injecte dans la génération de l'evolver.

AVANT: l'evolver générait des stratégies sans comprendre comment les marchés
évoluent sur le long terme (cycles bull/bear, crashes, rallies). Il n'avait
aucune mémoire des montagnes russes historiques.

MAINTENANT: memoire_marche_prompt() fetch ~7 ans de BTC en daily, extrait:
  - rendements par année calendaire (la photo de l'évolution année par année)
  - drawdown max (pire crash jamais vu)
  - nombre de crashes >30%
  - volatilité annuelle
  - return total
et l'injecte dans le prompt de génération. L'IA comprend désormais les cycles.

La couche backtest (2 ans) valide les stratégies; la mémoire (7 ans) éduque la
génération. Complémentaire."""
import os
import math
import statistics
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def _fetch_btc_daily(nb_jours=3300):
    """~9 ans de BTC en daily (3300 jours) -> remonte à 2017 (bull ICO + crash 2018)."""
    try:
        from indicateurs import historique_ohlcv_long
        return historique_ohlcv_long("BTCUSDT", "1d", nb_jours)
    except Exception:
        return []


def _max_drawdown(closes):
    """Pire drawdown peak-to-trough sur la serie (en %)."""
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (peak - c) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd * 100


def _count_drawdowns(closes, thresh=0.30):
    """Nombre d'épisodes distincts de drawdown >= thresh (crashes)."""
    if not closes:
        return 0
    peak = closes[0]
    in_dd = False
    count = 0
    for c in closes:
        if c > peak:
            peak = c
        if peak <= 0:
            continue
        dd = (peak - c) / peak
        if dd >= thresh and not in_dd:
            count += 1
            in_dd = True
        elif dd < thresh * 0.4:
            in_dd = False  # récupéré
    return count


def memoire_marche_prompt():
    """Retourne un bloc mémoire du marché injecté dans le prompt evolver.
    Vide si données indisponibles (graceful)."""
    bougies = _fetch_btc_daily(3300)
    if len(bougies) < 365:
        return ""
    closes = [b["cloture"] for b in bougies if b.get("cloture")]
    if len(closes) < 365:
        return ""

    # Rendements par année calendaire (la photo de l'évolution)
    by_year = {}
    for b in bougies:
        try:
            yr = datetime.utcfromtimestamp(b["temps"] / 1000).year
        except Exception:
            continue
        cl = b.get("cloture")
        if cl:
            by_year.setdefault(yr, []).append(cl)
    yearly = []
    for yr in sorted(by_year):
        cs = by_year[yr]
        if len(cs) < 30:
            continue
        try:
            ret = (cs[-1] / cs[0] - 1) * 100
            yearly.append((yr, ret))
        except Exception:
            continue

    # Stats globales
    max_dd = _max_drawdown(closes)
    crashes = _count_drawdowns(closes, 0.30)
    try:
        total_ret = (closes[-1] / closes[0] - 1) * 100
    except Exception:
        total_ret = 0.0
    span_years = len(closes) / 365.25
    # Volatilité annuelle approx (ecart-type rendements daily * sqrt(365))
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]
    vol_an = (statistics.pstdev(rets) * math.sqrt(365) * 100) if len(rets) > 10 else 0.0

    lines = []
    lines.append(f"Marché BTC analysé sur {span_years:.1f} ans ({len(closes)} jours).")
    lines.append(f"Return total: {total_ret:+.0f}% | Volatilité annuelle: {vol_an:.0f}% "
                 f"| Drawdown max: -{max_dd:.0f}% | Crashes >30%: {crashes}")
    if yearly:
        lines.append("Rendements annuels (montagnes russes): "
                     + " | ".join(f"{y}: {r:+.0f}%" for y, r in yearly))
    lines.append("LECON: le crypto alterne bulls spectaculaires et bears brutaux "
                 "(-50% à -80%). Une stratégie robuste doit survivre aux bears "
                 "(stop-loss serré, peu de trades en tendance baissière) et "
                 "profiter des reversions dans les ranges. Évite le trend-following "
                 "naïf qui se fait détruire aux retournements. Le mean-reversion "
                 "modéré (RSI 20-35) historiquement bien dans les phases de range "
                 "qui suivent les crashes.")

    return ("\n\n## MEMOIRE DU MARCHÉ (évolution sur plusieurs années)\n"
            "Voici comment le marché crypto a évolué historiquement. "
            "Une stratégie robuste doit survivre à ces cycles.\n"
            + "\n".join(lines))


if __name__ == "__main__":
    print("=" * 60)
    print("MÉMOIRE DU MARCHÉ (apprentissage multi-années)")
    print("=" * 60)
    print(memoire_marche_prompt() or "(données indisponibles)")
