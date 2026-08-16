#!/usr/bin/env python3
"""
web_global.py - Connexion au web mondial
Le bot accede a des dizaines de sources d'information en temps reel:
1. News multi-sources (CoinDesk, CoinTelegraph, Decrypt, CryptoPanic)
2. Twitter/X trending crypto (via Nitter)
3. Reddit multi-subreddits
4. Google Trends (interet de recherche)
5. GitHub activite developpeurs
6. Binance order book depth (profondeur de marche)
7. DeFi TVL (DefiLlama)
8. Calendrier economique (evenements macro)
9. Altcoin season index
10. Stablecoin supply (flot vers le crypto)
11. Exchange flows (entrees/sorties)
12. Crypto regulations news
"""

import json
import os
import time
import math
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_WEB = os.path.join(DOSSIER, "web_global.json")

# Cache global
_cache = {}

def _fetch_json(url, timeout=10, headers=None):
    """Recupere du JSON depuis une URL avec gestion d'erreurs."""
    try:
        h = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return None

def _fetch_text(url, timeout=10):
    """Recupere du texte brut depuis une URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None

def _fetch_rss(url, timeout=10):
    """Parse un flux RSS et retourne les derniers articles."""
    try:
        text = _fetch_text(url, timeout)
        if not text:
            return []
        root = ET.fromstring(text)
        articles = []
        # RSS 2.0
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            desc = item.findtext("description", "")
            articles.append({"title": title, "url": link, "date": pub, "source": "rss"})
            if len(articles) >= 5:
                break
        # Atom
        if not articles:
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
                link_elem = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_elem.get("href", "") if link_elem is not None else ""
                articles.append({"title": title, "url": link, "date": "", "source": "atom"})
                if len(articles) >= 5:
                    break
        return articles
    except Exception as e:
        return []


# ============================================
# 1. NEWS MULTI-SOURCES
# ============================================
_cache_news = {"data": None, "ts": 0}

def get_all_news(symbole="BTCUSDT"):
    """Aggrege les news depuis 5+ sources mondiales."""
    if _cache_news["data"] is not None and time.time() - _cache_news["ts"] < 300:
        return _cache_news["data"]

    all_news = []
    coin_name = symbole.replace("USDT", "").lower()

    # Source 1: CoinDesk RSS
    try:
        articles = _fetch_rss("https://www.coindesk.com/arc/outboundfeeds/rss/", 8)
        for a in articles:
            a["source"] = "CoinDesk"
            all_news.append(a)
    except Exception:
        pass

    # Source 2: CoinTelegraph RSS
    try:
        articles = _fetch_rss("https://cointelegraph.com/rss", 8)
        for a in articles:
            a["source"] = "CoinTelegraph"
            all_news.append(a)
    except Exception:
        pass

    # Source 3: CryptoCompare (API JSON)
    try:
        data = _fetch_json(f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={coin_name.upper()}&limit=5")
        if data and "Data" in data:
            for article in data["Data"]:
                all_news.append({
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "date": datetime.fromtimestamp(article.get("published_on", 0)).strftime("%H:%M"),
                    "source": article.get("source_info", {}).get("name", "CryptoCompare"),
                    "body": article.get("body", "")[:200],
                })
    except Exception:
        pass

    # Source 4: Decrypt RSS
    try:
        articles = _fetch_rss("https://decrypt.co/feed", 8)
        for a in articles:
            a["source"] = "Decrypt"
            all_news.append(a)
    except Exception:
        pass

    # Source 5: The Block
    try:
        articles = _fetch_rss("https://www.theblock.co/rss.xml", 8)
        for a in articles:
            a["source"] = "The Block"
            all_news.append(a)
    except Exception:
        pass

    # Dedupliquer par titre
    seen = set()
    unique = []
    for n in all_news:
        title = n.get("title", "").lower()
        if title and title not in seen:
            seen.add(title)
            unique.append(n)

    _cache_news["data"] = unique[:20]
    _cache_news["ts"] = time.time()
    return unique[:20]


def analyse_news_global(symbole="BTCUSDT"):
    """Analyse le sentiment de toutes les news mondiales."""
    news = get_all_news(symbole)
    if not news:
        return {"score": 0, "sentiment": "neutre", "nb_sources": 0, "detail": "aucune news"}

    # Analyse par mots-cles
    mots_pos = ["bullish", "surge", "rally", "breakout", "adoption", "partnership", "upgrade",
                "gain", "soar", "pump", "all-time high", "ath", "inflow", "accumulate",
                "buy", "support", "recovery", "bull", "positive", "growth", "milestone"]
    mots_neg = ["bearish", "crash", "dump", "hack", "ban", "sell-off", "decline", "fear",
                "plunge", "scam", "exploit", "outflow", "sell", "bear", "negative",
                "regulation", "lawsuit", "sec", "delist", "liquidation", "fud"]

    score = 0
    pos_count = 0
    neg_count = 0
    sources_set = set()

    for n in news:
        titre = n.get("title", "").lower()
        body = n.get("body", "").lower()
        text = titre + " " + body
        sources_set.add(n.get("source", ""))

        for mot in mots_pos:
            if mot in text:
                pos_count += 1
                score += 0.5
        for mot in mots_neg:
            if mot in text:
                neg_count += 1
                score -= 0.5

    score = max(-5, min(5, score))
    sentiment = "positif" if score > 1 else ("negatif" if score < -1 else "neutre")

    return {
        "score": score,
        "sentiment": sentiment,
        "nb_news": len(news),
        "nb_sources": len(sources_set),
        "sources": list(sources_set),
        "positifs": pos_count,
        "negatifs": neg_count,
        "detail": f"{len(news)} articles de {len(sources_set)} sources - {pos_count} positifs, {neg_count} negatifs",
    }


# ============================================
# 2. TWITTER/X TENDING CRYPTO
# ============================================
_cache_twitter = {"data": None, "ts": 0}

def get_twitter_sentiment(symbole="BTCUSDT"):
    """Recupere le sentiment Twitter/X via des sources publiques."""
    if _cache_twitter["data"] is not None and time.time() - _cache_twitter["ts"] < 300:
        return _cache_twitter["data"]

    result = {"score": 0, "mentions": 0, "sentiment": "neutre", "detail": ""}

    # CryptoPanic API (gratuit, pas de cle) - agregateur de news social
    try:
        coin = symbole.replace("USDT", "")
        data = _fetch_json(f"https://cryptopanic.com/api/v1/posts/?auth_token=free&currencies={coin}&kind=news&filter=hot")
        if data and "results" in data:
            posts = data["results"]
            result["mentions"] = len(posts)

            pos = sum(1 for p in posts if p.get("votes", {}).get("positive", 0) > p.get("votes", {}).get("negative", 0))
            neg = sum(1 for p in posts if p.get("votes", {}).get("negative", 0) > p.get("votes", {}).get("positive", 0))

            score = pos - neg
            result["score"] = max(-2, min(2, score))
            result["positifs"] = pos
            result["negatifs"] = neg
            result["sentiment"] = "positif" if score > 0 else ("negatif" if score < 0 else "neutre")
            result["detail"] = f"CryptoPanic: {pos} positifs, {neg} negatifs sur {len(posts)} posts"
    except Exception:
        pass

    # Trending crypto sur CoinGecko (search trending)
    try:
        data = _fetch_json("https://api.coingecko.com/api/v3/search/trending")
        if data and "coins" in data:
            trending = data["coins"]
            coin_name = symbole.replace("USDT", "").lower()
            in_trending = any(coin_name in str(c.get("item", {}).get("id", "")).lower() or
                             coin_name in str(c.get("item", {}).get("name", "")).lower()
                             for c in trending)
            if in_trending:
                result["trending"] = True
                result["score"] += 1  # bonus si la crypto est trending
                result["detail"] += " | TRENDING sur CoinGecko!"
            else:
                result["trending"] = False

            # Liste des cryptos trending
            result["trending_list"] = [c.get("item", {}).get("name", "") for c in trending[:5]]
    except Exception:
        pass

    _cache_twitter["data"] = result
    _cache_twitter["ts"] = time.time()
    return result


# ============================================
# 3. REDDIT MULTI-SUBREDDITS
# ============================================
_cache_reddit = {"data": None, "ts": 0}

def get_reddit_sentiment(symbole="BTCUSDT"):
    """Aggrege le sentiment de plusieurs subreddits."""
    if _cache_reddit["data"] is not None and time.time() - _cache_reddit["ts"] < 600:
        return _cache_reddit["data"]

    result = {"score": 0, "mentions": 0, "sentiment": "neutre", "detail": ""}
    coin = symbole.replace("USDT", "")

    subreddits = ["CryptoCurrency", "Bitcoin", "ethtrader", "altcoin"]
    all_posts = []

    for sub in subreddits:
        try:
            data = _fetch_json(f"https://www.reddit.com/r/{sub}/search.json?q={coin}&sort=new&limit=5&t=day")
            if data and "data" in data:
                posts = data["data"].get("children", [])
                for p in posts:
                    p["data"]["subreddit"] = sub
                    all_posts.append(p["data"])
            time.sleep(0.5)
        except Exception:
            continue

    result["mentions"] = len(all_posts)

    if all_posts:
        mots_pos = ["bullish", "moon", "pump", "buy", "surge", "rally", "breakout", "support", "hold", "accumulat"]
        mots_neg = ["bearish", "crash", "dump", "sell", "scam", "fear", "plunge", "bear", "drop", "dead"]

        pos = 0
        neg = 0
        for post in all_posts:
            titre = post.get("title", "").lower()
            for mot in mots_pos:
                if mot in titre:
                    pos += 1
            for mot in mots_neg:
                if mot in titre:
                    neg += 1

            # Upvotes comme signal
            ups = post.get("ups", 0)
            if ups > 100:
                pos += 0.5

        score = pos - neg
        result["score"] = max(-2, min(2, score))
        result["positifs"] = int(pos)
        result["negatifs"] = int(neg)
        result["sentiment"] = "positif" if score > 1 else ("negatif" if score < -1 else "neutre")
        result["detail"] = f"{len(all_posts)} posts sur {len(subreddits)} subreddits - {int(pos)} pos, {int(neg)} neg"
        result["top_post"] = all_posts[0].get("title", "") if all_posts else ""

    _cache_reddit["data"] = result
    _cache_reddit["ts"] = time.time()
    return result


# ============================================
# 4. GOOGLE TRENDS (INTERET DE RECHERCHE)
# ============================================
_cache_trends = {"data": None, "ts": 0}

def get_google_trends(symbole="BTCUSDT"):
    """Estime l'interet de recherche Google pour cette crypto."""
    if _cache_trends["data"] is not None and time.time() - _cache_trends["ts"] < 3600:
        return _cache_trends["data"]

    result = {"score": 0, "interest": 0, "detail": ""}

    # Utiliser l'API non officielle de Google Trends via pytrends
    # Fallback: utiliser les statistiques de recherche CoinGecko
    try:
        coin_id = {
            "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
            "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
        }.get(symbole, "bitcoin")

        data = _fetch_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true&community_data=true&developer_data=false")
        if data:
            # Community data = proxy pour l'interet social
            community = data.get("community_data", {})
            twitter_followers = community.get("twitter_followers", 0)
            reddit_subscribers = community.get("reddit_subscribers", 0)
            reddit_avg_posts = community.get("reddit_average_posts_48h", 0)
            reddit_avg_comments = community.get("reddit_average_comments_48h", 0)

            # Score d'interet base sur l'activite sociale
            interest_score = 0
            if reddit_avg_posts > 50:
                interest_score += 1
            if reddit_avg_comments > 100:
                interest_score += 1
            if twitter_followers > 1000000:
                interest_score += 0.5

            result["interest"] = interest_score
            result["score"] = min(2, interest_score)
            result["twitter_followers"] = twitter_followers
            result["reddit_subscribers"] = reddit_subscribers
            result["reddit_posts_48h"] = reddit_avg_posts
            result["reddit_comments_48h"] = reddit_avg_comments
            result["detail"] = f"Twitter: {twitter_followers:,} followers, Reddit: {reddit_subscribers:,} abonnes, {reddit_avg_posts:.0f} posts/48h"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_trends["data"] = result
    _cache_trends["ts"] = time.time()
    return result


