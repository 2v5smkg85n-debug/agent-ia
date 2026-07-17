#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sentiment_web.py — Sentiment de marche depuis le web (Perplexity sonar).

Interroge le web en temps reel pour determiner le biais directionnel
(haussier/baissier) court terme d'un actif + confiance + resume.

Cache fichier (TTL 6h) pour preserver le quota API.
Integre a la reflexion quotidienne (digest web). Filtre live = apres observation.

CLI:
  python sentiment_web.py             # digest de tous les marches cles
  python sentiment_web.py BTCUSDT     # sentiment d'un actif precis
"""
import os
import re
import json
import time
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(DOSSIER, ".env"))

PPLX_KEY = os.getenv("PPLX_API_KEY", "")
PPLX_URL = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")
CACHE_FILE = os.path.join(DOSSIER, "sentiment_cache.json")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
TTL = 6 * 3600  # 6 heures

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("sentiment")

# Noms lisibles pour ameliorer la qualite des requetes web
NOM_MARCHE = {
    "BTCUSDT": "Bitcoin (BTC)", "ETHUSDT": "Ethereum (ETH)",
    "SOLUSDT": "Solana (SOL)", "BNBUSDT": "BNB", "XRPUSDT": "XRP",
    "EURUSD=X": "Euro vs Dollar (EUR/USD)", "EURUSD": "Euro vs Dollar (EUR/USD)",
    "JPY=X": "Dollar vs Yen (USD/JPY)",
    "^GSPC": "S&P 500 (indice actions US)", "^FCHI": "CAC 40 (indice Paris)",
    "GC=F": "Or (Gold futures)", "CL=F": "Petrole WTI (crude oil futures)",
    "NG=F": "Gaz naturel (natural gas futures)", "SI=F": "Argent (Silver futures)",
}


def _nom(symbole):
    return NOM_MARCHE.get(symbole, symbole)


def _load_cache():
    try:
        return json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        log.warning("save cache sentiment: %s", e)


def _query_sonar(symbole):
    """Interroge Perplexity sonar pour le sentiment d'un actif."""
    import requests
    if not PPLX_KEY:
        return None
    nom = _nom(symbole)
    prompt = (
        "Tu es analyste de marche. Analyse l'actualite RECENTE (24-48h) de "
        + nom + " (symbole " + symbole
        + "): news, sentiment marches, analystes, catalyseurs. "
        "Determine le biais directionnel COURT TERME (jours a venir). "
        "Reponds en JSON STRICT (sans markdown, sans texte autour): "
        '{"biais": <nombre -1.0 a +1.0, negatif=baissier positif=haussier 0=neutre>, '
        '"confiance": <0.0 a 1.0>, "resume": "<1 phrase facteurs cles>", '
        '"catalyseurs": ["<facteur 1>", "<facteur 2>"]}'
    )
    headers = {"Authorization": "Bearer " + PPLX_KEY, "content-type": "application/json"}
    payload = {"model": PPLX_MODEL, "max_tokens": 600,
               "messages": [{"role": "user", "content": prompt}]}
    try:
        r = requests.post(PPLX_URL, headers=headers, json=payload, timeout=60)
        if r.status_code == 429:
            log.warning("sonar quota epuise pour %s", symbole)
            return None
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("sonar %s erreur: %s", symbole, e)
        return None
    # extraction JSON robuste
    content = content.strip()
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    return {
        "symbole": symbole,
        "biais": float(data.get("biais", 0) or 0),
        "confiance": float(data.get("confiance", 0) or 0),
        "resume": str(data.get("resume", ""))[:200],
        "catalyseurs": data.get("catalyseurs", [])[:5],
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "perplexity-sonar",
    }


def sentiment_actif(symbole):
    """Biais web d'un actif (avec cache 6h). Retourne dict ou None."""
    cache = _load_cache()
    entry = cache.get(symbole)
    if entry and (time.time() - entry.get("_ts_epoch", 0)) < TTL:
        return entry
    r = _query_sonar(symbole)
    if r:
        r["_ts_epoch"] = time.time()
        cache[symbole] = r
        _save_cache(cache)
    return r


def digest_sentiment(symbols=None):
    """Digest formate du sentiment web pour la reflexion.
    Par defaut: positions ouvertes + marches cles (BTC, ETH, EUR/USD, S&P, Or)."""
    try:
        pf = json.load(open(PT_FILE, encoding="utf-8"))
    except Exception:
        pf = {}
    syms = set(symbols) if symbols else set()
    for p in pf.get("positions", []):
        if p.get("symbole"):
            syms.add(p["symbole"])
    for s in ("BTCUSDT", "ETHUSDT", "EURUSD=X", "^GSPC", "GC=F"):
        syms.add(s)
    lignes = []
    for s in sorted(syms):
        r = sentiment_actif(s)
        if not r:
            lignes.append(s + ": (indispo)")
            continue
        b = r.get("biais", 0)
        c = r.get("confiance", 0)
        arrow = "HAUSSIER" if b > 0.2 else ("BAISSIER" if b < -0.2 else "NEUTRE")
        lignes.append(s + ": " + arrow + " biais=" + format(b, "+.2f")
                      + " conf=" + format(c, ".2f")
                      + " | " + str(r.get("resume", ""))[:120])
    return "\n".join(lignes) if lignes else "(indispo)"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        r = sentiment_actif(sys.argv[1])
        print(json.dumps(r, ensure_ascii=False, indent=2) if r else "indispo")
    else:
        print(digest_sentiment())
