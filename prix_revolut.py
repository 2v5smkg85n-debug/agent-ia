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

CACHE_TTL = 300  # 5 minutes (matche l'intervalle du bot)
_cache = {}

# Symboles qui n'existent PAS sur Revolut X (evite les erreurs 400)
BLACKLIST = {"SUIA", "COMP", "IMX", "AXS", "CAKE", "SAND"}

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
    "RNDRUSDT": "RENDER",
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
    "SEIUSDT": "SEI",
    "TIAUSDT": "TIA",
    "WIFUSDT": "WIF",
    "FLOKIUSDT": "FLOKI",
    "OPUSDT": "OP",
    "INJUSDT": "INJ",
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

    # Skip si dans la blacklist (n'existe pas sur Revolut X)
    if symbole_court in BLACKLIST:
        return 0

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

        # Si le spread est trop large (>5%), le carnet est desequilibre
        # On utilise le cote avec le plus de volume (generallement le bid)
        spread_pct = abs(best_ask - best_bid) / best_bid if best_bid > 0 else 1
        if spread_pct > 0.05:
            # Carno anormal - utiliser le bid (prix realiste)
            mid_price = best_bid
            print("  [REVOLUT] Spread anormal pour " + symbole_court + ": bid=" + str(best_bid) + " ask=" + str(best_ask) + " -> utilise bid")

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
            time.sleep(3.0)  # Delai anti rate-limit Revolut X
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


def get_candles_revolut(symbole, intervalle=15, nombre=20):
    """
    Recupere les bougies OHLC depuis Revolut X.
    
    Args:
        symbole: symbole bot (ex: "BTCUSDT") ou court (ex: "BTC")
        intervalle: intervalle en minutes (15 par defaut)
        nombre: nombre de bougies a recuperer
    
    Returns:
        liste de dict {"time", "open", "high", "low", "close"}
    """
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "")
    symbole_court = symbole_court.upper()
    if symbole_court in BLACKLIST:
        return []
    try:
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - nombre * intervalle * 60 * 1000
        url = f"https://revx.revolut.com/api/1.0/public/candles/{symbole_court}-EUR?interval={intervalle}&since={since_ms}&until={now_ms}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        candles_raw = data.get("data", [])
        candles = []
        for c in candles_raw:
            candles.append({
                "time": int(c.get("start", 0)) // 1000,
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0))
            })
        return candles[-nombre:]
    except Exception as e:
        return []


def lister_symboles_disponibles():
    """Retourne la liste des symboles supportes."""
    return sorted(SYMBOLES_REVOLUT.keys())


if __name__ == "__main__":
    # Test
    print("Test prix Revolut X:")
    for sym in ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"]:
        prix = get_prix_revolut(sym)
        print("  " + sym + ": " + str(prix) + " EUR")
