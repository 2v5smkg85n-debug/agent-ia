#!/usr/bin/env python3
"""
intelligence_pro.py - Module d'intelligence avancee pour le trading
- Fear & Greed Index (sentiment marche)
- Detection de regime de marche (bull/bear/sideways)
- Multi-timeframe analysis (15m, 1h, 4h, 1j)
- Kelly Criterion (taille de position optimale)
- Correlation entre cryptos (diversification)
- Backtesting des 10 maitres traders
"""

import json
import os
import time
import math
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_INTEL = os.path.join(DOSSIER, "intelligence_pro.json")

# Coin IDs CoinGecko
COIN_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink", "ARBUSDT": "arbitrum",
    "NEARUSDT": "near", "FETUSDT": "fetch-ai", "RNDRUSDT": "render-token",
    "LDOUSDT": "lido-dao", "AAVEUSDT": "aave", "PENDLEUSDT": "pendle",
}


def _load():
    try:
        with open(FICHIER_INTEL) as f:
            return json.load(f)
    except Exception:
        return {"last_update": 0, "fear_greed": {}, "regimes": {}, "correlations": {}}


def _save(data):
    try:
        with open(FICHIER_INTEL, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[INTEL] Erreur sauvegarde: {e}")


# ============================================
# FEAR & GREED INDEX
# ============================================
_cache_fg = {"value": None, "ts": 0}

def get_fear_greed():
    """Recupere le Fear & Greed Index depuis alternative.me"""
    if _cache_fg["value"] is not None and time.time() - _cache_fg["ts"] < 900:
        return _cache_fg["value"]
    try:
        import urllib.request
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        fg = data["data"][0]
        value = int(fg["value"])
        classification = fg["value_classification"]
        _cache_fg["value"] = {"value": value, "classification": classification, "ts": time.time()}
        _cache_fg["ts"] = time.time()
        return _cache_fg["value"]
    except Exception as e:
        print(f"[INTEL] Erreur Fear&Greed: {e}")
        return {"value": 50, "classification": "Neutral", "ts": 0}


def fear_greed_score():
    """Convertit le Fear & Greed en score utilisable par le bot.
    Extreme Fear (<25) = bonus d'achat (+2)
    Fear (25-45) = leger bonus (+1)
    Neutral (45-55) = neutre (0)
    Greed (55-75) = leger malus (-1)
    Extreme Greed (>75) = malus (-2)
    """
    fg = get_fear_greed()
    val = fg.get("value", 50)
    if val < 20:
        return 2, f"Extreme Fear ({val}) - opportunite d'achat"
    elif val < 35:
        return 1, f"Fear ({val}) - marché craintif"
    elif val < 55:
        return 0, f"Neutral ({val})"
    elif val < 75:
        return -1, f"Greed ({val}) - marché euphorique"
    else:
        return -2, f"Extreme Greed ({val}) -Attention bulle"


# ============================================
# DETECTION DE REGIME DE MARCHE
# ============================================
def detecter_regime(prix_histo):
    """Detecte le regime de marche: BULL, BEAR, ou SIDEWAYS.
    Utilise la SMA50 vs SMA200 (golden/death cross) + tendance.
    """
    if len(prix_histo) < 50:
        return "INCONNU", "donnees insuffisantes", 0

    prix_actuel = prix_histo[-1]
    sma50 = sum(prix_histo[-50:]) / 50
    sma20 = sum(prix_histo[-20:]) / 20 if len(prix_histo) >= 20 else sma50
    sma200 = sum(prix_histo[-200:]) / 200 if len(prix_histo) >= 200 else sma50

    # Variation 30j
    if len(prix_histo) >= 30:
        var_30j = (prix_actuel - prix_histo[-30]) / prix_histo[-30] * 100
    else:
        var_30j = 0

    # Volatilite 20j
    if len(prix_histo) >= 20:
        returns = [(prix_histo[i] - prix_histo[i-1]) / prix_histo[i-1] for i in range(-20, 0) if prix_histo[i-1] > 0]
        vol = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 * math.sqrt(365) * 100 if returns else 0
    else:
        vol = 0

    # Detection
    if sma20 > sma50 and sma50 > sma200 and var_30j > 5:
        regime = "BULL"
        detail = f"SMA20>SMA50>SMA200, +{var_30j:.1f}% 30j"
        score = 1
    elif sma20 < sma50 and sma50 < sma200 and var_30j < -5:
        regime = "BEAR"
        detail = f"SMA20<SMA50<SMA200, {var_30j:.1f}% 30j"
        score = -1
    elif abs(var_30j) < 3 and vol < 80:
        regime = "SIDEWAYS"
        detail = f"range etroit, var {var_30j:+.1f}%, vol {vol:.0f}%"
        score = 0
    elif sma20 > sma50:
        regime = "BULL_FAIBLE"
        detail = f"SMA20>SMA50 mais mixte, {var_30j:+.1f}% 30j"
        score = 0.5
    elif sma20 < sma50:
        regime = "BEAR_FAIBLE"
        detail = f"SMA20<SMA50, {var_30j:+.1f}% 30j"
        score = -0.5
    else:
        regime = "NEUTRE"
        detail = f"signaux mixtes, {var_30j:+.1f}% 30j"
        score = 0

    return regime, detail, score


def regime_global():
    """Detecte le regime global du marche crypto en analysant BTC."""
    try:
        import master_traders as mt
        prix_btc = mt.get_prix_histo("BTCUSDT")
        if len(prix_btc) < 50:
            return "INCONNU", "donnees insuffisantes", 0
        return detecter_regime(prix_btc)
    except Exception as e:
        print(f"[INTEL] Erreur regime global: {e}")
        return "INCONNU", str(e), 0


def strategie_par_regime(regime):
    """Retourne les ajustements de strategie selon le regime.
    En BULL: favoriser les strategies de breakout (Dennis), momentum (Soros)
    En BEAR: favoriser le mean reversion (Simons), RSI extreme (Tudor Jones)
    En SIDEWAYS: favoriser value (Buffett), range trading
    """
    ajustements = {
        "BULL": {"dennis": 1.3, "soros": 1.2, "rogers": 1.1, "tudor_jones": 0.8, "simons": 0.9},
        "BULL_FAIBLE": {"dennis": 1.1, "soros": 1.1, "rogers": 1.0, "tudor_jones": 0.9, "simons": 1.0},
        "BEAR": {"simons": 1.3, "tudor_jones": 1.3, "paulson": 1.2, "dennis": 0.7, "soros": 0.8},
        "BEAR_FAIBLE": {"simons": 1.1, "tudor_jones": 1.1, "paulson": 1.1, "dennis": 0.9, "soros": 0.9},
        "SIDEWAYS": {"buffett": 1.3, "dalio": 1.2, "yass": 1.1, "dennis": 1.0, "soros": 0.9},
        "NEUTRE": {},
    }
    return ajustements.get(regime, {})


# ============================================
# MULTI-TIMEFRAME ANALYSIS
# ============================================
_cache_mtf = {}

def get_ohlc_timeframe(symbole, timeframe="1d", days=30):
    """Recupere les bougies OHLC pour un timeframe donne.
    Utilise indicateurs.historique_ohlcv (Revolut X -> CoinGecko -> Binance) avec cache.
    """
    cache_key = f"{symbole}_{timeframe}"
    if cache_key in _cache_mtf and time.time() - _cache_mtf[cache_key]["ts"] < 300:
        return _cache_mtf[cache_key]["data"]

    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, timeframe, 100)
        if not bougies or len(bougies) < 5:
            return []
        # Convertir le format dict -> format liste [timestamp, open, high, low, close]
        raw = [[b["temps"], b["ouverture"], b["haut"], b["bas"], b["cloture"]] for b in bougies]
        _cache_mtf[cache_key] = {"data": raw, "ts": time.time()}
        return raw
    except Exception as e:
        print(f"[INTEL] Erreur OHLC {timeframe} {symbole}: {e}")
        return []


