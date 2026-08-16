#!/usr/bin/env python3
"""
Master Traders Intelligence — Les stratégies des 10 plus grands traders du monde.
Le bot analyse les bougies et applique les méthodes de chaque légende.
"""
import json
import os
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_MASTER = os.path.join(DOSSIER, "master_traders.json")

COINGECKO_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "AVAX": "avalanche-2", "LINK": "chainlink",
    "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol", "NEAR": "near",
    "LDO": "lido-dao", "AAVE": "aave", "UNI": "uniswap", "PENDLE": "pendle",
    "RNDR": "render-token", "FET": "fetch-ai", "OCEAN": "ocean-protocol",
    "SEI": "seiprotocol", "TIA": "celestia", "SUI": "sui",
}


def charger_master():
    try:
        with open(FICHIER_MASTER) as f:
            return json.load(f)
    except Exception:
        return {
            "trades_par_trader": {},
            "poids_traders": {t: 1.0 for t in [
                "buffett", "soros", "simons", "paulson", "cohen",
                "rogers", "dennis", "dalio", "tudor_jones", "yass"
            ]},
            "params_maitres": {
                "buffett": {"sma_long": 30, "seuil_discount": 5.0, "seuil_survalue": -10.0},
                "soros": {"var_7j_seuil": 8.0, "var_3j_seuil": 3.0},
                "simons": {"sma": 20, "z_score_achat": -2.0, "z_score_vente": 2.0},
                "paulson": {"jours_bulle": 30, "seuil_bulle": 20.0, "seuil_crash": -20.0},
                "cohen": {"nb_bougies": 3, "seuil_pattern": 3},
                "rogers": {"sma_long": 30, "seuil_bas": 0.92, "seuil_haut": 1.10},
                "dennis": {"periode_range": 20, "seuil_breakout": 0.998, "seuil_breakdown": 1.002},
                "dalio": {"periode_sharpe": 15, "seuil_bon_sharpe": 0.5, "seuil_mauvais": -0.5},
                "tudor_jones": {"periode_rsi": 14, "survente_extreme": 25, "survente": 35, "surchaté": 65, "surchaté_extreme": 75},
                "yass": {"periode_vol": 20, "seuil_haute_vol": 8.0, "seuil_faible_vol": 1.0},
            },
            "stats_par_maitre": {t: {"n": 0, "gagnants": 0, "pnl": 0.0, "bon_vote": 0, "mauvais_vote": 0} for t in [
                "buffett", "soros", "simons", "paulson", "cohen",
                "rogers", "dennis", "dalio", "tudor_jones", "yass"
            ]},
            "version": 1,
        }


def sauver_master(data):
    with open(FICHIER_MASTER, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_ohlc(symbole, jours=30):
    """Recupere les bougies OHLC via CoinGecko."""
    base = symbole.replace("USDT", "")
    cg_id = COINGECKO_MAP.get(base, base.lower())
    cache_key = f"ohlc_{cg_id}_{jours}"
    if not hasattr(get_ohlc, '_cache'):
        get_ohlc._cache = {}
    if cache_key in get_ohlc._cache:
        if time.time() - get_ohlc._cache[cache_key][0] < 300:
            return get_ohlc._cache[cache_key][1]
    try:
        import urllib.request
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc?vs_currency=eur&days={jours}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        bougies = []
        for b in data:
            bougies.append({"ts": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]})
        get_ohlc._cache[cache_key] = (time.time(), bougies)
        time.sleep(1)
        return bougies
    except Exception:
        if cache_key in get_ohlc._cache:
            return get_ohlc._cache[cache_key][1]
        return []


def get_prix_histo(symbole, jours=30):
    """Recupere l'historique des prix."""
    base = symbole.replace("USDT", "")
    cg_id = COINGECKO_MAP.get(base, base.lower())
    cache_key = f"prix_{cg_id}_{jours}"
    if not hasattr(get_prix_histo, '_cache'):
        get_prix_histo._cache = {}
    if cache_key in get_prix_histo._cache:
        if time.time() - get_prix_histo._cache[cache_key][0] < 300:
            return get_prix_histo._cache[cache_key][1]
    try:
        import urllib.request
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=eur&days={jours}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        prices = [p[1] for p in data.get("prices", [])]
        get_prix_histo._cache[cache_key] = (time.time(), prices)
        time.sleep(1)
        return prices
    except Exception:
        if cache_key in get_prix_histo._cache:
            return get_prix_histo._cache[cache_key][1]
        return []


