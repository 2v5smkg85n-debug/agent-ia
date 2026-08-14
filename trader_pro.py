#!/usr/bin/env python3
"""
Trader Pro Intelligence — Analyse multi-facteurs comme un trader professionnel.
Score chaque opportunité sur 6 dimensions avant d'acheter.
Apprend de ses erreurs en ajustant les poids des facteurs.
"""
import json
import os
import time
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_SCORES = os.path.join(DOSSIER, "trader_pro_scores.json")
COINGECKO_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "AVAX": "avalanche-2", "LINK": "chainlink",
    "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol", "NEAR": "near",
    "LDO": "lido-dao", "AAVE": "aave", "UNI": "uniswap", "PENDLE": "pendle",
    "RNDR": "render-token", "FET": "fetch-ai", "OCEAN": "ocean-protocol",
    "SEI": "seiprotocol", "TIA": "celestia", "SUI": "sui",
}


def charger_scores():
    try:
        with open(FICHIER_SCORES) as f:
            return json.load(f)
    except Exception:
        return {
            "poids_facteurs": {
                "tendance": 1.0,
                "momentum": 1.0,
                "rsi": 1.0,
                "volume": 1.0,
                "support_resistance": 1.0,
                "sentiment_marche": 1.0,
            },
            "historique_scores": [],
            "facteurs_gagnants": {},
            "facteurs_perdants": {},
            "version": 1,
        }


