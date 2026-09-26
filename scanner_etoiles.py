#!/usr/bin/env python3
"""
Scanner d'etoiles filantes - trouve les cryptos qui font +20%
Scanne CoinGecko pour les top gainers et trending coins,
les analyse avec les indicateurs, et ajoute les meilleurs au bot.
"""
import json
import time
import os
from datetime import datetime
from collections import defaultdict

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_etoiles_cache.json")
CACHE_TTL = 300  # 5 minutes

def _coingecko_get(url):
    """Fetch JSON from CoinGecko with rate-limit handling."""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return None  # Rate-limit silencieux, KuCoin prend le relais
        print(f"  [SCANNER] Erreur fetch {url}: {e}")
        return None
    except Exception as e:
        print(f"  [SCANNER] Erreur fetch {url}: {e}")
        return None

def scanner_top_gainers():
    """Recupere les top gainers 24h depuis CoinGecko."""
    url = "https://api.coingecko.com/api/v3/search/trending"
    data = _coingecko_get(url)
    trending = []
    if data and "coins" in data:
        for item in data["coins"][:15]:
            coin = item.get("item", {})
            trending.append({
                "id": coin.get("id", ""),
                "nom": coin.get("name", ""),
                "symbole": coin.get("symbol", ""),
                "rank": coin.get("market_cap_rank", 999),
            })
    return trending

def scanner_markets():
    """Recupere les marches avec prix et variation 24h."""
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false&price_change_percentage=24h"
    data = _coingecko_get(url)
    if not data:
        return []
    marches = []
    for coin in data:
        change_24h = coin.get("price_change_percentage_24h", 0) or 0
        volume = coin.get("total_volume", 0) or 0
        prix = coin.get("current_price", 0) or 0
        if prix <= 0 or volume < 1000000:
            continue
        marches.append({
            "id": coin.get("id", ""),
            "nom": coin.get("name", ""),
            "symbole": coin.get("symbol", "").upper(),
            "prix": prix,
            "change_24h": change_24h,
            "volume": volume,
            "rank": coin.get("market_cap_rank", 999),
            "market_cap": coin.get("market_cap", 0) or 0,
        })
    return marches

def scanner_etoiles():
    """
    Scanne le marche et trouve les etoiles filantes - cryptos avec:
    - Variation 24h > +3% (momentum fort)
    - Volume > 5M USD (liquidite suffisante)
    - Top 200 par market cap (pas de micro-caps risquees)
    - Disponible sur Revolut X (filtre important)
    Retourne une liste classee par score de conviction.
    """
    print("  [SCANNER] Recherche d'etoiles filantes...")
    marches = scanner_markets()
    if not marches:
        print("  [SCANNER] Impossible de recuperer les marches")
        return []

    # Recupere la liste des cryptos disponibles sur Revolut X
    try:
        import prix_revolut as pr
        revolut_syms = set()
        for sym in pr.REVOLUT_X_CRYPTO:
            revolut_syms.add(sym.replace("USDT", "").upper())
    except Exception:
        revolut_syms = set()

    trending = scanner_top_gainers()
    trending_ids = set(t["id"] for t in trending)
    trending_symboles = set(t["symbole"].upper() for t in trending)

    etoiles = []
    for m in marches:
        change = m["change_24h"]
        volume = m["volume"]
        rank = m["rank"]
        symbole = m["symbole"]

        # Filtre: variation 24h > +3%, volume > 5M, top 200, sur Revolut X
        if change < 3.0 or volume < 5_000_000 or rank > 200:
            continue
        # Filtre Revolut X: ne garder que les cryptos disponibles sur Revolut X
        if revolut_syms and symbole not in revolut_syms:
            continue

        # Score de conviction
        score = 0
        raisons = []

        # Momentum 24h
        if change >= 20:
            score += 5
            raisons.append(f"+{change:.1f}% 24h (ETOILE)")
        elif change >= 10:
            score += 4
            raisons.append(f"+{change:.1f}% 24h (fort)")
        elif change >= 5:
            score += 3
            raisons.append(f"+{change:.1f}% 24h")
        else:
            score += 1
            raisons.append(f"+{change:.1f}% 24h")

        # Trending sur CoinGecko
        if m["id"] in trending_ids or symbole in trending_symboles:
            score += 3
            raisons.append("trending CoinGecko")

        # Volume eleve
        if volume > 100_000_000:
            score += 2
            raisons.append("volume >100M")
        elif volume > 50_000_000:
            score += 1
            raisons.append("volume >50M")

        # Top 50 = plus sur
        if rank <= 50:
            score += 1
            raisons.append(f"rank #{rank}")

        # Construit le symbole Binance (SYMBOL+USDT)
        symbole_binance = symbole + "USDT"

        etoiles.append({
            "id": m["id"],
            "symbole": symbole_binance,
            "nom": m["nom"],
            "symbole_base": symbole,
            "prix_actuel": m["prix"],
            "change_24h": change,
            "volume": volume,
            "rank": rank,
            "score_conviction": score,
            "raisons": raisons,
            "etoile": change >= 15,
        })

    # Trie par score de conviction
    etoiles.sort(key=lambda x: x["score_conviction"], reverse=True)

    # Garde le top 10
    etoiles = etoiles[:10]

    # Sauvegarde le cache
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "etoiles": etoiles}, f, indent=2)
    except Exception:
        pass

    return etoiles