# ============================================
# LECTURE DES BOUGIES (patterns japonais)
# ============================================

def lire_bougies(bougies):
    """Analyse les 5 dernieres bougies pour detecter les patterns."""
    if len(bougies) < 5:
        return []
    patterns = []
    dernieres = bougies[-5:]

    for i, b in enumerate(dernieres):
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        corps = abs(c - o)
        mèche_haut = h - max(o, c)
        mèche_bas = min(o, c) - l
        amplitude = h - l if h > l else 0.0001

        # Doji (indecision)
        if corps < amplitude * 0.1:
            patterns.append({"nom": "Doji", "bougie": i, "signal": "neutre", "force": 0})

        # Marteau (hammer) - rejet bas = haussier
        if mèche_bas > corps * 2 and mèche_haut < corps * 0.5 and c > o:
            patterns.append({"nom": "Marteau", "bougie": i, "signal": "haussier", "force": 2})

        # Etoile filante (shooting star) - rejet haut = baissier
        if mèche_haut > corps * 2 and mèche_bas < corps * 0.5 and c < o:
            patterns.append({"nom": "Etoile filante", "bougie": i, "signal": "baissier", "force": -2})

        # Marubozu haussier (forte conviction haussiere)
        if mèche_haut < amplitude * 0.05 and mèche_bas < amplitude * 0.05 and c > o:
            patterns.append({"nom": "Marubozu haussier", "bougie": i, "signal": "haussier", "force": 3})

        # Marubozu baissier (forte conviction baissiere)
        if mèche_haut < amplitude * 0.05 and mèche_bas < amplitude * 0.05 and c < o:
            patterns.append({"nom": "Marubozu baissier", "bougie": i, "signal": "baissier", "force": -3})

        # Engulfing haussier (engouffrement)
        if i > 0:
            prev = dernieres[i - 1]
            if prev["close"] < prev["open"] and c > o and c > prev["open"] and o < prev["close"]:
                patterns.append({"nom": "Engulfing haussier", "bougie": i, "signal": "haussier", "force": 3})

        # Engulfing baissier
        if i > 0:
            prev = dernieres[i - 1]
            if prev["close"] > prev["open"] and c < o and c < prev["open"] and o > prev["close"]:
                patterns.append({"nom": "Engulfing baissier", "bougie": i, "signal": "baissier", "force": -3})

        # Harami haussier (petit corps dans grand corps baissier)
        if i > 0:
            prev = dernieres[i - 1]
            if prev["close"] < prev["open"] and abs(prev["open"] - prev["close"]) > corps * 2 and c > o:
                patterns.append({"nom": "Harami haussier", "bougie": i, "signal": "haussier", "force": 1})

    return patterns


# ============================================
# STRATEGIES DES 10 MAITRES
# ============================================

def strategie_buffett(prix_histo, bougies, params=None):
    """Warren Buffett: Value investing - achete sous-value, long terme, concentration."""
    p = params or {"sma_long": 30, "seuil_discount": 5.0, "seuil_survalue": -10.0}
    sma_periode = int(p.get("sma_long", 30))
    if len(prix_histo) < sma_periode:
        return 0, "donnees insuffisantes"
    prix_actuel = prix_histo[-1]
    sma_long = sum(prix_histo[-sma_periode:]) / sma_periode
    discount = (sma_long - prix_actuel) / sma_long * 100
    seuil_disc = p.get("seuil_discount", 5.0)
    seuil_surval = p.get("seuil_survalue", -10.0)
    if discount > seuil_disc:
        return 3, f"sous-value ({discount:.1f}% sous SMA{sma_periode}) - style Buffett"
    elif discount > seuil_disc * 0.4:
        return 2, f"legerement sous-value ({discount:.1f}%)"
    elif discount < seuil_surval:
        return -2, f"sur-value ({discount:.1f}% au-dessus SMA{sma_periode})"
    return 0, f"prix juste ({discount:.1f}% vs SMA{sma_periode})"


