#!/usr/bin/env python3
"""
Tracking Whales On-Chain — Suit les gros portefeuilles et mouvements on-chain.

Sources:
  1. Whale Alert API (mouvements >500k USD sur BTC, ETH, USDT)
  2. Binance Long/Short ratio (positionnement des traders)
  3. Glassnode-like metrics via API publiques

Retourne un score: -5 (pressure vente) a +5 (pressure achat)
"""
import json
import os
import time
import urllib.request
from datetime import datetime

CACHE_TTL = 300
_cache = {}


def get_whale_alert():
    """
    Recupere les grandes transactions via Whale Alert API (sans cle, limitees).
    Fallback: utilise l'API publique Binance pour le ratio long/short.
    """
    try:
        # Whale Alert API publique (sans cle, donnees limitees)
        url = "https://api.whale-alert.io/v1/transactions?api_key=&min_value=500000&start=" + str(int(time.time()) - 3600)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        transactions = data.get("transactions", [])
        if not transactions:
            return 0, 0, []

        # Analyser les transactions
        influx_exchange = 0  # vers exchanges = bearish (vente potentielle)
        outflux_exchange = 0  # hors exchanges = bullish (accumulation)
        top_tx = []

        for tx in transactions[:50]:
            from_type = tx.get("from", {}).get("owner_type", "")
            to_type = tx.get("to", {}).get("owner_type", "")
            value = tx.get("amount_usd", 0)

            if from_type == "exchange" and to_type != "exchange":
                outflux_exchange += value  # retrait = bullish
            elif to_type == "exchange" and from_type != "exchange":
                influx_exchange += value  # depot = bearish

            blockchain = tx.get("blockchain", "")
            symbol = tx.get("symbol", "")
            top_tx.append(str(value / 1e6) + "M$ " + symbol.upper() + " (" + blockchain + ")")

        total = influx_exchange + outflux_exchange
        if total == 0:
            return 0, len(transactions), top_tx[:3]

        # Score: plus de retraits que de depots = bullish
        score = ((outflux_exchange - influx_exchange) / total) * 5  # -5 a +5
        score = max(-5, min(5, score))

        return score, len(transactions), top_tx[:5]

    except Exception as e:
        print("  [WHALE] Whale Alert erreur: " + str(e))
        # Fallback: Binance Long/Short ratio
        return get_binance_ls_ratio()


def get_binance_ls_ratio():
    """
    Ratio Long/Short de Binance (indique le positionnement des traders).
    Beaucoup de longs = potentiellement bullish mais aussi risque de squeeze.
    """
    try:
        scores = []
        symbols = ["BTCUSDT", "ETHUSDT"]

        for sym in symbols:
            url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio/symbol=" + sym + "&period=1h&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            if data:
                ratio = float(data[0].get("longShortRatio", 1.0))
                # ratio > 1 = plus de longs que de shorts
                # Score: 1.0 = neutre, >2 = tres bullish (ou squeeze risk), <0.5 = bearish
                score = min(5, max(-5, (ratio - 1.0) * 5))
                scores.append(score)

        score_moyen = sum(scores) / len(scores) if scores else 0
        return score_moyen, len(symbols), ["Binance L/S ratio"]
    except Exception as e:
        print("  [WHALE] Binance L/S erreur: " + str(e))
        return 0, 0, []


def get_tether_supply():
    """
    Verifie l'evolution de l'offre USDT (Tether).
    Creation de USDT = potentiellement bullish (nouveau capital entre dans le marche).
    """
    try:
        url = "https://api.coingecko.com/api/v3/coins/tether"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        market_cap = data.get("market_data", {}).get("market_cap", {}).get("usd", 0)
        # Pas d'historique sans cle, mais on peut logger la valeur
        return market_cap
    except Exception as e:
        print("  [WHALE] Tether supply erreur: " + str(e))
        return 0


def score_whale_onchain(symbole=None):
    """
    Score global whale + on-chain.
    Combine: Whale Alert + Binance L/S + Tether supply.
    
    Returns:
        {
            "score_total": float (-5 a +5),
            "whale_score": float,
            "ls_score": float,
            "nb_transactions": int,
            "tether_supply": float,
            "top_mouvements": list,
            "verdict": str,
        }
    """
    cache_key = symbole or "global"
    if cache_key in _cache:
        if time.time() - _cache[cache_key]["timestamp"] < CACHE_TTL:
            return _cache[cache_key]["result"]

    print("  [WHALE] Scan whale + on-chain...")

    # 1. Whale Alert (ou Binance L/S en fallback)
    whale_score, nb_tx, top_mouvements = get_whale_alert()

    # 2. Binance L/S ratio
    ls_score, ls_count, _ = get_binance_ls_ratio()

    # 3. Tether supply (juste pour info)
    tether_supply = get_tether_supply()

    # Score combine (Whale Alert 50%, L/S ratio 50%)
    score_total = (whale_score * 0.5) + (ls_score * 0.5)

    if score_total >= 2:
        verdict = "ACCUMULATION FORTE"
    elif score_total >= 0.5:
        verdict = "ACCUMULATION"
    elif score_total <= -2:
        verdict = "DISTRIBUTION FORTE"
    elif score_total <= -0.5:
        verdict = "DISTRIBUTION"
    else:
        verdict = "EQUILIBRE"

    result = {
        "score_total": round(score_total, 2),
        "whale_score": round(whale_score, 2),
        "ls_score": round(ls_score, 2),
        "nb_transactions": nb_tx,
        "tether_supply": tether_supply,
        "top_mouvements": top_mouvements,
        "verdict": verdict,
    }

    _cache[cache_key] = {"result": result, "timestamp": time.time()}
    print("  [WHALE] Score: " + str(result["score_total"]) + " (" + verdict + ")")
    return result


def rapport_whale(symbole=None):
    """Genere un rapport lisible pour Telegram."""
    r = score_whale_onchain(symbole)

    rapport = "WHALE & ON-CHAIN\n"
    rapport += "=================\n\n"

    emoji = {"ACCUMULATION FORTE": "🐋", "ACCUMULATION": "🟢", "EQUILIBRE": "🟡", "DISTRIBUTION": "🔴", "DISTRIBUTION FORTE": "💥"}
    rapport += "Verdict: " + emoji.get(r["verdict"], "⚪") + " " + r["verdict"] + "\n"
    rapport += "Score: " + str(r["score_total"]) + "/5\n\n"

    rapport += "Whale Alert: " + str(r["whale_score"]) + " (" + str(r["nb_transactions"]) + " tx)\n"
    rapport += "Binance L/S: " + str(r["ls_score"]) + "\n"
    if r["tether_supply"]:
        rapport += "Tether supply: " + str(r["tether_supply"] / 1e9) + "B $\n"

    if r.get("top_mouvements"):
        rapport += "\nTop mouvements:\n"
        for mvt in r["top_mouvements"][:3]:
            rapport += "- " + str(mvt) + "\n"

    return rapport


if __name__ == "__main__":
    print(rapport_whale())
