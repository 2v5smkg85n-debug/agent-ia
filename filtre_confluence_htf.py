#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filtre_confluence_htf.py — Filtre de confluence multi-timeframe.

N'accepte une entree que si la tendance de la TIMEFRAME SUPERIEURE confirme:
  - ACHAT (long) : bloque si HTF en tendance baissiere (prix < EMA50 et pente <0)
  - VENTE (short): bloque si HTF en tendance haussiere

Mapping base -> HTF (la TF juste au-dessus):
  crypto (Binance, 4h dispo)  : 15m->1h, 1h->4h, 4h->1d, 1d->skip
  non-crypto (Yahoo, pas 4h)  : 15m->1h, 1h->1d, 4h->1d, 1d->skip

FAIL-OPEN (CRITIQUE): si fetch klines impossible ou pas assez de bougies ->
entree AUTORISEE. On ne bloque JAMAIS tout le trading sur une erreur API.
Toggle: CONF_MULTI_TF=0 desactive le filtre.

Integration: porte additive dans ouvrir_position (paper_trading.py), apres les
gardes cheap (anti-corr, anti-gap, circuit breaker) et avant le sizing — pour
ne pas faire de fetch reseau si le trade est deja bloque.
"""
import os

EMA_PERIODE = 50

_MAP_CRYPTO = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": None, "1w": None, "30m": "1h"}
_MAP_YAHOO = {"15m": "1h", "1h": "1d", "4h": "1d", "1d": None, "1w": None, "30m": "1h"}


def _ema_series(series, periode):
    """Liste des EMA (meme longueur que series). Vide si pas assez de donnees."""
    if len(series) < periode:
        return []
    k = 2.0 / (periode + 1)
    out = []
    ema = series[0]
    for v in series[1:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def _trend_htf(symbole, marche, tf_base):
    """Retourne 'haute', 'basse', 'neutre' ou None (erreur/indispo).

    None = on ne sait pas -> fail-open (autorise).
    'neutre' = base deja la plus haute TF, ou trend ambigue -> autorise (n'agit
    que sur les tendance nettes pour eviter de tout bloquer).
    """
    try:
        from indicateurs import historique_ohlcv
    except Exception:
        return None
    is_crypto = (marche == "crypto") or symbole.endswith("USDT")
    mapping = _MAP_CRYPTO if is_crypto else _MAP_YAHOO
    htf = mapping.get(tf_base)
    if htf is None:
        return "neutre"  # base deja la plus haute TF -> pas de filtre
    try:
        bougies = historique_ohlcv(symbole, htf, 120)
    except Exception:
        return None
    if not bougies or len(bougies) < EMA_PERIODE + 5:
        return None
    try:
        clotures = [float(b["cloture"]) for b in bougies]
    except Exception:
        return None
    ema_s = _ema_series(clotures, EMA_PERIODE)
    if len(ema_s) < 5:
        return None
    last_close = clotures[-1]
    last_ema = ema_s[-1]
    pente = ema_s[-1] - ema_s[-4]  # pente recente (sur 3 bougies HTF)
    prix_above = last_close > last_ema
    ema_rising = pente > 0
    if prix_above and ema_rising:
        return "haute"
    if (not prix_above) and (not ema_rising):
        return "basse"
    return "neutre"


def _entree_bloquee_confluence(signal):
    """True si l'entree doit etre bloquee par le filtre de confluence HTF.

    Retourne (bloquee: bool, raison: str). Fail-open: erreur API -> (False, "").
    """
    bs = signal.get("backtest_stats") or {}
    tf_base = bs.get("intervalle") or signal.get("intervalle")
    symbole = signal.get("symbole", "")
    marche = signal.get("marche", "crypto")
    action = (signal.get("action") or "ACHAT").upper()
    trend = _trend_htf(symbole, marche, tf_base)
    if trend is None:
        return False, ""  # fail-open
    if action in ("ACHAT", "LONG", "BUY") and trend == "basse":
        return True, "HTF baissiere (contre-tendance long)"
    if action in ("VENTE", "SHORT", "SELL") and trend == "haute":
        return True, "HTF haussiere (contre-tendance short)"
    return False, ""