def strategie_soros(prix_histo, bougies, params=None):
    """George Soros: Detection de bulles et inversions - momentum extremes."""
    p = params or {"var_7j_seuil": 8.0, "var_3j_seuil": 3.0}
    if len(prix_histo) < 14:
        return 0, "insuffisant"
    var_7j = (prix_histo[-1] - prix_histo[-8]) / prix_histo[-8] * 100
    var_3j = (prix_histo[-1] - prix_histo[-4]) / prix_histo[-4] * 100
    seuil_7j = p.get("var_7j_seuil", 8.0)
    seuil_3j = p.get("var_3j_seuil", 3.0)
    if var_7j > seuil_7j and var_3j < 0:
        return -3, f"baisse apres hausse (inversion Soros) 7j:{var_7j:+.1f}% 3j:{var_3j:+.1f}%"
    if var_7j < -seuil_7j and var_3j < var_7j:
        return -2, f"chute qui s'accelere 7j:{var_7j:+.1f}% 3j:{var_3j:+.1f}%"
    if var_3j > seuil_3j and var_7j > 0:
        return 2, f"momentum haussier 7j:{var_7j:+.1f}% 3j:{var_3j:+.1f}%"
    return 0, f"momentum neutre 7j:{var_7j:+.1f}% 3j:{var_3j:+.1f}%"


def strategie_simons(prix_histo, bougies, params=None):
    """James Simons: Quantitatif - patterns statistiques et mean reversion."""
    p = params or {"sma": 20, "z_score_achat": -2.0, "z_score_vente": 2.0}
    periode = int(p.get("sma", 20))
    if len(prix_histo) < periode:
        return 0, "insuffisant"
    sma = sum(prix_histo[-periode:]) / periode
    prix_actuel = prix_histo[-1]
    ecart_type = (sum((x - sma) ** 2 for x in prix_histo[-periode:]) / periode) ** 0.5
    if ecart_type == 0:
        return 0, "vol nulle"
    z_score = (prix_actuel - sma) / ecart_type
    z_achat = p.get("z_score_achat", -2.0)
    z_vente = p.get("z_score_vente", 2.0)
    if z_score < z_achat:
        return 3, f"z-score {z_score:.2f} (survente statistique) - style Simons"
    elif z_score < z_achat * 0.5:
        return 1, f"z-score {z_score:.2f} (legerement bas)"
    elif z_score > z_vente:
        return -2, f"z-score {z_score:.2f} (surchaté statistique)"
    return 0, f"z-score {z_score:.2f} (normal)"


def strategie_paulson(prix_histo, bougies):
    """John Paulson: Detection de bulles et short sur les actifs survalues."""
    if len(prix_histo) < 30:
        return 0, "insuffisant"
    # Paulson: cherche les bulles (hausse trop rapide)
    var_30j = (prix_histo[-1] - prix_histo[-30]) / prix_histo[-30] * 100
    var_7j = (prix_histo[-1] - prix_histo[-8]) / prix_histo[-8] * 100 if len(prix_histo) >= 8 else 0
    # Bulle: +20% en 30j avec acceleration
    if var_30j > 20 and var_7j > 5:
        return -3, f"bulle detectee (+{var_30j:.0f}% 30j, +{var_7j:.0f}% 7j) - short style Paulson"
    elif var_30j > 15:
        return -1, f"hausse suspecte (+{var_30j:.0f}% 30j)"
    # Apres un crash = opportunite d'achat
    if var_30j < -20:
        return 2, f"post-crash ({var_30j:.0f}% 30j) - opportunite value"
    return 0, f"pas de bulle ({var_30j:+.1f}% 30j)"


def strategie_cohen(prix_histo, bougies):
    """Steven Cohen: Short selling + momentum + patterns de bougies."""
    patterns = lire_bougies(bougies)
    if not patterns:
        return 0, "pas de pattern"
    # Cohen: utilise les patterns de bougies pour entrer/sortir
    score = 0
    details = []
    for p in patterns[-3:]:  # 3 dernieres bougies
        score += p["force"]
        details.append(f"{p['nom']}({p['signal']})")
    detail_str = ", ".join(details)
    if score >= 3:
        return 2, f"patterns haussiers: {detail_str}"
    elif score <= -3:
        return -2, f"patterns baissiers: {detail_str}"
    return score, f"patterns neutres: {detail_str}"


