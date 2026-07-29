#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
META-INTELLIGENCE — Auto-amelioration continue de l'agent de trading, SANS
IA externe (aucun appel Perplexity/Claude/Gemini). Pur Python.

Ce module combine et etend les briques existantes (indicateurs.py,
candlestick_learning.py, apprentissage_continu.py, paper_trading.py) en une
couche de "meta"-decision qui:

  1. BACKTEST INSTANTANE — rejoue l'historique recent pour estimer, en temps
     reel, la probabilite de succes des conditions techniques ACTUELLES
     (meme RSI, meme position Bollinger, meme direction MACD/SMA).
  2. FILTRE DE CORRELATION — evite d'ouvrir plusieurs positions fortement
     correlees (diversification du portefeuille).
  3. SIZING BASE SUR LA CONFIANCE — ajuste la taille de position selon la
     confiance du backtest instantane (skip / petite / normale / grande).
  4. POIDS ADAPTATIFS DES STRATEGIES — booste ou penalise chaque strategie
     selon sa performance RECENTE (20 derniers trades) vs sa performance
     globale.
  5. ADAPTATION AU REGIME DE MARCHE — utilise detecter_regime() pour
     favoriser momentum (bull), vente (bear), mean-reversion (range) ou
     exiger plus de confiance (volatile).
  6. META-ANALYSE — combine tout ce qui precede en une decision unique.
  7. RAPPORT — texte pret pour Telegram.

Aucune limite fixee sur l'apprentissage: chaque cycle relit les fichiers
JSON (paper_trading.json, pattern_learning.json...) et recalcule les poids
et scores a partir des donnees les plus recentes -> boucle d'amelioration
continue sans plafond arbitraire.

Usage:
    python meta_intelligence.py                    # meta-analyse complete (top 10 cryptos)
    python meta_intelligence.py --test BTCUSDT      # backtest instantane sur BTC
    python meta_intelligence.py --correlation       # matrice de correlation
    python meta_intelligence.py --strategies        # poids des strategies
    python meta_intelligence.py --rapport           # rapport complet (Telegram)