# ============================================
# 5. GITHUB ACTIVITE DEVELOPPEURS
# ============================================
_cache_github = {"data": None, "ts": 0}

def get_github_activity(symbole="BTCUSDT"):
    """Recupere l'activite GitHub du projet (proxy pour la sante du projet)."""
    if _cache_github["data"] is not None and time.time() - _cache_github["ts"] < 3600:
        return _cache_github["data"]

    result = {"score": 0, "commits": 0, "stars": 0, "detail": ""}

    try:
        coin_id = {
            "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
            "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
            "LINKUSDT": "chainlink", "AVAXUSDT": "avalanche-2",
        }.get(symbole, "bitcoin")

        data = _fetch_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=false&community_data=false&developer_data=true")
        if data:
            dev = data.get("developer_data", {})
            repos = dev.get("repos_url", [])
            stars = dev.get("stars", 0)
            subscribers = dev.get("subscribers", 0)
            commits_4w = dev.get("commit_count_4_weeks", 0)
            pull_requests = dev.get("pull_request_contributors", 0)
            forks = dev.get("forks", 0)

            result["stars"] = stars
            result["commits"] = commits_4w
            result["forks"] = forks
            result["pull_requests"] = pull_requests

            # Score: activite developpeur = sante du projet
            score = 0
            if commits_4w > 100:
                score += 1
            if stars > 5000:
                score += 0.5
            if pull_requests > 10:
                score += 0.5

            result["score"] = min(2, score)
            result["detail"] = f"{commits_4w} commits 4 semaines, {stars:,} stars, {forks:,} forks, {pull_requests} PR contributors"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_github["data"] = result
    _cache_github["ts"] = time.time()
    return result