def strategie_rogers(prix_histo, bougies):
    """Jim Rogers: Tendance long terme + matieres premieres - achete la valeur."""
    if len(prix_histo) < 30:
        return 0, "insuffisant"
    # Rogers: tendance long terme + achete quand c'est pas cher
    sma30 = sum(prix_histo[-30:]) / 30
    prix_actuel = prix_histo[-1]
    # Rogers preferait acheter bas et garder longtemps
    if prix_actuel < sma30 * 0.92:
        return 2, f"prix bas vs tendance long terme ({(prix_actuel/sma30-1)*100:.1f}%)"
    elif prix_actuel > sma30 * 1.10:
        return -1, f"prix haut vs tendance ({(prix_actuel/sma30-1)*100:.1f}%)"
    return 0, f"dans la tendance ({(prix_actuel/sma30-1)*100:.1f}%)"


def strategie_dennis(prix_histo, bougies, params=None):
    """Richard Dennis: Turtle Trading - cassure de range (breakout)."""
    p = params or {"periode_range": 20, "seuil_breakout": 0.998, "seuil_breakdown": 1.002}
    periode = int(p.get("periode_range", 20))
    if len(prix_histo) < periode:
        return 0, "insuffisant"
    high = max(prix_histo[-periode:])
    low = min(prix_histo[-periode:])
    prix_actuel = prix_histo[-1]
    range_val = high - low
    if range_val == 0:
        return 0, "range nul"
    position_range = (prix_actuel - low) / range_val * 100
    seuil_haut = p.get("seuil_breakout", 0.998)
    seuil_bas = p.get("seuil_breakdown", 1.002)
    if prix_actuel >= high * seuil_haut:
        return 3, f"BREAKOUT haut {periode}j! (prix au sommet du range) - style Turtle"
    elif prix_actuel <= low * seuil_bas:
        return -3, f"BREAKDOWN bas {periode}j! (prix au plus bas du range)"
    elif 40 < position_range < 60:
        return 0, f"milieu du range {periode}j ({position_range:.0f}%)"
    else:
        return 0, f"range {periode}j: {position_range:.0f}%"


def strategie_dalio(prix_histo, bougies):
    """Ray Dalio: Diversification + All Weather - correlation entre actifs."""
    if len(prix_histo) < 14:
        return 0, "insuffisant"
    # Dalio: cherche la stabilite et la non-correlation
    rendements = []
    for i in range(1, min(15, len(prix_histo))):
        if prix_histo[i-1] > 0:
            rendements.append((prix_histo[i] - prix_histo[i-1]) / prix_histo[i-1] * 100)
    if not rendements:
        return 0, "pas de rendements"
    avg = sum(rendements) / len(rendements)
    vol = (sum((r - avg) ** 2 for r in rendements) / len(rendements)) ** 0.5
    # Sharpe-like ratio
    sharpe = avg / vol if vol > 0 else 0
    if sharpe > 0.5:
        return 2, f"bon ratio Sharpe {sharpe:.2f} (rendement/volatilite) - style Dalio"
    elif sharpe < -0.5:
        return -2, f"mauvais Sharpe {sharpe:.2f}"
    return 0, f"Sharpe {sharpe:.2f} (neutre)"


def strategie_tudor_jones(prix_histo, bougies, params=None):
    """Paul Tudor Jones: Detection de crashes - RSI + momentum + risk management."""
    p = params or {"periode_rsi": 14, "survente_extreme": 25, "survente": 35, "surchaté": 65, "surchaté_extreme": 75}
    periode = int(p.get("periode_rsi", 14))
    if len(prix_histo) < periode + 1:
        return 0, "insuffisant"
    gains = []
    pertes = []
    for i in range(1, min(periode + 1, len(prix_histo))):
        diff = prix_histo[i] - prix_histo[i-1]
        if diff > 0:
            gains.append(diff)
            pertes.append(0)
        else:
            gains.append(0)
            pertes.append(abs(diff))
    if not gains:
        return 0, "pas de donnees"
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(pertes) / len(pertes)
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    se = p.get("survente_extreme", 25)
    sv = p.get("survente", 35)
    sc = p.get("surchaté", 65)
    sce = p.get("surchaté_extreme", 75)
    if rsi < se:
        return 3, f"RSI {rsi:.0f} survente extreme - style Tudor Jones"
    elif rsi < sv:
        return 1, f"RSI {rsi:.0f} survente"
    elif rsi > sce:
        return -2, f"RSI {rsi:.0f} surchaté extreme"
    elif rsi > sc:
        return -1, f"RSI {rsi:.0f} surchaté"
    return 0, f"RSI {rsi:.0f} neutre"