"""
import os
import sys
import json
import math
import statistics
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

# ============================================
# IMPORTS DU CODEBASE (jamais bloquants — repli neutre si echec)
# ============================================
try:
    from indicateurs import (
        historique_ohlcv, analyser_actif, rsi, macd, bandes_bollinger,
        moyennes_mobiles,
    )
except Exception:
    historique_ohlcv = None
    analyser_actif = None
    rsi = None
    macd = None
    bandes_bollinger = None
    moyennes_mobiles = None

try:
    from candlestick_learning import detecter_motif, score_motif, analyser_avec_apprentissage
except Exception:
    detecter_motif = None
    score_motif = None
    analyser_avec_apprentissage = None

try:
    from apprentissage_continu import detecter_regime, backtester_patterns, _symboles_crypto
except Exception:
    detecter_regime = None
    backtester_patterns = None
    _symboles_crypto = None

try:
    from paper_trading import MARCHES_PAPER, RISK_PAR_TRADE, MAX_POSITIONS
except Exception:
    # Repli minimal si paper_trading.py indisponible (import lourd/echoue)
    MARCHES_PAPER = {
        "BTCUSDT": {"nom": "Bitcoin", "marche": "crypto", "source": "binance"},
        "ETHUSDT": {"nom": "Ethereum", "marche": "crypto", "source": "binance"},
        "SOLUSDT": {"nom": "Solana", "marche": "crypto", "source": "binance"},
        "BNBUSDT": {"nom": "BNB", "marche": "crypto", "source": "binance"},
        "XRPUSDT": {"nom": "XRP", "marche": "crypto", "source": "binance"},
    }
    RISK_PAR_TRADE = 0.21
    MAX_POSITIONS = 4

# ============================================
# FICHIERS (tout dans DOSSIER, jamais /tmp en dur)
# ============================================
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_POIDS_STRATEGIES = os.path.join(DOSSIER, "strategy_weights.json")
FICHIER_LOG_META = os.path.join(DOSSIER, "meta_intelligence_log.jsonl")


# ============================================
# UTILITAIRES GENERIQUES
# ============================================
def _charger_json(chemin, defaut):
    try:
        if os.path.exists(chemin):
            with open(chemin, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return defaut


def _sauver_json(chemin, data):
    try:
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _log_meta(evenement, details=None):
    """Journalise un evenement meta (ne doit jamais planter le module)."""
    try:
        ligne = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "evenement": evenement,
            "details": details or {},
        }
        with open(FICHIER_LOG_META, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _symboles_crypto_suivis():
    """Liste des cryptos suivies (via MARCHES_PAPER, filtre marche=='crypto')."""
    try:
        if _symboles_crypto:
            return _symboles_crypto()
        return [s for s, cfg in MARCHES_PAPER.items() if cfg.get("marche") == "crypto"]
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def _top_n_cryptos(n=10):
    """Top N cryptos suivies, en respectant top_cryptos.json si dispo (classement
    par apprentissage), sinon les N premieres de MARCHES_PAPER."""
    try:
        tc = _charger_json(os.path.join(DOSSIER, "top_cryptos.json"), {})
        top = tc.get("top", [])
        if top:
            return top[:n]
    except Exception:
        pass
    return _symboles_crypto_suivis()[:n]


# ============================================
# 1. BACKTEST INSTANTANE (probabilite temps reel)
# ============================================
def _classer_rsi(valeur):
    """Classe le RSI en bucket grossier pour comparer des conditions 'similaires'."""
    if valeur is None:
        return "na"
    if valeur < 30:
        return "survente"
    if valeur < 45:
        return "bas"
    if valeur < 55:
        return "neutre"
    if valeur < 70:
        return "haut"
    return "surachat"


def _classer_bb(prix, bb_bas, bb_milieu, bb_haut):
    """Classe la position du prix par rapport aux bandes de Bollinger."""
    if not (bb_bas and bb_milieu and bb_haut):
        return "na"
    if prix <= bb_bas:
        return "sous_bas"
    if prix >= bb_haut:
        return "sur_haut"
    demi = bb_milieu - bb_bas
    if demi > 0 and prix <= bb_bas + 0.25 * demi:
        return "proche_bas"
    if demi > 0 and prix >= bb_haut - 0.25 * demi:
        return "proche_haut"
    return "milieu"


def _direction_macd(macd_line, signal_line):
    if macd_line is None or signal_line is None:
        return "na"
    return "haussier" if macd_line > signal_line else "baissier"


def _direction_sma(sma_courte, sma_longue):
    if sma_courte is None or sma_longue is None:
        return "na"
    return "haussier" if sma_courte > sma_longue else "baissier"


def _conditions_a_lindex(clotures, haut_bas_index, i, periode_bb=20, bb_ecart=2.0):
    """Calcule les 'conditions' (buckets RSI/BB/MACD/SMA) a la position i d'une
    serie de clotures, en n'utilisant que les donnees disponibles jusqu'a i
    (pas de fuite de donnees futures)."""
    fenetre = clotures[: i + 1]
    if len(fenetre) < 55:  # assez d'historique pour RSI/MACD/SMA50
        return None
    try:
        rsi_val = rsi(fenetre, 14) if rsi else None
        sma_c, sma_l = moyennes_mobiles(fenetre, 20, 50) if moyennes_mobiles else (None, None)
        macd_line, signal_line, _hist = macd(fenetre) if macd else (None, None, None)
        bb_m, bb_h, bb_b = bandes_bollinger(fenetre, periode_bb, bb_ecart) if bandes_bollinger else (None, None, None)
        prix = fenetre[-1]
        return {
            "rsi": _classer_rsi(rsi_val),
            "bb": _classer_bb(prix, bb_b, bb_m, bb_h),
            "macd": _direction_macd(macd_line, signal_line),
            "sma": _direction_sma(sma_c, sma_l),
        }
    except Exception:
        return None


def _conditions_signal_courant(signal_courant):
    """Extrait les buckets de conditions depuis un signal_courant fourni par
    l'appelant (dict avec indicateurs, cf. analyser_actif()) ou calcule via
    analyser_actif() si seul le symbole est passe."""
    try:
        ind = signal_courant.get("indicateurs", {}) if isinstance(signal_courant, dict) else {}
        rsi_val = ind.get("RSI")
        sma_c = ind.get("SMA20")
        sma_l = ind.get("SMA50")
        macd_line = ind.get("MACD")
        signal_line = ind.get("MACD_signal")
        bb_h = ind.get("BB_haut")
        bb_b = ind.get("BB_bas")
        bb_m = ind.get("BB_milieu")
        prix = signal_courant.get("prix")
        return {
            "rsi": _classer_rsi(rsi_val),
            "bb": _classer_bb(prix, bb_b, bb_m, bb_h) if prix else "na",
            "macd": _direction_macd(macd_line, signal_line),
            "sma": _direction_sma(sma_c, sma_l),
        }
    except Exception:
        return {"rsi": "na", "bb": "na", "macd": "na", "sma": "na"}


def backtest_instantane(symbole, signal_courant=None, intervalle="15m", lookback=200):
    """
    Backtest en temps reel: rejoue les 'lookback' dernieres bougies et, pour
    chaque position historique ou les conditions techniques (RSI/BB/MACD/SMA)
    correspondaient EXACTEMENT aux conditions actuelles, mesure ce qui s'est
    passe 5-10 bougies plus tard.

    signal_courant: dict retourne par analyser_actif() (optionnel). Si absent,
    on appelle analyser_actif(symbole, intervalle) pour obtenir les conditions
    actuelles.

    Retourne: {"win_rate": float, "gain_moyen": float, "sample_size": int,
               "confiance": float}
    """
    resultat = {"win_rate": 0.0, "gain_moyen": 0.0, "sample_size": 0, "confiance": 0.3}
    try:
        if historique_ohlcv is None:
            return resultat

        # Conditions actuelles (celles qu'on veut tester "dans le passe")
        if signal_courant is None and analyser_actif is not None:
            try:
                signal_courant = analyser_actif(symbole, intervalle)
            except Exception:
                signal_courant = None
        if not signal_courant:
            return resultat
        conditions_cibles = _conditions_signal_courant(signal_courant)
        if conditions_cibles.get("rsi") == "na" and conditions_cibles.get("macd") == "na":
            return resultat  # pas assez d'info pour comparer

        bougies = historique_ohlcv(symbole, intervalle, lookback)
        if not bougies or len(bougies) < 60:
            return resultat
        clotures = [b["cloture"] for b in bougies]

        HORIZON_MIN, HORIZON_MAX = 5, 10

        gains = []
        wins = 0
        # On parcourt l'historique, en s'assurant d'avoir assez de bougies
        # avant (>=55 pour les indicateurs) et apres (>=HORIZON_MAX) chaque
        # position testee.
        for i in range(55, len(bougies) - HORIZON_MAX):
            cond_i = _conditions_a_lindex(clotures, None, i)
            if cond_i is None:
                continue
            # Match EXACT des 4 conditions (memes buckets RSI/BB/MACD/SMA)
            if cond_i != conditions_cibles:
                continue

            prix_entree = clotures[i]
            if not prix_entree or prix_entree <= 0:
                continue

            # Moyenne du gain sur l'horizon [5,10] bougies plus tard (plus
            # robuste qu'un seul point de mesure)
            variations_horizon = []
            for h in range(HORIZON_MIN, HORIZON_MAX + 1):
                idx = i + h
                if idx >= len(bougies):
                    break
                prix_futur = clotures[idx]
                variations_horizon.append((prix_futur - prix_entree) / prix_entree * 100)
            if not variations_horizon:
                continue
            gain_pct = sum(variations_horizon) / len(variations_horizon)
            gains.append(gain_pct)
            if gain_pct > 0:
                wins += 1

        sample_size = len(gains)
        resultat["sample_size"] = sample_size
        if sample_size == 0:
            resultat["confiance"] = 0.3
            return resultat

        win_rate = wins / sample_size
        gain_moyen = sum(gains) / sample_size
        resultat["win_rate"] = round(win_rate, 4)
        resultat["gain_moyen"] = round(gain_moyen, 4)

        # --- Calcul de la confiance ---
        # < 10 echantillons -> confiance faible fixe (0.3)
        # win_rate > 70% et sample_size > 30 -> confiance maximale (1.0)
        # sinon: win_rate pondere par la taille de l'echantillon (plus il y a
        # de donnees, plus on fait confiance au win_rate mesure)
        if sample_size < 10:
            resultat["confiance"] = 0.3
        elif win_rate > 0.70 and sample_size > 30:
            resultat["confiance"] = 1.0
        else:
            sample_weight = min(1.0, sample_size / 50.0)  # plafonne a 1.0 vers 50 echantillons
            confiance = win_rate * (0.5 + 0.5 * sample_weight)
            resultat["confiance"] = round(max(0.0, min(1.0, confiance)), 4)

        return resultat
    except Exception as e:
        _log_meta("erreur_backtest_instantane", {"symbole": symbole, "erreur": str(e)})
        return resultat


# ============================================
# 2. FILTRE DE CORRELATION (diversification)
# ============================================
def _pearson(x, y):
    """Coefficient de correlation de Pearson entre deux series (pur Python,
    via statistics — pas de numpy)."""
    try:
        n = min(len(x), len(y))
        if n < 5:
            return 0.0
        x = x[-n:]
        y = y[-n:]
        mx = statistics.fmean(x)
        my = statistics.fmean(y)
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
        vx = math.sqrt(sum((a - mx) ** 2 for a in x))
        vy = math.sqrt(sum((b - my) ** 2 for b in y))
        if vx == 0 or vy == 0:
            return 0.0
        return cov / (vx * vy)
    except Exception:
        return 0.0


def _rendements(clotures):
    """Convertit une serie de prix en rendements (variation relative)."""
    try:
        return [
            (clotures[i] - clotures[i - 1]) / clotures[i - 1]
            for i in range(1, len(clotures))
            if clotures[i - 1]
        ]
    except Exception:
        return []


def matrice_correlation(symboles=None, lookback=50):
    """
    Recupere les 'lookback' dernieres bougies journalieres pour toutes les
    cryptos suivies et calcule la correlation de Pearson (sur les rendements)
    entre chaque paire.

    Retourne: {"BTCUSDT-ETHUSDT": 0.92, "BTCUSDT-AAVEUSDT": 0.65, ...}
    """
    correlations = {}
    try:
        if historique_ohlcv is None:
            return correlations
        if symboles is None:
            symboles = _symboles_crypto_suivis()

        series = {}
        for sym in symboles:
            try:
                bougies = historique_ohlcv(sym, "1d", lookback)
                if bougies and len(bougies) >= 10:
                    series[sym] = _rendements([b["cloture"] for b in bougies])
            except Exception:
                continue

        syms = list(series.keys())
        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                s1, s2 = syms[i], syms[j]
                corr = _pearson(series[s1], series[s2])
                cle = f"{s1}-{s2}"
                correlations[cle] = round(corr, 4)

        return correlations
    except Exception as e:
        _log_meta("erreur_matrice_correlation", {"erreur": str(e)})
        return correlations


_CACHE_CORRELATION = {"data": None, "ts": None}


def _matrice_correlation_cachee(ttl_secondes=1800):
    """Evite de recalculer la matrice de correlation a chaque appel
    (couteux: fetch de N*(N-1)/2 historiques). Cache 30 min par defaut."""
    try:
        maintenant = datetime.now()
        if (_CACHE_CORRELATION["data"] is not None and _CACHE_CORRELATION["ts"]
                and (maintenant - _CACHE_CORRELATION["ts"]).total_seconds() < ttl_secondes):
            return _CACHE_CORRELATION["data"]
        data = matrice_correlation()
        _CACHE_CORRELATION["data"] = data
        _CACHE_CORRELATION["ts"] = maintenant
        return data
    except Exception:
        return matrice_correlation()


def positions_correlees(symbole_ouvert, nouveau_symbole, seuil=0.7):
    """
    Verifie si ouvrir 'nouveau_symbole' serait trop correle avec une position
    deja ouverte sur 'symbole_ouvert'.

    Retourne True si correlation > seuil (NE PAS ouvrir), False sinon (OK).
    """
    try:
        if symbole_ouvert == nouveau_symbole:
            return True
        matrice = _matrice_correlation_cachee()
        if not matrice:
            return False  # pas de donnees -> fail-open (autorise)
        cle1 = f"{symbole_ouvert}-{nouveau_symbole}"
        cle2 = f"{nouveau_symbole}-{symbole_ouvert}"
        corr = matrice.get(cle1)
        if corr is None:
            corr = matrice.get(cle2)
        if corr is None:
            return False  # pas de donnee de correlation -> autorise par defaut
        return abs(corr) > seuil
    except Exception as e:
        _log_meta("erreur_positions_correlees", {"erreur": str(e)})
        return False


def positions_correlees_avec_portefeuille(nouveau_symbole, symboles_ouverts, seuil=0.7):
    """Variante pratique: verifie la correlation contre TOUTES les positions
    ouvertes d'un coup. Retourne True si au moins une est trop correlee."""
    try:
        for sym_ouvert in symboles_ouverts or []:
            if positions_correlees(sym_ouvert, nouveau_symbole, seuil):
                return True
        return False
    except Exception:
        return False


