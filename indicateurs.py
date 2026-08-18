#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INDICATEURS TECHNIQUES REELS - Calculs en vrai dans le code.
RSI, MACD, moyennes mobiles (SMA/EMA), Bandes de Bollinger.

Les signaux sont bases sur de vrais indicateurs, pas sur l'IA.
Plus precis, plus reproductible, plus rapide.

Usage:
    python indicateurs.py analyse BTCUSDT       # analyse complete d'un actif
    python indicateurs.py signaux               # signaux d'achat/vente sur tous les cryptos
    python indicateurs.py signal BTCUSDT        # signal pour un actif precis
    python indicateurs.py scan                  # scan tous les actifs, affiche les opportunistes
"""
import os
import sys
import json
import time
import math
import requests
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# ============================================
# RECUPERATION HISTORIQUE OHLCV (CoinGecko first, Binance fallback)
# ============================================
# Mapping complet CoinGecko: symbole -> coin_id
COINGECKO_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "LDOUSDT": "lido-dao",
    "AAVEUSDT": "aave",
    "UNIUSDT": "uniswap",
    "PENDLEUSDT": "pendle",
    "ARBUSDT": "arbitrum",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink",
    "OPUSDT": "optimism",
    "INJUSDT": "injective-protocol",
    "NEARUSDT": "near",
    "ADAUSDT": "cardano",
    "MATICUSDT": "matic-network",
    "DOTUSDT": "polkadot",
    "LTCUSDT": "litecoin",
    "PEPEUSDT": "pepe",
    "ATOMUSDT": "cosmos",
    "APTUSDT": "aptos",
    "SUIUSDT": "sui",
    "SEIUSDT": "sei-network",
    "TIAUSDT": "celestia",
    "FILUSDT": "filecoin",
    "HBARUSDT": "hedera-hashgraph",
    "ICPUSDT": "internet-computer",
    "TRXUSDT": "tron",
}

NOMS = {
    "BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana",
    "BNBUSDT": "BNB", "XRPUSDT": "XRP", "LDOUSDT": "Lido DAO",
    "AAVEUSDT": "Aave", "UNIUSDT": "Uniswap", "PENDLEUSDT": "Pendle",
    "ARBUSDT": "Arbitrum", "DOGEUSDT": "Dogecoin", "AVAXUSDT": "Avalanche",
    "LINKUSDT": "Chainlink", "OPUSDT": "Optimism", "INJUSDT": "Injective",
    "NEARUSDT": "NEAR", "ADAUSDT": "Cardano", "MATICUSDT": "Polygon",
    "DOTUSDT": "Polkadot", "LTCUSDT": "Litecoin", "PEPEUSDT": "Pepe",
    "ATOMUSDT": "Cosmos", "APTUSDT": "Aptos", "SUIUSDT": "Sui",
    "SEIUSDT": "Sei", "TIAUSDT": "Celestia", "FILUSDT": "Filecoin",
    "HBARUSDT": "Hedera", "ICPUSDT": "Internet Computer", "TRXUSDT": "Tron",
}

SYMBOLES_SUIVIS = list(NOMS.keys())

def historique_ohlcv(symbole="BTCUSDT", intervalle="1h", limite=200):
    """
    Recupere l'historique OHLCV (chandeliers).
    Crypto -> CoinGecko (primaire) puis Binance (fallback). Forex/actions -> Yahoo.
    intervalle: 15m, 1h, 4h, 1d
    limite: nombre de bougies (max 1000)
    """
    # Symboles non-crypto (forex/actions/indices/matieres) -> Yahoo Finance
    if _est_symbole_yahoo(symbole):
        bougies = _historique_yahoo(symbole, intervalle, limite)
        if bougies:
            return bougies
    # Crypto -> Revolut X d'abord (EUR, prix identiques a Revolut)
    bougies = _historique_revolut(symbole, intervalle, limite)
    if bougies and len(bougies) >= 20:
        return bougies
    # Fallback: CoinGecko
    bougies = _historique_coingecko(symbole, intervalle, limite)
    if bougies and len(bougies) >= 20:
        return bougies
    # Fallback: Binance (au cas ou)
    bougies = _historique_binance(symbole, intervalle, limite)
    if bougies:
        return bougies
    return []

# Symboles non-crypto reconnus (Yahoo Finance)
_SYMBOLUMS_YAHOO_INDIC = {
    "EURUSD=X", "GBPUSD=X", "JPY=X", "GC=F",
    "AAPL", "TSLA", "NVDA", "MSFT",
    "BZ=F", "NG=F", "HG=F", "ZW=F",
    "^GSPC", "^IXIC", "^GDAXI", "^FCHI",
}

def _est_symbole_yahoo(symbole):
    return symbole in _SYMBOLUMS_YAHOO_INDIC

def _historique_yahoo(symbole, intervalle, limite):
    """Recupere l'historique OHLCV via Yahoo Finance (forex/actions/indices/matieres)."""
    from urllib.parse import quote
    # Conversion intervalle -> range Yahoo (assez de donnees pour la limite)
    ranges = {"15m": "5d", "1h": "1mo", "4h": "3mo", "1d": "1y"}
    plage = ranges.get(intervalle, "1mo")
    try:
        # Encode le symbole (^FCHI -> %5EFCHI) pour eviter les requetes mal formees
        sym_enc = quote(symbole, safe="")
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym_enc}"
               f"?interval={intervalle}&range={plage}")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        res = data["chart"]["result"][0]
        timestamps = res.get("timestamp", [])
        quote = res["indicators"]["quote"][0]
        bougies = []
        for i in range(len(timestamps)):
            o = quote["open"][i]
            h = quote["high"][i]
            b = quote["low"][i]
            c = quote["close"][i]
            v = quote["volume"][i] if quote["volume"][i] is not None else 0
            # Saute les bougies incompletes (marche ferme / donnees manquantes)
            if o is None or h is None or b is None or c is None:
                continue
            bougies.append({
                "temps": timestamps[i],
                "ouverture": float(o),
                "haut": float(h),
                "bas": float(b),
                "cloture": float(c),
                "volume": float(v)
            })
        return bougies[-limite:] if len(bougies) > limite else bougies
    except Exception:
        return []