def strategie_yass(prix_histo, bougies):
    """Jeff Yass: Options pricing - volatilite implicite + edge statistique."""
    if len(prix_histo) < 20:
        return 0, "insuffisant"
    # Yass: cherche la volatilite (opportunite options-like)
    rendements = []
    for i in range(1, min(21, len(prix_histo))):
        if prix_histo[i-1] > 0:
            rendements.append((prix_histo[i] - prix_histo[i-1]) / prix_histo[i-1] * 100)
    if not rendements:
        return 0, "insuffisant"
    vol = (sum((r - sum(rendements)/len(rendements)) ** 2 for r in rendements) / len(rendements)) ** 0.5
    # Yass: aime la volatilite (plus de mouvements = plus d'opportunites)
    if vol > 8:
        return 2, f"vol elevee {vol:.1f}% (opportunite) - style Yass"
    elif vol > 4:
        return 1, f"vol moyenne {vol:.1f}%"
    elif vol < 1:
        return -1, f"vol trop faible {vol:.1f}% (pas d'opportunite)"
    return 0, f"vol {vol:.1f}% (normale)"


# ============================================
# CONSENSUS DES MAITRES
# ============================================

MAITRES = {
    "buffett": ("Warren Buffett", strategie_buffett),
    "soros": ("George Soros", strategie_soros),
    "simons": ("James Simons", strategie_simons),
    "paulson": ("John Paulson", strategie_paulson),
    "cohen": ("Steven Cohen", strategie_cohen),
    "rogers": ("Jim Rogers", strategie_rogers),
    "dennis": ("Richard Dennis", strategie_dennis),
    "dalio": ("Ray Dalio", strategie_dalio),
    "tudor_jones": ("Paul Tudor Jones", strategie_tudor_jones),
    "yass": ("Jeff Yass", strategie_yass),
}


def consensus_maitres(symbole):
    """Fait voter les 10 maitres sur une opportunite.
    Retourne: score consensus, details par maitre, recommandation."""
    prix_histo = get_prix_histo(symbole)
    bougies = get_ohlc(symbole)
    if len(prix_histo) < 5:
        return 0, {}, "Donnees insuffisantes", {}

    master = charger_master()
    scores = {}
    details = {}
    total_pondere = 0
    total_poids = 0

    for key, (nom, func) in MAITRES.items():
        try:
            params_maitre = master.get("params_maitres", {}).get(key, {})
            score, detail = func(prix_histo, bougies, params_maitre)
            poids = master["poids_traders"].get(key, 1.0)
            scores[key] = score
            details[nom] = {"score": score, "detail": detail, "poids": poids}
            total_pondere += score * poids
            total_poids += poids
        except Exception as e:
            scores[key] = 0
            details[nom] = {"score": 0, "detail": f"erreur: {e}", "poids": 1.0}

    score_consensus = total_pondere / total_poids if total_poids > 0 else 0

    # TP/SL selon le consensus
    if score_consensus >= 2:
        reco = "ACHAT_FORT"
    elif score_consensus >= 1:
        reco = "ACHAT"
    elif score_consensus >= -1:
        reco = "ATTENDRE"
    elif score_consensus >= -2:
        reco = "NE_PAS_ACHETER"
    else:
        reco = "VENTE"

    # Lecture des bougies
    patterns = lire_bougies(bougies)
    patterns_str = ", ".join(f"{p['nom']}({p['signal']})" for p in patterns) if patterns else "aucun pattern"

    return score_consensus, details, reco, {"patterns": patterns_str, "nb_patterns": len(patterns)}


