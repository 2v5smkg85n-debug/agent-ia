#!/usr/bin/env python3
"""
Multi-Timeframe Avance — Analyse 6 timeframes simultanement pour confirmer les signaux.

Timeframes: 1m, 5m, 15m, 1h, 4h, 1j
Pour chaque timeframe: RSI, SMA20 vs SMA50, MACD, momentum
Score: -5 (bearish tous TF) a +5 (bullish tous TF)

Un signal est valide seulement si au moins 4/6 timeframes sont d'accord.
"""
import json
import math
import os
import time
import urllib.request
from datetime import datetime

CACHE_TTL = 120  # 2 minutes (timeframes courts changent vite)
_cache = {}

TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


def get_klines_binance(symbole, intervalle, limite=100):
    """Recupere les bougies (klines) de Binance pour un timeframe donne."""
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=" + symbole + "&interval=" + intervalle + "&limit=" + str(limite)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        # Format Binance: [open_time, open, high, low, close, volume, ...]
        prix_fermes = [float(k[4]) for k in data]
        volumes = [float(k[5]) for k in data]
        return prix_fermes, volumes
    except Exception as e:
        print("  [MTF] Erreur klines " + symbole + " " + intervalle + ": " + str(e))
        return [], []


def calculer_rsi(prix, periode=14):
    """Calcule le RSI a partir d'une liste de prix."""
    if len(prix) < periode + 1:
        return 50.0

    gains = []
    pertes = []
    for i in range(1, len(prix)):
        diff = prix[i] - prix[i-1]
        gains.append(max(diff, 0))
        pertes.append(max(-diff, 0))

    # Moyenne mobile simple sur la premiere periode
    avg_gain = sum(gains[:periode]) / periode if periode <= len(gains) else 0
    avg_perte = sum(pertes[:periode]) / periode if periode <= len(pertes) else 0

    # Wilder's smoothing
    for i in range(periode, len(gains)):
        avg_gain = (avg_gain * (periode - 1) + gains[i]) / periode
        avg_perte = (avg_perte * (periode - 1) + pertes[i]) / periode

    if avg_perte == 0:
        return 100.0
    rs = avg_gain / avg_perte
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculer_sma(prix, periode):
    """Simple Moving Average."""
    if len(prix) < periode:
        return sum(prix) / len(prix) if prix else 0
    return sum(prix[-periode:]) / periode


def analyser_timeframe(prix, volumes):
    """
    Analyse un timeframe donne.
    Retourne: (score -1/0/+1, rsi, details)
    """
    if len(prix) < 20:
        return 0, 50, "donnees insuffisantes"

    rsi = calculer_rsi(prix)
    sma20 = calculer_sma(prix, 20)
    sma50 = calculer_sma(prix, min(50, len(prix)))
    prix_actuel = prix[-1]

    score = 0
    details = []

    # 1. RSI
    if rsi < 30:
        score += 1
        details.append("RSI survente " + str(round(rsi, 1)))
    elif rsi > 70:
        score -= 1
        details.append("RSI surachat " + str(round(rsi, 1)))
    else:
        details.append("RSI " + str(round(rsi, 1)))

    # 2. SMA20 vs SMA50 (tendance)
    if sma20 > sma50:
        score += 1
        details.append("SMA20>SMA50 haussier")
    else:
        score -= 1
        details.append("SMA20<SMA50 baissier")

    # 3. Prix vs SMA20 (momentum court terme)
    if prix_actuel > sma20:
        score += 0.5
        details.append("prix>SMA20")
    else:
        score -= 0.5
        details.append("prix<SMA20")

    # 4. Volume (confirmation)
    if len(volumes) >= 2:
        vol_moyen = sum(volumes[-10:]) / min(10, len(volumes))
        vol_actuel = volumes[-1]
        if vol_actuel > vol_moyen * 1.5:
            # Volume eleve = mouvement fort
            if score > 0:
                score += 0.5
                details.append("volume eleve confirme")
            elif score < 0:
                score -= 0.5
                details.append("volume eleve contre")

    # Normaliser entre -1 et +1
    score = max(-1, min(1, score / 3))

    return score, rsi, " | ".join(details)