# Cache intelligent pour les bougies Revolut X
# TTL adapte selon l'intervalle: plus l'intervalle est long, plus le cache dure
_CACHE_BOUGIES = {}  # cle: (symbole, intervalle) -> {"bougies": [...], "timestamp": float}

_TTL_BOUGIES = {"1m": 60, "5m": 120, "15m": 300, "30m": 600, "1h": 900, "4h": 3600, "1d": 14400}

def _historique_revolut(symbole, intervalle, limite):
    """Recupere les chandeliers OHLCV depuis Revolut X (API publique, EUR).
    Cache intelligent: 1h -> 15min, 4h -> 1h, 1d -> 4h."""
    # Verifier le cache
    cache_key = (symbole, intervalle)
    ttl = _TTL_BOUGIES.get(intervalle, 300)
    if cache_key in _CACHE_BOUGIES:
        entry = _CACHE_BOUGIES[cache_key]
        if _t.time() - entry["timestamp"] < ttl:
            bougies = entry["bougies"]
            return bougies[-limite:] if len(bougies) > limite else bougies
    try:
        # Convertir le symbole bot en symbole Revolut X court
        symbole_court = symbole.replace("USDT", "").replace("EUR", "").replace("USD", "").upper()
        # Skip si dans la blacklist Revolut X
        import prix_revolut as pr
        if symbole_court in pr.BLACKLIST:
            return []
        # Convertir intervalle en minutes
        intervalles = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        interval_min = intervalles.get(intervalle, 15)
        # Calculer since/until (limite * interval en ms)
        now_ms = int(_t.time() * 1000)
        since_ms = now_ms - (limite * interval_min * 60 * 1000)
        url = (f"https://revx.revolut.com/api/1.0/public/candles/{symbole_court}-EUR"
               f"?interval={interval_min}&since={since_ms}&until={now_ms}")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items:
            return []
        bougies = []
        for b in items:
            bougies.append({
                "temps": b["start"],
                "ouverture": float(b["open"]),
                "haut": float(b["high"]),
                "bas": float(b["low"]),
                "cloture": float(b["close"]),
                "volume": float(b.get("volume", 0))
            })
        # Mettre en cache
        _CACHE_BOUGIES[cache_key] = {"bougies": bougies, "timestamp": _t.time()}
        return bougies[-limite:] if len(bougies) > limite else bougies
    except Exception as e:
        return []