def analyse_multi_timeframe(symbole):
    """Analyse le signal sur plusieurs timeframes.
    Retourne un score global qui confirme ou infirme le signal.
    Un signal fort doit etre confirme sur au moins 2 timeframes.
    """
    timeframes = ["1h", "4h", "1d"]
    scores = {}
    details = {}

    for tf in timeframes:
        try:
            ohlc = get_ohlc_timeframe(symbole, tf)
            if len(ohlc) < 5:
                scores[tf] = 0
                details[tf] = "donnees insuffisantes"
                continue

            # Extraire les closes
            closes = [c[4] for c in ohlc]

            # Detecte donnees low-quality: range < 0.1% du prix moyen = Revolut X quasi-identiques
            _range_tf = max(closes) - min(closes)
            _mean_tf = sum(closes) / len(closes)
            if _mean_tf > 0 and (_range_tf / _mean_tf) < 0.001:
                scores[tf] = 0
                details[tf] = "donnees low-quality (range < 0.1%)"
                continue

            # Calculer SMA courte vs longue
            sma_courte = sum(closes[-5:]) / 5
            sma_longue = sum(closes[-10:]) / 10 if len(closes) >= 10 else sma_courte
            prix_actuel = closes[-1]

            # RSI simplifie
            gains = []
            pertes = []
            for i in range(1, min(15, len(closes))):
                diff = closes[i] - closes[i-1]
                if diff > 0:
                    gains.append(diff)
                    pertes.append(0)
                else:
                    gains.append(0)
                    pertes.append(abs(diff))
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(pertes) / len(pertes) if pertes else 0
            rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

            # Score du timeframe
            score = 0
            detail_parts = []

            if sma_courte > sma_longue:
                score += 1
                detail_parts.append("SMA courte > longue")
            else:
                score -= 1
                detail_parts.append("SMA courte < longue")

            if rsi < 35:
                score += 1
                detail_parts.append(f"RSI {rsi:.0f} survente")
            elif rsi > 65:
                score -= 1
                detail_parts.append(f"RSI {rsi:.0f} surchaté")
            else:
                detail_parts.append(f"RSI {rsi:.0f}")

            if prix_actuel > sma_longue:
                score += 0.5
                detail_parts.append("prix > SMA longue")
            else:
                score -= 0.5
                detail_parts.append("prix < SMA longue")

            scores[tf] = score
            details[tf] = ", ".join(detail_parts)

        except Exception as e:
            scores[tf] = 0
            details[tf] = f"erreur: {e}"

    # Score global multi-timeframe
    score_global = sum(scores.values()) / len(scores) if scores else 0

    # Confirmation: au moins 2 timeframes d'accord
    positifs = sum(1 for s in scores.values() if s > 0)
    negatifs = sum(1 for s in scores.values() if s < 0)

    if positifs >= 2 and score_global > 0:
        confirmation = "CONFIRME_ACHAT"
    elif negatifs >= 2 and score_global < 0:
        confirmation = "CONFIRME_VENTE"
    else:
        confirmation = "MIXTE"

    return score_global, confirmation, scores, details


