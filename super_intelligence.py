#!/usr/bin/env python3
"""
super_intelligence.py - Couche 5: Super-intelligence multi-sources
- Analyse IA multi-modeles (Gemini + Perplexity) sur le marche
- News sentiment en temps reel (crypto news + analyse IA)
- On-chain metrics (whale movements, exchange flows)
- Patterns de chart avances (tete-epaules, triangles, wedges, double top/bottom)
- Social sentiment (Reddit mentions, trending)
- Funding rates (sentiment futures)
- Correlation macro (DXY, S&P 500, gold, BTC dominance)
- Volume profile + VWAP avance
"""

import json
import os
import time
import math
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_SI = os.path.join(DOSSIER, "super_intelligence.json")

# Charger les cles API
def _load_env():
    env_path = os.path.join(DOSSIER, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

_load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PPLX_API_KEY = os.environ.get("PPLX_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

COIN_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink", "ARBUSDT": "arbitrum",
    "NEARUSDT": "near", "FETUSDT": "fetch-ai", "RNDRUSDT": "render-token",
    "LDOUSDT": "lido-dao", "AAVEUSDT": "aave", "PENDLEUSDT": "pendle",
}

_cache = {}

def _save_si(data):
    try:
        with open(FICHIER_SI, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _load_si():
    try:
        with open(FICHIER_SI) as f:
            return json.load(f)
    except Exception:
        return {}


# ============================================
# 1. ANALYSE IA MULTI-MODELES
# ============================================
_cache_ia = {"data": None, "ts": 0}

def analyse_ia_marche(symbole="BTCUSDT"):
    """Utilise Gemini AI pour analyser le marche en temps reel.
    L'IA recoit les donnees techniques et donne un verdict.
    """
    if _cache_ia["data"] is not None and time.time() - _cache_ia["ts"] < 300:
        return _cache_ia["data"]

    try:
        import master_traders as mt
        import intelligence_pro as ip

        # Recolter les donnees
        prix_histo = mt.get_prix_histo(symbole)
        if len(prix_histo) < 10:
            return {"score": 0, "verdict": "donnees insuffisantes", "confiance": 0}

        prix_actuel = prix_histo[-1]
        sma20 = sum(prix_histo[-20:]) / 20 if len(prix_histo) >= 20 else prix_actuel
        sma50 = sum(prix_histo[-50:]) / 50 if len(prix_histo) >= 50 else sma20
        var_24h = (prix_histo[-1] - prix_histo[-2]) / prix_histo[-2] * 100 if len(prix_histo) >= 2 else 0
        var_7j = (prix_histo[-1] - prix_histo[-8]) / prix_histo[-8] * 100 if len(prix_histo) >= 8 else 0

        # Consensus maitres
        score_mt, details_mt, reco_mt, extra_mt = mt.consensus_maitres(symbole)
        patterns = extra_mt.get("patterns", "aucun")

        # Fear & Greed
        fg = ip.get_fear_greed()

        # Regime
        regime, regime_detail, regime_score = ip.regime_global()

        # Prompt pour l'IA
        prompt = f"""Analyse le marche crypto {symbole} en tant que trader professionnel:

DONNEES TECHNIQUES:
- Prix actuel: ${prix_actuel:.2f}
- Variation 24h: {var_24h:+.2f}%
- Variation 7j: {var_7j:+.2f}%
- SMA20: ${sma20:.2f} (prix {'au-dessus' if prix_actuel > sma20 else 'en-dessous'})
- SMA50: ${sma50:.2f} (prix {'au-dessus' if prix_actuel > sma50 else 'en-dessous'})
- Patterns bougies: {patterns}
- Consensus 10 maitres traders: {reco_mt} (score {score_mt:+.2f})
- Fear & Greed Index: {fg.get('value', 50)} ({fg.get('classification', 'Neutral')})
- Regime de marche: {regime} ({regime_detail})

Donne ton analyse en format JSON strict:
{{"verdict": "ACHAT/VENTE/ATTENDRE", "confiance": 0-100, "raison": "...", "target_prix": ..., "risque": "FAIBLE/MODERE/ELEVE"}}
Reponds UNIQUEMENT avec le JSON."""

        # Appel Gemini
        verdict_ia = _call_gemini(prompt)

        # Appel Perplexity (si cle valide)
        verdict_pplx = _call_perplexity(prompt)

        # Consensus des deux IA
        result = {
            "gemini": verdict_ia,
            "perplexity": verdict_pplx,
            "score": 0,
            "verdict": "ATTENDRE",
            "confiance": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Calculer le consensus
        scores = []
        for v in [verdict_ia, verdict_pplx]:
            if v and "verdict" in v:
                if v["verdict"] == "ACHAT":
                    scores.append(v.get("confiance", 50) / 100 * 2)
                elif v["verdict"] == "VENTE":
                    scores.append(-v.get("confiance", 50) / 100 * 2)
                else:
                    scores.append(0)

        if scores:
            result["score"] = sum(scores) / len(scores)
            result["confiance"] = abs(result["score"]) * 50
            if result["score"] > 0.5:
                result["verdict"] = "ACHAT"
            elif result["score"] < -0.5:
                result["verdict"] = "VENTE"
            else:
                result["verdict"] = "ATTENDRE"

        _cache_ia["data"] = result
        _cache_ia["ts"] = time.time()
        return result

    except Exception as e:
        print(f"[SI] Erreur analyse IA: {e}")
        return {"score": 0, "verdict": "erreur", "confiance": 0, "erreur": str(e)}


def _call_gemini(prompt):
    """Appelle l'API Gemini pour une analyse."""
    if not GEMINI_API_KEY:
        return None
    try:
        import urllib.request
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300}
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Extraire le JSON
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"[SI] Erreur Gemini: {e}")
        return None


def _call_perplexity(prompt):
    """Appelle l'API Perplexity pour une analyse."""
    if not PPLX_API_KEY:
        return None
    try:
        import urllib.request
        url = "https://api.perplexity.ai/chat/completions"
        payload = json.dumps({
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 300,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {PPLX_API_KEY}"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        text = data["choices"][0]["message"]["content"]
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"[SI] Erreur Perplexity: {e}")
        return None


# ============================================
# 2. NEWS SENTIMENT TEMPS REEL
# ============================================
_cache_news = {"data": None, "ts": 0}

def get_crypto_news(symbole="BTCUSDT"):
    """Recupere les dernieres news crypto depuis CoinGecko/CryptoCompare."""
    if _cache_news["data"] is not None and time.time() - _cache_news["ts"] < 600:
        return _cache_news["data"]

    news_list = []

    # CryptoCompare news API (gratuit, pas de cle)
    try:
        import urllib.request
        coin_name = symbole.replace("USDT", "")
        url = f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={coin_name}&limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for article in data.get("Data", []):
            news_list.append({
                "title": article.get("title", ""),
                "source": article.get("source_info", {}).get("name", ""),
                "url": article.get("url", ""),
                "published": datetime.fromtimestamp(article.get("published_on", 0)).strftime("%H:%M"),
                "body": article.get("body", "")[:200],
            })
    except Exception as e:
        print(f"[SI] Erreur news: {e}")

    _cache_news["data"] = news_list
    _cache_news["ts"] = time.time()
    return news_list


def analyse_news_sentiment(symbole="BTCUSDT"):
    """Analyse le sentiment des news avec Gemini AI."""
    news = get_crypto_news(symbole)
    if not news:
        return {"score": 0, "sentiment": "neutre", "nb_news": 0, "detail": "aucune news"}

    try:
        # Preparer le resume des titres
        titres = "\n".join([f"- {n['title']}" for n in news[:5]])
        prompt = f"""Analyse le sentiment de ces news crypto pour {symbole}:

{titres}

Donne ton analyse en JSON strict:
{{"sentiment": "positif/neutre/negatif", "score": -2 a +2, "resume": "...", "impact": "FAIBLE/MODERE/FORT"}}
Reponds UNIQUEMENT avec le JSON."""

        result = _call_gemini(prompt)
        if result:
            result["nb_news"] = len(news)
            return result
        else:
            # Fallback: analyse basique par mots-cles
            return _sentiment_fallback(news)
    except Exception as e:
        return _sentiment_fallback(news)


def _sentiment_fallback(news_list):
    """Analyse basique du sentiment par mots-cles si l'IA est indisponible."""
    mots_positifs = ["bullish", "surge", "rally", "breakout", "adoption", "partnership", "upgrade", "gain", "soar", "pump"]
    mots_negatifs = ["bearish", "crash", "dump", "hack", "ban", "sell-off", "decline", "fear", "plunge", "scam"]

    score = 0
    for n in news_list:
        titre = n.get("title", "").lower()
        for mot in mots_positifs:
            if mot in titre:
                score += 1
        for mot in mots_negatifs:
            if mot in titre:
                score -= 1

    sentiment = "positif" if score > 0 else ("negatif" if score < 0 else "neutre")
    return {
        "sentiment": sentiment,
        "score": max(-2, min(2, score)),
        "resume": f"Analyse par mots-cles: {score} signaux",
        "impact": "MODERE" if abs(score) >= 2 else "FAIBLE",
        "nb_news": len(news_list),
    }


# ============================================
# 3. ON-CHAIN METRICS (WHALES & FLOWS)
# ============================================
_cache_onchain = {"data": None, "ts": 0}

def get_onchain_metrics(symbole="BTCUSDT"):
    """Recupere les metriques on-chain publiques."""
    if _cache_onchain["data"] is not None and time.time() - _cache_onchain["ts"] < 600:
        return _cache_onchain["data"]

    metrics = {}

    # Blockchain.com API (BTC seulement, gratuit)
    if symbole == "BTCUSDT":
        try:
            import urllib.request
            # Hashrate (indicateur de sante du reseau)
            url = "https://blockchain.info/q/hashrate"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                hashrate = int(resp.read())
            metrics["hashrate"] = hashrate

            # Difficulty
            url2 = "https://blockchain.info/q/getdifficulty"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                difficulty = float(resp2.read())
            metrics["difficulty"] = difficulty

            # Confirmation time (moyenne)
            url3 = "https://blockchain.info/q/avgtxsize"
            req3 = urllib.request.Request(url3, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req3, timeout=10) as resp3:
                tx_size = int(resp3.read())
            metrics["avg_tx_size"] = tx_size
        except Exception as e:
            print(f"[SI] Erreur onchain BTC: {e}")

    # Whale transactions via Blockchain.com (large transactions)
    try:
        import urllib.request
        url = "https://blockchain.info/unconfirmed-transactions?format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        txs = data.get("txs", [])
        # Compter les grosses transactions (> 10 BTC)
        grosses_tx = [tx for tx in txs[:100] if any(int(out.get("value", 0)) > 1000000000 for out in tx.get("out", []))]
        metrics["whale_tx_count"] = len(grosses_tx)
        metrics["whale_activity"] = "HAUTE" if len(grosses_tx) > 5 else ("MODEREE" if len(grosses_tx) > 2 else "FAIBLE")
    except Exception as e:
        print(f"[SI] Erreur whale tx: {e}")

    _cache_onchain["data"] = metrics
    _cache_onchain["ts"] = time.time()
    return metrics


def analyse_onchain(symbole="BTCUSDT"):
    """Analyse les metriques on-chain pour un signal de trading."""
    metrics = get_onchain_metrics(symbole)
    if not metrics:
        return {"score": 0, "detail": "donnees on-chain indisponibles"}

    score = 0
    details = []

    # Whale activity
    whale = metrics.get("whale_activity", "FAIBLE")
    if whale == "HAUTE":
        score += 1
        details.append(f"Activite whale haute ({metrics.get('whale_tx_count', 0)} grosses tx)")
    elif whale == "MODEREE":
        score += 0.5
        details.append("Activite whale moderee")

    # Hashrate (BTC seulement)
    if "hashrate" in metrics:
        details.append(f"Hashrate: {metrics['hashrate'] / 1e9:.1f} GH/s (reseau sain)")

    return {"score": score, "detail": ", ".join(details), "metrics": metrics}


# ============================================
# 4. PATTERNS DE CHART AVANCES
# ============================================
def detecter_patterns_avances(prix_histo):
    """Detecte les patterns de chart avances:
    - Tete et epaules
    - Double top / double bottom
    - Triangle ascendant / descendant
    - Wedge ascending / descending
    - Drapeau (flag)
    """
    patterns = []
    if len(prix_histo) < 30:
        return patterns

    # Extraire les hauts et bas (swings)
    hauts = []
    bas = []
    for i in range(2, len(prix_histo) - 2):
        if prix_histo[i] > prix_histo[i-1] and prix_histo[i] > prix_histo[i-2] and prix_histo[i] > prix_histo[i+1] and prix_histo[i] > prix_histo[i+2]:
            hauts.append((i, prix_histo[i]))
        if prix_histo[i] < prix_histo[i-1] and prix_histo[i] < prix_histo[i-2] and prix_histo[i] < prix_histo[i+1] and prix_histo[i] < prix_histo[i+2]:
            bas.append((i, prix_histo[i]))

    # 1. DOUBLE TOP (M) - baissier
    if len(hauts) >= 2:
        h1, h2 = hauts[-2], hauts[-1]
        if abs(h1[1] - h2[1]) / h1[1] < 0.02 and h2[0] - h1[0] >= 3:
            patterns.append({
                "nom": "Double Top",
                "signal": "baissier",
                "score": -2,
                "detail": f"deux sommets a {h1[1]:.2f} et {h2[1]:.2f} - cassure probable",
            })

    # 2. DOUBLE BOTTOM (W) - haussier
    if len(bas) >= 2:
        b1, b2 = bas[-2], bas[-1]
        if abs(b1[1] - b2[1]) / b1[1] < 0.02 and b2[0] - b1[0] >= 3:
            patterns.append({
                "nom": "Double Bottom",
                "signal": "haussier",
                "score": 2,
                "detail": f"deux creux a {b1[1]:.2f} et {b2[1]:.2f} - rebond probable",
            })

    # 3. TETE ET EPAULES - baissier
    if len(hauts) >= 3:
        h1, h2, h3 = hauts[-3], hauts[-2], hauts[-1]
        if h2[1] > h1[1] and h2[1] > h3[1]:
            diff_e1 = abs(h1[1] - h3[1]) / h1[1]
            if diff_e1 < 0.05:
                patterns.append({
                    "nom": "Tete et Epaules",
                    "signal": "baissier",
                    "score": -3,
                    "detail": f"tete a {h2[1]:.2f}, epaules a {h1[1]:.2f}/{h3[1]:.2f} - cassure baissiere",
                })

    # 4. TRIANGLE ASCENDANT - haussier
    if len(hauts) >= 2 and len(bas) >= 2:
        h1, h2 = hauts[-2], hauts[-1]
        b1, b2 = bas[-2], bas[-1]
        # Resistance horizontale + support ascendant
        if abs(h1[1] - h2[1]) / h1[1] < 0.02 and b2[1] > b1[1]:
            patterns.append({
                "nom": "Triangle Ascendant",
                "signal": "haussier",
                "score": 2,
                "detail": f"resistance {h2[1]:.2f}, support ascendant - breakout haussier",
            })

    # 5. TRIANGLE DESCENDANT - baissier
    if len(hauts) >= 2 and len(bas) >= 2:
        h1, h2 = hauts[-2], hauts[-1]
        b1, b2 = bas[-2], bas[-1]
        if abs(b1[1] - b2[1]) / b1[1] < 0.02 and h2[1] < h1[1]:
            patterns.append({
                "nom": "Triangle Descendant",
                "signal": "baissier",
                "score": -2,
                "detail": f"support {b2[1]:.2f}, resistance descendante - breakdown probable",
            })

    # 6. WEDGE ASCENDANT - baissier (resserrement ascendant)
    if len(hauts) >= 2 and len(bas) >= 2:
        h1, h2 = hauts[-2], hauts[-1]
        b1, b2 = bas[-2], bas[-1]
        pente_h = (h2[1] - h1[1]) / (h2[0] - h1[0]) if h2[0] != h1[0] else 0
        pente_b = (b2[1] - b1[1]) / (b2[0] - b1[0]) if b2[0] != b1[0] else 0
        if pente_h > 0 and pente_b > 0 and pente_b > pente_h:
            patterns.append({
                "nom": "Wedge Ascendant",
                "signal": "baissier",
                "score": -1,
                "detail": "resserrement ascendant - cassure baissiere probable",
            })

    # 7. WEDGE DESCENDANT - haussier (resserrement descendant)
    if len(hauts) >= 2 and len(bas) >= 2:
        h1, h2 = hauts[-2], hauts[-1]
        b1, b2 = bas[-2], bas[-1]
        pente_h = (h2[1] - h1[1]) / (h2[0] - h1[0]) if h2[0] != h1[0] else 0
        pente_b = (b2[1] - b1[1]) / (b2[0] - b1[0]) if b2[0] != b1[0] else 0
        if pente_h < 0 and pente_b < 0 and abs(pente_h) > abs(pente_b):
            patterns.append({
                "nom": "Wedge Descendant",
                "signal": "haussier",
                "score": 1,
                "detail": "resserrement descendant - cassure haussiere probable",
            })

    # 8. SUPPORT / RESISTANCE KEY
    prix_actuel = prix_histo[-1]
    if len(prix_histo) >= 50:
        max_50 = max(prix_histo[-50:])
        min_50 = min(prix_histo[-50:])
        position = (prix_actuel - min_50) / (max_50 - min_50) * 100 if max_50 != min_50 else 50
        if position < 10:
            patterns.append({
                "nom": "Proximite Support Fort",
                "signal": "haussier",
                "score": 2,
                "detail": f"prix au plus bas 50j ({position:.0f}% du range) - support proche",
            })
        elif position > 90:
            patterns.append({
                "nom": "Proximite Resistance Forte",
                "signal": "baissier",
                "score": -1,
                "detail": f"prix au plus haut 50j ({position:.0f}% du range) - resistance proche",
            })

    return patterns


# ============================================
# 5. SOCIAL SENTIMENT (REDDIT)
# ============================================
_cache_social = {"data": None, "ts": 0}

def get_social_sentiment(symbole="BTCUSDT"):
    """Recupere le sentiment social depuis Reddit et autres sources."""
    if _cache_social["data"] is not None and time.time() - _cache_social["ts"] < 600:
        return _cache_social["data"]

    result = {"mentions": 0, "sentiment": "neutre", "score": 0, "detail": ""}

    # Reddit: compter les mentions (via JSON API public)
    try:
        import urllib.request
        coin_name = symbole.replace("USDT", "")
        # r/CryptoCurrency search
        url = f"https://www.reddit.com/search.json?q={coin_name}&sort=new&limit=25&t=day"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        posts = data.get("data", {}).get("children", [])
        result["mentions"] = len(posts)

        # Analyser les titres (sentiment basique)
        positifs = 0
        negatifs = 0
        mots_pos = ["bullish", "moon", "pump", "buy", "surge", "rally", "breakout", "support"]
        mots_neg = ["bearish", "crash", "dump", "sell", "scam", "fear", "plunge", "bear"]

        for post in posts:
            titre = post.get("data", {}).get("title", "").lower()
            for mot in mots_pos:
                if mot in titre:
                    positifs += 1
            for mot in mots_neg:
                if mot in titre:
                    negatifs += 1

        score = positifs - negatifs
        result["score"] = max(-2, min(2, score))
        result["positifs"] = positifs
        result["negatifs"] = negatifs

        if score > 1:
            result["sentiment"] = "positif"
            result["detail"] = f"{positifs} mentions positives vs {negatifs} negatives"
        elif score < -1:
            result["sentiment"] = "negatif"
            result["detail"] = f"{positifs} mentions positives vs {negatifs} negatives"
        else:
            result["sentiment"] = "neutre"
            result["detail"] = f"{positifs} positives vs {negatifs} negatives sur {len(posts)} posts"

    except Exception as e:
        print(f"[SI] Erreur Reddit: {e}")
        result["detail"] = f"Reddit indisponible: {e}"

    _cache_social["data"] = result
    _cache_social["ts"] = time.time()
    return result


# ============================================
# 6. FUNDING RATES (SENTIMENT FUTURES)
# ============================================
_cache_funding = {"data": None, "ts": 0}

def get_funding_rates(symbole="BTCUSDT"):
    """Recupere les funding rates depuis Binance (API publique, pas de cle requise)."""
    if _cache_funding["data"] is not None and time.time() - _cache_funding["ts"] < 300:
        return _cache_funding["data"]

    result = {"rate": 0, "sentiment": "neutre", "score": 0}

    try:
        import urllib.request
        # Binance funding rate API (public, no auth)
        binance_sym = symbole.replace("USDT", "") + "USDT"
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={binance_sym}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        rate = float(data.get("lastFundingRate", 0))
        result["rate"] = rate
        result["rate_pct"] = rate * 100

        # Funding rate positif = longs paient shorts = marche haussier (trop de longs = risque)
        # Funding rate negatif = shorts paient longs = marche baissier (trop de shorts = rebond possible)
        if rate > 0.0005:  # > 0.05%
            result["sentiment"] = "trop de longs"
            result["score"] = -1  # risque de squeeze long
            result["detail"] = f"Funding {rate*100:.4f}% - longs surcharges, risque de squeeze"
        elif rate < -0.0005:  # < -0.05%
            result["sentiment"] = "trop de shorts"
            result["score"] = 1  # opportunite de squeeze short
            result["detail"] = f"Funding {rate*100:.4f}% - shorts surcharges, squeeze haussier possible"
        else:
            result["sentiment"] = "equilibre"
            result["score"] = 0
            result["detail"] = f"Funding {rate*100:.4f}% - marche equilibre"

    except Exception as e:
        print(f"[SI] Erreur funding: {e}")
        result["detail"] = "indisponible"

    _cache_funding["data"] = result
    _cache_funding["ts"] = time.time()
    return result


# ============================================
# 7. CORRELATION MACRO (BTC DOMINANCE, DXY)
# ============================================
_cache_macro = {"data": None, "ts": 0}

def get_macro_indicators():
    """Recupere les indicateurs macro qui influencent le crypto."""
    if _cache_macro["data"] is not None and time.time() - _cache_macro["ts"] < 900:
        return _cache_macro["data"]

    result = {"score": 0, "detail": ""}

    # BTC dominance via CoinGecko (indique si l'argent coule vers le BTC ou les alts)
    try:
        import urllib.request
        url = "https://api.coingecko.com/api/v3/global"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        market_cap = data.get("data", {}).get("total_market_cap", {}).get("usd", 0)
        btc_cap = data.get("data", {}).get("market_cap_percentage", {}).get("btc", 0)
        eth_cap = data.get("data", {}).get("market_cap_percentage", {}).get("eth", 0)
        vol_24h = data.get("data", {}).get("total_volume", {}).get("usd", 0)
        market_cap_change = data.get("data", {}).get("market_cap_change_percentage_24h_usd", 0)

        result["btc_dominance"] = btc_cap
        result["eth_dominance"] = eth_cap
        result["market_cap"] = market_cap
        result["vol_24h"] = vol_24h
        result["change_24h"] = market_cap_change

        details = []
        score = 0

        # BTC dominance haute = risk-off (les gens fuient vers le BTC)
        if btc_cap > 55:
            score -= 0.5
            details.append(f"BTC dominance haute ({btc_cap:.1f}%) - risk-off")
        elif btc_cap < 45:
            score += 1
            details.append(f"BTC dominance basse ({btc_cap:.1f}%) - altseason possible")

        # Volume vs market cap ratio
        if market_cap > 0:
            vol_ratio = vol_24h / market_cap * 100
            result["vol_ratio"] = vol_ratio
            if vol_ratio > 10:
                score += 0.5
                details.append(f"Volume eleve ({vol_ratio:.1f}% market cap) - marche actif")
            elif vol_ratio < 3:
                score -= 0.5
                details.append(f"Volume faible ({vol_ratio:.1f}%) - marche inactif")

        # Market cap change
        if market_cap_change > 3:
            score += 1
            details.append(f"Market cap +{market_cap_change:.1f}% 24h - marche haussier")
        elif market_cap_change < -3:
            score -= 1
            details.append(f"Market cap {market_cap_change:.1f}% 24h - marche baissier")

        result["score"] = score
        result["detail"] = ", ".join(details) if details else "macro neutre"

    except Exception as e:
        print(f"[SI] Erreur macro: {e}")
        result["detail"] = f"indisponible: {e}"

    _cache_macro["data"] = result
    _cache_macro["ts"] = time.time()
    return result


# ============================================
# 8. VOLUME PROFILE + VWAP
# ============================================
def calculer_vwap(symbole="BTCUSDT"):
    """Calcule le VWAP (Volume Weighted Average Price) sur les dernieres 24h."""
    try:
        import master_traders as mt
        bougies = mt.get_ohlc(symbole)
        if not bougies or len(bougies) < 3:
            return {"vwap": 0, "score": 0, "detail": "donnees insuffisantes"}

        # VWAP = sum(typical_price * volume) / sum(volume)
        total_pv = 0
        total_vol = 0
        for b in bougies:
            high = b.get("high", 0)
            low = b.get("low", 0)
            close = b.get("close", 0)
            vol = b.get("volume", 1)  # CoinGecko ne donne pas toujours le volume
            typical_price = (high + low + close) / 3
            total_pv += typical_price * vol
            total_vol += vol

        if total_vol == 0:
            # Si pas de volume, utiliser le typical price moyen
            vwap = sum((b.get("high", 0) + b.get("low", 0) + b.get("close", 0)) / 3 for b in bougies) / len(bougies)
        else:
            vwap = total_pv / total_vol

        prix_actuel = bougies[-1].get("close", 0)
        if vwap > 0:
            ecart = (prix_actuel - vwap) / vwap * 100
            if ecart > 2:
                score = -1
                detail = f"prix {ecart:+.1f}% au-dessus VWAP {vwap:.2f} - surachat"
            elif ecart < -2:
                score = 1
                detail = f"prix {ecart:+.1f}% sous VWAP {vwap:.2f} - sous-value"
            else:
                score = 0
                detail = f"prix {ecart:+.1f}% vs VWAP {vwap:.2f} - neutre"
        else:
            score = 0
            detail = "VWAP nul"

        return {"vwap": vwap, "prix_actuel": prix_actuel, "ecart_pct": ecart if vwap > 0 else 0, "score": score, "detail": detail}
    except Exception as e:
        return {"vwap": 0, "score": 0, "detail": f"erreur: {e}"}


def calculer_volume_profile(symbole="BTCUSDT"):
    """Analyse le profil de volume pour identifier les zones de support/resistance."""
    try:
        import master_traders as mt
        bougies = mt.get_ohlc(symbole)
        if not bougies or len(bougies) < 10:
            return {"score": 0, "detail": "insuffisant"}

        # Creer des bins de prix
        all_prices = []
        for b in bougies:
            all_prices.extend([b.get("high", 0), b.get("low", 0), b.get("close", 0)])

        prix_min = min(all_prices)
        prix_max = max(all_prices)
        if prix_max == prix_min:
            return {"score": 0, "detail": "range nul"}

        nb_bins = 10
        bin_size = (prix_max - prix_min) / nb_bins
        bins = [0] * nb_bins

        for b in bougies:
            close = b.get("close", 0)
            bin_idx = min(int((close - prix_min) / bin_size), nb_bins - 1)
            bins[bin_idx] += 1

        # Trouver le POC (Point of Control) - le bin avec le plus de volume
        poc_idx = bins.index(max(bins))
        poc_price = prix_min + (poc_idx + 0.5) * bin_size
        prix_actuel = bougies[-1].get("close", 0)

        score = 0
        detail = ""

        if prix_actuel > poc_price:
            # Prix au-dessus du POC = resistance au-dessus
            score = -0.5
            detail = f"POC a {poc_price:.2f}, prix au-dessus ({((prix_actuel/poc_price)-1)*100:+.1f}%)"
        else:
            # Prix en-dessous du POC = support au-dessus
            score = 0.5
            detail = f"POC a {poc_price:.2f}, prix en-dessous ({((prix_actuel/poc_price)-1)*100:+.1f}%)"

        # Value area (70% du volume autour du POC)
        total_vol = sum(bins)
        value_area_vol = total_vol * 0.7
        va_vol = bins[poc_idx]
        va_low = poc_idx
        va_high = poc_idx
        while va_vol < value_area_vol and (va_low > 0 or va_high < nb_bins - 1):
            if va_low > 0 and (va_high >= nb_bins - 1 or bins[va_low - 1] >= bins[va_high + 1]):
                va_low -= 1
                va_vol += bins[va_low]
            elif va_high < nb_bins - 1:
                va_high += 1
                va_vol += bins[va_high]
        va_low_price = prix_min + va_low * bin_size
        va_high_price = prix_min + (va_high + 1) * bin_size

        return {
            "poc_price": poc_price,
            "va_low": va_low_price,
            "va_high": va_high_price,
            "score": score,
            "detail": f"{detail} | VA: {va_low_price:.2f}-{va_high_price:.2f}",
        }
    except Exception as e:
        return {"score": 0, "detail": f"erreur: {e}"}


# ============================================
# SCORE SUPER-INTELLIGENCE GLOBAL
# ============================================
def score_super_intelligence(symbole="BTCUSDT"):
    """Combine toutes les sources d'intelligence en un score global.
    8 sources:
    1. IA multi-modeles (Gemini + Perplexity)
    2. News sentiment
    3. On-chain metrics
    4. Patterns de chart avances
    5. Social sentiment (Reddit)
    6. Funding rates
    7. Correlation macro
    8. VWAP + Volume Profile
    """
    infos = {}

    # 1. IA multi-modeles
    ia = analyse_ia_marche(symbole)
    infos["ia"] = ia

    # 2. News sentiment
    news = analyse_news_sentiment(symbole)
    infos["news"] = news

    # 3. On-chain
    onchain = analyse_onchain(symbole)
    infos["onchain"] = onchain

    # 4. Patterns avances
    try:
        import master_traders as mt
        prix_histo = mt.get_prix_histo(symbole)
        patterns = detecter_patterns_avances(prix_histo)
        pattern_score = sum(p.get("score", 0) for p in patterns) if patterns else 0
        infos["patterns"] = {"score": pattern_score, "patterns": patterns}
    except Exception as e:
        infos["patterns"] = {"score": 0, "erreur": str(e)}

    # 5. Social sentiment
    social = get_social_sentiment(symbole)
    infos["social"] = social

    # 6. Funding rates
    funding = get_funding_rates(symbole)
    infos["funding"] = funding

    # 7. Macro
    macro = get_macro_indicators()
    infos["macro"] = macro

    # 8. VWAP + Volume Profile
    vwap = calculer_vwap(symbole)
    vol_profile = calculer_volume_profile(symbole)
    infos["vwap"] = vwap
    infos["volume_profile"] = vol_profile

    # Score pondere
    score_ia = ia.get("score", 0) * 2.0  # poids fort pour l'IA
    score_news = news.get("score", 0) * 1.0
    score_onchain = onchain.get("score", 0) * 1.0
    score_patterns = pattern_score * 1.5
    score_social = social.get("score", 0) * 0.5
    score_funding = funding.get("score", 0) * 1.0
    score_macro = macro.get("score", 0) * 1.0
    score_vwap = vwap.get("score", 0) * 1.0
    score_vol = vol_profile.get("score", 0) * 0.5

    score_total = (score_ia + score_news + score_onchain + score_patterns +
                   score_social + score_funding + score_macro + score_vwap + score_vol)

    infos["score_total"] = round(score_total, 2)
    infos["scores_detail"] = {
        "ia": score_ia,
        "news": score_news,
        "onchain": score_onchain,
        "patterns": score_patterns,
        "social": score_social,
        "funding": score_funding,
        "macro": score_macro,
        "vwap": score_vwap,
        "volume_profile": score_vol,
    }

    return infos


def rapport_super_intelligence(symbole="BTCUSDT"):
    """Genere un rapport texte complet de la super-intelligence."""
    infos = score_super_intelligence(symbole)

    lignes = [f"=== SUPER-INTELLIGENCE {symbole} ===\n"]

    # 1. IA
    ia = infos.get("ia", {})
    lignes.append(f"1. ANALYSE IA (Gemini + Perplexity)")
    lignes.append(f"   Verdict: {ia.get('verdict', '?')} (confiance {ia.get('confiance', 0):.0f}%)")
    if ia.get("gemini"):
        lignes.append(f"   Gemini: {ia['gemini'].get('verdict', '?')} - {ia['gemini'].get('raison', '')[:60]}")
    if ia.get("perplexity"):
        lignes.append(f"   Perplexity: {ia['perplexity'].get('verdict', '?')} - {ia['perplexity'].get('raison', '')[:60]}")
    lignes.append("")

    # 2. News
    news = infos.get("news", {})
    lignes.append(f"2. NEWS SENTIMENT ({news.get('nb_news', 0)} articles)")
    lignes.append(f"   Sentiment: {news.get('sentiment', '?')} (score {news.get('score', 0):+.1f})")
    lignes.append(f"   {news.get('resume', '')[:80]}")
    lignes.append("")

    # 3. On-chain
    oc = infos.get("onchain", {})
    lignes.append(f"3. ON-CHAIN METRICS")
    lignes.append(f"   {oc.get('detail', 'indisponible')}")
    lignes.append("")

    # 4. Patterns
    pat = infos.get("patterns", {})
    patterns = pat.get("patterns", [])
    lignes.append(f"4. PATTERNS DE CHART ({len(patterns)} detectes)")
    if patterns:
        for p in patterns:
            lignes.append(f"   {p['nom']} ({p['signal']}) - score {p['score']:+d}: {p['detail'][:60]}")
    else:
        lignes.append("   Aucun pattern avance detecte")
    lignes.append("")

    # 5. Social
    soc = infos.get("social", {})
    lignes.append(f"5. SOCIAL SENTIMENT (Reddit)")
    lignes.append(f"   {soc.get('mentions', 0)} mentions - {soc.get('sentiment', '?')} (score {soc.get('score', 0):+.1f})")
    lignes.append(f"   {soc.get('detail', '')[:80]}")
    lignes.append("")

    # 6. Funding
    fund = infos.get("funding", {})
    lignes.append(f"6. FUNDING RATE (Futures)")
    lignes.append(f"   {fund.get('detail', 'indisponible')}")
    lignes.append("")

    # 7. Macro
    mac = infos.get("macro", {})
    lignes.append(f"7. MACRO GLOBAL")
    lignes.append(f"   BTC dominance: {mac.get('btc_dominance', 0):.1f}%")
    lignes.append(f"   {mac.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 8. VWAP + Volume Profile
    vwap = infos.get("vwap", {})
    vp = infos.get("volume_profile", {})
    lignes.append(f"8. VWAP & VOLUME PROFILE")
    lignes.append(f"   {vwap.get('detail', 'indisponible')}")
    lignes.append(f"   {vp.get('detail', 'indisponible')}")
    lignes.append("")

    # Score global
    lignes.append(f"{'='*50}")
    lignes.append(f"SCORE SUPER-INTELLIGENCE: {infos.get('score_total', 0):+.2f}")
    scores = infos.get("scores_detail", {})
    for src, s in scores.items():
        barre = "#" * int(abs(s) * 5) if s != 0 else ""
        signe = "+" if s > 0 else ""
        lignes.append(f"  {src:20s} {signe}{s:+.2f} {barre}")

    # Verdict
    total = infos.get("score_total", 0)
    if total >= 3:
        lignes.append(f"\nVERDICT: ACHAT FORTEMENT CONFIRME ({total:+.1f})")
    elif total >= 1.5:
        lignes.append(f"\nVERDICT: ACHAT ({total:+.1f})")
    elif total >= -1.5:
        lignes.append(f"\nVERDICT: ATTENDRE ({total:+.1f})")
    elif total >= -3:
        lignes.append(f"\nVERDICT: EVITER ({total:+.1f})")
    else:
        lignes.append(f"\nVERDICT: VENTE ({total:+.1f})")

    return "\n".join(lignes)


if __name__ == "__main__":
    print(rapport_super_intelligence("BTCUSDT"))