def _historique_binance(symbole, intervalle, limite):
    try:
        url = (f"https://api.binance.com/api/v3/klines?"
               f"symbol={symbole}&interval={intervalle}&limit={limite}")
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        bougies = []
        for b in data:
            bougies.append({
                "temps": b[0],
                "ouverture": float(b[1]),
                "haut": float(b[2]),
                "bas": float(b[3]),
                "cloture": float(b[4]),
                "volume": float(b[5])
            })
        return bougies
    except Exception as e:
        return []

def historique_ohlcv_long(symbole="BTCUSDT", intervalle="1h", nb_bougies=17520):
    """Fetch >1000 bougies via CoinGecko (primaire) ou pagination Binance."""
    if _est_symbole_yahoo(symbole):
        return historique_ohlcv(symbole, intervalle, min(nb_bougies, 1000))
    # Essaie CoinGecko d'abord (jusqu'a 90 jours)
    bougies = _historique_coingecko(symbole, intervalle, min(nb_bougies, 1000))
    if bougies and len(bougies) >= 60:
        return bougies
    # Fallback: pagination Binance
    import time as _t
    interval_ms = {"15m": 900000, "30m": 1800000, "1h": 3600000,
                   "4h": 14400000, "1d": 86400000}.get(intervalle, 3600000)
    now_ms = int(_t.time() * 1000)
    start_ms = now_ms - nb_bougies * interval_ms
    bougies = []
    calls = 0
    while start_ms < now_ms and len(bougies) < nb_bougies and calls < 40:
        calls += 1
        try:
            url = (f"https://api.binance.com/api/v3/klines?symbol={symbole}"
                   f"&interval={intervalle}&startTime={start_ms}&limit=1000")
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            chunk = [{"temps": x[0], "ouverture": float(x[1]), "haut": float(x[2]),
                      "bas": float(x[3]), "cloture": float(x[4]), "volume": float(x[5])} for x in data]
            bougies.extend(chunk)
            start_ms = chunk[-1]["temps"] + interval_ms  # avance apres la derniere
            if len(chunk) < 1000:
                break  # plus de donnees dispo (coin recent)
            _t.sleep(0.1)  # rate-limit friendly
        except Exception:
            break
    # dedup par temps + tri + trim
    seen = {}
    for x in bougies:
        seen[x["temps"]] = x
    bougies = sorted(seen.values(), key=lambda x: x["temps"])
    return bougies[-nb_bougies:] if len(bougies) > nb_bougies else bougies

