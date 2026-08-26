#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sentiment_marche.py — Sentiment du marché: le Crypto Fear & Greed Index.

L'agent n'utilisait que les prix/indicateurs. Maintenant il connaît le sentiment
réel du marché (Fear & Greed Index, API gratuite sans clé) — la dimension
comportementale. Principe: "sois avide quand les autres ont peur".

Deux usages:
  - sentiment_prompt(): injecté dans l'evolver (4e couche de connaissance, après
    sagesse + leçons live + mémoire marché). L'IA sait si le marché a peur/greed.
  - sentiment_multiplier(): taille de position contrarian (achète plus en fear,
    moins en greed) — pour intégration dans ouvrir_position."""
import os
from datetime import datetime

import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FNG_URL = "https://api.alternative.me/fng/"
_cache_fg = {"data": None, "ts": 0}
_CACHE_TTL = 300  # 5 minutes


def fetch_fear_greed(limit=30):
    """Récupère les dernières valeurs du Fear & Greed Index (nouveau -> ancien). Cache 5min."""
    import time
    now = time.time()
    if _cache_fg["data"] is not None and now - _cache_fg["ts"] < _CACHE_TTL:
        return _cache_fg["data"]
    try:
        r = requests.get(FNG_URL, params={"limit": limit}, timeout=12)
        r.raise_for_status()
        data = r.json().get("data", [])
        _cache_fg["data"] = data
        _cache_fg["ts"] = now
        return data
    except Exception:
        return []


def _classification(valeur):
    v = int(valeur)
    if v < 25:
        return "Extreme Fear"
    if v < 45:
        return "Fear"
    if v <= 55:
        return "Neutral"
    if v <= 75:
        return "Greed"
    return "Extreme Greed"


def _stats_sentiment(data):
    """Retourne (actuel, class_actuelle, moyenne_7j, trend_7j, extremes)."""
    if not data:
        return None
    actuel = int(data[0]["value"])
    class_actuel = data[0].get("value_classification") or _classification(actuel)
    derniers7 = [int(d["value"]) for d in data[:7]]
    moy7 = sum(derniers7) / len(derniers7) if derniers7 else actuel
    # trend: moyenne 7j actuelle vs 7j précédents
    prev7 = [int(d["value"]) for d in data[7:14]] if len(data) >= 14 else []
    trend = (moy7 - (sum(prev7) / len(prev7) if prev7 else moy7))
    # nombre de jours en Extreme Fear sur 30j
    extremes = sum(1 for d in data if int(d["value"]) < 25)
    return actuel, class_actuel, moy7, trend, extremes


def sentiment_prompt():
    """Bloc sentiment injecté dans le prompt evolver. Vide si indispo (graceful)."""
    data = fetch_fear_greed(30)
    s = _stats_sentiment(data)
    if not s:
        return ""
    actuel, classe, moy7, trend, extremes = s
    fleche = "↑ (moins peur)" if trend > 3 else ("↓ (plus peur)" if trend < -3 else "→ stable")
    lignes = []
    lignes.append(f"Sentiment actuel: {actuel}/100 ({classe}). Moyenne 7j: {moy7:.0f}. "
                   f"Trend 7j: {fleche}. Jours en Extreme Fear (30j): {extremes}.")
    if actuel < 25:
        lignes.append("CONTEXTE: Extreme Fear — historiquement une zone d'achat contrarian "
                      "(les capitulations marquent souvent les bottoms).")
    elif actuel > 75:
        lignes.append("CONTEXTE: Extreme Greed — euphorie, risque de top. Prudent sur les "
                      "nouveaux achats, stop-loss serrés.")
    return ("\n\n## SENTIMENT DU MARCHÉ (Fear & Greed Index)\n"
            "Le sentiment comportemental du marché crypto. "
            "Principe: sois avide quand les autres ont peur.\n"
            + "\n".join(lignes))


def get_fear_greed():
    """Retourne la valeur actuelle du Fear & Greed Index (0-100). 50 si indispo."""
    data = fetch_fear_greed(1)
    if not data:
        return 50
    return int(data[0]["value"])


def sentiment_multiplier():
    """Multiplicateur de taille contrarian pour ouvrir_position.
    Extreme Fear=1.0 (zone achat) ... Extreme Greed=0.5 (prudence).
    Retourne (mult, classe). 1.0 si indispo (ne modifie pas le sizing)."""
    data = fetch_fear_greed(1)
    if not data:
        return 1.0, "inconnu"
    actuel = int(data[0]["value"])
    classe = data[0].get("value_classification") or _classification(actuel)
    # Contrarian: plus de peur = plus de taille; plus de greed = moins
    if actuel < 25:
        mult = 1.00
    elif actuel < 45:
        mult = 0.95
    elif actuel <= 55:
        mult = 0.85
    elif actuel <= 75:
        mult = 0.70
    else:
        mult = 0.50
    return mult, classe


if __name__ == "__main__":
    print("=" * 60)
    print("SENTIMENT DU MARCHÉ (Fear & Greed Index)")
    print("=" * 60)
    print(sentiment_prompt() or "(indisponible)")
    mult, classe = sentiment_multiplier()
    print(f"\nMultiplicateur contrarian: x{mult:.2f} ({classe})")