def apprendre_trade(symbole, score_consensus, gain, votes_par_maitre=None):
    """Apprend d'un trade: ajuste le poids de chaque maitre selon sa contribution."""
    master = charger_master()
    entry = {
        "symbole": symbole,
        "score": score_consensus,
        "gain": gain,
        "gagnant": gain > 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "votes": votes_par_maitre or {},
    }
    master.setdefault("trades_par_trader", {}).setdefault("historique", []).append(entry)
    master["trades_par_trader"]["historique"] = master["trades_par_trader"]["historique"][-200:]

    # Ajuster les poids: un maitre qui a vote juste gagne du poids
    if votes_par_maitre:
        for key, vote in votes_par_maitre.items():
            # Si le maitre etait positif et le trade gagnant -> renforcer
            # Si le maitre etait positif et le trade perdant -> reduire
            if vote > 0 and gain > 0:
                master["poids_traders"][key] = min(2.0, master["poids_traders"].get(key, 1.0) + 0.03)
            elif vote > 0 and gain < 0:
                master["poids_traders"][key] = max(0.3, master["poids_traders"].get(key, 1.0) - 0.03)
            elif vote < 0 and gain < 0:
                master["poids_traders"][key] = min(2.0, master["poids_traders"].get(key, 1.0) + 0.03)
            elif vote < 0 and gain > 0:
                master["poids_traders"][key] = max(0.3, master["poids_traders"].get(key, 1.0) - 0.03)

    sauver_master(master)
    return master