def _historique_coingecko(symbole, intervalle, limite):
    """Recupere l'historique via CoinGecko (API publique gratuite).
    Agrege les prix en vraies bougies OHLCV selon l'intervalle."""
    coin_id = COINGECKO_MAP.get(symbole)
    if not coin_id:
        return []
    # Conversion intervalle -> jours CoinGecko
    jours = {"15m": 1, "1h": 7, "4h": 30, "1d": 90}.get(intervalle, 7)
    # Interval en millisecondes pour l'agregation
    interval_ms = {"15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}.get(intervalle, 3600000)
    try:
        url = (f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
               f"?vs_currency=usd&days={jours}")
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        if not prices or len(prices) < 10:
            return []
        
        # Agrege les prix en bougies OHLCV selon l'intervalle
        buckets = {}
        for p in prices:
            ts = p[0]
            prix = p[1]
            bucket = (ts // interval_ms) * interval_ms
            if bucket not in buckets:
                buckets[bucket] = {"ouverture": prix, "haut": prix, "bas": prix, "cloture": prix, "volume": 0}
            else:
                buckets[bucket]["haut"] = max(buckets[bucket]["haut"], prix)
                buckets[bucket]["bas"] = min(buckets[bucket]["bas"], prix)
                buckets[bucket]["cloture"] = prix
        
        # Trie par temps et cree les bougies
        bougies = []
        for ts in sorted(buckets.keys()):
            b = buckets[ts]
            bougies.append({
                "temps": ts,
                "ouverture": b["ouverture"],
                "haut": b["haut"],
                "bas": b["bas"],
                "cloture": b["cloture"],
                "volume": b["volume"]
            })
        
        return bougies[-limite:] if len(bougies) > limite else bougies
    except Exception as e:
        print(f"[CoinGecko] Erreur {symbole}: {e}")
        return []

def prix_actuel(symbole):
    """Prix actuel via Revolut X (EUR, identique a Revolut)."""
    try:
        import prix_revolut as pr
        p = pr.get_prix_revolut(symbole)
        if p > 0:
            return p
    except:
        pass
    # Fallback CoinGecko
    coin_id = COINGECKO_MAP.get(symbole)
    if coin_id:
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd", timeout=10)
            return float(r.json()[coin_id]["usd"])
        except:
            pass
    # Fallback Binance
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbole}", timeout=10)
        return float(r.json()["price"])
    except:
        return None

# ============================================
# INDICATEURS TECHNIQUES (calculs reels)
# ============================================
def moyennes_mobiles(clotures, periode_courte=20, periode_longue=50):
    """Calcule SMA courte et longue. Retourne (sma_courte, sma_longue)."""
    if len(clotures) < periode_longue:
        return None, None
    sma_courte = sum(clotures[-periode_courte:]) / periode_courte
    sma_longue = sum(clotures[-periode_longue:]) / periode_longue
    return sma_courte, sma_longue

def ema(valeurs, periode):
    """Calcule l'EMA (Exponential Moving Average)."""
    if len(valeurs) < periode:
        return None
    multiplicateur = 2 / (periode + 1)
    ema = valeurs[0]
    for v in valeurs[1:]:
        ema = (v - ema) * multiplicateur + ema
    return ema

def rsi(clotures, periode=14):
    """Calcule le RSI (Relative Strength Index). 0-100."""
    if len(clotures) < periode + 1:
        return None
    gains = []
    pertes = []
    for i in range(1, periode + 1):
        diff = clotures[-(i+1)] - clotures[-(i+2)]
        if diff > 0:
            gains.append(diff)
        else:
            pertes.append(-diff)
    gain_moyen = sum(gains) / periode if gains else 0
    perte_moyenne = sum(pertes) / periode if pertes else 0
    if perte_moyenne == 0:
        return 100.0
    rs = gain_moyen / perte_moyenne
    return 100 - (100 / (1 + rs))

def macd(clotures, courte=12, longue=26, signal=9):
    """Calcule le MACD. Retourne (ligne_macd, ligne_signal, histogramme)."""
    if len(clotures) < longue + signal:
        return None, None, None
    # Calcule EMA sur toute la serie
    def calc_ema_series(valeurs, periode):
        multiplicateur = 2 / (periode + 1)
        emas = [valeurs[0]]
        for v in valeurs[1:]:
            emas.append((v - emas[-1]) * multiplicateur + emas[-1])
        return emas

    ema_courte = calc_ema_series(clotures, courte)
    ema_longue = calc_ema_series(clotures, longue)
    # Aligne les longueurs
    macd_line = [ec - el for ec, el in zip(ema_courte[len(ema_courte)-len(ema_longue):], ema_longue)]
    if len(macd_line) < signal:
        return None, None, None
    signal_line = calc_ema_series(macd_line, signal)
    histogramme = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], histogramme

