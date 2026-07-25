import math
from collections import deque, defaultdict

# Module autonome de protection anti-stop-loss.
# Hooks supportés: hook_entree, hook_sizing, self_test
# Aucun accès réseau, aucune écriture disque, aucun import interdit.

_STATE = {
    "recent_signals": deque(maxlen=200),
    "loss_streak_by_symbol": defaultdict(int),
    "loss_streak_by_strategy": defaultdict(int),
}

# Stratégies déjà identifiées comme fragiles dans le diagnostic.
_WEAK_STRATEGIES = {
    "Evolved 00955",
    "RSI Mean Reversion",
    "Bollinger Breakout",
}

# Seuils conservateurs ciblant la fuite STOP-LOSS.
_VOL_KEYS = ("volatilite", "volatility", "atr", "atr_pct", "range_pct", "range", "std", "sigma")
_CRASH_KEYS = ("crash", "panic", "stress", "liquidation", "liq", "dump", "selloff")
_CORR_KEYS = ("corr", "correlation", "beta", "btc_eth", "btc/eth", "btc-eth")
_MOMENTUM_KEYS = ("trend", "momentum", "direction", "score", "strength", "conviction")


def _s(v, default=""):
    if v is None:
        return default
    try:
        return str(v)
    except Exception:
        return default


