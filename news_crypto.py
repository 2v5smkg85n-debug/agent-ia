#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""news_crypto.py — Recherche web en temps reel pour le bot.

Source 2/4: comme Perplexity Computer, le bot cherche des news crypto en direct
et analyse le sentiment pour ajuster ses decisions de trading.

3 fonctions:
  1. get_news_crypto() — recupere les dernieres news (RSS CoinDesk + CoinTelegraph)
  2. get_trending_coins() — recupere les cryptos trending (CoinGecko API gratuite)
  3. score_news_sentiment(symbole) — analyse le sentiment des news pour un symbole

Integration dans paper_trading.py: ajoute le score de sentiment au score total.
"""
import json
import re
import time
import urllib.request

# Cache pour eviter le spam API
_cache_news = {"data": [], "ts": 0}
_cache_trending = {"data": [], "ts": 0}
_CACHE_TTL = 300  # 5 minutes

# Flux RSS gratuits (sans cle API)
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
]

# Mots-cles pour l'analyse de sentiment
MOTS_POSITIFS = [
    "bullish", "surge", "rally", "breakout", "adoption", "partnership",
    "upgrade", "buy", "long", "moon", "pump", "green",
    "all-time high", "institutional", "etf approval", "inflow",
    "growth", "positive", "optimism", "recovery", "bounce", "reversal",
    "accumulation", "whale buy", "staking", "burn", "supply cut",
    "launch", "mainnet", "milestone", "record", "support level",
    "golden cross", "oversold", "discount",
]

MOTS_NEGATIFS = [
    "bearish", "crash", "dump", "sell-off", "hack", "exploit", "rug pull",
    "scam", "ban", "lawsuit", "sec", "regulation", "delist", "liquidation",
    "fud", "fear", "red", "bloodbath", "correction", "decline", "drop",
    "outflow", "sell", "short", "rejection", "breakdown",
    "warning", "risk", "concern", "negative", "downturn", "plunge",
    "bankrupt", "insolvency", "fraud", "investigation", "shutdown",
]


def _parse_rss(url):
    """Parse un flux RSS et retourne une liste d'articles."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/xml,text/xml"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        articles = []
        # Extraire les items RSS
        items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)
        for item in items[:30]:
            titre = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item, re.DOTALL)
            if not titre:
                titre = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            lien = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            desc = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item, re.DOTALL)
            if not desc:
                desc = re.search(r"<description>(.*?)</description>", item, re.DOTALL)

            titre_text = titre.group(1).strip() if titre else ""
            lien_text = lien.group(1).strip() if lien else ""
            desc_text = desc.group(1).strip() if desc else ""
            # Nettoyer le HTML de la description
            desc_text = re.sub(r"<[^>]+>", "", desc_text)

            if titre_text:
                articles.append({
                    "titre": titre_text,
                    "url": lien_text,
                    "body": desc_text[:500],
                })
        return articles
    except Exception:
        return []


def get_news_crypto(limite=50):
    """Recupere les dernieres news crypto depuis les flux RSS.
    Retourne une liste de dict: {titre, url, body}.
    """
    now = time.time()
    if _cache_news["data"] and now - _cache_news["ts"] < _CACHE_TTL:
        return _cache_news["data"][:limite]

    tous_articles = []
    for url in RSS_FEEDS:
        articles = _parse_rss(url)
        tous_articles.extend(articles)

    _cache_news["data"] = tous_articles
    _cache_news["ts"] = now
    return tous_articles[:limite]


def get_trending_coins():
    """Recupere les cryptos trending depuis CoinGecko (API gratuite).
    Retourne une liste de symboles (format bot: BTCUSDT, ETHUSDT, etc.).
    """
    now = time.time()
    if _cache_trending["data"] and now - _cache_trending["ts"] < _CACHE_TTL:
        return _cache_trending["data"]

    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        trending = []
        for coin in data.get("coins", []):
            item = coin.get("item", {})
            symbole = item.get("symbol", "").upper()
            if symbole:
                trending.append(symbole + "USDT")

        _cache_trending["data"] = trending
        _cache_trending["ts"] = now
        return trending

    except Exception:
        return _cache_trending["data"]