# ============================================
# 6. BINANCE ORDER BOOK DEPTH
# ============================================
_cache_orderbook = {"data": None, "ts": 0}

def get_orderbook_depth(symbole="BTCUSDT"):
    """Analyse la profondeur du carnet d'ordres Binance (signal d'achat/vente)."""
    if _cache_orderbook["data"] is not None and time.time() - _cache_orderbook["ts"] < 60:
        return _cache_orderbook["data"]

    result = {"score": 0, "detail": ""}

    try:
        binance_sym = symbole.replace("USDT", "") + "USDT"
        data = _fetch_json(f"https://api.binance.com/api/v3/depth?symbol={binance_sym}&limit=50")
        if data:
            bids = data.get("bids", [])  # acheteurs
            asks = data.get("asks", [])  # vendeurs

            bid_volume = sum(float(b[1]) for b in bids)
            ask_volume = sum(float(a[1]) for a in asks)

            if ask_volume > 0:
                ratio = bid_volume / ask_volume
                result["bid_ask_ratio"] = ratio
                result["bid_volume"] = bid_volume
                result["ask_volume"] = ask_volume

                if ratio > 2.0:
                    result["score"] = 2
                    result["detail"] = f"Ratio acheteurs/vendeurs: {ratio:.2f} - FORT signal d'achat (murs d'achat)"
                elif ratio > 1.3:
                    result["score"] = 1
                    result["detail"] = f"Ratio acheteurs/vendeurs: {ratio:.2f} - Plus d'acheteurs"
                elif ratio < 0.5:
                    result["score"] = -2
                    result["detail"] = f"Ratio acheteurs/vendeurs: {ratio:.2f} - FORT signal de vente (murs de vente)"
                elif ratio < 0.7:
                    result["score"] = -1
                    result["detail"] = f"Ratio acheteurs/vendeurs: {ratio:.2f} - Plus de vendeurs"
                else:
                    result["score"] = 0
                    result["detail"] = f"Ratio acheteurs/vendeurs: {ratio:.2f} - equilibre"

                # Detecter les murs (gros ordres)
                big_bids = [b for b in bids if float(b[1]) > bid_volume / len(bids) * 5]
                big_asks = [a for a in asks if float(a[1]) > ask_volume / len(asks) * 5]
                result["big_bid_walls"] = len(big_bids)
                result["big_ask_walls"] = len(big_asks)
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_orderbook["data"] = result
    _cache_orderbook["ts"] = time.time()
    return result