def _f(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _lower_text(d):
    parts = []
    if isinstance(d, dict):
        for k, v in d.items():
            parts.append(_s(k))
            if isinstance(v, (str, int, float, bool)) or v is None:
                parts.append(_s(v))
    return " ".join(parts).lower()


def _signal_risk(signal):
    text = _lower_text(signal)
    strat = _s(signal.get("strategie", "")).strip()
    score = _f(signal.get("score", 0.0), 0.0)

    risk = 0.0

    if strat in _WEAK_STRATEGIES:
        risk += 1.15
    if any(k in text for k in _CRASH_KEYS):
        risk += 1.60
    if any(k in text for k in _CORR_KEYS):
        risk += 0.90
    if any(k in text for k in _VOL_KEYS):
        risk += 1.10

    if score != 0.0:
        if score < 0:
            risk += min(1.25, abs(score) * 0.35)
        elif score < 0.25:
            risk += 0.35
        elif score > 0.75:
            risk -= 0.25

    reason = _s(signal.get("raison", "")).lower()
    if "stop" in reason or "loss" in reason or "sl" in reason:
        risk += 0.65
    if "breakout" in strat.lower():
        risk += 0.10

    return risk


def _streak_penalty(pf, signal):
    sym = _s(signal.get("symbole", "")).strip()
    strat = _s(signal.get("strategie", "")).strip()

    sym_streak = _STATE["loss_streak_by_symbol"].get(sym, 0)
    strat_streak = _STATE["loss_streak_by_strategy"].get(strat, 0)

    # Sans historique détaillé des pertes ouvertes/fermées par actif,
    # on applique une pénalisation prudente dès qu'une série défavorable est détectée.
    return 0.35 * sym_streak + 0.25 * strat_streak


def _position_pressure(pf):
    positions = pf.get("positions", {})
    try:
        n = len(positions)
    except Exception:
        n = 0
    if n <= 0:
        return 0.0
    return min(1.0, n / 4.0) * 0.25


def hook_entree(pf, signal):
    """
    Retourne (allow_bool, raison_str).
    Veto ciblé pour réduire la fuite STOP-LOSS.
    """
    try:
        signal = signal or {}
        pf = pf or {}

        strat = _s(signal.get("strategie", "")).strip()
        sym = _s(signal.get("symbole", "")).strip()
        score = _f(signal.get("score", 0.0), 0.0)
        reason = _s(signal.get("raison", "")).strip()

        risk = _signal_risk(signal)
        risk += _streak_penalty(pf, signal)
        risk += _position_pressure(pf)

        liquidites = _f(pf.get("liquidites", 0.0), 0.0)
        capital_initial = max(_f(pf.get("capital_initial", 0.0), 0.0), 1.0)
        liquidite_ratio = liquidites / capital_initial

        # Cash preservation: si le portefeuille s'érode, on devient plus sélectif.
        if liquidite_ratio < 0.92:
            risk += 0.20
        if liquidite_ratio < 0.88:
            risk += 0.35

        # Veto fort sur les setups faibles pendant les régimes dangereux.
        danger = any(k in _lower_text(signal) for k in _CRASH_KEYS) or any(k in _lower_text(signal) for k in _VOL_KEYS)

        if strat in _WEAK_STRATEGIES and (risk >= 1.55 or score < 0.15):
            return False, f"veto_strategie_faible:{strat}"

        if danger and score < 0.55:
            return False, "veto_regime_volatilite_crash"

        if risk >= 2.00:
            return False, "veto_risque_stoploss_excessif"

        if risk >= 1.35 and score < 0.40:
            return False, "veto_conviction_insuffisante_en_regime_risque"

        if "stop-loss" in reason.lower() and score < 0.60:
            return False, "veto_signal_oriente_stoploss_et_score_faible"

        # Si l'actif est déjà marqué par une série de pertes, on coupe les nouvelles entrées.
        if sym and _STATE["loss_streak_by_symbol"].get(sym, 0) >= 2:
            return False, "veto_seriе_pertes_actif"

        # Acceptation prudente.
        return True, "ok"
    except Exception:
        return False, "safe_fail_closed"


def hook_sizing(pf, signal, montant, prix_actuel):
    """
    Réduit la taille sur les setups exposés au stop-loss.
    Retourne un montant EUR ajusté.
    """
    try:
        pf = pf or {}
        signal = signal or {}
        montant = max(0.0, _f(montant, 0.0))
        prix_actuel = max(_f(prix_actuel, 0.0), 0.0)

        risk = _signal_risk(signal)
        risk += _streak_penalty(pf, signal)
        risk += _position_pressure(pf)

        strat = _s(signal.get("strategie", "")).strip()
        score = _f(signal.get("score", 0.0), 0.0)

        factor = 1.0

        if strat in _WEAK_STRATEGIES:
            factor *= 0.55

        if risk >= 2.0:
            factor *= 0.20
        elif risk >= 1.5:
            factor *= 0.35
        elif risk >= 1.0:
            factor *= 0.60

        if score < 0.25:
            factor *= 0.70
        elif score > 0.80 and risk < 0.9:
            factor *= 1.10

        # Petite protection supplémentaire sur les actifs chers lorsque le signal est fragile.
        if prix_actuel > 0:
            nominal = montant / prix_actuel
            if nominal > 0 and risk >= 1.2:
                factor *= 0.90

        adjusted = montant * factor

        liquidites = _f(pf.get("liquidites", 0.0), 0.0)
        if liquidites > 0:
            adjusted = min(adjusted, liquidites)

        return max(0.0, adjusted)
    except Exception:
        return max(0.0, _f(montant, 0.0) * 0.5)


def self_test():
    pf = {
        "liquidites": 996.17,
        "positions": {},
        "trades_fermes": [],
        "capital_initial": 1000.0,
    }

    safe_signal = {
        "symbole": "BTC/EUR",
        "strategie": "backtest-gagnant",
        "marche": "spot",
        "raison": "signal propre",
        "score": 0.82,
    }

    risky_signal = {
        "symbole": "ETH/EUR",
        "strategie": "RSI Mean Reversion",
        "marche": "spot",
        "raison": "crash volatility stop-loss",
        "score": 0.18,
    }

    allow1, why1 = hook_entree(pf, safe_signal)
    if not isinstance(allow1, bool) or not isinstance(why1, str):
        return False

    allow2, why2 = hook_entree(pf, risky_signal)
    if allow2 is not False:
        return False

    s1 = hook_sizing(pf, safe_signal, 100.0, 50000.0)
    s2 = hook_sizing(pf, risky_signal, 100.0, 50000.0)

    if not isinstance(s1, float) or not isinstance(s2, float):
        return False
    if s1 <= 0.0:
        return False
    if s2 > s1:
        return False

    return True