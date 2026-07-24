#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sentiment_gate.py — Filtre d'ENTRÉE basé sur le sentiment marché (Feature 2).

Complète le sizing contrarian (sentiment_marche.sentiment_multiplier) par un
GATE d'entrée (veto): BLOQUE les achats en euphorie (Extreme Greed) ou quand
l'actu crypto est fortement baissière. Principe contrarian + news-aware.

Sources (zéro coût d'API à l'entrée):
  - Fear & Greed Index (API gratuite sans clé, cache mémoire 30 min).
  - sentiment_web cache fichier (populé par le cron digest, TTL 6h) — lecture seule,
    aucun appel Perplexity pendant la boucle de trading.

Off par défaut (SENTIMENT_GATE=0). Fail-open: toute erreur -> autorise l'entrée.

CLI:
  python sentiment_gate.py [SYMBOLE]
"""
import os
import time
import json

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CACHE_WEB = os.path.join(DOSSIER, "sentiment_cache.json")

_FNG_CACHE = {"v": None, "t": 0.0}
FNG_TTL = 1800  # 30 min (l'index bouge lentement, valeur quotidienne)

# Seuils (contrarian + news-aware)
FNG_EUPHORIE = 80          # Extreme Greed: sommet, n'achète pas
WEB_BAISSIER_FORT = -0.5   # biais <= -0.5 + confiance haute = actu baissière
WEB_CONFIANCE_MIN = 0.7


def _fear_greed():
    """Valeur actuelle du F&G, avec cache mémoire 30 min. None si indispo."""
    now = time.time()
    if _FNG_CACHE["v"] is not None and now - _FNG_CACHE["t"] < FNG_TTL:
        return _FNG_CACHE["v"]
    try:
        from sentiment_marche import fetch_fear_greed
        data = fetch_fear_greed(limit=1)
        v = int(data[0]["value"]) if data else None
    except Exception:
        v = None
    _FNG_CACHE["v"] = v
    _FNG_CACHE["t"] = now
    return v


def _web_sentiment(symbole):
    """Lit le cache sentiment_web (biais -1..+1, confiance 0..1). Pas d'appel API."""
    try:
        cache = json.load(open(CACHE_WEB, encoding="utf-8"))
        e = cache.get(symbole) or {}
        return float(e.get("biais", 0) or 0), float(e.get("confiance", 0) or 0)
    except Exception:
        return 0.0, 0.0


def gate_achat(symbole):
    """Retourne (allow: bool, raison: str). allow=True si l'entrée est autorisée.

    Règles (contrarian + news-aware):
      1. BLOCK si F&G >= 80 (Extreme Greed euphorie sommet) — ne pas acheter le top.
      2. BLOCK si sentiment web baissier (biais <= -0.5) ET confiance >= 0.7
         — actu défavorable, ne pas acheter contre la tendance info.
      3. allow sinon.
    """
    fng = _fear_greed()
    biais, conf = _web_sentiment(symbole)

    if fng is not None and fng >= FNG_EUPHORIE:
        return False, f"Extreme Greed (F&G={fng}) — euphorie sommet, achat bloqué"

    if biais <= WEB_BAISSIER_FORT and conf >= WEB_CONFIANCE_MIN:
        return False, f"sentiment web baissier (biais={biais:+.2f}, conf={conf:.0%}) — actu défavorable"

    return True, f"sentiment OK (F&G={fng if fng is not None else 'n/a'}, biais={biais:+.2f})"


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    allow, raison = gate_achat(sym)
    print(f"{sym}: {'AUTORISÉ' if allow else 'BLOQUÉ'} — {raison}")