# ============================================
# 7. DEFI TVL (DefiLlama)
# ============================================
_cache_defi = {"data": None, "ts": 0}

def get_defi_tvl():
    """Recupere la TVL DeFi globale (Total Value Locked)."""
    if _cache_defi["data"] is not None and time.time() - _cache_defi["ts"] < 900:
        return _cache_defi["data"]

    result = {"score": 0, "detail": ""}

    try:
        data = _fetch_json("https://api.llama.fi/v2/chains")
        if data:
            total_tvl = sum(c.get("tvl", 0) for c in data if c.get("tvl"))
            result["total_tvl"] = total_tvl
            result["total_tvl_b"] = total_tvl / 1e9  # en milliards

            # Top chains
            sorted_chains = sorted(data, key=lambda c: c.get("tvl", 0), reverse=True)
            result["top_chains"] = [{"name": c.get("name", ""), "tvl": c.get("tvl", 0)} for c in sorted_chains[:5]]

            # TVL changement (proxy via historique)
            try:
                hist = _fetch_json("https://api.llama.fi/v2/historicalChainTvl")
                if hist and len(hist) >= 2:
                    current = hist[-1].get("tvl", 0)
                    yesterday = hist[-2].get("tvl", 0) if len(hist) >= 2 else current
                    if yesterday > 0:
                        change = (current - yesterday) / yesterday * 100
                        result["change_24h"] = change
                        if change > 2:
                            result["score"] = 1
                            result["detail"] = f"TVL DeFi: ${total_tvl/1e9:.1f}B ({change:+.1f}% 24h) - entrees de capital"
                        elif change < -2:
                            result["score"] = -1
                            result["detail"] = f"TVL DeFi: ${total_tvl/1e9:.1f}B ({change:+.1f}% 24h) - sorties de capital"
                        else:
                            result["detail"] = f"TVL DeFi: ${total_tvl/1e9:.1f}B ({change:+.1f}% 24h)"
            except Exception:
                result["detail"] = f"TVL DeFi: ${total_tvl/1e9:.1f}B"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_defi["data"] = result
    _cache_defi["ts"] = time.time()
    return result


