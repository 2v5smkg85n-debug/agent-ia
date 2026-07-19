#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bougies_patterns.py — Lecture des chandeliers japonais (candlestick patterns).

Detecte les patterns classiques sur les dernieres bougies et retourne un biais
haussier/baissier + confiance. Patterns: engulfing, marteau (hammer), etoile
filante (shooting star), marubozu, doji, morning/evening star.

biais: -1.0 (tres baissier) .. +1.0 (tres haussier)
confiance: 0.0 .. 1.0 (nombre/poids des patterns detectes)

MODE DETECTEUR + BACKTEST: on valide d'abord que le biais predit l'issue des
trades avant d'integrer (discipline = ADX/trailing/EXTEND).
"""
import os, sys


def _ohlc(b):
    """Extrait OHLC d'une bougie (FR ou EN)."""
    o = float(b.get("ouverture", b.get("open", 0)) or 0)
    h = float(b.get("plus_haut", b.get("high", 0)) or 0)
    l = float(b.get("plus_bas", b.get("low", 0)) or 0)
    c = float(b.get("cloture", b.get("close", 0)) or 0)
    return o, h, l, c


def _body(o, c):
    return abs(c - o)


def _range(o, h, l, c):
    return max(h - l, 1e-9)


def analyser_patterns(bougies, lookback=3):
    """Analyse les dernieres bougies. Retourne {biais, confiance, patterns, detail}."""
    if not bougies or len(bougies) < 3:
        return {"biais": 0.0, "confiance": 0.0, "patterns": [], "detail": []}
    recentes = bougies[-lookback:]
    o0, h0, l0, c0 = _ohlc(recentes[-3])  # avant-avant-derniere
    o1, h1, l1, c1 = _ohlc(recentes[-2])  # avant-derniere
    o2, h2, l2, c2 = _ohlc(recentes[-1])  # derniere
    b1 = _body(o1, c1); b2 = _body(o2, c2)
    r1 = _range(o1, h1, l1, c1); r2 = _range(o2, h2, l2, c2)
    # mèche haute / basse de la derniere bougie
    meche_haute = h2 - max(o2, c2)
    meche_basse = min(o2, c2) - l2

    patterns = []
    detail = []
    score = 0.0  # + haussier, - baissier

    # 1) Engulfing haussier: verte englobe la rouge precedente
    if c2 > o2 and c1 < o1 and o2 <= c1 and c2 >= o1 and b2 > b1:
        patterns.append("engulfing_haussier"); score += 0.5
        detail.append(("engulfing_haussier", +0.5))
    # 2) Engulfing baissier: rouge englobe la verte
    if c2 < o2 and c1 > o1 and o2 >= c1 and c2 <= o1 and b2 > b1:
        patterns.append("engulfing_baissier"); score -= 0.5
        detail.append(("engulfing_baissier", -0.5))
    # 3) Marteau (hammer) haussier: petite body haut, longue mèche basse
    if b2 > 0 and meche_basse > 2 * b2 and meche_haute < b2 and c2 >= o2:
        patterns.append("marteau_haussier"); score += 0.3
        detail.append(("marteau_haussier", +0.3))
    # Marteau inversé baissier apres hausse
    if b2 > 0 and meche_haute > 2 * b2 and meche_basse < b2 and c2 <= o2:
        patterns.append("etoile_filante"); score -= 0.3
        detail.append(("etoile_filante", -0.3))
    # 4) Marubozu haussier (forte conviction haussiere)
    if r2 > 0 and b2 > 0.85 * r2 and c2 > o2:
        patterns.append("marubozu_haussier"); score += 0.25
        detail.append(("marubozu_haussier", +0.25))
    if r2 > 0 and b2 > 0.85 * r2 and c2 < o2:
        patterns.append("marubozu_baissier"); score -= 0.25
        detail.append(("marubozu_baissier", -0.25))
    # 5) Morning star (3 bougies, retournement haussier)
    if c0 < o0 and c1 < o1 and b1 < 0.3 * r1 and c2 > o2 and c2 > (o1 + c1) / 2:
        patterns.append("morning_star"); score += 0.45
        detail.append(("morning_star", +0.45))
    # Evening star (retournement baissier)
    if c0 > o0 and c1 > o1 and b1 < 0.3 * r1 and c2 < o2 and c2 < (o1 + c1) / 2:
        patterns.append("evening_star"); score -= 0.45
        detail.append(("evening_star", -0.45))
    # 6) Doji: indecision (neutre)
    if r2 > 0 and b2 < 0.1 * r2:
        patterns.append("doji");  # neutre
        detail.append(("doji", 0.0))

    biais = max(-1.0, min(1.0, score))
    confiance = min(1.0, abs(score) / 1.0)
    return {
        "biais": round(biais, 2),
        "confiance": round(confiance, 2),
        "patterns": patterns,
        "detail": detail,
    }


def biais_bougies(bougies, lookback=3):
    """Raccourci: retourne juste le biais (-1..+1)."""
    return analyser_patterns(bougies, lookback).get("biais", 0.0)


# ---- TEST standalone ----
if __name__ == "__main__":
    # demo sur BTC recent
    try:
        from indicateurs import historique_ohlcv
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "GC=F"]:
            bougies = historique_ohlcv(sym, "1h", 50)
            if bougies:
                r = analyser_patterns(bougies)
                print(f"{sym}: biais={r['biais']:+.2f} conf={r['confiance']:.2f} "
                      f"patterns={r['patterns'] or '-'}")
            else:
                print(f"{sym}: pas de donnees")
    except Exception as e:
        print(f"erreur demo: {e}")
