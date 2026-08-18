#!/usr/bin/env python3
"""
Prix Revolut X — Recupere les prix crypto depuis l'API publique de Revolut X.

API publique (sans authentification):
  GET https://revx.revolut.com/api/2.0/public/order-book/{SYMBOL}-EUR

Retourne le mid-price (moyenne bid/ask) en EUR pour chaque crypto.
Cache de 60 secondes pour eviter le spam API.
"""
import json
import os
import time
import urllib.request

CACHE_TTL = 60  # 1 minute
_cache = {}

# Mapping symbole bot -> symbole Revolut X
SYMBOLES_REVOLUT = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "BNBUSDT": "BNB",
    "XRPUSDT": "XRP",
    "DOGEUSDT": "DOGE",
    "AVAXUSDT": "AVAX",
    "LINKUSDT": "LINK",
    "ARBUSDT": "ARB",
    "NEARUSDT": "NEAR",
    "LDOUSDT": "LDO",
    "AAVEUSDT": "AAVE",
    "PENDLEUSDT": "PENDLE",
    "FETUSDT": "FET",
    "RNDRUSDT": "RNDR",
    "OCEANUSDT": "OCEAN",
    "APTUSDT": "APT",
    "MATICUSDT": "MATIC",
    "UNIUSDT": "UNI",
    "PEPEUSDT": "PEPE",
    "ADAUSDT": "ADA",
    "DOTUSDT": "DOT",
    "TRXUSDT": "TRX",
    "SHIBUSDT": "SHIB",
    "LTCUSDT": "LTC",
    "ATOMUSDT": "ATOM",
    "SUIUSDT": "SUI",
}

# Mapping inverse (symbole court -> symbole bot)
SYMBOLES_BOT = {v: k for k, v in SYMBOLES_REVOLUT.items()}


def get_prix_revolut(symbole):
    """
    Recupere le mid-price d'un symbole depuis Revolut X.
    
    Args:
        symbole: symbole bot (ex: "BTCUSDT") ou court (ex: "BTC")
    
    Returns:
        prix (float) en EUR, ou 0 si erreur
    """
    # Normaliser le symbole
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "")
    symbole_court = symbole_court.upper()

    # Verifier le cache
    cache_key = symbole_court
    if cache_key in _cache:
        if time.time() - _cache[cache_key]["timestamp"] < CACHE_TTL:
            return _cache[cache_key]["prix"]

    try:
        url = "https://revx.revolut.com/api/2.0/public/order-book/" + symbole_court + "-EUR"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        bids = data.get("data", {}).get("bids", [])
        asks = data.get("data", {}).get("asks", [])

        if not bids or not asks:
            return 0

        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        mid_price = (best_bid + best_ask) / 2

        # Mettre en cache
        _cache[cache_key] = {"prix": mid_price, "timestamp": time.time()}

        return mid_price

    except Exception as e:
        print("  [REVOLUT] Erreur prix " + symbole_court + ": " + str(e))
        return 0


def get_prix_batch(symboles):
    """
    Recupere les prix de plusieurs symboles en batch.
    
    Args:
        symboles: liste de symboles bot (ex: ["BTCUSDT", "ETHUSDT"])
    
    Returns:
        dict {symbole_bot: prix_eur}
    """
    resultats = {}
    for i, sym in enumerate(symboles):
        if not sym:
            continue
        if i > 0:
            time.sleep(0.5)  # Delai anti rate-limit
        prix = get_prix_revolut(sym)
        resultats[sym] = prix
    return resultats


def get_prix_avec_variation(symbole):
    """
    Recupere le prix + variation 24h (si disponible).
    
    Returns:
        {"prix": float, "var_24h": float}
    """
    prix = get_prix_revolut(symbole)

    # Pour la variation 24h, on utilise le cache historique
    cache_key = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "").upper() + "_hist"
    if cache_key in _cache:
        old = _cache[cache_key]
        if prix > 0 and old.get("prix", 0) > 0:
            var_24h = ((prix - old["prix"]) / old["prix"]) * 100
        else:
            var_24h = 0
    else:
        var_24h = 0

    # Sauvegarder pour le prochain calcul
    _cache[cache_key] = {"prix": prix, "timestamp": time.time()}

    return {"prix": prix, "var_24h": var_24h}


def lister_symboles_disponibles():
    """Retourne la liste des symboles supportes."""
    return sorted(SYMBOLES_REVOLUT.keys())


if __name__ == "__main__":
    # Test
    print("Test prix Revolut X:")
    for sym in ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"]:
        prix = get_prix_revolut(sym)
        print("  " + sym + ": " + str(prix) + " EUR")