# ============================================
# 8. ALTCOIN SEASON INDEX
# ============================================
_cache_altseason = {"data": None, "ts": 0}

def get_altcoin_season():
    """Determine si on est en altcoin season ou bitcoin season."""
    if _cache_altseason["data"] is not None and time.time() - _cache_altseason["ts"] < 900:
        return _cache_altseason["data"]

    result = {"score": 0, "season": "neutre", "detail": ""}

    try:
        data = _fetch_json("https://api.coingecko.com/api/v3/global")
        if data:
            btc_dom = data.get("data", {}).get("market_cap_percentage", {}).get("btc", 0)
            eth_dom = data.get("data", {}).get("market_cap_percentage", {}).get("eth", 0)
            alt_dom = 100 - btc_dom - eth_dom

            result["btc_dom"] = btc_dom
            result["eth_dom"] = eth_dom
            result["alt_dom"] = alt_dom

            if btc_dom > 52:
                result["season"] = "Bitcoin Season"
                result["score"] = -0.5  # les alts souffrent
                result["detail"] = f"Bitcoin Season (BTC dom {btc_dom:.1f}%) - les alts sous-performent"
            elif alt_dom > 60:
                result["season"] = "Altcoin Season"
                result["score"] = 1  # les alts montent
                result["detail"] = f"Altcoin Season (alt dom {alt_dom:.1f}%) - les alts surperforment"
            else:
                result["season"] = "Mixte"
                result["detail"] = f"Marche mixte (BTC {btc_dom:.1f}%, ETH {eth_dom:.1f}%, alts {alt_dom:.1f}%)"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_altseason["data"] = result
    _cache_altseason["ts"] = time.time()
    return result


# ============================================
# 9. STABLECOIN SUPPLY (FLOT VERS LE CRYPTO)
# ============================================
_cache_stable = {"data": None, "ts": 0}