# ============================================
# 3. SIZING BASE SUR LA CONFIANCE
# ============================================
def taille_position_optimale(confiance, capital, risk_base=0.21):
    """
    Ajuste la taille de la position selon la confiance du backtest instantane:
      confiance < 0.4        -> skip (0)
      confiance 0.4 - 0.6    -> petite (risk_base * 0.5)
      confiance 0.6 - 0.8    -> normale (risk_base * 1.0)
      confiance > 0.8        -> grande (risk_base * 1.5, plafonnee a 30% du capital)

    Retourne: {"montant": float, "confiance": float, "taille": str}
    """
    try:
        confiance = max(0.0, min(1.0, float(confiance)))
        capital = max(0.0, float(capital))

        if confiance < 0.4:
            return {"montant": 0.0, "confiance": confiance, "taille": "skip"}

        if confiance <= 0.6:
            ratio = risk_base * 0.5
            taille = "petite"
        elif confiance <= 0.8:
            ratio = risk_base * 1.0
            taille = "normale"
        else:
            ratio = risk_base * 1.5
            taille = "grande"

        montant = capital * ratio
        plafond = capital * 0.30
        montant = min(montant, plafond)

        return {"montant": round(montant, 2), "confiance": round(confiance, 4), "taille": taille}
    except Exception as e:
        _log_meta("erreur_taille_position_optimale", {"erreur": str(e)})
        return {"montant": 0.0, "confiance": 0.0, "taille": "skip"}


