#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memoire_marche.py — Mémoire du marché multi-actifs: apprend l'évolution de
plusieurs classes d'actifs sur plusieurs années et l'injecte dans l'evolver.

AVANT: l'evolver ne comprenait que le BTC, et seulement via le backtest.
MAINTENANT: memoire_marche_prompt() fetch:
  - BTC + ETH (~9 ans, Binance daily) -> crypto
  - S&P 500, Apple, Nvidia, Microsoft (Yahoo range=max) -> actions
extrait par actif: rendements annuels, drawdown max, crashes, volatilité,
return total; puis compare crypto vs actions. L'IA comprend les différences
de régime entre classes d'actifs (crypto = volatil & cyclique, actions =
trend haussier régulier, etc.)."""
import os
import math
import statistics
from datetime import datetime

import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# (nom affiché, symbole, source)
ACTIFS = [
    ("BTC", "BTCUSDT", "binance"),
    ("ETH", "ETHUSDT", "binance"),
    ("S&P 500", "^GSPC", "yahoo"),
    ("Apple", "AAPL", "yahoo"),
    ("Nvidia", "NVDA", "yahoo"),
    ("Microsoft", "MSFT", "yahoo"),
]


def _fetch_binance_daily(symbole, nb_jours=3300):
    try:
        from indicateurs import historique_ohlcv_long
        return historique_ohlcv_long(symbole, "1d", nb_jours)
    except Exception:
        return []


def _fetch_yahoo_daily(symbole):
    """Yahoo Finance range=10y -> 10 ans de daily (range=max est casse: 168 barres)."""
    from urllib.parse import quote
    try:
        sym_enc = quote(symbole, safe="")
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym_enc}"
               f"?interval=1d&range=10y")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        res = data["chart"]["result"][0]
        timestamps = res.get("timestamp", [])
        q = res["indicators"]["quote"][0]
        bougies = []
        for i in range(len(timestamps)):
            c = q["close"][i]
            if c is None:
                continue
            bougies.append({"temps": timestamps[i] * 1000, "cloture": float(c)})
        return bougies
    except Exception:
        return []


def _max_drawdown(closes):
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
            in_dd = False
    return count


def _analyser_actif(bougies):
    """Retourne un dict de stats ou None si données insuffisantes."""
    if len(bougies) < 365:
        return None
    closes = [b["cloture"] for b in bougies if b.get("cloture")]
    if len(closes) < 365:
        return None

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

    # Affiche les 12 dernieres annees max (sinon trop long pour le S&P sur 100 ans)
    if len(yearly) > 12:
        yearly = yearly[-12:]

    max_dd = _max_drawdown(closes)
    crashes = _count_drawdowns(closes, 0.30)
    try:
        total_ret = (closes[-1] / closes[0] - 1) * 100
    except Exception:
        total_ret = 0.0
    span_years = len(closes) / 365.25
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]
    vol_an = (statistics.pstdev(rets) * math.sqrt(365) * 100) if len(rets) > 10 else 0.0

    return {
        "span": span_years,
        "total": total_ret,
        "vol": vol_an,
        "max_dd": max_dd,
        "crashes": crashes,
        "yearly": yearly,
    }


def memoire_marche_prompt():
    """Retourne un bloc mémoire multi-actifs injecté dans le prompt evolver.
    Vide si aucune donnée (graceful)."""
    blocs = []
    for nom, sym, source in ACTIFS:
        if source == "binance":
            bougies = _fetch_binance_daily(sym)
        else:
            bougies = _fetch_yahoo_daily(sym)
        st = _analyser_actif(bougies)
        if not st:
            continue
        ligne0 = (f"- {nom} ({st['span']:.1f} ans): return total {st['total']:+.0f}% | "
                  f"volatilité {st['vol']:.0f}% | drawdown max -{st['max_dd']:.0f}% | "
                  f"crashes >30%: {st['crashes']}")
        ligne1 = ""
        if st["yearly"]:
            ligne1 = "      rendements annuels: " + " | ".join(
                f"{y}: {r:+.0f}%" for y, r in st["yearly"])
        blocs.append(ligne0 + ("\n" + ligne1 if ligne1 else ""))

    if not blocs:
        return ""

    # Leçon comparative crypto vs actions
    lecon = (
        "LECON: le crypto (BTC/ETH) est ~3-5x plus volatil que les actions et alterne "
        "bulls spectaculaires (+150-300%) et bears brutaux (-65-83%). Les actions "
        "(S&P 500/tech) trendent plus regulièrement haussier avec des drawdowns moins "
        "profonds (-30-50%) et une volatilité ~2-3x plus faible. Les strategies "
        "mean-reversion (RSI survente) performent en crypto dans les ranges post-crash; "
        "le trend-following modéré marche mieux sur actions. Adapte le stop-loss et la "
        "taille de position a la volatilité de la classe d'actif."
    )

    return ("\n\n## MEMOIRE DU MARCHÉ (évolution multi-actifs sur plusieurs années)\n"
            "Voici comment chaque classe d'actifs a évolué. "
            "Une stratégie robuste doit survivre à ces cycles.\n"
            + "\n".join(blocs) + "\n" + lecon)


if __name__ == "__main__":
    print("=" * 60)
    print("MÉMOIRE DU MARCHÉ (multi-actifs, plusieurs années)")
    print("=" * 60)
    print(memoire_marche_prompt() or "(données indisponibles)")