def bandes_bollinger(clotures, periode=20, ecart_type=2):
    """Calcule les Bandes de Bollinger. Retourne (milieu, haut, bas)."""
    if len(clotures) < periode:
        return None, None, None
    dernieres = clotures[-periode:]
    moyenne = sum(dernieres) / periode
    variance = sum((x - moyenne) ** 2 for x in dernieres) / periode
    ecart = math.sqrt(variance)
    return moyenne, moyenne + ecart_type * ecart, moyenne - ecart_type * ecart

# ============================================
# GENERATION DE SIGNAUX (basee sur indicateurs reels)
# ============================================
_SP_CACHE = {"vals": None, "mtime": 0}

def _strat_params():
    """Lit strat_params.json (cache en memoire). Permet a l'auto-tuning de fonctionner."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strat_params.json")
    try:
        mtime = os.path.getmtime(path)
        if _SP_CACHE["mtime"] != mtime:
            _SP_CACHE["vals"] = json.load(open(path))
            _SP_CACHE["mtime"] = mtime
        return _SP_CACHE["vals"] or {}
    except Exception:
        return {}

def analyser_actif(symbole, intervalle="1h"):
    """Analyse complete d'un actif avec tous les indicateurs."""
    bougies = historique_ohlcv(symbole, intervalle, 200)
    if not bougies or len(bougies) < 60:
        return None
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]

    # Seuils dynamiques depuis strat_params.json (auto-tuning compatible)
    sp = _strat_params()
    _rsi_achat = float(sp.get("rsi_achat", 35))
    _rsi_surachat = float(sp.get("rsi_vente", 70))
    _bb_ecart = float(sp.get("bb_ecart", 2.0))

    # Calcule tous les indicateurs
    sma_courte, sma_longue = moyennes_mobiles(clotures, 20, 50)
    rsi_val = rsi(clotures, 14)
    macd_line, signal_line, histo = macd(clotures)
    bb_milieu, bb_haut, bb_bas = bandes_bollinger(clotures, 20, _bb_ecart)

    # Determine le signal
    signaux = []
    score = 0  # -3 (vente forte) a +3 (achat fort)

    # 1. Croisement moyennes mobiles
    if sma_courte and sma_longue:
        if sma_courte > sma_longue:
            signaux.append("SMA: tendance haussiere (SMA20 > SMA50)")
            score += 1
        else:
            signaux.append("SMA: tendance baissiere (SMA20 < SMA50)")
            score -= 1  # penalite moderee (gate bougies complete)

    # 2. RSI (survente/surachat) — seuils dynamiques
    if rsi_val is not None:
        if rsi_val < _rsi_achat:
            signaux.append(f"RSI: survente ({rsi_val:.1f}) - opportunite d'achat")
            score += 2
        elif rsi_val > _rsi_surachat:
            signaux.append(f"RSI: surachat ({rsi_val:.1f}) - risque de correction")
            score -= 2
        elif rsi_val < 50:
            signaux.append(f"RSI: legerement bas ({rsi_val:.1f}) - zone d'achat faible")
            score += 1
        else:
            signaux.append(f"RSI: neutre ({rsi_val:.1f})")

    # 3. MACD (momentum)
    if macd_line is not None and signal_line is not None:
        if macd_line > signal_line and histo > 0:
            signaux.append("MACD: momentum positif (croisement haussier)")
            score += 1
        elif macd_line < signal_line and histo < 0:
            signaux.append("MACD: momentum negatif (croisement baissier)")
            score -= 1
        else:
            signaux.append("MACD: neutre")

    # 4. Bandes de Bollinger — signal etendu pour marche QUIET
    if bb_haut and bb_bas and bb_milieu:
        _demi_bas = bb_milieu - bb_bas  # distance milieu -> bande basse
        if prix <= bb_bas:
            signaux.append("Bollinger: prix sous bande basse (survente)")
            score += 1
        elif _demi_bas > 0 and prix <= bb_bas + 0.25 * _demi_bas:
            # Prix proche de la bande basse (dans le quart inferieur) — signal range
            signaux.append(f"Bollinger: proche bande basse (zone d'achat range)")
            score += 1
        elif prix >= bb_haut:
            signaux.append("Bollinger: prix sur bande haute (surachat)")
            score -= 1
        else:
            signaux.append("Bollinger: dans les bandes normales")

    # 5b. MOMENTUM (strategie gagnante): achete quand la crypto MONTE
    # SMA20 > SMA50 (uptrend) + RSI 50-65 (fort mais pas surachte) = momentum
    if sma_courte is not None and sma_longue is not None and sma_courte > sma_longue:
        if rsi_val is not None and 50 <= rsi_val <= 65:
            score += 2
            signaux.append("MOMENTUM: uptrend + RSI fort (50-65) — achete la force")
        elif rsi_val is not None and 45 <= rsi_val <= 50:
            score += 1
            signaux.append("MOMENTUM faible: uptrend + RSI 45-50")

    # 5c. BREAKOUT BOLLINGER: prix casse la bande superieure = continuation haussiere
    if prix is not None and bb_haut is not None and bb_bas is not None:
        if prix > bb_haut:
            score += 2
            signaux.append("BREAKOUT: prix au-dessus BB haute — continuation haussiere")

    # 5d. MACD CROSSOVER: MACD line croise au-dessus signal line = achat momentum
    if macd_line is not None and signal_line is not None:
        if macd_line > signal_line and macd_line > 0:
            score += 2
            signaux.append("MACD: croisement haussier + MACD positif — momentum confirme")
        elif macd_line > signal_line:
            score += 1
            signaux.append("MACD: croisement haussier (MACD negatif — signal faible)")

    # Verdict
    if score >= 2:
        verdict = "ACHAT"
    elif score <= -2:
        verdict = "VENTE"
    elif score > 0:
        verdict = "ACHAT FAIBLE"
    elif score < 0:
        verdict = "VENTE FAIBLE"
    else:
        verdict = "NEUTRE"

    return {
        "symbole": symbole,
        "prix": prix,
        "intervalle": intervalle,
        "indicateurs": {
            "RSI": rsi_val,
            "SMA20": sma_courte,
            "SMA50": sma_longue,
            "MACD": macd_line,
            "MACD_signal": signal_line,
            "MACD_histo": histo,
            "BB_milieu": bb_milieu,
            "BB_haut": bb_haut,
            "BB_bas": bb_bas,
        },
        "signaux": signaux,
        "score": score,
        "verdict": verdict,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

# ============================================
# SCAN DE TOUS LES ACTIFS
# ============================================
# Anciens NOMS et SYMBOLES_SUIVIS remplaces par les versions etendues plus haut
# (garde pour compatibilite mais utilise les versions avec 30 cryptos)

def scan_complet(intervalle="1h"):
    """Analyse tous les actifs et affiche les opportunistes."""
    print(f"SCAN TECHNIQUE - {datetime.now().strftime('%d/%m/%Y %H:%M')} (intervalle: {intervalle})")
    print("="*60)
    resultats = []
    for sym in SYMBOLES_SUIVIS:
        print(f"\nAnalyse {NOMS.get(sym,sym)} ({sym})...", end=" ", flush=True)
        analyse = analyser_actif(sym, intervalle)
        if analyse:
            resultats.append(analyse)
            print(f"{analyse['verdict']} (score {analyse['score']:+d})")
        else:
            print("echec")
        time.sleep(0.5)

    # Trie par score (meilleures opportunites en premier)
    resultats.sort(key=lambda x: x["score"], reverse=True)

    print("\n" + "="*60)
    print("OPPORTUNITES (triees par score)")
    print("="*60)
    for r in resultats:
        emoji = "🟢" if r["verdict"] == "ACHAT" else ("🔴" if r["verdict"] == "VENTE" else "⚪")
        print(f"\n{emoji} {NOMS.get(r['symbole'],r['symbole'])} - {r['verdict']} (score {r['score']:+d})")
        print(f"   Prix: {r['prix']:.2f} EUR")
        print(f"   RSI: {r['indicateurs']['RSI']:.1f}" if r['indicateurs']['RSI'] else "   RSI: N/A")
        print(f"   Signaux:")
        for s in r["signaux"]:
            print(f"     - {s}")

    # Sauvegarde les resultats
    fichier_scan = os.path.join(DOSSIER, "dernier_scan.json")
    with open(fichier_scan, "w") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print(f"\nScan sauvegarde dans dernier_scan.json")

    # Resume des signaux d'achat
    achats = [r for r in resultats if r["verdict"] in ["ACHAT", "ACHAT FAIBLE"]]
    if achats:
        print(f"\n>>> {len(achats)} signal(s) d'achat detecte(s): " + ", ".join(NOMS.get(a['symbole'],a['symbole']) for a in achats))
    else:
        print(f"\n>>> Aucun signal d'achat actuellement.")

    return resultats

def signal_unique(symbole, intervalle="1h"):
    """Affiche l'analyse detaillee d'un seul actif."""
    analyse = analyser_actif(symbole, intervalle)
    if not analyse:
        print(f"Impossible d'analyser {symbole}. Verifie le symbole.")
        return
    print("="*60)
    print(f"ANALYSE TECHNIQUE - {NOMS.get(symbole,symbole)} ({symbole})")
    print(f"Intervalle: {intervalle} | Date: {analyse['date']}")
    print("="*60)
    print(f"\nPrix actuel: {analyse['prix']:.2f} EUR")
    print(f"Verdict: {analyse['verdict']} (score {analyse['score']:+d}/3)")
    print(f"\n--- INDICATEURS ---")
    ind = analyse["indicateurs"]
    print(f"RSI (14):        {ind['RSI']:.1f}" if ind['RSI'] else "RSI: N/A")
    print(f"SMA 20:          {ind['SMA20']:.2f}" if ind['SMA20'] else "SMA20: N/A")
    print(f"SMA 50:          {ind['SMA50']:.2f}" if ind['SMA50'] else "SMA50: N/A")
    if ind['MACD'] is not None:
        print(f"MACD:            {ind['MACD']:.4f}")
        print(f"MACD signal:     {ind['MACD_signal']:.4f}")
        print(f"MACD histogramme:{ind['MACD_histo']:.4f}")
    if ind['BB_haut']:
        print(f"Bollinger haut:  {ind['BB_haut']:.2f}")
        print(f"Bollinger bas:   {ind['BB_bas']:.2f}")
    print(f"\n--- SIGNAUX ---")
    for s in analyse["signaux"]:
        print(f"  - {s}")
    print("="*60)

def aide():
    print("""
INDICATEURS TECHNIQUES REELS - Aide
===========================================
Indicateurs calcules: RSI, MACD, SMA (20/50), Bandes de Bollinger
Sources: Binance (temps reel, gratuit)

Commandes:
  python indicateurs.py scan                    Scan tous les cryptos, affiche opportunites
  python indicateurs.py analyse BTCUSDT          Analyse complete d'un actif
  python indicateurs.py signal BTCUSDT           Signal succinct pour un actif
  python indicateurs.py scan 4h                  Scan sur intervalle 4h
  python indicateurs.py scan 1d                  Scan sur intervalle journalier

Intervalles: 15m, 1h, 4h, 1d
Symboles: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT

Scores:
  +3 a +2: ACHAT (fort)
  +1: ACHAT faible
   0: NEUTRE
  -1: VENTE faible
  -2 a -3: VENTE (fort)
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0].lower() == "aide":
        aide()
    elif args[0].lower() == "scan":
        intervalle = args[1] if len(args) > 1 else "1h"
        scan_complet(intervalle)
    elif args[0].lower() == "analyse":
        symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
        intervalle = args[2] if len(args) > 2 else "1h"
        signal_unique(symbole, intervalle)
    elif args[0].lower() == "signal":
        symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
        signal_unique(symbole)
    else:
        aide()
