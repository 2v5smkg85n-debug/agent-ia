#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""social_consensus.py — Consensus social multi-traders X/Twitter (Feature).

Surveille 8 traders crypto influents sur X/Twitter (via Nitter, sans API X
payante) et utilise l'API Perplexity pour extraire des signaux de trading
structurés (actif, direction, confiance, price_target, timeframe, raison)
depuis leurs posts récents. Les signaux sont ensuite agrégés en un score de
consensus social par actif, utilisable comme:
  - GATE d'entrée pour paper_trading.py (bloque l'achat si le consensus des
    traders est franchement baissier sur l'actif visé).
  - Résumé texte pour le digest Telegram.

Source: Perplexity API (web search intégré) — 1 seul appel par trader qui
cherche ET extrait les signaux en une seule requête. Pas besoin de Nitter
(ni d'API X payante).

Cache fichier /tmp/social_cache.json (TTL 30 min par handle) pour éviter de
marteler l'API à chaque cycle.

Off par défaut (SOCIAL_GATE=0). Fail-open: toute erreur, indispo Perplexity,
ou < 3 signaux -> autorise l'entrée (pas de blocage intempestif).

CLI (iPhone-friendly, une seule commande par usage):
  python social_consensus.py                  — run complet, affiche tout
  python social_consensus.py --gate BTCUSDT    — teste le gate pour un symbole
  python social_consensus.py --resume          — résumé texte digest Telegram
"""
import os
import re
import time
import json

try:
    import requests
except Exception:
    requests = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = "/tmp/social_cache.json"
CACHE_TTL = 1800  # 30 min — ne pas marteler Nitter

PPLX_API_KEY = os.getenv("PPLX_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PPLX_URL = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL = "llama-3.1-sonar-small-128k-online"

# Les 8 traders surveillés (handle -> description courte, pour audit/logs)
TRADERS = {
    "PeterLBrandt": "Peter Brandt — TA classique, tendances long terme",
    "TheCryptoLark": "Lark Davis — tech + fondamental, altcoins",
    "ToneVays": "Tone Vays — TA vidéo, niveaux BTC",
    "CryptoMichNL": "Michael Van De Poppe — trading court terme",
    "scottmelker": "Scott Melker — altcoins, pédagogique",
    "CryptoDogIII": "The Crypto Dog — momentum, informel",
    "donalt": "DonAlt — analyse chartiste, support/résistance",
    "woonomic": "Willy Woo — statistiques on-chain",
}

# Mapping noms crypto usuels -> symboles de trading de l'agent
SYMBOLE_MAP = {
    "BTC": "BTCUSDT", "BITCOIN": "BTCUSDT",
    "ETH": "ETHUSDT", "ETHEREUM": "ETHUSDT",
    "SOL": "SOLUSDT", "SOLANA": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT", "RIPPLE": "XRPUSDT",
    "ADA": "ADAUSDT", "CARDANO": "ADAUSDT",
    "DOGE": "DOGEUSDT", "DOGECOIN": "DOGEUSDT",
    "AVAX": "AVAXUSDT", "AVALANCHE": "AVAXUSDT",
    "DOT": "DOTUSDT", "POLKADOT": "DOTUSDT",
    "MATIC": "MATICUSDT", "POLYGON": "MATICUSDT",
    "LINK": "LINKUSDT", "CHAINLINK": "LINKUSDT",
    "LTC": "LTCUSDT", "LITECOIN": "LTCUSDT",
    "TRX": "TRXUSDT", "TRON": "TRXUSDT",
    "SHIB": "SHIBUSDT",
    "TON": "TONUSDT",
    "ATOM": "ATOMUSDT", "COSMOS": "ATOMUSDT",
    "UNI": "UNIUSDT", "UNISWAP": "UNIUSDT",
    "NEAR": "NEARUSDT",
    "APT": "APTUSDT", "APTOS": "APTUSDT",
    "ARB": "ARBUSDT", "ARBITRUM": "ARBUSDT",
    "OP": "OPUSDT", "OPTIMISM": "OPUSDT",
}

# Seuils de consensus (score = (bullish - bearish) / total, entre -1 et +1)
SEUIL_FORT = 0.5
SEUIL_MOYEN = 0.2
SEUIL_CONTRE = -0.2


# ---------------------------------------------------------------- UTILS

def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _load_cache():
    try:
        return json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def symbole_depuis_actif(actif):
    """Normalise un nom d'actif brut (BTC, Bitcoin, btc...) -> symbole trading."""
    if not actif:
        return None
    cle = str(actif).strip().upper()
    if cle in SYMBOLE_MAP:
        return SYMBOLE_MAP[cle]
    # déjà un symbole complet type BTCUSDT ?
    if cle.endswith("USDT"):
        return cle
    return None


# ---------------------------------------------------------------- PERPLEXITY WEB SEARCH

def _chercher_signaux_trader(handle):
    """Utilise Perplexity API (web search integre) pour chercher les derniers
    posts crypto du trader sur X/Twitter et en extraire des signaux structures.
    Un seul appel API par trader. Cache 30 min. Retourne liste de signaux."""
    cache = _load_cache()
    entry = cache.get(handle)
    now = time.time()
    if entry and now - entry.get("t", 0) < CACHE_TTL:
        return entry.get("signaux", [])

    if not PPLX_API_KEY or requests is None:
        return []

    desc = TRADERS.get(handle, "")
    system_prompt = (
        "Tu es un analyste de trading crypto. Cherche sur le web les derniers "
        "posts et analyses de ce trader sur X/Twitter et extrais ses signaux "
        "de trading crypto. Reponds en JSON uniquement."
    )
    user_prompt = (
        f"Trader: @{handle} ({desc})\n\n"
        "Cherche ses derniers posts sur X/Twitter (48 dernieres heures) concernant "
        "le crypto. Pour chaque signal trading trouve, extrais: asset (symbole court: "
        "BTC, ETH, SOL, etc.), direction (bullish/bearish/neutral), confidence (0.0-1.0), "
        "price_target (nombre ou null), timeframe (short/medium/long), reasoning (1 phrase). "
        'Reponds UNIQUEMENT avec un JSON: {"signaux": [{"asset": "...", "direction": "...", '
        '"confidence": 0.0, "price_target": null, "timeframe": "...", "reasoning": "..."}]}. '
        'Si aucun signal trouve, retourne {"signaux": []}.'
    )

    try:
        r = requests.post(
            PPLX_URL,
            headers={
                "Authorization": f"Bearer {PPLX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": PPLX_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        contenu = data["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", contenu, re.S)
        bloc = m.group(0) if m else contenu
        parsed = json.loads(bloc)
        signaux = parsed.get("signaux", []) if isinstance(parsed, dict) else []
        out = []
        for s in signaux:
            if not isinstance(s, dict):
                continue
            out.append({
                "asset": str(s.get("asset", "")).strip().upper(),
                "direction": str(s.get("direction", "neutral")).strip().lower(),
                "confidence": float(s.get("confidence", 0) or 0),
                "price_target": s.get("price_target"),
                "timeframe": str(s.get("timeframe", "medium")).strip().lower(),
                "reasoning": str(s.get("reasoning", "")).strip(),
                "trader": handle,
            })
        cache[handle] = {"t": now, "signaux": out}
        _save_cache(cache)
        return out
    except Exception:
        return []


# ---------------------------------------------------------------- COLLECTE / AGREGATION

def collecter_signaux():
    """Fonction principale: pour chacun des 8 traders, utilise Perplexity web
    search pour recuperer et extraire les signaux. Retourne la liste agrégée."""
    tous_signaux = []
    for handle in TRADERS:
        try:
            signaux = _chercher_signaux_trader(handle)
            tous_signaux.extend(signaux)
        except Exception:
            continue
    return tous_signaux


def consensus_social(symbole=None, signaux=None):
    """Agrège les signaux en un score de consensus.
    Si symbole est fourni, filtre uniquement les signaux de cet actif (BTC
    matche BTCUSDT, etc. via SYMBOLE_MAP).
    Retourne {score, bullish, bearish, neutral, total, signals, niveau}."""
    try:
        if signaux is None:
            signaux = collecter_signaux()

        if symbole:
            sym_norm = symbole.strip().upper()
            if not sym_norm.endswith("USDT"):
                sym_norm = symbole_depuis_actif(symbole) or sym_norm
            filtres = [
                s for s in signaux
                if symbole_depuis_actif(s.get("asset")) == sym_norm
            ]
        else:
            filtres = list(signaux)

        bullish = sum(1 for s in filtres if s.get("direction") == "bullish")
        bearish = sum(1 for s in filtres if s.get("direction") == "bearish")
        neutral = sum(1 for s in filtres if s.get("direction") == "neutral")
        total = len(filtres)

        score = (bullish - bearish) / total if total > 0 else 0.0

        if score > SEUIL_FORT:
            niveau = "fort"
        elif score > SEUIL_MOYEN:
            niveau = "moyen"
        elif score >= SEUIL_CONTRE:
            niveau = "faible"
        else:
            niveau = "contre"

        return {
            "score": round(score, 3),
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
            "total": total,
            "signals": filtres,
            "niveau": niveau,
        }
    except Exception:
        return {"score": 0.0, "bullish": 0, "bearish": 0, "neutral": 0,
                "total": 0, "signals": [], "niveau": "faible"}


# ---------------------------------------------------------------- GATE (paper_trading)

def gate_achat(symbole):
    """Gate d'entrée pour paper_trading.py. Retourne (allow: bool, raison: str).

    Règles:
      - Si SOCIAL_GATE != "1" -> ce gate n'est pas censé être appelé, mais on
        autorise par sécurité (l'activation se fait côté appelant).
      - Si < 3 signaux au total pour l'actif -> fail-open, "consensus insuffisant".
      - Si score < -0.2 (niveau "contre") ET total >= 3 -> BLOCK.
      - Sinon (bullish ou neutre) -> allow.
    """
    try:
        res = consensus_social(symbole)
        if res["total"] < 3:
            return True, "consensus insuffisant"
        if res["score"] < SEUIL_CONTRE and res["total"] >= 3:
            return False, (
                f"consensus social baissier (score={res['score']:+.2f}, "
                f"{res['bearish']} bearish / {res['total']} signaux)"
            )
        return True, (
            f"consensus social OK (score={res['score']:+.2f}, "
            f"{res['bullish']} bullish / {res['total']} signaux)"
        )
    except Exception as e:
        return True, f"gate erreur (fail-open): {e}"


# ---------------------------------------------------------------- RESUME (digest)

def resume():
    """Résumé texte pour le digest Telegram: top actifs avec score de consensus
    + dernier signal individuel par trader."""
    try:
        signaux = collecter_signaux()
        if not signaux:
            return "📊 Social Consensus: aucun signal disponible (Nitter/Perplexity indispo)"

        actifs = set()
        for s in signaux:
            sym = symbole_depuis_actif(s.get("asset"))
            if sym:
                actifs.add(sym)

        lignes = ["📊 Social Consensus:"]
        # tri par |score| décroissant pour mettre en avant les consensus les plus nets
        resultats = []
        for sym in actifs:
            r = consensus_social(sym, signaux=signaux)
            resultats.append((sym, r))
        resultats.sort(key=lambda x: abs(x[1]["score"]), reverse=True)

        for sym, r in resultats[:6]:
            nom = sym.replace("USDT", "")
            lignes.append(
                f"  {nom}: {r['score']:+.1f} ({r['bullish']} bullish, "
                f"{r['bearish']} bearish) — {r['niveau'].upper()}"
            )

        lignes.append("")
        lignes.append("Derniers signaux par trader:")
        par_trader = {}
        for s in signaux:
            par_trader[s.get("trader")] = s  # le dernier écrase (ordre de collecte)
        for handle in TRADERS:
            s = par_trader.get(handle)
            if not s:
                continue
            lignes.append(
                f"  @{handle}: {s.get('asset', '?')} {s.get('direction', '?')} "
                f"(conf {s.get('confidence', 0):.0%}) — {s.get('reasoning', '')}"
            )

        return "\n".join(lignes)
    except Exception as e:
        return f"📊 Social Consensus: erreur ({e})"


# ---------------------------------------------------------------- CLI

def main():
    import sys
    args = sys.argv[1:]
    try:
        if "--gate" in args:
            idx = args.index("--gate")
            symbole = args[idx + 1] if idx + 1 < len(args) else "BTCUSDT"
            allow, raison = gate_achat(symbole)
            print(f"{symbole}: {'AUTORISÉ' if allow else 'BLOQUÉ'} — {raison}")
            return
        if "--resume" in args:
            print(resume())
            return
        # run complet par défaut
        signaux = collecter_signaux()
        print(f"Signaux collectés: {len(signaux)}")
        for s in signaux:
            print(f"  [{s.get('trader')}] {s.get('asset')} {s.get('direction')} "
                  f"conf={s.get('confidence')} tf={s.get('timeframe')} "
                  f"tp={s.get('price_target')} — {s.get('reasoning')}")
        print()
        print(resume())
    except Exception as e:
        print(f"[social_consensus] erreur: {e}")


if __name__ == "__main__":
    main()