# ============================================
# 4. POIDS ADAPTATIFS DES STRATEGIES
# ============================================
def poids_strategies(fenetre_recente=20):
    """
    Lit paper_trading.json (trades_fermes), regroupe par strategie, calcule
    le win rate RECENT (derniers 'fenetre_recente' trades) vs le win rate
    GLOBAL de la strategie.

    weight = win_rate_recent / win_rate_global
      -> weight > 1: la strategie s'ameliore recemment (boost)
      -> weight < 1: la strategie se degrade recemment (penalite)

    Retourne: {"RSI Mean Reversion": 1.2, "Bollinger Breakout": 0.8, ...}
    Ecrit le resultat dans strategy_weights.json (DOSSIER).
    """
    poids = {}
    try:
        pf = _charger_json(FICHIER_PAPER, {})
        trades = pf.get("trades_fermes", [])
        if not trades:
            _sauver_json(FICHIER_POIDS_STRATEGIES, {"poids": {}, "mis_a_jour": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return poids

        # Regroupe les trades par strategie, dans l'ordre chronologique
        # (trades_fermes est deja append-only donc chronologique)
        par_strategie = {}
        for t in trades:
            strat = t.get("strategie") or t.get("source") or "inconnu"
            par_strategie.setdefault(strat, []).append(t)

        for strat, ts in par_strategie.items():
            n = len(ts)
            gagnes_global = sum(1 for t in ts if t.get("gain_eur", 0.0) > 0)
            win_rate_global = gagnes_global / n if n else 0.0

            recents = ts[-fenetre_recente:]
            n_recent = len(recents)
            gagnes_recent = sum(1 for t in recents if t.get("gain_eur", 0.0) > 0)
            win_rate_recent = gagnes_recent / n_recent if n_recent else 0.0

            if win_rate_global > 0:
                weight = win_rate_recent / win_rate_global
            elif win_rate_recent > 0:
                weight = 1.5  # global nul mais recent positif -> boost prudent
            else:
                weight = 1.0  # pas assez de signal -> neutre

            # Clamp pour eviter des poids extremes sur peu de donnees
            weight = max(0.2, min(2.0, weight))
            poids[strat] = round(weight, 3)

        _sauver_json(FICHIER_POIDS_STRATEGIES, {
            "poids": poids,
            "mis_a_jour": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fenetre_recente": fenetre_recente,
        })
        return poids
    except Exception as e:
        _log_meta("erreur_poids_strategies", {"erreur": str(e)})
        return poids


def _charger_poids_strategies():
    """Charge strategy_weights.json (le recalcule si absent/vide)."""
    data = _charger_json(FICHIER_POIDS_STRATEGIES, {})
    poids = data.get("poids", {})
    if not poids:
        poids = poids_strategies()
    return poids


def boost_signal(symbole, strategie, score_courant):
    """
    Ajuste un score de signal selon le poids appris de la strategie:
        score_ajuste = score_courant * weight
    Si weight < 0.5, la strategie sous-performe -> le score est reduit
    d'autant plus fortement.
    """
    try:
        poids = _charger_poids_strategies()
        weight = poids.get(strategie, 1.0)
        return round(float(score_courant) * float(weight), 4)
    except Exception as e:
        _log_meta("erreur_boost_signal", {"symbole": symbole, "strategie": strategie, "erreur": str(e)})
        return score_courant


# ============================================
# 5. ADAPTATION AU REGIME DE MARCHE
# ============================================
def adapter_au_regime(symbole):
    """
    Utilise detecter_regime() (apprentissage_continu.py) pour determiner
    quel type de strategie privilegier selon le regime de marche courant.

    Retourne: {"regime": str, "ajustement": float, "strategie_preferee": str}
    """
    resultat = {"regime": "inconnu", "ajustement": 1.0, "strategie_preferee": "aucune"}
    try:
        if detecter_regime is None:
            return resultat
        info_regime = detecter_regime(symbole)
        regime = info_regime.get("regime", "inconnu")
        confiance_regime = info_regime.get("confiance", 0.0)
        resultat["regime"] = regime

        if regime == "trending_bull":
            # Booste les signaux momentum (MACD/tendance), reduit le mean-reversion
            resultat["ajustement"] = round(1.0 + 0.3 * confiance_regime, 3)
            resultat["strategie_preferee"] = "Momentum / MACD Trend Following"
        elif regime == "trending_bear":
            # Reduit tous les signaux d'achat, booste les signaux de vente
            resultat["ajustement"] = round(1.0 - 0.4 * confiance_regime, 3)
            resultat["strategie_preferee"] = "Vente / Short / Cash defensif"
        elif regime == "ranging":
            # Le mean-reversion (RSI survente/surachat) marche bien en range
            resultat["ajustement"] = round(1.0 + 0.2 * confiance_regime, 3)
            resultat["strategie_preferee"] = "RSI Mean Reversion / Bollinger Range"
        elif regime == "volatile":
            # Exige plus de confiance avant d'agir (reduit l'exposition par defaut)
            resultat["ajustement"] = round(1.0 - 0.3 * confiance_regime, 3)
            resultat["strategie_preferee"] = "Attente / confiance renforcee requise"
        else:
            resultat["ajustement"] = 1.0
            resultat["strategie_preferee"] = "aucune (regime inconnu)"

        resultat["ajustement"] = round(max(0.3, min(1.5, resultat["ajustement"])), 3)
        return resultat
    except Exception as e:
        _log_meta("erreur_adapter_au_regime", {"symbole": symbole, "erreur": str(e)})
        return resultat


# ============================================
# 6. META-ANALYSE (boucle d'auto-amelioration "sans limites")
# ============================================
def meta_analyse(symbole="BTCUSDT", capital=None, symboles_ouverts=None, intervalle="15m"):
    """
    Combine toutes les briques ci-dessus en une decision unique:
        instant backtest + correlation + confidence sizing + strategy
        weights + regime.

    Retourne un dict de decision complet (voir docstring du module pour le
    schema).
    """
    decision = {
        "symbole": symbole,
        "regime": "inconnu",
        "confiance": 0.0,
        "taille_position": "skip",
        "montant": 0.0,
        "strategies_poids": {},
        "correlation_bloquee": False,
        "backtest_win_rate": 0.0,
        "score_ajuste": 0.0,
        "recommendation": "SKIP",
    }
    try:
        # Capital courant: lu depuis paper_trading.json si non fourni
        if capital is None:
            pf = _charger_json(FICHIER_PAPER, {})
            capital = pf.get("liquidites", pf.get("capital_initial", 1000.0))

        # 1. Signal technique courant (base reelle pour tout le reste)
        signal_courant = None
        if analyser_actif is not None:
            try:
                signal_courant = analyser_actif(symbole, intervalle)
            except Exception:
                signal_courant = None
        score_brut = signal_courant.get("score", 0) if signal_courant else 0
        strategie = "technique"  # strategie par defaut utilisee par analyser_actif

        # 2. Backtest instantane -> confiance
        bt = backtest_instantane(symbole, signal_courant, intervalle=intervalle)
        confiance = bt.get("confiance", 0.3)

        # 3. Regime de marche -> ajustement directionnel
        regime_info = adapter_au_regime(symbole)
        decision["regime"] = regime_info.get("regime", "inconnu")
        ajustement_regime = regime_info.get("ajustement", 1.0)
        # En regime volatile, on exige une confiance plus elevee
        if regime_info.get("regime") == "volatile":
            confiance = confiance * 0.8

        # 4. Poids de strategie (apprentissage adaptatif)
        poids = poids_strategies()
        decision["strategies_poids"] = poids
        score_ajuste = boost_signal(symbole, strategie, score_brut) * ajustement_regime

        # 5. Filtre de correlation (diversification du portefeuille)
        bloque = False
        if symboles_ouverts:
            bloque = positions_correlees_avec_portefeuille(symbole, symboles_ouverts)
        decision["correlation_bloquee"] = bloque

        # 6. Sizing base sur la confiance
        sizing = taille_position_optimale(confiance, capital, RISK_PAR_TRADE)

        # 7. Recommandation finale
        if bloque:
            recommendation = "SKIP"
        elif sizing["taille"] == "skip" or score_ajuste <= 0:
            recommendation = "ATTENDRE"
        elif score_ajuste >= 2 and confiance >= 0.6:
            recommendation = "ACHAT"
        else:
            recommendation = "ATTENDRE"

        decision.update({
            "confiance": round(confiance, 4),
            "taille_position": sizing["taille"],
            "montant": sizing["montant"],
            "backtest_win_rate": bt.get("win_rate", 0.0),
            "backtest_gain_moyen": bt.get("gain_moyen", 0.0),
            "backtest_sample_size": bt.get("sample_size", 0),
            "score_brut": score_brut,
            "score_ajuste": round(score_ajuste, 4),
            "recommendation": recommendation,
        })

        _log_meta("meta_analyse", {"symbole": symbole, "recommendation": recommendation,
                                    "confiance": decision["confiance"]})
        return decision
    except Exception as e:
        _log_meta("erreur_meta_analyse", {"symbole": symbole, "erreur": str(e)})
        return decision


def meta_analyse_tous(top_n=10):
    """Lance meta_analyse() sur le top N des cryptos suivies. Utilise pour la
    boucle d'auto-amelioration continue (aucune limite: relit toujours les
    dernieres donnees disponibles a chaque appel)."""
    resultats = []
    try:
        symboles = _top_n_cryptos(top_n)
        pf = _charger_json(FICHIER_PAPER, {})
        capital = pf.get("liquidites", pf.get("capital_initial", 1000.0))
        symboles_ouverts = [p.get("symbole") for p in pf.get("positions", [])]
        for sym in symboles:
            d = meta_analyse(sym, capital=capital, symboles_ouverts=symboles_ouverts)
            resultats.append(d)
        return resultats
    except Exception as e:
        _log_meta("erreur_meta_analyse_tous", {"erreur": str(e)})
        return resultats


# ============================================
# 7. RAPPORT D'APPRENTISSAGE (texte Telegram)
# ============================================
def rapport_meta(top_n=10):
    """
    Construit un rapport texte pret pour Telegram:
      - Top 3 strategies par performance recente
      - Regime actuel de chaque crypto suivie
      - Correlations les plus fortes
      - Distribution de confiance sur le top N cryptos
    """
    try:
        lignes = ["🧠 META-INTELLIGENCE — RAPPORT", ""]

        # --- Top 3 strategies ---
        poids = poids_strategies()
        pf = _charger_json(FICHIER_PAPER, {})
        trades = pf.get("trades_fermes", [])
        par_strategie = {}
        for t in trades:
            strat = t.get("strategie") or t.get("source") or "inconnu"
            par_strategie.setdefault(strat, []).append(t)
        stats_strategies = []
        for strat, ts in par_strategie.items():
            n = len(ts)
            gagnes = sum(1 for t in ts if t.get("gain_eur", 0.0) > 0)
            wr = gagnes / n * 100 if n else 0.0
            stats_strategies.append({
                "strategie": strat, "n": n, "win_rate": wr,
                "poids": poids.get(strat, 1.0),
            })
        stats_strategies.sort(key=lambda s: (s["poids"], s["win_rate"]), reverse=True)
        lignes.append("🏆 Top 3 strategies (poids adaptatif):")
        if stats_strategies:
            for s in stats_strategies[:3]:
                lignes.append(f"  {s['strategie']}: poids x{s['poids']:.2f} | "
                              f"win rate {s['win_rate']:.0f}% ({s['n']} trades)")
        else:
            lignes.append("  (pas encore de trades fermes)")
        lignes.append("")

        # --- Regime par crypto ---
        symboles = _top_n_cryptos(top_n)
        lignes.append(f"📊 Regime de marche (top {len(symboles)} cryptos):")
        confiances = []
        for sym in symboles:
            regime_info = adapter_au_regime(sym)
            lignes.append(f"  {sym}: {regime_info['regime']} "
                          f"(strategie preferee: {regime_info['strategie_preferee']})")
        lignes.append("")

        # --- Correlations les plus fortes ---
        correlations = _matrice_correlation_cachee()
        lignes.append("🔗 Correlations les plus fortes:")
        if correlations:
            top_corr = sorted(correlations.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
            for paire, corr in top_corr:
                lignes.append(f"  {paire}: {corr:+.2f}")
        else:
            lignes.append("  (donnees insuffisantes)")
        lignes.append("")

        # --- Distribution de confiance ---
        lignes.append("🎯 Distribution de confiance (meta-analyse):")
        decisions = meta_analyse_tous(top_n)
        for d in decisions:
            confiances.append(d.get("confiance", 0.0))
            lignes.append(f"  {d['symbole']}: confiance {d['confiance']:.2f} | "
                          f"{d['recommendation']} | taille={d['taille_position']}")
        if confiances:
            lignes.append("")
            lignes.append(f"  Confiance moyenne: {statistics.fmean(confiances):.2f} "
                          f"(min {min(confiances):.2f} / max {max(confiances):.2f})")

        return "\n".join(lignes)
    except Exception as e:
        _log_meta("erreur_rapport_meta", {"erreur": str(e)})
        return "🧠 META-INTELLIGENCE — erreur lors de la generation du rapport."


# ============================================
# 8. MAIN / CLI
# ============================================
def aide():
    print("""
META-INTELLIGENCE - Aide
===========================================
Module d'auto-amelioration continue, SANS IA externe (pur Python).

Commandes:
  python meta_intelligence.py                    Meta-analyse complete (top 10 cryptos)
  python meta_intelligence.py --test BTCUSDT      Backtest instantane sur un actif
  python meta_intelligence.py --correlation       Matrice de correlation
  python meta_intelligence.py --strategies        Poids des strategies (adaptatif)
  python meta_intelligence.py --rapport           Rapport complet (format Telegram)
  python meta_intelligence.py --aide              Affiche cette aide
""")


def main():
    try:
        args = sys.argv[1:]
        if not args:
            print("=" * 60)
            print(f"META-INTELLIGENCE - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print("=" * 60)
            resultats = meta_analyse_tous(10)
            for d in resultats:
                print(f"\n{d['symbole']}: {d['recommendation']} "
                      f"(regime={d['regime']}, confiance={d['confiance']:.2f}, "
                      f"taille={d['taille_position']}, montant={d['montant']:.2f}EUR)")
                print(f"  backtest instantane: win_rate={d['backtest_win_rate']*100:.1f}% "
                      f"gain_moyen={d.get('backtest_gain_moyen',0):+.3f}% "
                      f"(n={d.get('backtest_sample_size',0)})")
                print(f"  score brut={d.get('score_brut',0)} -> score ajuste={d['score_ajuste']:+.2f} "
                      f"| correlation_bloquee={d['correlation_bloquee']}")
            print("\n" + "=" * 60)
        elif args[0] == "--test":
            symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
            print(f"Backtest instantane sur {symbole}...")
            signal_courant = analyser_actif(symbole, "15m") if analyser_actif else None
            r = backtest_instantane(symbole, signal_courant)
            print(json.dumps(r, indent=2, ensure_ascii=False))
        elif args[0] == "--correlation":
            print("Calcul de la matrice de correlation...")
            r = matrice_correlation()
            for paire, corr in sorted(r.items(), key=lambda kv: abs(kv[1]), reverse=True):
                print(f"  {paire}: {corr:+.4f}")
        elif args[0] == "--strategies":
            print("Poids des strategies (adaptatif)...")
            r = poids_strategies()
            print(json.dumps(r, indent=2, ensure_ascii=False))
            print(f"\nEcrit dans: {FICHIER_POIDS_STRATEGIES}")
        elif args[0] == "--rapport":
            print(rapport_meta())
        elif args[0] in ("--aide", "-h", "--help"):
            aide()
        else:
            aide()
    except Exception as e:
        print(f"Erreur (module resilient, ne devrait pas planter): {e}")
        _log_meta("erreur_main", {"erreur": str(e)})


if __name__ == "__main__":
    main()
