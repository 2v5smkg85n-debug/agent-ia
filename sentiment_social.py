#!/usr/bin/env python3
"""
Sentiment Social Temps Reel — Analyse Reddit + CryptoTwitter pour le sentiment marche.

Sources:
  1. Reddit (r/CryptoCurrency, r/Bitcoin, r/Ethereum) - API JSON publique
  2. Crypto Twitter via recherche web (trending hashtags crypto)
  3. Fear & Greed Index (deja dans intelligence_pro mais on l'inclut ici)

Retourne un score de sentiment: -5 (tres bearish) a +5 (tres bullish)
"""
import json
import os
import re
import time
import urllib.request
from datetime import datetime

CACHE_TTL = 300  # 5 minutes
_cache = {}


def nettoyer_texte(texte):
    """Nettoie le texte pour analyse basique."""
    texte = texte.lower()
    texte = re.sub(r'http\S+', '', texte)
    texte = re.sub(r'[^a-zA-Z\s]', '', texte)
    return texte.strip()


def analyser_sentiment_texte(texte):
    """
    Analyse de sentiment basique par mots-cles (pas de NLP lourd).
    Retourne: -1 (bearish), 0 (neutre), +1 (bullish)
    """
    mots_bullish = [
        "bull", "bullish", "moon", "rocket", "pump", "buy", "long", "hold",
        "hodl", "accumulate", "breakout", "support", "bounce", "rally",
        "surge", "soar", "green", "gain", "profit", "uptrend", "bullrun",
        "ath", "all time high", "accumulate", "dip buying", "oversold",
        "reversal", "bottom", "recovery", "optimistic", "confident",
    ]
    mots_bearish = [
        "bear", "bearish", "dump", "sell", "short", "crash", "correction",
        "drop", "decline", "red", "loss", "downtrend", "bearmarket",
        "resistance", "reject", "breakdown", "capitulation", "fear",
        "panic", "bloodbath", "plunge", "collapse", "overbought",
        "bubble", "fraud", "scam", "hack", "liquidation", "fomo",
    ]

    texte = nettoyer_texte(texte)
    mots = texte.split()

    score_bull = sum(1 for m in mots if any(b in m for b in mots_bullish))
    score_bear = sum(1 for m in mots if any(b in m for b in mots_bearish))

    if score_bull > score_bear:
        return 1
    elif score_bear > score_bull:
        return -1
    return 0


def scanner_reddit(subreddit="CryptoCurrency", limite=25):
    """
    Recupere les posts recents d'un subreddit via l'API JSON publique de Reddit.
    Retourne: (score_sentiment, nombre_posts, top_mots)
    """
    try:
        url = "https://www.reddit.com/r/" + subreddit + "/hot.json?limit=" + str(limite)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) CryptoBot/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        posts = data.get("data", {}).get("children", [])
        if not posts:
            return 0, 0, []

        scores = []
        titres = []
        for post in posts:
            titre = post.get("data", {}).get("title", "")
            score_post = post.get("data", {}).get("score", 0)
            if titre:
                sentiment = analyser_sentiment_texte(titre)
                # Ponderer par le score du post
                poids = min(score_post / 100, 5)  # max 5x
                scores.append(sentiment * poids)
                titres.append(titre)

        if not scores:
            return 0, len(posts), []

        score_moyen = sum(scores) / len(scores)
        return score_moyen, len(posts), titres[:5]

    except Exception as e:
        print("  [SENTIMENT] Reddit " + subreddit + " erreur: " + str(e))
        return 0, 0, []


def get_fear_greed():
    """Recupere le Fear & Greed Index."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        value = int(data["data"][0]["value"])
        # Convertir: 0-25 (fear extreme) -> -5, 75-100 (greed extreme) -> +5
        score = (value - 50) / 10  # -5 a +5
        return score, value, data["data"][0].get("value_classification", "")
    except Exception as e:
        print("  [SENTIMENT] Fear&Greed erreur: " + str(e))
        return 0, 50, "Neutre"


def score_sentiment_social(symbole=None):
    """
    Score global de sentiment social.
    Combine Reddit + Fear & Greed.
    
    Returns:
        {
            "score_total": float (-5 a +5),
            "reddit_score": float,
            "fear_greed_score": float,
            "fear_greed_value": int,
            "fear_greed_label": str,
            "reddit_posts": int,
            "top_posts": list,
            "verdict": str,
        }
    """
    # Verifier le cache
    cache_key = symbole or "global"
    if cache_key in _cache:
        if time.time() - _cache[cache_key]["timestamp"] < CACHE_TTL:
            return _cache[cache_key]["result"]

    print("  [SENTIMENT] Scan Reddit + Fear&Greed...")

    # 1. Reddit (3 subreddits)
    subreddits = ["CryptoCurrency", "Bitcoin", "Ethereum"]
    reddit_scores = []
    total_posts = 0
    all_top_posts = []

    for sub in subreddits:
        score, posts, top = scanner_reddit(sub, limite=20)
        reddit_scores.append(score)
        total_posts += posts
        all_top_posts.extend(top[:2])

    reddit_score = sum(reddit_scores) / len(reddit_scores) if reddit_scores else 0

    # 2. Fear & Greed
    fg_score, fg_value, fg_label = get_fear_greed()

    # 3. Score combine (Reddit 40%, Fear&Greed 60%)
    score_total = (reddit_score * 0.4) + (fg_score * 0.6)

    # Verdict
    if score_total >= 2:
        verdict = "TRES BULLISH"
    elif score_total >= 0.5:
        verdict = "BULLISH"
    elif score_total <= -2:
        verdict = "TRES BEARISH"
    elif score_total <= -0.5:
        verdict = "BEARISH"
    else:
        verdict = "NEUTRE"

    result = {
        "score_total": round(score_total, 2),
        "reddit_score": round(reddit_score, 2),
        "fear_greed_score": round(fg_score, 2),
        "fear_greed_value": fg_value,
        "fear_greed_label": fg_label,
        "reddit_posts": total_posts,
        "top_posts": all_top_posts[:3],
        "verdict": verdict,
    }

    _cache[cache_key] = {"result": result, "timestamp": time.time()}
    print("  [SENTIMENT] Score: " + str(result["score_total"]) + " (" + verdict + ")")
    return result


def rapport_sentiment(symbole=None):
    """Genere un rapport lisible pour Telegram."""
    r = score_sentiment_social(symbole)

    rapport = "SOCIAL SENTIMENT\n"
    rapport += "================\n\n"

    emoji = {"TRES BULLISH": "🚀", "BULLISH": "🟢", "NEUTRE": "🟡", "BEARISH": "🔴", "TRES BEARISH": "💥"}
    rapport += "Verdict: " + emoji.get(r["verdict"], "⚪") + " " + r["verdict"] + "\n"
    rapport += "Score: " + str(r["score_total"]) + "/5\n\n"

    rapport += "Fear & Greed: " + str(r["fear_greed_value"]) + "/100 (" + r["fear_greed_label"] + ")\n"
    rapport += "Reddit sentiment: " + str(r["reddit_score"]) + " (" + str(r["reddit_posts"]) + " posts analyses)\n\n"

    if r.get("top_posts"):
        rapport += "Top posts Reddit:\n"
        for post in r["top_posts"]:
            rapport += "- " + post[:60] + "\n"

    return rapport


if __name__ == "__main__":
    print(rapport_sentiment())