# ============================================
# KELLY CRITERION (TAILLE DE POSITION OPTIMALE)
# ============================================
def kelly_criterion(win_rate, gain_moyen, perte_moyenne):
    """Calcule la fraction optimale de capital a risquer.
    Formule de Kelly: f = (p*b - q) / b
    ou p = win rate, q = 1-p, b = gain/perte ratio
    """
    if win_rate <= 0 or win_rate >= 1:
        return 0.05, "win rate extreme, position minimale"
    if perte_moyenne == 0:
        return 0.05, "perte moyenne nulle"
    b = abs(gain_moyen / perte_moyenne)
    if b <= 0:
        return 0.05, "ratio gain/perte invalide"
    q = 1 - win_rate
    f = (win_rate * b - q) / b
    # Kelly fractionne (on utilise 25% du Kelly pour eviter la ruine)
    f = max(0, f) * 0.25
    # Cap a 15% du capital par position
    f = min(f, 0.15)
    if f < 0.01:
        return 0.05, f"Kelly={f:.3f} trop faible, position minimale 5%"
    return f, f"Kelly={f:.1%} (WR={win_rate:.0%}, b={b:.2f})"


def calculer_taille_position(capital_disponible, symbole, historique_trades=None):
    """Calcule la taille optimale de position pour un symbole.
    Utilise le win rate et le ratio gain/perte historique.
    """
    # Valeurs par defaut
    win_rate = 0.50
    gain_moy = 3.0  # 3% TP
    perte_moy = 1.5  # 1.5% SL

    # Si on a un historique, calculer les vrais stats
    if historique_trades:
        trades_sym = [t for t in historique_trades if t.get("symbole") == symbole]
        if len(trades_sym) >= 5:
            gagnants = [t for t in trades_sym if t.get("gain_eur", 0) > 0]
            perdants = [t for t in trades_sym if t.get("gain_eur", 0) <= 0]
            if trades_sym:
                win_rate = len(gagnants) / len(trades_sym)
            if gagnants:
                gain_moy = sum(t.get("gain_pct", 3) for t in gagnants) / len(gagnants)
            if perdants:
                perte_moy = abs(sum(t.get("gain_pct", -1.5) for t in perdants) / len(perdants))

    fraction, raison = kelly_criterion(win_rate, gain_moy, perte_moy)
    montant = capital_disponible * fraction
    return montant, fraction, raison


