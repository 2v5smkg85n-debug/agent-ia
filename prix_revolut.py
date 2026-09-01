#!/usr/bin/env python3
"""
Prix Revolut X — Recupere les prix crypto depuis l'API publique de Revolut X.

API publique (sans authentification):
  GET https://revx.revolut.com/api/2.0/public/order-book/{SYMBOL}-EUR

Retourne le mid-price (moyenne bid/ask) en EUR pour chaque crypto.
Cache de 300 secondes (5 minutes) pour eviter le spam API.
"""
import json
import os
import time
import urllib.request

CACHE_TTL = 300  # 5 minutes (matche l'intervalle du bot)
_cache = {}

# Symboles qui n'existent PAS sur Revolut X (evite les erreurs 400)
BLACKLIST = {"COMP", "IMX", "AXS", "CAKE", "SAND", "FLOKI", "PEPE", "MATIC", "SUI", "RNDR", "OCEAN"}
# Symboles avec spread anormal sur Revolut X: pas de nouvelles positions, mais monitoring OK
SPREAD_BLACKLIST = {"BNBUSDT", "AAVEUSDT", "SUIUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "SOLUSDT", "TIAUSDT", "WIFUSDT", "CRVUSDT", "INJUSDT", "NEARUSDT", "FETUSDT"}

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
    # MATICUSDT, PEPEUSDT, FLOKIUSDT retirés (blacklist Revolut X)
    "UNIUSDT": "UNI",
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
    # FLOKIUSDT retiré (blacklist Revolut X)
    "OPUSDT": "OP",
    "INJUSDT": "INJ",
}

# Mapping inverse (symbole court -> symbole bot)
SYMBOLES_BOT = {v: k for k, v in SYMBOLES_REVOLUT.items()}


def get_spread_pct(symbole):
    """Retourne le spread (%) entre bid et ask sur Revolut X.
    0 si erreur ou symbole indisponible."""
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "").upper()
    if symbole_court in BLACKLIST:
        return 100.0  # trop risque
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
            return 100.0
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        if best_bid <= 0:
            return 100.0
        spread = abs(best_ask - best_bid) / best_bid * 100
        return spread
    except Exception:
        return 100.0


def get_prix_revolut(symbole, force_refresh=False):
    """
    Recupere le mid-price d'un symbole depuis Revolut X.
    
    Args:
        symbole: symbole bot (ex: "BTCUSDT") ou court (ex: "BTC")
        force_refresh: bypass le cache (pour les check SL)
    
    Returns:
        prix (float) en EUR, ou 0 si erreur
    """
    # Normaliser le symbole
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "")
    symbole_court = symbole_court.upper()

    # Skip si dans la blacklist (n'existe pas sur Revolut X)
    if symbole_court in BLACKLIST:
        return 0

    # Verifier le cache (sauf si force_refresh)
    cache_key = symbole_court
    if not force_refresh and cache_key in _cache:
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
        _err = str(e)
        if "429" in _err:
            # Rate limit: attend 2s et réessaie une fois
            time.sleep(2.0)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                bids = data.get("data", {}).get("bids", [])
                asks = data.get("data", {}).get("asks", [])
                if bids and asks:
                    best_bid = float(bids[0]["price"])
                    best_ask = float(asks[0]["price"])
                    mid_price = (best_bid + best_ask) / 2
                    spread_pct = abs(best_ask - best_bid) / best_bid if best_bid > 0 else 1
                    if spread_pct > 0.05:
                        mid_price = best_bid
                    _cache[cache_key] = {"prix": mid_price, "timestamp": time.time()}
                    return mid_price
            except Exception:
                pass
        print("  [REVOLUT] Erreur prix " + symbole_court + ": " + _err)
        return 0


