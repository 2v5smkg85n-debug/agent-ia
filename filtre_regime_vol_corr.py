import math
import statistics
from collections import deque

# Module autonome: filtre de régime basé sur volatilité réalisée et corrélation glissante.
# Compatible avec un usage offline / paper / backtest.

EPS = 1e-12


def _safe_mean(values):
    vals = [v for v in values if v is not None and not isinstance(v, bool)]
    return statistics.fmean(vals) if vals else 0.0


def _safe_stdev(values):
    vals = [v for v in values if v is not None and not isinstance(v, bool)]
    if len(vals) < 2:
        return 0.0
    try:
        return statistics.pstdev(vals)
    except statistics.StatisticsError:
        return 0.0


def _pearson_corr(x, y):
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x = list(x)[-n:]
    y = list(y)[-n:]
    mx = _safe_mean(x)
    my = _safe_mean(y)
    cov = 0.0
    vx = 0.0
    vy = 0.0
    for a, b in zip(x, y):
        da = a - mx
        db = b - my
        cov += da * db
        vx += da * da
        vy += db * db
    if vx <= EPS or vy <= EPS:
        return 0.0
    return cov / math.sqrt(vx * vy + EPS)


def _log_return(prev_price, price):
    if prev_price is None or price is None:
        return None
    if prev_price <= 0 or price <= 0:
        return None
    return math.log(price / prev_price)


def analyser_volatilite(prices, window=20):
    """
    Calcule une volatilité réalisée simple sur rendements logarithmiques.
    Retourne un dict avec vol, mean_ret, n.
    """
    if not prices or len(prices) < 3:
        return {"vol": 0.0, "mean_ret": 0.0, "n": 0}
    rets = []
    prev = None
    for p in prices:
        r = _log_return(prev, p)
        if r is not None:
            rets.append(r)
        prev = p
    if not rets:
        return {"vol": 0.0, "mean_ret": 0.0, "n": 0}
    w = rets[-window:] if len(rets) > window else rets
    mean_ret = _safe_mean(w)
    vol = _safe_stdev(w)
    return {"vol": vol, "mean_ret": mean_ret, "n": len(w)}


def calculer_correlation(series_a, series_b, window=20):
    """
    Corrélation de Pearson sur rendements logarithmiques glissants.
    Renvoie un dict avec correlation, n, direction.
    """
    if not series_a or not series_b:
        return {"correlation": 0.0, "n": 0, "direction": "neutral"}
    n = min(len(series_a), len(series_b))
    a = list(series_a)[-n:]
    b = list(series_b)[-n:]

    ra = []
    rb = []
    pa = None
    pb = None
    for x, y in zip(a, b):
        rx = _log_return(pa, x)
        ry = _log_return(pb, y)
        if rx is not None and ry is not None:
            ra.append(rx)
            rb.append(ry)
        pa = x
        pb = y

    if len(ra) < 2 or len(rb) < 2:
        return {"correlation": 0.0, "n": len(ra), "direction": "neutral"}

    ra = ra[-window:] if len(ra) > window else ra
    rb = rb[-window:] if len(rb) > window else rb
    corr = _pearson_corr(ra, rb)
    direction = "positive" if corr > 0.25 else "negative" if corr < -0.25 else "neutral"
    return {"correlation": corr, "n": min(len(ra), len(rb)), "direction": direction}