def ameliorer_strategies():
    """Analyse l'historique et ameliore les parametres de chaque maitre.
    Ajuste les seuils pour maximiser le win rate de chaque strategie."""
    master = charger_master()
    hist = master.get("trades_par_trader", {}).get("historique", [])
    if len(hist) < 3:
        return master, "Pas assez de trades pour ameliorer (minimum 3)"

    ameliorations = []
    params = master.get("params_maitres", {})

    # Pour chaque maitre, analyser ses votes vs les resultats
    for key in MAITRES:
        if key not in params:
            continue
        trades_maitre = []
        for t in hist:
            votes = t.get("votes", {})
            vote = votes.get(key, 0)
            if vote != 0:
                trades_maitre.append({
                    "vote": vote,
                    "gain": t.get("gain", 0),
                    "gagnant": t.get("gagnant", False),
                    "symbole": t.get("symbole", ""),
                })

        if len(trades_maitre) < 2:
            continue

        # Calculer le win rate du maitre
        gagnants = sum(1 for t in trades_maitre if (t["vote"] > 0 and t["gagnant"]) or (t["vote"] < 0 and not t["gagnant"]))
        wr = gagnants / len(trades_maitre) * 100

        # Si win rate < 40%, assouplir les seuils (etre moins strict)
        # Si win rate > 70%, durcir les seuils (etre plus selectif)
        ajustement = 0.0
        if wr < 40:
            ajustement = -0.10  # assouplir
        elif wr > 70:
            ajustement = 0.10  # durcir

        if ajustement == 0:
            continue

        p = params[key]
        if key == "buffett":
            p["seuil_discount"] = max(2.0, min(15.0, p.get("seuil_discount", 5.0) - ajustement))
            ameliorations.append(f"Buffett: seuil discount {p['seuil_discount']:.1f}% (WR {wr:.0f}%)")
        elif key == "soros":
            p["var_7j_seuil"] = max(3.0, min(20.0, p.get("var_7j_seuil", 8.0) - ajustement))
            ameliorations.append(f"Soros: seuil momentum {p['var_7j_seuil']:.1f}% (WR {wr:.0f}%)")
        elif key == "simons":
            p["z_score_achat"] = max(-3.0, min(-0.5, p.get("z_score_achat", -2.0) + ajustement))
            ameliorations.append(f"Simons: z-score achat {p['z_score_achat']:.1f} (WR {wr:.0f}%)")
        elif key == "dennis":
            p["seuil_breakout"] = max(0.99, min(1.0, p.get("seuil_breakout", 0.998) + ajustement * 0.001))
            ameliorations.append(f"Dennis: seuil breakout {p['seuil_breakout']:.3f} (WR {wr:.0f}%)")
        elif key == "tudor_jones":
            p["survente"] = max(15, min(45, p.get("survente", 35) + int(ajustement * 5)))
            ameliorations.append(f"Tudor Jones: survente {p['survente']} (WR {wr:.0f}%)")
        elif key == "paulson":
            p["seuil_bulle"] = max(10.0, min(40.0, p.get("seuil_bulle", 20.0) - ajustement * 2))
            ameliorations.append(f"Paulson: seuil bulle {p['seuil_bulle']:.0f}% (WR {wr:.0f}%)")
        elif key == "rogers":
            p["seuil_bas"] = max(0.85, min(0.98, p.get("seuil_bas", 0.92) - ajustement * 0.01))
            ameliorations.append(f"Rogers: seuil bas {p['seuil_bas']:.2f} (WR {wr:.0f}%)")
        elif key == "dalio":
            p["seuil_bon_sharpe"] = max(0.1, min(1.5, p.get("seuil_bon_sharpe", 0.5) - ajustement))
            ameliorations.append(f"Dalio: seuil Sharpe {p['seuil_bon_sharpe']:.1f} (WR {wr:.0f}%)")
        elif key == "yass":
            p["seuil_haute_vol"] = max(3.0, min(15.0, p.get("seuil_haute_vol", 8.0) - ajustement))
            ameliorations.append(f"Yass: seuil vol {p['seuil_haute_vol']:.1f}% (WR {wr:.0f}%)")
        elif key == "cohen":
            p["seuil_pattern"] = max(1, min(5, p.get("seuil_pattern", 3) + int(ajustement)))
            ameliorations.append(f"Cohen: seuil pattern {p['seuil_pattern']} (WR {wr:.0f}%)")

        # Mettre a jour les stats
        stats = master.get("stats_par_maitre", {}).get(key, {})
        stats["n"] = len(trades_maitre)
        stats["gagnants"] = gagnants
        stats["pnl"] = sum(t["gain"] for t in trades_maitre)
        stats["win_rate"] = wr
        master.setdefault("stats_par_maitre", {})[key] = stats

    master["params_maitres"] = params
    master["derniere_amelioration"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    sauver_master(master)
    return master, "\n".join(ameliorations) if ameliorations else "Aucune amelioration necessaire"


def rapport_maitres():
    """Genere un rapport des maitres."""
    master = charger_master()
    lignes = ["=== MASTER TRADERS INTELLIGENCE ===\n"]
    lignes.append("Poids des maitres (apres apprentissage):")
    for key, (nom, _) in MAITRES.items():
        poids = master["poids_traders"].get(key, 1.0)
        barre = "#" * int(poids * 10)
        lignes.append(f"  {nom:25s} {poids:.2f} {barre}")
    hist = master.get("trades_par_trader", {}).get("historique", [])
    lignes.append(f"\nHistorique: {len(hist)} trades")
    gagnants = [h for h in hist if h.get("gagnant")]
    perdants = [h for h in hist if not h.get("gagnant")]
    lignes.append(f"Gagnants: {len(gagnants)} | Perdants: {len(perdants)}")

    # Stats par maitre
    stats = master.get("stats_par_maitre", {})
    if stats:
        lignes.append("\n--- Performance par maitre ---")
        for key, (nom, _) in MAITRES.items():
            s = stats.get(key, {})
            n = s.get("n", 0)
            if n > 0:
                wr = s.get("win_rate", 0)
                pnl = s.get("pnl", 0)
                lignes.append(f"  {nom:25s} {n} trades, WR {wr:.0f}%, PnL {pnl:+.2f}EUR")

    # Parametres evolutifs
    params = master.get("params_maitres", {})
    if params:
        lignes.append("\n--- Parametres evolutifs ---")
        for key, (nom, _) in MAITRES.items():
            p = params.get(key, {})
            if p:
                p_str = ", ".join(f"{k}={v}" for k, v in p.items())
                lignes.append(f"  {nom:25s} {p_str}")
    derniere = master.get("derniere_amelioration", "jamais")
    lignes.append(f"\nDerniere amelioration: {derniere}")
    return "\n".join(lignes)


if __name__ == "__main__":
    sym = "BTCUSDT"
    score, details, reco, extra = consensus_maitres(sym)
    print(f"\n=== {sym} ===")
    print(f"Score consensus: {score:+.2f} -> {reco}")
    print(f"Patterns bougies: {extra.get('patterns', 'aucun')}")
    print("\nVotes des maitres:")
    for nom, d in details.items():
        emoji = "🟢" if d["score"] > 0 else ("🔴" if d["score"] < 0 else "🟡")
        print(f"  {emoji} {nom:25s} {d['score']:+d} (poids {d['poids']:.1f}) - {d['detail']}")