def score_multi_timeframe(symbole):
    """
    Analyse le symbole sur 6 timeframes.
    
    Returns:
        {
            "score_total": float (-5 a +5),
            "timeframes": dict par TF,
            "nb_bullish": int,
            "nb_bearish": int,
            "consensus": bool (au moins 4/6 d'accord),
            "direction": str,
            "verdict": str,
        }
    """
    cache_key = symbole
    if cache_key in _cache:
        if time.time() - _cache[cache_key]["timestamp"] < CACHE_TTL:
            return _cache[cache_key]["result"]

    # S'assurer que le symbole finit par USDT
    if not symbole.endswith("USDT"):
        symbole = symbole + "USDT"

    print("  [MTF] Analyse " + symbole + " sur 6 timeframes...")

    tf_results = {}
    total_score = 0
    nb_bullish = 0
    nb_bearish = 0

    for tf in TIMEFRAMES:
        prix, volumes = get_klines_binance(symbole, tf, limite=100)
        if not prix:
            tf_results[tf] = {"score": 0, "rsi": 50, "details": "erreur API"}
            continue

        score, rsi, details = analyser_timeframe(prix, volumes)
        tf_results[tf] = {
            "score": round(score, 2),
            "rsi": round(rsi, 1),
            "prix": prix[-1],
            "details": details,
        }
        total_score += score
        if score > 0.2:
            nb_bullish += 1
        elif score < -0.2:
            nb_bearish += 1

    # Consensus: au moins 4/6 timeframes dans la meme direction
    consensus = (nb_bullish >= 4) or (nb_bearish >= 4)

    if nb_bullish >= 4:
        direction = "HAUSSIER"
    elif nb_bearish >= 4:
        direction = "BAISSIER"
    elif nb_bullish >= nb_bearish:
        direction = "LEGEREMENT HAUSSIER"
    else:
        direction = "LEGEREMENT BAISSIER"

    # Score total: -5 a +5
    score_total = max(-5, min(5, total_score * 5 / len(TIMEFRAMES)))

    if score_total >= 2:
        verdict = "ACHAT FORT - Multi-TF aligne"
    elif score_total >= 0.5:
        verdict = "ACHAT - Multi-TF favorable"
    elif score_total <= -2:
        verdict = "VENTE FORT - Multi-TF aligne"
    elif score_total <= -0.5:
        verdict = "VENTE - Multi-TF defavorable"
    else:
        verdict = "ATTENDRE - Signaux mixtes"

    result = {
        "score_total": round(score_total, 2),
        "timeframes": tf_results,
        "nb_bullish": nb_bullish,
        "nb_bearish": nb_bearish,
        "consensus": consensus,
        "direction": direction,
        "verdict": verdict,
    }

    _cache[cache_key] = {"result": result, "timestamp": time.time()}
    print("  [MTF] " + symbole + ": " + str(nb_bullish) + "H/" + str(nb_bearish) + "B score " + str(round(score_total, 2)) + " (" + verdict + ")")
    return result


def rapport_mtf(symbole):
    """Genere un rapport lisible pour Telegram."""
    r = score_multi_timeframe(symbole)

    rapport = "MULTI-TIMEFRAME " + symbole + "\n"
    rapport += "===========================\n\n"

    emoji = {"HAUSSIER": "🟢", "BAISSIER": "🔴", "LEGEREMENT HAUSSIER": "🟡", "LEGEREMENT BAISSIER": "🟠"}
    rapport += "Direction: " + emoji.get(r["direction"], "⚪") + " " + r["direction"] + "\n"
    rapport += "Score: " + str(r["score_total"]) + "/5\n"
    rapport += "Consensus: " + ("OUI (4+ TF alignes)" if r["consensus"] else "NON (signaux mixtes)") + "\n"
    rapport += "Bullish: " + str(r["nb_bullish"]) + "/6 | Bearish: " + str(r["nb_bearish"]) + "/6\n\n"

    rapport += "Details par timeframe:\n"
    for tf in TIMEFRAMES:
        info = r["timeframes"].get(tf, {})
        score = info.get("score", 0)
        rsi = info.get("rsi", 0)
        emoji_tf = "🟢" if score > 0.2 else ("🔴" if score < -0.2 else "🟡")
        rapport += emoji_tf + " " + tf + ": RSI " + str(rsi) + " (" + str(score) + ")\n"

    rapport += "\n" + r["verdict"]
    return rapport


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(rapport_mtf(sym))
