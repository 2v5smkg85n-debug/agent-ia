#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""social_consensus.py — Consensus social multi-traders X/Twitter (Feature).

Simule 8 traders crypto influents (personas connus, style/méthodologie
publique) et utilise l'API Gemini pour générer des signaux de trading
structurés (actif, direction, confiance, price_target, timeframe, raison)
en se basant sur le style habituel de chaque trader ET les conditions de
marché récentes (prix + Fear & Greed Index). Les signaux sont ensuite
agrégés en un score de consensus social par actif, utilisable comme:
  - GATE d'entrée pour paper_trading.py (bloque l'achat si le consensus des
    traders est franchement baissier sur l'actif visé).
  - Résumé texte pour le digest Telegram.

Source: API Gemini (pas de recherche web intégrée) — comme Gemini n'a pas
accès au web en direct, on lui fournit le contexte marché (prix 24h Binance
+ Fear & Greed Index) et on lui demande d'analyser, pour chaque trader
connu, quels actifs seraient bullish/bearish selon SA méthodologie
habituelle appliquée à ces conditions de marché. Ce sont donc des "signaux
synthétiques" ancrés sur des données de marché réelles, pas des posts
réels extraits du web.

Cache fichier /tmp/social_cache.json (TTL 30 min par handle) pour éviter de
marteler l'API à chaque cycle. Le contexte marché (prix + F&G) est lui
aussi caché 30 min pour limiter les appels Binance/alternative.me.

Off par défaut (SOCIAL_GATE=0). Fail-open: toute erreur, indispo Gemini,
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
CACHE_TTL = 1800  # 30 min — ne pas marteler Gemini/Binance

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
FNG_URL = "https://api.alternative.me/fng/"
MARCHE_SYMBOLES = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

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


# ---------------------------------------------------------------- CONTEXTE MARCHE

def _fetch_market_context():
    """Récupère le contexte marché courant (prix/variations 24h Binance +
    Fear & Greed Index). Caché 30 min sous la clé '_market' du cache pour
    éviter de marteler Binance/alternative.me à chaque trader/cycle.
    Retourne un dict {"prix": {...}, "fear_greed": {...}} (vide si erreur)."""
    cache = _load_cache()
    entry = cache.get("_market")
    now = time.time()
    if entry and now - entry.get("t", 0) < CACHE_TTL:
        return entry.get("data", {})

    ctx = {"prix": {}, "fear_greed": {}}
    if requests is None:
        return ctx

    # Prix / variations 24h via Binance (public, sans clé)
    try:
        symbols_param = json.dumps(MARCHE_SYMBOLES)
        r = requests.get(
            BINANCE_TICKER_URL,
            params={"symbols": symbols_param},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        for item in data:
            sym = item.get("symbol")
            if not sym:
                continue
            ctx["prix"][sym] = {
                "prix": item.get("lastPrice"),
                "variation_24h_pct": item.get("priceChangePercent"),
                "volume_24h": item.get("volume"),
                "high_24h": item.get("highPrice"),
                "low_24h": item.get("lowPrice"),
            }
    except Exception:
        pass

    # Fear & Greed Index (public, sans clé)
    try:
        r = requests.get(FNG_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", [])
        if items:
            fng = items[0]
            ctx["fear_greed"] = {
                "valeur": fng.get("value"),
                "classification": fng.get("value_classification"),
            }
    except Exception:
        pass

    cache = _load_cache()
    cache["_market"] = {"t": now, "data": ctx}
    _save_cache(cache)
    return ctx


# ---------------------------------------------------------------- GEMINI (analyse persona)

def _chercher_signaux_trader(handle):
    """Utilise l'API Gemini pour générer des signaux synthétiques crédibles
    pour ce trader: on fournit à Gemini la persona du trader (style/
    méthodologie connue publiquement) + le contexte marché actuel (prix
    Binance + Fear & Greed Index), et on lui demande d'analyser quels actifs
    seraient bullish/bearish selon la méthodologie habituelle de ce trader
    appliquée aux conditions de marché du moment. Pas de recherche web réelle
    (Gemini n'en a pas) — ce sont des signaux "synthétiques" ancrés sur des
    données de marché réelles. Un seul appel API par trader. Cache 30 min.
    Retourne liste de signaux."""
    cache = _load_cache()
    entry = cache.get(handle)
    now = time.time()
    if entry and now - entry.get("t", 0) < CACHE_TTL:
        return entry.get("signaux", [])

    if not GEMINI_API_KEY or requests is None:
        return []

    desc = TRADERS.get(handle, "")
    marche = _fetch_market_context()

    prompt = (
        f"En tant que {handle} ({desc}), analyse le marché crypto actuel. "
        "Quels actifs crypto seraient bullish/bearish selon ton style de "
        "trading? Base toi sur ta méthodologie habituelle et les conditions "
        "de marché récentes.\n\n"
        "DONNEES DE MARCHE ACTUELLES (Binance, 24h):\n"
        f"{json.dumps(marche.get('prix', {}), ensure_ascii=False, indent=2)}\n\n"
        "FEAR & GREED INDEX:\n"
        f"{json.dumps(marche.get('fear_greed', {}), ensure_ascii=False)}\n\n"
        "Pour chaque signal trading identifié, extrais: asset (symbole court: "
        "BTC, ETH, SOL, etc.), direction (bullish/bearish/neutral), "
        "confidence (0.0-1.0), price_target (nombre ou null), timeframe "
        "(short/medium/long), reasoning (1 phrase resumant ta methodologie "
        "appliquee a ce cas). "
        'Reponds UNIQUEMENT avec un JSON: {"signaux": [{"asset": "...", '
        '"direction": "...", "confidence": 0.0, "price_target": null, '
        '"timeframe": "...", "reasoning": "..."}]}. '
        'Si aucun signal pertinent, retourne {"signaux": []}.'
    )

    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
        }
        r = requests.post(GEMINI_URL, json=payload, timeout=45)
        r.raise_for_status()
        data = r.json()
        contenu = data["candidates"][0]["content"]["parts"][0]["text"]
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
        cache = _load_cache()
        cache[handle] = {"t": now, "signaux": out}
        _save_cache(cache)
        return out
    except Exception:
        return []


# ---------------------------------------------------------------- COLLECTE / AGREGATION

def collecter_signaux():
    """Fonction principale: pour chacun des 8 traders, utilise Gemini pour
    générer les signaux synthétiques basés sur leur persona + le marché
    actuel. Retourne la liste agrégée."""
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
            return "📊 Social Consensus: aucun signal disponible (Gemini indispo)"

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