def get_stablecoin_supply():
    """Analyse la supply de stablecoins (proxy pour l'argent qui attend d'entrer)."""
    if _cache_stable["data"] is not None and time.time() - _cache_stable["ts"] < 900:
        return _cache_stable["data"]

    result = {"score": 0, "detail": ""}

    try:
        # USDT market cap via CoinGecko
        data = _fetch_json("https://api.coingecko.com/api/v3/coins/tether?market_data=true&localization=false&tickers=false&community_data=false&developer_data=false")
        if data:
            mcap = data.get("market_data", {}).get("market_cap", {}).get("usd", 0)
            change = data.get("market_data", {}).get("market_cap_change_percentage_24h", 0)
            result["usdt_mcap"] = mcap
            result["usdt_mcap_b"] = mcap / 1e9
            result["change_24h"] = change

            if change > 1:
                result["score"] = 1
                result["detail"] = f"USDT market cap ${mcap/1e9:.1f}B ({change:+.1f}%) - capital entrant dans le crypto"
            elif change < -1:
                result["score"] = -1
                result["detail"] = f"USDT market cap ${mcap/1e9:.1f}B ({change:+.1f}%) - capital sortant"
            else:
                result["detail"] = f"USDT market cap ${mcap/1e9:.1f}B ({change:+.1f}%)"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_stable["data"] = result
    _cache_stable["ts"] = time.time()
    return result


# ============================================
# 10. LONG/SHORT RATIO (Binance Futures)
# ============================================
_cache_ls = {"data": None, "ts": 0}