# ============================================
# CORRELATION ENTRE CRYPTOS
# ============================================
_cache_corr = {"data": None, "ts": 0}

def calculer_correlations():
    """Calcule la matrice de correlation entre les principales cryptos.
    Permet d'eviter d'ouvrir des positions trop correlees.
    """
    if _cache_corr["data"] is not None and time.time() - _cache_corr["ts"] < 3600:
        return _cache_corr["data"]

    try:
        import master_traders as mt
        cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                   "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LDOUSDT", "AAVEUSDT"]
        prix_data = {}
        for sym in cryptos:
            try:
                histo = mt.get_prix_histo(sym)
                if len(histo) >= 20:
                    # Calculer les returns quotidiens
                    returns = [(histo[i] - histo[i-1]) / histo[i-1] for i in range(1, len(histo)) if histo[i-1] > 0]
                    prix_data[sym] = returns[-20:]  # 20 derniers jours
                time.sleep(0.5)
            except Exception:
                continue

        if len(prix_data) < 2:
            return {}

        # Matrice de correlation
        correlations = {}
        syms = list(prix_data.keys())
        for i, s1 in enumerate(syms):
            for j, s2 in enumerate(syms):
                if i < j:
                    r1 = prix_data[s1]
                    r2 = prix_data[s2]
                    min_len = min(len(r1), len(r2))
                    if min_len < 5:
                        continue
                    r1 = r1[-min_len:]
                    r2 = r2[-min_len:]
                    m1, m2 = sum(r1)/min_len, sum(r2)/min_len
                    v1 = sum((x-m1)**2 for x in r1)
                    v2 = sum((x-m2)**2 for x in r2)
                    if v1 == 0 or v2 == 0:
                        corr = 0
                    else:
                        cov = sum((r1[k]-m1)*(r2[k]-m2) for k in range(min_len))
                        corr = cov / (v1 * v2) ** 0.5
                    correlations[f"{s1}_{s2}"] = round(corr, 2)

        _cache_corr["data"] = correlations
        _cache_corr["ts"] = time.time()
        return correlations
    except Exception as e:
        print(f"[INTEL] Erreur correlation: {e}")
        return {}


def verifier_diversification(symbole, positions_ouvertes):
    """Verifie si l'ouverture d'une nouvelle position sur symbole
    cree un risque de concentration (trop de correlation).
    Retourne True si OK, False si trop de correlation.
    """
    if not positions_ouvertes:
        return True, "Aucune position ouverte, diversification OK"

    correlations = calculer_correlations()
    if not correlations:
        return True, "Donnees de correlation indisponibles"

    symboles_ouverts = [p.get("symbole", "") for p in positions_ouvertes]
    correlations_hautes = 0

    for sym_ouvert in symboles_ouverts:
        key1 = f"{symbole}_{sym_ouvert}"
        key2 = f"{sym_ouvert}_{symbole}"
        corr = correlations.get(key1, correlations.get(key2, 0))
        if corr > 0.8:
            correlations_hautes += 1

    if correlations_hautes >= 3:
        return False, f"3+ positions tres correlees a {symbole} - risque de concentration"
    elif correlations_hautes >= 2:
        return False, f"2 positions tres correlees - diversification insuffisante"
    return True, f"OK: {correlations_hautes} correlation(s) haute(s)"


# ============================================
# TP/SL ADAPTATIFS PAR CONSENSUS
# ============================================
def tp_sl_adaptatifs(score_consensus, regime, fear_greed_val):
    """Calcule le TP et SL optimaux selon le contexte.
    Score consensus fort + regime bull + fear = TP plus large.
    Score faible + regime bear + greed = TP serre.
    """
    tp_base = 3.0  # 3%
    sl_base = 1.5  # 1.5%

    # Ajustement par consensus
    if score_consensus >= 2:
        tp_base *= 1.5  # TP 4.5%
        sl_base *= 1.0
    elif score_consensus >= 1:
        tp_base *= 1.2  # TP 3.6%
    elif score_consensus < -1:
        tp_base *= 0.7  # TP 2.1% (si on achete quand meme, sortir vite)
        sl_base *= 1.3  # SL 1.95%

    # Ajustement par regime
    if regime in ["BULL", "BULL_FAIBLE"]:
        tp_base *= 1.2  # laisser courir les gains
        sl_base *= 0.9  # SL plus serre
    elif regime in ["BEAR", "BEAR_FAIBLE"]:
        tp_base *= 0.8  # sortir vite
        sl_base *= 1.2  # SL plus large (volatilite)

    # Ajustement par sentiment
    if fear_greed_val < 25:
        tp_base *= 1.1  # potentiel de rebond plus grand
    elif fear_greed_val > 75:
        tp_base *= 0.9  # prendre ses gains vite

    # Limites
    tp = max(1.5, min(8.0, tp_base))
    sl = max(0.8, min(4.0, sl_base))

    # Ratio TP/SL doit etre >= 1.5
    if tp / sl < 1.5:
        sl = tp / 1.5

    return round(tp, 2), round(sl, 2)


