#!/usr/bin/env python3
"""
TradingView Technical Analysis - Source 5 pour le bot crypto
Recupere le rating technique de TradingView (23+ indicateurs agreges)
et l'utilise comme signal de confirmation independant.

Rating: STRONG_BUY > BUY > NEUTRAL > SELL > STRONG_SELL
Gratuit, pas de cle API. Package: tradingview-ta
"""

import time
import threading

# Cache local (evite les appels repetes dans la meme fenetre)
_cache = {}            # {symbole: (timestamp, rating, score, rsi)}
_cache_lock = threading.Lock()
CACHE_DUREE = 300       # 5 minutes
DELAI_ENTRE_APPELS = 3  # secondes (evite HTTP 429)
_dernier_appel = 0.0

# Mapping rating -> score bonus
RATING_SCORES = {
    "STRONG_BUY":  2,
    "BUY":         1,
    "NEUTRAL":     0,
    "SELL":       -1,
    "STRONG_SELL": -2,
}

# Mapping symbole bot -> symbole TradingView
# (la plupart sont identiques, mais certains necessitent un mapping)
SYMBOL_MAP = {
    "1000SATSUSDT": "SATSUSDT",
    "1000SHIBUSDT": "SHIBUSDT",
    "1000PEPEUSDT": "PEPEUSDT",
}

# Exchange TradingView (BINANCE a la meilleure couverture crypto)
TV_EXCHANGE = "BINANCE"
TV_SCREENER = "crypto"
TV_INTERVAL = None  # defini au runtime


def _get_tv_handler():
    """Importe tradingview_ta de facon paresseuse."""
    from tradingview_ta import TA_Handler, Interval
    global TV_INTERVAL
    TV_INTERVAL = Interval.INTERVAL_1_HOUR
    return TA_Handler, Interval


def _rating_to_score(rating):
    """Convertit un rating TradingView en score numerique."""
    return RATING_SCORES.get(rating, 0)


def analyser_symbole(symbole, intervalle="1h"):
    """
    Recupere le rating TradingView pour un symbole.
    Retourne: (rating, score_bonus, rsi, details) ou (None, 0, 0, "") si indisponible.
    """
    # Mapping symbole
    tv_sym = SYMBOL_MAP.get(symbole, symbole)

    # Verifier le cache
    now = time.time()
    with _cache_lock:
        if tv_sym in _cache:
            ts, rating, score, rsi = _cache[tv_sym]
            if now - ts < CACHE_DUREE:
                return rating, score, rsi, f"cache ({int(CACHE_DUREE - (now - ts))}s)"

    # Delai entre appels (evite 429)
    global _dernier_appel
    elapsed = now - _dernier_appel
    if elapsed < DELAI_ENTRE_APPELS:
        time.sleep(DELAI_ENTRE_APPELS - elapsed)
    _dernier_appel = time.time()

    try:
        TA_Handler, Interval = _get_tv_handler()
        interval_map = {
            "15m": Interval.INTERVAL_15_MINUTES,
            "1h": Interval.INTERVAL_1_HOUR,
            "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY,
        }
        tv_int = interval_map.get(intervalle, Interval.INTERVAL_1_HOUR)

        handler = TA_Handler(
            symbol=tv_sym,
            screener=TV_SCREENER,
            exchange=TV_EXCHANGE,
            interval=tv_int,
        )
        analysis = handler.get_analysis()
        summary = analysis.summary
        rating = summary["RECOMMENDATION"]
        buy_count = summary.get("BUY", 0)
        neutral_count = summary.get("NEUTRAL", 0)
        sell_count = summary.get("SELL", 0)
        rsi = analysis.indicators.get("RSI", 0)
        macd = analysis.indicators.get("MACD.macd", 0)
        macd_signal = analysis.indicators.get("MACD.signal", 0)
        close = analysis.indicators.get("close", 0)

        score = _rating_to_score(rating)
        details = f"TV:{rating} B:{buy_count} N:{neutral_count} S:{sell_count} RSI:{rsi:.1f}"

        # Mettre en cache
        with _cache_lock:
            _cache[tv_sym] = (time.time(), rating, score, rsi)

        return rating, score, rsi, details

    except Exception as e:
        err = str(e)
        if "429" in err:
            # Rate limite - on skip sans bloquer le bot
            return None, 0, 0, "rate-limited (429)"
        return None, 0, 0, f"erreur: {err[:50]}"


def enrichir_signaux(signaux, intervalle="1h"):
    """
    Enrichit une liste de signaux avec le rating TradingView.
    Ajuste le score de chaque signal selon le rating.
    Retourne la liste des signaux enrichis (aucun signal n'est filtre).
    """
    if not signaux:
        return signaux

    print("  [TRADINGVIEW] Recuperation des ratings techniques...")
    nb_reussis = 0
    nb_rate_limited = 0
    nb_erreurs = 0

    for sig in signaux:
        sym = sig.get("symbole", "")
        if not sym:
            continue

        rating, score_tv, rsi, details = analyser_symbole(sym, intervalle)

        sig["tv_rating"] = rating or "N/A"
        sig["tv_score"] = score_tv
        sig["tv_rsi"] = rsi
        sig["tv_details"] = details

        if rating is None:
            if "429" in details:
                nb_rate_limited += 1
            else:
                nb_erreurs += 1
            # Ne pas bloquer le signal - juste ne pas ajuster le score
            continue

        nb_reussis += 1

        # Ajuster le score du signal
        if score_tv > 0:
            sig["score"] = sig.get("score", 0) + score_tv
            nom = sig.get("nom", sym)
            print(f"  [TRADINGVIEW] {nom}: {rating} -> +{score_tv} (RSI:{rsi:.1f})")
        elif score_tv < 0:
            sig["score"] = sig.get("score", 0) + score_tv
            nom = sig.get("nom", sym)
            print(f"  [TRADINGVIEW] {nom}: {rating} -> {score_tv} (RSI:{rsi:.1f})")
        else:
            nom = sig.get("nom", sym)
            print(f"  [TRADINGVIEW] {nom}: NEUTRAL (RSI:{rsi:.1f})")

    resume = f"  [TRADINGVIEW] {nb_reussis} analyses, {nb_rate_limited} rate-limited, {nb_erreurs} erreurs"
    print(resume)

    return signaux


def vider_cache():
    """Vide le cache (utile pour forcer un refresh)."""
    with _cache_lock:
        _cache.clear()


# === TEST ===
if __name__ == "__main__":
    print("Test TradingView Signals\n")
    test_syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NEARUSDT", "AAVEUSDT"]
    for sym in test_syms:
        rating, score, rsi, details = analyser_symbole(sym)
        print(f"{sym:12s} | rating={rating} | score={score:+d} | RSI={rsi:.1f} | {details}")
        time.sleep(0.5)