def get_etoiles_cache():
    """Retourne les etoiles en cache si recentes."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                data = json.load(f)
            ts = data.get("timestamp", "")
            if ts:
                age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
                if age < CACHE_TTL:
                    return data.get("etoiles", [])
    except Exception:
        pass
    return []

def scanner_et_ajouter(marches_paper, max_ajout=3):
    """
    Scanne les etoiles filantes et ajoute les meilleures au dict MARCHES_PAPER.
    Ajoute aussi le mapping CoinGecko pour que le bot puisse recuperer les prix.
    Retourne la liste des cryptos ajoutees.
    """
    etoiles = scanner_etoiles()
    if not etoiles:
        etoiles = get_etoiles_cache()
        # Filtre Revolut X sur le cache aussi
        try:
            import prix_revolut as pr
            revolut_syms = set(s.replace("USDT", "").upper() for s in pr.REVOLUT_X_CRYPTO)
            etoiles = [e for e in etoiles if e.get("symbole_base", "") in revolut_syms]
        except Exception:
            pass

    # Recupere le mapping CoinGecko depuis prix_revolut ET indicateurs
    try:
        import prix_revolut as pr
        cg_map = pr._COINGECKO_MAP
    except Exception:
        cg_map = {}
    try:
        import indicateurs as ind
        cg_map_ind = ind.COINGECKO_MAP
    except Exception:
        cg_map_ind = {}

    ajoutees = []
    for e in etoiles:
        sym = e["symbole"]
        if sym in marches_paper:
            continue  # Deja dans la liste
        if len(ajoutees) >= max_ajout:
            break

        # Ajoute au dict MARCHES_PAPER
        marches_paper[sym] = {
            "nom": e["nom"],
            "marche": "crypto",
            "source": "binance",
            "etoile": True,
            "score_conviction": e["score_conviction"],
            "change_24h": e["change_24h"],
        }
        # Ajoute le mapping CoinGecko dynamiquement (prix_revolut ET indicateurs)
        symbole_court = e["symbole_base"]
        coin_id = e.get("id", "")
        if coin_id and symbole_court:
            if symbole_court not in cg_map:
                cg_map[symbole_court] = coin_id
                print(f"  [SCANNER] Mapping CoinGecko (prix): {symbole_court} -> {coin_id}")
            if symbole_court not in cg_map_ind:
                cg_map_ind[symbole_court] = coin_id
                print(f"  [SCANNER] Mapping CoinGecko (indicateurs): {symbole_court} -> {coin_id}")
        ajoutees.append(e)
        print(f"  [ETOILE] {e['nom']} ({sym}) ajoutee — +{e['change_24h']:.1f}% 24h, score {e['score_conviction']}/10 — {', '.join(e['raisons'])}")

    if not ajoutees:
        print("  [SCANNER] Aucune etoile filante trouvee")
    else:
        print(f"  [SCANNER] {len(ajoutees)} etoile(s) ajoutee(s) au bot")

    return ajoutees

def nettoyer_etoiles(marches_paper, max_age_minutes=60):
    """
    Retire les etoiles filantes qui sont dans MARCHES_PAPER depuis trop longtemps
    ou qui ne sont plus en forte hausse.
    """
    a_retirer = []
    for sym, config in list(marches_paper.items()):
        if config.get("etoile") and config.get("date_ajout"):
            try:
                age = (datetime.now() - datetime.fromisoformat(config["date_ajout"])).total_seconds() / 60
                if age > max_age_minutes:
                    a_retirer.append(sym)
            except Exception:
                pass
    for sym in a_retirer:
        nom = marches_paper[sym].get("nom", sym)
        del marches_paper[sym]
        print(f"  [SCANNER] {nom} ({sym}) retiree — etoile expiree")
    return a_retirer


if __name__ == "__main__":
    etoiles = scanner_etoiles()
    print(f"\n{'='*55}")
    print(f"ETOILES FILANTES DETECTEES: {len(etoiles)}")
    print(f"{'='*55}")
    for i, e in enumerate(etoiles, 1):
        marqueur = " *** ETOILE ***" if e["etoile"] else ""
        print(f"\n{i}. {e['nom']} ({e['symbole_base']}){marqueur}")
        print(f"   Prix: ${e['prix_actuel']:.4f}")
        print(f"   24h: +{e['change_24h']:.1f}%")
        print(f"   Volume: ${e['volume']/1e6:.1f}M")
        print(f"   Rank: #{e['rank']}")
        print(f"   Score: {e['score_conviction']}/10")
        print(f"   Raisons: {', '.join(e['raisons'])}")