# ============================================
# BACKTESTING DES 10 MAITRES
# ============================================
def backtester_maitres(symbole, jours=90):
    """Backteste les 10 strategies de maitres sur l'historique.
    Simule des trades sur les 'jours' derniers jours et calcule les performances.
    """
    try:
        import master_traders as mt

        prix_histo = mt.get_prix_histo(symbole)
        if len(prix_histo) < 30:
            return {"erreur": "donnees insuffisantes"}, "Pas assez de donnees pour backtester"

        # Simuler des trades tous les 5 jours
        resultats = {key: {"trades": 0, "gagnants": 0, "perdants": 0, "pnl_total": 0, "pnl_pct": 0} for key in mt.MAITRES}

        # Fenetre glissante: utiliser 30j de donnees pour le signal, acheter, sortir apres 5j
        pas = 5
        for i in range(30, len(prix_histo) - pas, pas):
            fenetre = prix_histo[i-30:i]
            prix_entree = prix_histo[i]
            prix_sortie = prix_histo[i + pas] if i + pas < len(prix_histo) else prix_histo[-1]

            # Bougies simulées (approximation)
            bougies = []
            for j in range(max(0, i-5), i):
                o = prix_histo[j-1] if j > 0 else prix_histo[j]
                c = prix_histo[j]
                bougies.append({"open": o, "high": max(o, c), "low": min(o, c), "close": c})

            gain_pct = (prix_sortie - prix_entree) / prix_entree * 100

            # Tester chaque maitre
            for key, (nom, func) in mt.MAITRES.items():
                try:
                    score, _ = func(fenetre, bougies)
                    if score > 0:
                        # Simuler un achat
                        resultats[key]["trades"] += 1
                        gain_eur = gain_pct * 10 / 100  # 10 EUR par trade simule
                        resultats[key]["pnl_total"] += gain_eur
                        resultats[key]["pnl_pct"] += gain_pct
                        if gain_pct > 0:
                            resultats[key]["gagnants"] += 1
                        else:
                            resultats[key]["perdants"] += 1
                except Exception:
                    pass

        # Calculer les stats finales
        rapport = "=== BACKTEST {} ({} jours) ===\n\n".format(symbole, min(jours, len(prix_histo)))
        rapport_tries = []

        for key, (nom, _) in mt.MAITRES.items():
            r = resultats[key]
            n = r["trades"]
            if n == 0:
                rapport_tries.append((nom, n, 0, 0, 0, 0))
                continue
            wr = r["gagnants"] / n * 100
            pnl = r["pnl_total"]
            pnl_moy = r["pnl_pct"] / n
            rapport_tries.append((nom, n, wr, pnl, pnl_moy, r["gagnants"]))

        # Trier par PnL
        rapport_tries.sort(key=lambda x: x[3], reverse=True)

        rapport += f"{'Maitre':<25} {'Trades':>6} {'WR':>6} {'PnL':>8} {'PnL moy':>8}\n"
        rapport += "-" * 60 + "\n"
        for nom, n, wr, pnl, pnl_moy, g in rapport_tries:
            emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
            rapport += f"{emoji} {nom:<23} {n:>6} {wr:>5.0f}% {pnl:>+7.2f}€ {pnl_moy:>+7.1f}%\n"

        # Recommandations
        rapport += "\n--- Recommandations ---\n"
        gagnants = [(n, wr, pnl, nom) for nom, n, wr, pnl, _, _ in rapport_tries if n > 0 and pnl > 0]
        perdants = [(n, wr, pnl, nom) for nom, n, wr, pnl, _, _ in rapport_tries if n > 0 and pnl < 0]

        if gagnants:
            rapport += f"Top performer: {gagnants[0][3]} ({gagnants[0][2]:+.2f}€, WR {gagnants[0][1]:.0f}%)\n"
        if perdants:
            rapport += f"A eviter: {perdants[-1][3]} ({perdants[-1][2]:+.2f}€, WR {perdants[-1][1]:.0f}%)\n"

        return resultats, rapport

    except Exception as e:
        return {"erreur": str(e)}, f"Erreur backtest: {e}"