def _prix_coingecko(symbole_court):
    """Fallback: recupere le prix via CoinGecko (API publique gratuite)."""
    try:
        # Mapping symbole -> id CoinGecko
        mapping = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "BNB": "binancecoin", "XRP": "ripple", "DOGE": "dogecoin",
            "AVAX": "avalanche-2", "LINK": "chainlink", "ARB": "arbitrum",
            "NEAR": "near", "LDO": "lido-dao", "AAVE": "aave",
            "PENDLE": "pendle", "FET": "fetch-ai", "RENDER": "render-token",
            "APT": "aptos", "UNI": "uniswap", "PEPE": "pepe",
            "DOT": "polkadot", "ATOM": "cosmos", "SUI": "sui",
            "SEI": "sei-network", "TIA": "celestia", "WIF": "dogwifcoin",
            "FLOKI": "floki", "OP": "optimism", "INJ": "injective-protocol",
        }
        coin_id = mapping.get(symbole_court, "")
        if not coin_id:
            return 0
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=eur"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        prix = data.get(coin_id, {}).get("eur", 0)
        if prix > 0:
            print(f"  [COINGECKO] Fallback {symbole_court}: {prix} EUR")
        return prix
    except Exception as e:
        if "429" in str(e):
            # Rate limit CoinGecko: attend 3s et réessaie
            time.sleep(3.0)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                prix = data.get(coin_id, {}).get("eur", 0)
                if prix > 0:
                    print(f"  [COINGECKO] Fallback {symbole_court}: {prix} EUR")
                return prix
            except Exception:
                pass
        return 0


def get_prix_secours(symbole):
    """Prix avec fallback: Revolut X (force refresh) puis CoinGecko."""
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "").upper()
    # 1. Revolut X sans cache
    prix = get_prix_revolut(symbole, force_refresh=True)
    if prix and prix > 0:
        return prix
    # 2. Fallback CoinGecko
    prix = _prix_coingecko(symbole_court)
    return prix


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
            time.sleep(1.0)  # Delai anti rate-limit Revolut X
        prix = get_prix_revolut(sym)
        resultats[sym] = prix
    return resultats


# Cache du taux EUR/USDT (mis a jour depuis Revolut X BTC)
_eur_usdt_rate = 0
_eur_usdt_ts = 0

def _get_eur_usdt_rate():
    """Recupere le taux EUR/USDT depuis Revolut X BTC (cache 5 min)."""
    global _eur_usdt_rate, _eur_usdt_ts
    if _eur_usdt_rate > 0 and (time.time() - _eur_usdt_ts) < 300:
        return _eur_usdt_rate
    # BTC en EUR depuis Revolut (utilise cache, pas force_refresh)
    btc_eur = get_prix_revolut("BTCUSDT")
    if btc_eur > 0:
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            btc_usdt = float(data["price"])
            if btc_usdt > 0:
                _eur_usdt_rate = btc_eur / btc_usdt
                _eur_usdt_ts = time.time()
                return _eur_usdt_rate
        except Exception:
            pass
    # Fallback: taux fixe approximatif
    if _eur_usdt_rate == 0:
        _eur_usdt_rate = 0.92  # ~1 USD = 0.92 EUR
    return _eur_usdt_rate

def get_prix_binance_batch(symboles):
    """Recupere les prix de plusieurs cryptos en UN SEUL appel Binance.
    Retourne les prix en EUR (conversion USDT -> EUR via taux cache).
    Beaucoup plus rapide que Revolut X pour les SL checks."""
    if not symboles:
        return {}
    try:
        # Binance ticker/price accepte plusieurs symboles en un seul appel
        # Format: ?symbols=["BTCUSDT","ETHUSDT"]
        import urllib.parse
        symbols_json = json.dumps(symboles)
        symbols_encoded = urllib.parse.quote(symbols_json)
        url = f"https://api.binance.com/api/v3/ticker/price?symbols={symbols_encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        # Taux de conversion EUR/USDT
        _rate = _get_eur_usdt_rate()
        resultats = {}
        for item in data:
            sym = item["symbol"]
            prix_usdt = float(item["price"])
            resultats[sym] = prix_usdt * _rate  # Convertit en EUR
        return resultats
    except Exception:
        return {}


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