def score_news_sentiment(symbole):
    """Analyse le sentiment des news pour un symbole donne.
    Retourne (score, details).
    score: -2 (tres bearish) a +2 (tres bullish), 0 = neutre.
    details: liste des signaux detectes.
    """
    symbole_court = symbole.replace("USDT", "").replace("EUR", "").upper()
    # Noms et aliases pour la recherche dans les news
    aliases = _get_aliases(symbole_court)

    articles = get_news_crypto(50)
    if not articles:
        return 0, []

    score = 0
    details = []
    articles_pertinents = 0

    for article in articles:
        texte = (article["titre"] + " " + article.get("body", "")).lower()
        # Verifier si l'article parle de cette crypto
        if not any(a.lower() in texte for a in aliases):
            continue

        articles_pertinents += 1

        # Compter les mots positifs et negatifs
        nb_pos = sum(1 for mot in MOTS_POSITIFS if mot.lower() in texte)
        nb_neg = sum(1 for mot in MOTS_NEGATIFS if mot.lower() in texte)

        if nb_pos > nb_neg:
            score += 1
            if nb_pos >= 2:
                details.append(f"News +: {article['titre'][:60]}")
        elif nb_neg > nb_pos:
            score -= 1
            if nb_neg >= 2:
                details.append(f"News -: {article['titre'][:60]}")

    # Normaliser le score: max +/-2
    if score > 2:
        score = 2
    elif score < -2:
        score = -2

    # Bonus trending: si la crypto est dans les trending coins
    trending = get_trending_coins()
    if symbole in trending:
        score += 1
        details.append(f"Trending CoinGecko (+1)")
        if score > 2:
            score = 2

    if not details and articles_pertinents == 0:
        return 0, []
    elif not details:
        return 0, [f"Pas de news recentes pour {symbole_court}"]
    else:
        return score, details


def _get_aliases(symbole_court):
    """Retourne les aliases pour rechercher une crypto dans les news."""
    aliases_map = {
        "BTC": ["BTC", "Bitcoin", "BTCUSD"],
        "ETH": ["ETH", "Ethereum", "Ether"],
        "SOL": ["SOL", "Solana"],
        "XRP": ["XRP", "Ripple"],
        "ADA": ["ADA", "Cardano"],
        "DOGE": ["DOGE", "Dogecoin", "Doge"],
        "AVAX": ["AVAX", "Avalanche"],
        "LINK": ["LINK", "Chainlink"],
        "DOT": ["DOT", "Polkadot"],
        "LTC": ["LTC", "Litecoin"],
        "ARB": ["ARB", "Arbitrum"],
        "NEAR": ["NEAR", "NEAR Protocol"],
        "AAVE": ["AAVE", "Aave"],
        "UNI": ["UNI", "Uniswap"],
        "PENDLE": ["PENDLE", "Pendle"],
        "FET": ["FET", "Fetch.ai", "Fetch"],
        "RNDR": ["RNDR", "Render", "RENDER"],
        "LDO": ["LDO", "Lido"],
        "FIL": ["FIL", "Filecoin"],
        "ATOM": ["ATOM", "Cosmos"],
        "OP": ["OP", "Optimism"],
        "INJ": ["INJ", "Injective"],
        "SUI": ["SUI", "Sui Network"],
        "APT": ["APT", "Aptos"],
        "SEI": ["SEI", "Sei Network"],
        "TIA": ["TIA", "Celestia"],
        "WIF": ["WIF", "dogwifhat"],
        "CRV": ["CRV", "Curve"],
        "SHIB": ["SHIB", "Shiba Inu", "Shib"],
        "XLM": ["XLM", "Stellar"],
        "ALGO": ["ALGO", "Algorand"],
        "ICP": ["ICP", "Internet Computer"],
        "ETC": ["ETC", "Ethereum Classic"],
        "TRX": ["TRX", "Tron", "TRON"],
        "BNB": ["BNB", "Binance Coin"],
        "PEPE": ["PEPE", "Pepe"],
        "FLOKI": ["FLOKI", "Floki"],
    }
    return aliases_map.get(symbole_court, [symbole_court])


def resume_sentiment():
    """Resume global du sentiment crypto pour les briefings.
    Retourne un texte avec les news importantes et le sentiment global.
    """
    articles = get_news_crypto(20)
    if not articles:
        return "News indisponible"

    # Compter le sentiment global
    pos = 0
    neg = 0
    for a in articles:
        texte = (a["titre"] + " " + a.get("body", "")).lower()
        nb_pos = sum(1 for mot in MOTS_POSITIFS if mot.lower() in texte)
        nb_neg = sum(1 for mot in MOTS_NEGATIFS if mot.lower() in texte)
        if nb_pos > nb_neg:
            pos += 1
        elif nb_neg > nb_pos:
            neg += 1

    sentiment = "Positif" if pos > neg else ("Negatif" if neg > pos else "Neutre")

    lignes = [f"Sentiment news: {sentiment} ({pos} positifs, {neg} negatifs sur {len(articles)} articles)"]
    trending = get_trending_coins()
    if trending:
        lignes.append(f"Trending: {', '.join(trending[:5])}")

    # Top 3 news
    for a in articles[:3]:
        lignes.append(f"- {a['titre'][:70]}")

    return "\n".join(lignes)


if __name__ == "__main__":
    print("=" * 60)
    print("NEWS CRYPTO - Recherche web en temps reel")
    print("=" * 60)

    print("\n--- Trending Coins ---")
    trending = get_trending_coins()
    print(f"Trending: {trending[:10]}")

    print("\n--- Sentiment par crypto ---")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "ARBUSDT"]:
        score, details = score_news_sentiment(sym)
        print(f"\n{sym}: score={score:+d}")
        for d in details:
            print(f"  - {d}")

    print("\n--- Resume global ---")
    print(resume_sentiment())