def detecter_regime(prices_main, prices_peer=None, window=20, corr_high=0.65, vol_high=0.012):
    """
    Détecte un régime de marché utile pour le trading:
    - 'risk_off_contagion' : volatilité élevée + corrélation élevée avec un peer
    - 'high_momentum'      : volatilité modérée + rendement moyen positif
    - 'mean_reversion'     : volatilité élevée + corrélation faible/négative
    - 'calm'               : faible volatilité
    """
    vol_info = analyser_volatilite(prices_main, window=window)
    vol = vol_info["vol"]
    mean_ret = vol_info["mean_ret"]

    corr = 0.0
    corr_info = {"correlation": 0.0, "n": 0, "direction": "neutral"}
    if prices_peer is not None:
        corr_info = calculer_correlation(prices_main, prices_peer, window=window)
        corr = corr_info["correlation"]

    if vol >= vol_high and corr >= corr_high:
        regime = "risk_off_contagion"
    elif vol >= vol_high and corr <= 0.15:
        regime = "mean_reversion"
    elif vol < vol_high and mean_ret > 0:
        regime = "high_momentum"
    elif vol < vol_high * 0.75:
        regime = "calm"
    else:
        regime = "mixed"

    confidence = 0.0
    confidence += min(1.0, vol / max(vol_high, EPS)) * 0.45
    confidence += min(1.0, max(corr, 0.0) / max(corr_high, EPS)) * 0.35
    confidence += min(1.0, max(mean_ret, 0.0) / max(vol_high, EPS)) * 0.20
    confidence = max(0.0, min(1.0, confidence))

    return {
        "regime": regime,
        "volatility": vol,
        "mean_return": mean_ret,
        "correlation": corr,
        "vol_info": vol_info,
        "corr_info": corr_info,
        "confidence": confidence,
    }


def score_risque_regime(prices_main, prices_peer=None, window=20):
    """
    Produit un score [0,1] de risque de marché.
    Plus le score est élevé, plus il faut réduire la taille ou bloquer les entrées.
    """
    info = detecter_regime(prices_main, prices_peer=prices_peer, window=window)
    vol = info["volatility"]
    corr = abs(info["correlation"])
    regime = info["regime"]

    score = 0.0
    score += min(1.0, vol / 0.012) * 0.5
    score += min(1.0, corr / 0.7) * 0.3
    if regime == "risk_off_contagion":
        score += 0.25
    elif regime == "mean_reversion":
        score += 0.10
    elif regime == "calm":
        score -= 0.15

    return max(0.0, min(1.0, score))


def ajuster_exposition(base_size, prices_main, prices_peer=None, window=20):
    """
    Réduit automatiquement la taille quand le régime devient défavorable.
    Retourne (size_ajustee, meta).
    """
    base_size = float(base_size)
    info = detecter_regime(prices_main, prices_peer=prices_peer, window=window)
    risk = score_risque_regime(prices_main, prices_peer=prices_peer, window=window)

    if info["regime"] == "risk_off_contagion":
        multiplier = 0.25
    elif info["regime"] == "mean_reversion":
        multiplier = 0.55
    elif info["regime"] == "mixed":
        multiplier = 0.75
    elif info["regime"] == "high_momentum":
        multiplier = 1.00
    else:
        multiplier = 0.90

    multiplier *= (1.0 - 0.45 * risk)
    multiplier = max(0.10, min(1.0, multiplier))
    adjusted = base_size * multiplier

    return adjusted, {
        "multiplier": multiplier,
        "risk_score": risk,
        "regime": info["regime"],
        "correlation": info["correlation"],
        "volatility": info["volatility"],
        "confidence": info["confidence"],
    }


def self_test():
    try:
        prices_a = [
            100.0, 100.8, 101.2, 101.6, 102.4, 103.1, 102.9, 103.5, 104.0, 104.8,
            105.2, 105.9, 106.4, 106.0, 106.8, 107.5, 108.1, 108.7, 109.0, 109.8,
            110.5, 111.1
        ]
        prices_b = [
            50.0, 50.4, 50.6, 50.9, 51.3, 51.8, 51.7, 52.1, 52.5, 52.9,
            53.1, 53.7, 54.0, 53.8, 54.2, 54.7, 55.0, 55.3, 55.4, 55.8,
            56.1, 56.4
        ]

        vol = analyser_volatilite(prices_a, window=10)
        corr = calculer_correlation(prices_a, prices_b, window=10)
        regime = detecter_regime(prices_a, prices_peer=prices_b, window=10)
        size, meta = ajuster_exposition(1000.0, prices_a, prices_peer=prices_b, window=10)

        assert isinstance(vol, dict)
        assert isinstance(corr, dict)
        assert isinstance(regime, dict)
        assert isinstance(size, float)
        assert isinstance(meta, dict)
        assert "regime" in regime
        assert "correlation" in corr
        assert 0.0 <= meta["multiplier"] <= 1.0
        return True
    except Exception:
        return False