# ============================================
# SCORE GLOBAL D'INTELLIGENCE
# ============================================
def score_intelligent(symbole, positions_ouvertes=None, capital_disponible=1000):
    """Calcule un score global en combinant toutes les intelligences.
    - Fear & Greed (bonus/malus)
    - Regime de marche (filtre)
    - Multi-timeframe (confirmation)
    - Correlation (diversification)
    - Kelly (taille de position)
    """
    infos = {}

    # 1. Fear & Greed
    fg = get_fear_greed()
    fg_score, fg_detail = fear_greed_score()
    infos["fear_greed"] = {"value": fg.get("value", 50), "classification": fg.get("classification", "Neutral"), "score": fg_score, "detail": fg_detail}

    # 2. Regime
    regime, regime_detail, regime_score = regime_global()
    infos["regime"] = {"regime": regime, "detail": regime_detail, "score": regime_score}

    # 3. Multi-timeframe
    mtf_score, mtf_conf, mtf_scores, mtf_details = analyse_multi_timeframe(symbole)
    infos["multi_timeframe"] = {"score": mtf_score, "confirmation": mtf_conf, "scores": mtf_scores, "details": mtf_details}

    # 4. Diversification
    div_ok, div_detail = verifier_diversification(symbole, positions_ouvertes or [])
    infos["diversification"] = {"ok": div_ok, "detail": div_detail}

    # 5. TP/SL adaptatifs
    tp, sl = tp_sl_adaptatifs(mtf_score, regime, fg.get("value", 50))
    infos["tp_sl"] = {"tp": tp, "sl": sl}

    # Score total
    score_total = fg_score * 0.5 + regime_score * 1.0 + mtf_score * 1.5
    infos["score_total"] = round(score_total, 2)

    return infos


def rapport_intelligence(symbole="BTCUSDT"):
    """Genere un rapport texte de l'intelligence globale."""
    infos = score_intelligent(symbole)

    lignes = [f"=== INTELLIGENCE GLOBALE {symbole} ===\n"]

    fg = infos["fear_greed"]
    lignes.append(f"PSYCHOLOGIE MARCHE:")
    lignes.append(f"  Fear & Greed: {fg['value']} ({fg['classification']}) -> score {fg['score']:+.0f}")
    lignes.append(f"  {fg['detail']}\n")

    reg = infos["regime"]
    lignes.append(f"REGIME DE MARCHE: {reg['regime']}")
    lignes.append(f"  {reg['detail']}")
    lignes.append(f"  Score: {reg['score']:+.1f}\n")

    mtf = infos["multi_timeframe"]
    lignes.append(f"MULTI-TIMEFRAME: {mtf['confirmation']} (score {mtf['score']:+.2f})")
    for tf, s in mtf["scores"].items():
        lignes.append(f"  {tf}: {s:+.1f} - {mtf['details'].get(tf, '')}")
    lignes.append("")

    div = infos["diversification"]
    emoji_div = "OK" if div["ok"] else "BLOCAGE"
    lignes.append(f"DIVERSIFICATION: {emoji_div}")
    lignes.append(f"  {div['detail']}\n")

    tp_sl = infos["tp_sl"]
    lignes.append(f"TP/SL ADAPTATIFS: TP +{tp_sl['tp']:.1f}% / SL -{tp_sl['sl']:.1f}%")
    lignes.append(f"  Ratio TP/SL: {tp_sl['tp']/tp_sl['sl']:.1f}\n")

    lignes.append(f"SCORE GLOBAL: {infos['score_total']:+.2f}")
    if infos['score_total'] >= 2:
        lignes.append("VERDICT: ACHAT FORTEMENT CONFIRME")
    elif infos['score_total'] >= 1:
        lignes.append("VERDICT: ACHAT")
    elif infos['score_total'] >= -1:
        lignes.append("VERDICT: ATTENDRE")
    else:
        lignes.append("VERDICT: EVITER")

    return "\n".join(lignes)


# ============================================
# TEST
# ============================================
if __name__ == "__main__":
    print(rapport_intelligence("BTCUSDT"))