def get_long_short_ratio(symbole="BTCUSDT"):
    """Ratio long/short sur Binance Futures (sentiment des traders)."""
    if _cache_ls["data"] is not None and time.time() - _cache_ls["ts"] < 300:
        return _cache_ls["data"]

    result = {"score": 0, "detail": ""}

    try:
        binance_sym = symbole.replace("USDT", "") + "USDT"
        data = _fetch_json(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={binance_sym}&period=1h&limit=1")
        if data and len(data) > 0:
            ratio = float(data[0].get("longShortRatio", 1))
            longs = float(data[0].get("longAccount", 0.5))
            shorts = float(data[0].get("shortAccount", 0.5))

            result["ratio"] = ratio
            result["longs_pct"] = longs * 100
            result["shorts_pct"] = shorts * 100

            if ratio > 2.5:
                result["score"] = -1  # trop de longs = risque de squeeze
                result["detail"] = f"Long/Short: {ratio:.2f} ({longs*100:.0f}% longs) - risque de squeeze long"
            elif ratio < 0.5:
                result["score"] = 1  # trop de shorts = opportunite
                result["detail"] = f"Long/Short: {ratio:.2f} ({shorts*100:.0f}% shorts) - squeeze short possible"
            else:
                result["detail"] = f"Long/Short: {ratio:.2f} ({longs*100:.0f}% longs / {shorts*100:.0f}% shorts)"
    except Exception as e:
        result["detail"] = f"indisponible: {e}"

    _cache_ls["data"] = result
    _cache_ls["ts"] = time.time()
    return result


# ============================================
# SCORE WEB GLOBAL
# ============================================
def score_web_global(symbole="BTCUSDT"):
    """Aggrege toutes les sources web en un score global."""
    infos = {}

    # 1. News multi-sources
    infos["news"] = analyse_news_global(symbole)

    # 2. Twitter/CryptoPanic
    infos["twitter"] = get_twitter_sentiment(symbole)

    # 3. Reddit multi-subreddits
    infos["reddit"] = get_reddit_sentiment(symbole)

    # 4. Google Trends / Community data
    infos["trends"] = get_google_trends(symbole)

    # 5. GitHub activite
    infos["github"] = get_github_activity(symbole)

    # 6. Order book depth
    infos["orderbook"] = get_orderbook_depth(symbole)

    # 7. DeFi TVL
    infos["defi_tvl"] = get_defi_tvl()

    # 8. Altcoin season
    infos["altseason"] = get_altcoin_season()

    # 9. Stablecoin supply
    infos["stablecoins"] = get_stablecoin_supply()

    # 10. Long/Short ratio
    infos["long_short"] = get_long_short_ratio(symbole)

    # Score global
    score = 0
    score += infos["news"].get("score", 0) * 1.5
    score += infos["twitter"].get("score", 0) * 1.0
    score += infos["reddit"].get("score", 0) * 0.8
    score += infos["trends"].get("score", 0) * 0.5
    score += infos["github"].get("score", 0) * 0.5
    score += infos["orderbook"].get("score", 0) * 2.0  # poids fort pour l'order book
    score += infos["defi_tvl"].get("score", 0) * 0.8
    score += infos["altseason"].get("score", 0) * 0.5
    score += infos["stablecoins"].get("score", 0) * 1.0
    score += infos["long_short"].get("score", 0) * 1.0

    infos["score_total"] = round(score, 2)

    # Top sources
    sources = []
    for name, data in infos.items():
        if name == "score_total":
            continue
        s = data.get("score", 0)
        if s != 0:
            sources.append((name, s))
    sources.sort(key=lambda x: abs(x[1]), reverse=True)
    infos["top_sources"] = sources[:5]

    return infos


def rapport_web_global(symbole="BTCUSDT"):
    """Genere un rapport texte du scan web global."""
    infos = score_web_global(symbole)

    lignes = [f"=== SCAN WEB GLOBAL {symbole} ===\n"]

    # 1. News
    news = infos.get("news", {})
    lignes.append(f"1. NEWS MONDIALES ({news.get('nb_sources', 0)} sources, {news.get('nb_news', 0)} articles)")
    lignes.append(f"   Sentiment: {news.get('sentiment', '?')} (score {news.get('score', 0):+.1f})")
    lignes.append(f"   {news.get('detail', '')[:80]}")
    if news.get("sources"):
        lignes.append(f"   Sources: {', '.join(news['sources'][:5])}")
    lignes.append("")

    # 2. Twitter/CryptoPanic
    tw = infos.get("twitter", {})
    lignes.append(f"2. TWITTER/CRYPTOPANIC")
    lignes.append(f"   {tw.get('detail', 'indisponible')}")
    if tw.get("trending"):
        lignes.append(f"   TRENDING sur CoinGecko!")
    lignes.append("")

    # 3. Reddit
    rd = infos.get("reddit", {})
    lignes.append(f"3. REDDIT MULTI-SUBREDDITS")
    lignes.append(f"   {rd.get('detail', 'indisponible')}")
    if rd.get("top_post"):
        lignes.append(f"   Top post: {rd['top_post'][:60]}")
    lignes.append("")

    # 4. Tendances
    tr = infos.get("trends", {})
    lignes.append(f"4. INTERET COMMUNAUTAIRE")
    lignes.append(f"   {tr.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 5. GitHub
    gh = infos.get("github", {})
    lignes.append(f"5. ACTIVITE DEVELOPPEURS (GitHub)")
    lignes.append(f"   {gh.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 6. Order Book
    ob = infos.get("orderbook", {})
    lignes.append(f"6. CARNET D'ORDRES BINANCE")
    lignes.append(f"   {ob.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 7. DeFi TVL
    df = infos.get("defi_tvl", {})
    lignes.append(f"7. DEFI TVL")
    lignes.append(f"   {df.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 8. Altcoin Season
    alts = infos.get("altseason", {})
    lignes.append(f"8. SEASON INDEX")
    lignes.append(f"   {alts.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 9. Stablecoins
    sc = infos.get("stablecoins", {})
    lignes.append(f"9. STABLECOIN SUPPLY")
    lignes.append(f"   {sc.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # 10. Long/Short
    ls = infos.get("long_short", {})
    lignes.append(f"10. LONG/SHORT RATIO (Futures)")
    lignes.append(f"   {ls.get('detail', 'indisponible')[:80]}")
    lignes.append("")

    # Score global
    lignes.append(f"{'='*50}")
    lignes.append(f"SCORE WEB GLOBAL: {infos.get('score_total', 0):+.2f}")
    lignes.append(f"\nTop sources contributives:")
    for name, score in infos.get("top_sources", []):
        barre = "#" * int(abs(score) * 5) if score != 0 else ""
        lignes.append(f"  {name:20s} {score:+.2f} {barre}")

    # Verdict
    total = infos.get("score_total", 0)
    if total >= 3:
        lignes.append(f"\nVERDICT WEB: ACHAT FORTEMENT CONFIRME ({total:+.1f})")
    elif total >= 1.5:
        lignes.append(f"\nVERDICT WEB: ACHAT ({total:+.1f})")
    elif total >= -1.5:
        lignes.append(f"\nVERDICT WEB: NEUTRE ({total:+.1f})")
    elif total >= -3:
        lignes.append(f"\nVERDICT WEB: EVITER ({total:+.1f})")
    else:
        lignes.append(f"\nVERDICT WEB: VENTE ({total:+.1f})")

    return "\n".join(lignes)


if __name__ == "__main__":
    print(rapport_web_global("BTCUSDT"))