def sauver_scores(data):
    with open(FICHIER_SCORES, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_prix_historique(symbole, jours=14):
    """Recupere l'historique des prix via CoinGecko."""
    base = symbole.replace("USDT", "")
    cg_id = COINGECKO_MAP.get(base, base.lower())
    try:
        import urllib.request
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=eur&days={jours}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        prices = [p[1] for p in data.get("prices", [])]
        return prices
    except Exception:
        return []


def analyser_tendance(prix_historique):
    """Facteur 1: Tendance generale (SMA 7j vs SMA 14j)."""
    if len(prix_historique) < 14:
        return 0, "donnees insuffisantes"
    sma7 = sum(prix_historique[-7:]) / 7
    sma14 = sum(prix_historique[-14:]) / 14
    prix_actuel = prix_historique[-1]
    # Tendance haussiere si prix > SMA7 > SMA14
    if prix_actuel > sma7 > sma14:
        return 2, f"haussiere (prix>{sma7:.2f}>SMA14 {sma14:.2f})"
    elif prix_actuel > sma14:
        return 1, f"neutre-haut (prix>SMA14 {sma14:.2f})"
    elif prix_actuel < sma7 < sma14:
        return -2, f"baissiere (prix<{sma7:.2f}<SMA14 {sma14:.2f})"
    else:
        return -1, f"neutre-bas (prix<SMA14 {sma14:.2f})"


def analyser_momentum(prix_historique):
    """Facteur 2: Momentum (variation 3j et acceleration)."""
    if len(prix_historique) < 5:
        return 0, "insuffisant"
    var_3j = (prix_historique[-1] - prix_historique[-4]) / prix_historique[-4] * 100
    var_1j = (prix_historique[-1] - prix_historique[-2]) / prix_historique[-2] * 100
    # Momentum positif si var_3j > 0 et acceleration
    if var_3j > 3 and var_1j > 0:
        return 2, f"fort+ ({var_3j:+.1f}% 3j, {var_1j:+.1f}% 1j)"
    elif var_3j > 0 and var_1j > 0:
        return 1, f"positif ({var_3j:+.1f}% 3j)"
    elif var_3j < -5 and var_1j < 0:
        return -2, f"fort- ({var_3j:+.1f}% 3j)"
    elif var_3j < 0:
        return -1, f"negatif ({var_3j:+.1f}% 3j)"
    else:
        return 0, f"plat ({var_3j:+.1f}% 3j)"


def analyser_rsi(prix_historique):
    """Facteur 3: RSI (survente/surachat)."""
    if len(prix_historique) < 15:
        return 0, "insuffisant"
    # Calcul RSI 14
    gains = []
    pertes = []
    for i in range(1, min(15, len(prix_historique))):
        diff = prix_historique[i] - prix_historique[i-1]
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
    if rsi < 30:
        return 2, f"survente (RSI {rsi:.0f} - bon point d'entree)"
    elif rsi < 45:
        return 1, f"faible (RSI {rsi:.0f})"
    elif rsi > 70:
        return -2, f"surchaté (RSI {rsi:.0f} - attendre correction)"
    elif rsi > 55:
        return -1, f"eleve (RSI {rsi:.0f})"
    else:
        return 0, f"neutre (RSI {rsi:.0f})"


def analyser_volume_volatilite(prix_historique):
    """Facteur 4: Volatilite (ATR-like)."""
    if len(prix_historique) < 7:
        return 0, "insuffisant", 0
    # Volatilite = ecart-type des rendements quotidiens
    rendements = []
    for i in range(1, len(prix_historique)):
        if prix_historique[i-1] > 0:
            rendements.append((prix_historique[i] - prix_historique[i-1]) / prix_historique[i-1] * 100)
    if not rendements:
        return 0, "insuffisant", 0
    avg = sum(rendements) / len(rendements)
    variance = sum((r - avg) ** 2 for r in rendements) / len(rendements)
    vol = variance ** 0.5
    if vol < 2:
        return 1, f"faible vol ({vol:.1f}%) - stable", vol
    elif vol < 5:
        return 0, f"vol normale ({vol:.1f}%)", vol
    elif vol < 10:
        return -1, f"vol elevee ({vol:.1f}%) - risque", vol
    else:
        return -2, f"vol extreme ({vol:.1f}%) - danger", vol


def analyser_support_resistance(prix_historique):
    """Facteur 5: Position par rapport aux support/resistance."""
    if len(prix_historique) < 14:
        return 0, "insuffisant"
    prix_actuel = prix_historique[-1]
    recent = prix_historique[-14:]
    high = max(recent)
    low = min(recent)
    range_p = high - low
    if range_p == 0:
        return 0, "plat"
    position = (prix_actuel - low) / range_p * 100
    if position < 25:
        return 2, f"proche support ({position:.0f}% du range) - bon achat"
    elif position < 50:
        return 1, f"bas du range ({position:.0f}%)"
    elif position > 85:
        return -2, f"proche resistance ({position:.0f}%) - attendre"
    elif position > 65:
        return -1, f"haut du range ({position:.0f}%)"
    else:
        return 0, f"milieu range ({position:.0f}%)"


def score_opportunite(symbole, prix_actuel):
    """Score global d'une opportunite comme un trader pro.
    Retourne: score (-6 a +6), details, recommandation."""
    scores = charger_scores()
    prix_histo = get_prix_historique(symbole)
    if len(prix_histo) < 5:
        return 0, "Donnees insuffisantes", "SKIP", {}

    facteurs = {}
    details = []

    # 1. Tendance
    s_tendance, r_tendance = analyser_tendance(prix_histo)
    w = scores["poids_facteurs"]["tendance"]
    facteurs["tendance"] = s_tendance * w
    details.append(f"Tendance: {r_tendance} ({s_tendance:+d}x{w:.1f}={s_tendance*w:+.1f})")

    # 2. Momentum
    s_mom, r_mom = analyser_momentum(prix_histo)
    w = scores["poids_facteurs"]["momentum"]
    facteurs["momentum"] = s_mom * w
    details.append(f"Momentum: {r_mom} ({s_mom:+d}x{w:.1f}={s_mom*w:+.1f})")

    # 3. RSI
    s_rsi, r_rsi = analyser_rsi(prix_histo)
    w = scores["poids_facteurs"]["rsi"]
    facteurs["rsi"] = s_rsi * w
    details.append(f"RSI: {r_rsi} ({s_rsi:+d}x{w:.1f}={s_rsi*w:+.1f})")

    # 4. Volatilite
    s_vol, r_vol, vol = analyser_volume_volatilite(prix_histo)
    w = scores["poids_facteurs"]["volume"]
    facteurs["volume"] = s_vol * w
    details.append(f"Volatilite: {r_vol} ({s_vol:+d}x{w:.1f}={s_vol*w:+.1f})")

    # 5. Support/Resistance
    s_sr, r_sr = analyser_support_resistance(prix_histo)
    w = scores["poids_facteurs"]["support_resistance"]
    facteurs["support_resistance"] = s_sr * w
    details.append(f"Support/Res: {r_sr} ({s_sr:+d}x{w:.1f}={s_sr*w:+.1f})")

    # Score total
    score_total = sum(facteurs.values())

    # Ajuster TP/SL selon volatilite
    if vol > 0:
        tp_dynamique = max(2.0, min(8.0, vol * 1.5))  # TP = 1.5x volatilite
        sl_dynamique = max(1.0, min(4.0, vol * 0.8))   # SL = 0.8x volatilite
    else:
        tp_dynamique = 3.0
        sl_dynamique = 1.5

    # Recommandation (seuils assouplis pour ne pas tout bloquer)
    if score_total >= 4:
        reco = "ACHAT_FORT"
    elif score_total >= 1.5:
        reco = "ACHAT"
    elif score_total >= -1.5:
        reco = "ATTENDRE"  # neutre - laisse passer mais sans boost
    elif score_total >= -3:
        reco = "NE_PAS_ACHETER"
    else:
        reco = "VENTE"

    details_str = "\n".join(details)
    details_str += f"\nScore total: {score_total:+.1f}/6.0"
    details_str += f"\nTP optimal: +{tp_dynamique:.1f}% | SL optimal: -{sl_dynamique:.1f}%"

    return score_total, details_str, reco, {"tp": tp_dynamique, "sl": sl_dynamique, "vol": vol}


def apprendre_erreur(symbole, score_initial, resultat, facteurs_contexte=None):
    """Apprend d'un trade: si gagnant, renforce les facteurs qui ont contribue.
    Si perdant, reduit les facteurs qui ont induit en erreur."""
    scores = charger_scores()
    entry = {
        "symbole": symbole,
        "score": score_initial,
        "resultat": resultat,  # gain_eur
        "gagnant": resultat > 0,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "facteurs": facteurs_contexte or {},
    }
    scores["historique_scores"].append(entry)
    # Garder seulement les 200 derniers
    scores["historique_scores"] = scores["historique_scores"][-200:]

    # Ajuster les poids: petit ajustement (0.05) base sur le resultat
    ajustement = 0.05 if resultat > 0 else -0.05
    for facteur in scores["poids_facteurs"]:
        # Si le facteur etait positif et le trade gagnant -> renforcer
        # Si le facteur etait positif et le trade perdant -> reduire
        val_facteur = (facteurs_contexte or {}).get(facteur, 0)
        if val_facteur != 0:
            if (val_facteur > 0 and resultat > 0) or (val_facteur < 0 and resultat < 0):
                scores["poids_facteurs"][facteur] = min(2.0, scores["poids_facteurs"][facteur] + 0.05)
            else:
                scores["poids_facteurs"][facteur] = max(0.3, scores["poids_facteurs"][facteur] - 0.05)

    sauver_scores(scores)
    return scores


def rapport_trader_pro():
    """Genere un rapport du trader pro."""
    scores = charger_scores()
    lignes = ["=== TRADER PRO INTELLIGENCE ===\n"]
    lignes.append("Poids des facteurs (apres apprentissage):")
    for facteur, poids in scores["poids_facteurs"].items():
        barre = "#" * int(poids * 10)
        lignes.append(f"  {facteur:25s} {poids:.2f} {barre}")
    lignes.append(f"\nHistorique: {len(scores['historique_scores'])} trades")
    gagnants = [h for h in scores["historique_scores"] if h.get("gagnant")]
    perdants = [h for h in scores["historique_scores"] if not h.get("gagnant")]
    lignes.append(f"Gagnants: {len(gagnants)} | Perdants: {len(perdants)}")
    if gagnants:
        pnl_g = sum(h["resultat"] for h in gagnants)
        lignes.append(f"PnL gagnants: {pnl_g:+.2f}EUR")
    if perdants:
        pnl_p = sum(h["resultat"] for h in perdants)
        lignes.append(f"PnL perdants: {pnl_p:+.2f}EUR")
    return "\n".join(lignes)


if __name__ == "__main__":
    # Test sur BTC
    score, details, reco, params = score_opportunite("BTCUSDT", 55000)
    print(f"BTC: score={score:+.1f} reco={reco}")
    print(details)
    print(f"TP={params['tp']:.1f}% SL={params['sl']:.1f}%")
