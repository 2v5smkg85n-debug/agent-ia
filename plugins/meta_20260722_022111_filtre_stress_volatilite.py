import math
import statistics
from collections import deque

_WINDOW_VOL = 24
_WINDOW_REF = 96
_WINDOW_RET = 12
_RISK_MULTIPLIER = 0.35
_VETO_RATIO = 2.8
_MIN_HISTORY = 20

_state = {
    "prices": {},
    "vols": {},
}

def _to_float(x, default=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default

def _extract_price(signal, pf):
    for key in ("prix", "price", "last", "close", "prix_actuel"):
        if isinstance(signal, dict) and key in signal:
            p = _to_float(signal.get(key), 0.0)
            if p > 0:
                return p
    if isinstance(pf, dict):
        positions = pf.get("positions", {})
        if isinstance(positions, dict):
            sym = signal.get("symbole") if isinstance(signal, dict) else None
            pos = positions.get(sym) if sym is not None else None
            if isinstance(pos, dict):
                for key in ("prix_entree", "entry_price", "prix", "price"):
                    p = _to_float(pos.get(key), 0.0)
                    if p > 0:
                        return p
    return 0.0

def _rolling_vol(prices):
    if len(prices) < _WINDOW_RET + 2:
        return None
    rets = []
    vals = list(prices)
    for i in range(1, len(vals)):
        prev = vals[i - 1]
        cur = vals[i]
        if prev > 0 and cur > 0:
            rets.append(math.log(cur / prev))
    if len(rets) < 5:
        return None
    tail = rets[-_WINDOW_VOL:]
    if len(tail) < 5:
        return None
    try:
        return statistics.pstdev(tail)
    except Exception:
        return None

def _stress_ratio(sym):
    vols = _state["vols"].get(sym)
    if not vols or len(vols) < _MIN_HISTORY:
        return None
    recent = list(vols)[-_WINDOW_VOL:]
    reference = list(vols)[-_WINDOW_REF:]
    if len(recent) < 5 or len(reference) < 20:
        return None
    try:
        med_ref = statistics.median(reference)
        if med_ref <= 0:
            return None
        med_recent = statistics.median(recent)
        return med_recent / med_ref
    except Exception:
        return None

def hook_entree(pf, signal):
    try:
        if not isinstance(pf, dict) or not isinstance(signal, dict):
            return (True, "format_invalide")
        sym = signal.get("symbole")
        if not sym:
            return (True, "sans_symbole")
        price = _extract_price(signal, pf)
        if price <= 0:
            return (True, "prix_indisponible")

        prices = _state["prices"].setdefault(sym, deque(maxlen=max(_WINDOW_REF * 2, 150)))
        vols = _state["vols"].setdefault(sym, deque(maxlen=max(_WINDOW_REF * 2, 150)))
        prices.append(price)

        vol = _rolling_vol(prices)
        if vol is not None:
            vols.append(vol)

        ratio = _stress_ratio(sym)
        if ratio is None:
            return (True, "historique_insuffisant")

        score = _to_float(signal.get("score"), 0.0)
        if ratio >= _VETO_RATIO:
            return (False, "veto_volatilite_extreme")

        if ratio >= 1.8:
            if score < 0.65:
                return (False, "veto_stress_volatilite")
            return (True, "stress_modere")

        return (True, "normal")
    except Exception:
        return (True, "safe_fallback")

def hook_sizing(pf, signal, montant, prix_actuel):
    try:
        base = _to_float(montant, 0.0)
        if base <= 0:
            return 0.0

        sym = signal.get("symbole") if isinstance(signal, dict) else None
        if not sym:
            return base

        ratio = _stress_ratio(sym)
        score = _to_float(signal.get("score"), 0.0) if isinstance(signal, dict) else 0.0

        factor = 1.0
        if ratio is not None:
            if ratio >= _VETO_RATIO:
                factor = 0.0
            elif ratio >= 2.2:
                factor = _RISK_MULTIPLIER * 0.6
            elif ratio >= 1.8:
                factor = _RISK_MULTIPLIER
            elif ratio >= 1.4:
                factor = 0.7

        if score >= 0.8:
            factor *= 1.15
        elif score < 0.5:
            factor *= 0.85

        adjusted = base * max(0.0, min(1.0, factor))

        liquidites = _to_float(pf.get("liquidites"), adjusted) if isinstance(pf, dict) else adjusted
        if liquidites > 0:
            adjusted = min(adjusted, liquidites)
        return max(0.0, adjusted)
    except Exception:
        return max(0.0, _to_float(montant, 0.0))

def self_test():
    try:
        pf = {
            "liquidites": 1000.0,
            "positions": {},
            "trades_fermes": [],
            "capital_initial": 1000.0,
        }
        sig = {
            "symbole": "BTC-EUR",
            "score": 0.72,
            "prix": 100.0,
            "strategie": "test",
            "marche": "spot",
            "raison": "unit_test",
        }

        for i in range(160):
            sig["prix"] = 100.0 + (i * 0.1)
            allow, reason = hook_entree(pf, sig)
            if not isinstance(allow, bool) or not isinstance(reason, str):
                return False

        size = hook_sizing(pf, sig, 250.0, 120.0)
        if not isinstance(size, float) and not isinstance(size, int):
            return False
        if size < 0:
            return False

        return True
    except Exception:
        return False