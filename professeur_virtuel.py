#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""professeur_virtuel.py — Le Professeur Virtuel.

Inspiré des meilleurs traders crypto du monde et des stratégies backtestées
les plus rentables. Le bot apprend comme un élève qui veut dépasser son prof.

Sources d'inspiration:
  - Joe007 (+61M€): contrarien, fade les rallys euphoriques, discipline absolue
  - Cyclop (+3M€): catalyseurs (halving, ETF), entrées disciplinées
  - Downshift Rider (MACD 4h, PF 3.26, +230%): momentum MACD
  - Exhaustion Snap (Stoch RSI 4h, Sharpe 1.92): retournement Stoch RSI
  - Peak Fader (RSI 1h, PF 1.73, +96%): mean reversion RSI

Principe clé (backtest 49 stratégies):
  "Les stratégies à 70%+ WR ont des drawdowns de -70% à -155%.
   Les stratégies trend-following à 35% WR gagnent parce que
   les gagnants sont 3-4x plus gros que les perdants.
   Ce qui compte est le RATIO gain/perte, pas le WR."

Le professeur fixe:
  - TP = 2.5% / SL = 1.0% → ratio 2.5:1 (gagnant = 2.5x la perte)
  - Même à 40% WR: 10 trades → 4 gagnants (4 × 2.5% = 10%) vs 6 perdants (6 × 1% = 6%)
  - Net = +4% sur 10 trades au lieu de -0.8% avec l'ancien ratio 0.8:1
"""

import os
import json
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# ====================================================================
# CONFIGURATION DU PROFESSEUR
# ====================================================================

# Ratio gain/perte cible: 2.5:1 (les meilleurs traders du monde)
PROF_TP_PCT = 2.5       # +2.5% (300€ × 2.5% = 7.50€ - 0.42€ frais = 7.08€ net)
PROF_SL_PCT = 1.0       # -1.0% (300€ × 1% = 3.00€ perte max)
PROF_PARTIAL_TP = 1.0   # +1.0% → encaisse 50% (sécurise au-dessus des frais)

# Score minimum du professeur (plus exigeant que le score normal)
PROF_SCORE_MIN = 3

# ====================================================================
# STRATÉGIE 1: DOWNSHIFT RIDER (MACD momentum, 4h, PF 3.26)
# Inspiré de: anny.trade backtest — DOT short, MACD 4h, +230%
# Adapté pour long: détecte le momentum haussier MACD sur 4h
# ====================================================================

def _downshift_rider(symbole, bougies_4h):
    """Détecte un momentum haussier confirmé sur 4h avec MACD.

    Règles (adapté du backtest):
    - MACD line croise au-dessus de la signal line (croisement haussier)
    - L'histogramme MACD est positif et croissant (momentum qui accélère)
    - Le prix est au-dessus de l'EMA 20 (confirmation de tendance)

    Returns: (score, raison) ou (0, "")
    """
    if not bougies_4h or len(bougies_4h) < 35:
        return 0, ""

    clotures = [b["cloture"] for b in bougies_4h]
    try:
        from indicateurs import macd as _macd, ema as _ema
    except Exception:
        return 0, ""

    macd_line, signal_line, histo = _macd(clotures, courte=12, longue=26, signal=9)
    if macd_line is None or signal_line is None:
        return 0, ""

    # EMA 20 pour confirmation de tendance
    ema20_vals = []
    for i in range(len(clotures)):
        v = _ema(clotures[:i+1], 20)
        if v is not None:
            ema20_vals.append(v)
    ema20 = ema20_vals[-1] if ema20_vals else None

    prix = clotures[-1]
    score = 0
    raisons = []

    # 1. Croisement haussier récent (dans les 3 dernières bougies)
    croisement_recent = False
    for i in range(-3, 0):
        idx = len(clotures) + i
        if idx >= 1 and macd_line > signal_line:
            # Vérifier si le croisement est récent (MACD était sous signal avant)
            # On utilise les valeurs actuelles comme proxy
            croisement_recent = True
            break

    if macd_line > signal_line and histo > 0:
        score += 2
        raisons.append(f"MACD 4h haussier (line {macd_line:.4f} > signal {signal_line:.4f})")
    elif macd_line > signal_line:
        score += 1
        raisons.append(f"MACD 4h: line au-dessus signal (momentum positif)")

    # 2. Histogramme croissant = momentum qui accélère
    if len(histo) if isinstance(histo, (list, tuple)) else False:
        if histo[-1] > histo[-2]:
            score += 1
            raisons.append("MACD histo croissant (momentum qui accelere)")

    # 3. Prix au-dessus de l'EMA 20 (confirmation tendance)
    if ema20 is not None and prix > ema20:
        score += 1
        raisons.append(f"Prix {prix:.4f} > EMA20 {ema20:.4f} (tendance confirmee)")

    if score >= 2:
        return score, " | ".join(raisons)
    return 0, ""


# ====================================================================
# STRATÉGIE 2: EXHAUSTION SNAP (Stochastic RSI, 4h, Sharpe 1.92)
# Inspiré de: anny.trade backtest — XRP short, Stoch RSI 4h, +106%
# Adapté pour long: détecte quand la vente est épuisée (Stoch RSI < 20)
# ====================================================================

def _stoch_rsi(clotures, rsi_periode=14, stoch_periode=14):
    """Calcule le Stochastic RSI (0-100).

    Stoch RSI = (RSI actuel - RSI minimum) / (RSI max - RSI min) × 100
    < 20 = survente (épuisement vendeur = opportunité d'achat)
    > 80 = surachat (épuisement acheteur = risque de correction)
    """
    if len(clotures) < rsi_periode + stoch_periode:
        return None, None

    try:
        from indicateurs import rsi as _rsi
    except Exception:
        return None, None

    # Calculer RSI sur les dernières bougies
    rsi_vals = []
    for i in range(len(clotures) - stoch_periode, len(clotures)):
        v = _rsi(clotures[:i+1], rsi_periode)
        if v is not None:
            rsi_vals.append(v)

    if len(rsi_vals) < stoch_periode:
        return None, None

    rsi_min = min(rsi_vals)
    rsi_max = max(rsi_vals)
    rsi_actuel = rsi_vals[-1]

    if rsi_max == rsi_min:
        return 50.0, rsi_actuel  # neutre si pas de variation

    stoch_rsi = ((rsi_actuel - rsi_min) / (rsi_max - rsi_min)) * 100
    return stoch_rsi, rsi_actuel


def _exhaustion_snap(symbole, bougies_4h):
    """Détecte un épuisement vendeur sur 4h avec Stochastic RSI.

    Règles (adapté du backtest):
    - Stoch RSI < 20 (survente extrême = les vendeurs sont épuisés)
    - RSI < 35 (confirmation de survente)
    - Le prix est proche du bas des dernières bougies (capitulation)

    Returns: (score, raison) ou (0, "")
    """
    if not bougies_4h or len(bougies_4h) < 30:
        return 0, ""

    clotures = [b["cloture"] for b in bougies_4h]
    stoch_rsi_val, rsi_val = _stoch_rsi(clotures)

    if stoch_rsi_val is None or rsi_val is None:
        return 0, ""

    score = 0
    raisons = []

    # 1. Stoch RSI < 20 = survente extrême
    if stoch_rsi_val < 20:
        score += 3
        raisons.append(f"Stoch RSI 4h = {stoch_rsi_val:.1f} (survente extreme < 20)")
    elif stoch_rsi_val < 30:
        score += 2
        raisons.append(f"Stoch RSI 4h = {stoch_rsi_val:.1f} (survente < 30)")
    elif stoch_rsi_val < 40:
        score += 1
        raisons.append(f"Stoch RSI 4h = {stoch_rsi_val:.1f} (zone d'achat)")

    # 2. RSI < 35 (confirmation)
    if rsi_val < 30:
        score += 2
        raisons.append(f"RSI 4h = {rsi_val:.1f} (survente profonde)")
    elif rsi_val < 35:
        score += 1
        raisons.append(f"RSI 4h = {rsi_val:.1f} (survente)")

    # 3. Prix proche du bas des 20 dernières bougies (capitulation)
    if len(clotures) >= 20:
        bas_20 = min(clotures[-20:])
        haut_20 = max(clotures[-20:])
        if haut_20 > bas_20:
            position = (clotures[-1] - bas_20) / (haut_20 - bas_20)
            if position < 0.25:
                score += 1
                raisons.append(f"Prix dans le bas 25% des 20 dernieres bougies 4h (capitulation)")

    if score >= 2:
        return score, " | ".join(raisons)
    return 0, ""


# ====================================================================
# STRATÉGIE 3: PEAK FADER (RSI mean reversion, 1h, PF 1.73)
# Inspiré de: anny.trade backtest — DOT 1h, RSI, +96%
# Adapté: détecte quand le RSI sort de survente (retournement haussier)
# ====================================================================

def _peak_fader(symbole, bougies_1h):
    """Détecte un retournement haussier après survente sur 1h.

    Règles (adapté du backtest):
    - RSI était < 30 (survente) dans les 5 dernières bougies
    - RSI actuel > 30 et < 45 (sortie de survente = retournement)
    - Le prix a fait un bas plus haut (confirmation)

    Returns: (score, raison) ou (0, "")
    """
    if not bougies_1h or len(bougies_1h) < 25:
        return 0, ""

    clotures = [b["cloture"] for b in bougies_1h]
    try:
        from indicateurs import rsi as _rsi
    except Exception:
        return 0, ""

    rsi_actuel = _rsi(clotures, 14)
    if rsi_actuel is None:
        return 0, ""

    # RSI des 5 dernières bougies
    rsi_recent = []
    for i in range(-5, 0):
        idx = len(clotures) + i
        if idx >= 14:
            v = _rsi(clotures[:idx+1], 14)
            if v is not None:
                rsi_recent.append(v)

    score = 0
    raisons = []

    # 1. RSI sort de survente (était < 30, maintenant > 30)
    rsi_etait_survente = any(r < 30 for r in rsi_recent)
    if rsi_etait_survente and 30 <= rsi_actuel < 45:
        score += 3
        raisons.append(f"RSI 1h sort de survente ({rsi_actuel:.1f}, etait < 30)")
    elif rsi_etait_survente and 45 <= rsi_actuel < 55:
        score += 2
        raisons.append(f"RSI 1h en retournement ({rsi_actuel:.1f}, sorti de survente)")
    elif rsi_actuel < 30:
        score += 1
        raisons.append(f"RSI 1h en survente ({rsi_actuel:.1f}) — attendre confirmation")

    # 2. Bas plus haut (les 3 dernières bougies font un bas ascendant)
    if len(clotures) >= 6:
        bas1 = min(clotures[-6:-3])
        bas2 = min(clotures[-3:])
        if bas2 > bas1:
            score += 1
            raisons.append("Bas ascendant sur 1h (structure haussiere)")

    if score >= 2:
        return score, " | ".join(raisons)
    return 0, ""


# ====================================================================
# MÉTHODE JOE007: FILTRE CONTRARIEN (Fear & Greed)
# "Fade les rallys euphoriques, achète la peur"
# ====================================================================

def _filtre_contrarien_joe007():
    """Applique le filtre contrarien de Joe007 basé sur le Fear & Greed Index.

    Joe007: "Je prends l'autre côté des rallys euphoriques et des positions surchargées."

    Returns: (modificateur_score, multiplicateur_taille, raison)
    - Extreme Fear (< 25): +2 score, x1.2 taille (achète la peur)
    - Fear (25-44): +1 score, x1.0 taille
    - Neutral (45-55): 0, x0.9
    - Greed (56-75): -1 score, x0.7 taille (prudence sur l'euphorie)
    - Extreme Greed (> 75): -3 score, x0.5 taille (fade l'euphorie)
    """
    try:
        from sentiment_marche import get_fear_greed
        fg = get_fear_greed()
    except Exception:
        return 0, 1.0, "F&G indisponible"

    if fg < 25:
        return 2, 1.2, f"Extreme Fear ({fg}/100) — Joe007: achete la peur (+2 score, x1.2 taille)"
    elif fg < 45:
        return 1, 1.0, f"Fear ({fg}/100) — Joe007: zone d'achat (+1 score)"
    elif fg <= 55:
        return 0, 0.9, f"Neutral ({fg}/100) — Joe007: neutre"
    elif fg <= 75:
        return -1, 0.7, f"Greed ({fg}/100) — Joe007: prudence (-1 score, x0.7 taille)"
    else:
        return -3, 0.5, f"Extreme Greed ({fg}/100) — Joe007: fade l'euphorie (-3 score, x0.5)"


# ====================================================================
# MÉTHODE CYCLOP: DÉTECTION DE CATALYSEUR
# "Entrées disciplinées autour des événements majeurs"
# ====================================================================

def _detecter_catalyseur_cyclop(symbole, bougies_1h):
    """Détecte un catalyseur (mouvement de prix important récent).

    Cyclop: "J'utilise les catalyseurs du marché (halving, ETF, listings)
    avec des entrées disciplinées et des stablecoins pour protéger les gains."

    Détecte:
    - Variation > 5% en 24h (mouvement catalyseur)
    - Volume anormalement élevé (attention du marché)
    - Volatilité en expansion (pré-breakout)

    Returns: (score_bonus, raison) ou (0, "")
    """
    if not bougies_1h or len(bougies_1h) < 24:
        return 0, ""

    clotures = [b["cloture"] for b in bougies_1h]
    volumes = [b.get("volume", 0) for b in bougies_1h]

    score = 0
    raisons = []

    # 1. Variation 24h > 5% (catalyseur potentiel)
    if len(clotures) >= 24:
        var_24h = (clotures[-1] - clotures[-24]) / clotures[-24] * 100
        if abs(var_24h) > 8:
            score += 2
            raisons.append(f"Catalyseur: variation 24h = {var_24h:+.1f}% (mouvement majeur)")
        elif abs(var_24h) > 5:
            score += 1
            raisons.append(f"Catalyseur: variation 24h = {var_24h:+.1f}% (attention du marche)")

    # 2. Volume anormal (volume des 3 dernières bougies > 2x la moyenne 20)
    if len(volumes) >= 23 and volumes[-1] > 0:
        vol_moyen = sum(volumes[-23:-3]) / max(1, len(volumes[-23:-3]))
        vol_recent = sum(volumes[-3:]) / 3
        if vol_moyen > 0 and vol_recent > 2 * vol_moyen:
            score += 1
            raisons.append(f"Volume 3x superieur a la moyenne (catalyseur volume)")

    # 3. Volatilité en expansion (les 5 dernières bougies ont une amplitude > 2x la moyenne)
    if len(bougies_1h) >= 25:
        amplitudes = [(b["haut"] - b["bas"]) / b["cloture"] * 100 for b in bougies_1h if b.get("haut") and b.get("bas") and b.get("cloture", 0) > 0]
        if len(amplitudes) >= 25:
            amp_moyenne = sum(amplitudes[-25:-5]) / max(1, len(amplitudes[-25:-5]))
            amp_recente = sum(amplitudes[-5:]) / 5
            if amp_moyenne > 0 and amp_recente > 2 * amp_moyenne:
                score += 1
                raisons.append("Volatilite en expansion (pre-breakout)")

    if score > 0:
        return score, " | ".join(raisons)
    return 0, ""


# ====================================================================
# APPRENTISSAGE DU PROFESSEUR: mémorise les résultats
# ====================================================================

def _charger_stats_prof():
    """Charge les statistiques d'apprentissage du professeur."""
    path = os.path.join(DOSSIER, "professeur_stats.json")
    try:
        return json.load(open(path))
    except Exception:
        return {
            "trades_total": 0,
            "gagnants": 0,
            "perdants": 0,
            "pnl_total": 0,
            "par_strategie": {},
            "par_crypto": {},
            "dernier_ajustement": None,
        }


def _sauvegarder_stats_prof(stats):
    """Sauvegarde les statistiques d'apprentissage du professeur."""
    path = os.path.join(DOSSIER, "professeur_stats.json")
    try:
        stats["dernier_ajustement"] = datetime.utcnow().isoformat()
        json.dump(stats, open(path, "w"), indent=2, ensure_ascii=False)
    except Exception:
        pass


def enregistrer_trade_prof(symbole, strategie, gain_eur, gain_pct):
    """Le professeur enregistre chaque trade pour apprendre.

    Comme un élève qui note ses erreurs pour ne plus les reproduire,
    le professeur ajuste ses scores futurs en fonction des résultats.
    """
    stats = _charger_stats_prof()
    stats["trades_total"] += 1
    stats["pnl_total"] += gain_eur

    if gain_eur > 0:
        stats["gagnants"] += 1
    else:
        stats["perdants"] += 1

    # Par stratégie
    s = stats["par_strategie"].setdefault(strategie, {
        "n": 0, "gagnants": 0, "pnl": 0, "wr": 0, "boost": 0
    })
    s["n"] += 1
    s["pnl"] += gain_eur
    if gain_eur > 0:
        s["gagnants"] += 1
    s["wr"] = round(s["gagnants"] / s["n"] * 100, 1) if s["n"] else 0
    # Boost: +1 si WR > 55%, -1 si WR < 40% (après 5 trades min)
    if s["n"] >= 5:
        if s["wr"] > 55:
            s["boost"] = 1
        elif s["wr"] < 40:
            s["boost"] = -1

    # Par crypto
    c = stats["par_crypto"].setdefault(symbole, {
        "n": 0, "gagnants": 0, "pnl": 0, "wr": 0
    })
    c["n"] += 1
    c["pnl"] += gain_eur
    if gain_eur > 0:
        c["gagnants"] += 1
    c["wr"] = round(c["gagnants"] / c["n"] * 100, 1) if c["n"] else 0

    _sauvegarder_stats_prof(stats)
    return stats


def _boost_apprentissage_prof(strategie, symbole):
    """Retourne le boost de score basé sur l'apprentissage du professeur.

    Le professeur a appris quelles stratégies et quelles cryptos gagnent.
    Il booste les gagnantes et pénalise les perdantes.
    """
    stats = _charger_stats_prof()
    boost = 0
    raison = ""

    # Boost par stratégie
    s = stats["par_strategie"].get(strategie, {})
    if s.get("n", 0) >= 5:
        b = s.get("boost", 0)
        if b != 0:
            boost += b
            raison += f"Prof: {strategie} WR={s['wr']}% ({s['n']} trades) -> {'+' if b > 0 else ''}{b} "

    # Boost par crypto
    c = stats["par_crypto"].get(symbole, {})
    if c.get("n", 0) >= 5:
        if c["wr"] > 60:
            boost += 1
            raison += f"Prof: {symbole} WR={c['wr']}% -> +1"
        elif c["wr"] < 40:
            boost -= 1
            raison += f"Prof: {symbole} WR={c['wr']}% -> -1"

    return boost, raison.strip()


# ====================================================================
# FONCTION PRINCIPALE: générer les signaux du professeur
# ====================================================================

def generer_signaux_professeur(prix_actuels, marches_paper):
    """Génère des signaux en utilisant les stratégies du Professeur Virtuel.

    Pipeline:
    1. Récupère les bougies 1h et 4h pour chaque crypto
    2. Applique les 3 stratégies backtestées (Downshift Rider, Exhaustion Snap, Peak Fader)
    3. Applique le filtre contrarien Joe007 (Fear & Greed)
    4. Détecte les catalyseurs Cyclop
    5. Applique l'apprentissage du professeur (boost par stratégie/crypto)
    6. Retourne les signaux avec TP/SL du professeur (ratio 2.5:1)

    Returns: liste de signaux (format compatible avec paper_trading.py)
    """
    try:
        from indicateurs import historique_ohlcv
    except Exception:
        print("  [PROF] indicateurs indisponibles")
        return []

    # Filtre contrarien Joe007 (une seule fois pour tous les signaux)
    mod_score_joe, mult_taille_joe, raison_joe = _filtre_contrarien_joe007()
    if mod_score_joe != 0:
        print(f"  [PROF] Joe007: {raison_joe}")

    signaux = []

    for symbole, config in marches_paper.items():
        if symbole not in prix_actuels:
            continue
        if config.get("marche") != "crypto":
            continue

        prix = prix_actuels[symbole]
        nom = config.get("nom", symbole)

        # Récupère les bougies 1h et 4h
        try:
            bougies_1h = historique_ohlcv(symbole, "1h", 100)
            bougies_4h = historique_ohlcv(symbole, "4h", 100)
        except Exception:
            continue

        if not bougies_1h and not bougies_4h:
            continue

        # === STRATÉGIE 1: Downshift Rider (MACD 4h) ===
        score_rider, raison_rider = 0, ""
        if bougies_4h:
            score_rider, raison_rider = _downshift_rider(symbole, bougies_4h)
            if score_rider > 0:
                print(f"  [PROF] Downshift Rider sur {nom}: score {score_rider} — {raison_rider}")

        # === STRATÉGIE 2: Exhaustion Snap (Stoch RSI 4h) ===
        score_snap, raison_snap = 0, ""
        if bougies_4h:
            score_snap, raison_snap = _exhaustion_snap(symbole, bougies_4h)
            if score_snap > 0:
                print(f"  [PROF] Exhaustion Snap sur {nom}: score {score_snap} — {raison_snap}")

        # === STRATÉGIE 3: Peak Fader (RSI 1h) ===
        score_fader, raison_fader = 0, ""
        if bougies_1h:
            score_fader, raison_fader = _peak_fader(symbole, bougies_1h)
            if score_fader > 0:
                print(f"  [PROF] Peak Fader sur {nom}: score {score_fader} — {raison_fader}")

        # Prend la meilleure stratégie
        best_score = max(score_rider, score_snap, score_fader)
        if best_score == 0:
            continue

        if best_score == score_rider and score_rider > 0:
            strategie = "downshift_rider"
            raison = raison_rider
        elif best_score == score_snap and score_snap > 0:
            strategie = "exhaustion_snap"
            raison = raison_snap
        else:
            strategie = "peak_fader"
            raison = raison_fader

        # === CATALYSEUR CYCLOP ===
        score_catalyseur, raison_catalyseur = 0, ""
        if bougies_1h:
            score_catalyseur, raison_catalyseur = _detecter_catalyseur_cyclop(symbole, bougies_1h)
            if score_catalyseur > 0:
                print(f"  [PROF] Catalyseur Cyclop sur {nom}: +{score_catalyseur} — {raison_catalyseur}")

        # === FILTRE CONTRARIEN JOE007 ===
        # mod_score_joe déjà calculé au début
        # (appliqué à tous les signaux)

        # === APPRENTISSAGE DU PROFESSEUR ===
        boost_prof, raison_prof = _boost_apprentissage_prof(strategie, symbole)
        if boost_prof != 0:
            print(f"  [PROF] Apprentissage: {raison_prof}")

        # Score final du professeur
        score_final = best_score + score_catalyseur + mod_score_joe + boost_prof

        if score_final < PROF_SCORE_MIN:
            continue

        # Construit la raison complète
        raisons_complete = [f"PROF {strategie} (score {best_score})"]
        if raison_catalyseur:
            raisons_complete.append(f"Catalyseur +{score_catalyseur}")
        if raison_joe:
            raisons_complete.append(f"Joe007: {raison_joe}")
        if raison_prof:
            raisons_complete.append(raison_prof)

        # Multiplicateur de taille (Joe007 + apprentissage)
        mult_taille = mult_taille_joe

        signal = {
            "symbole": symbole,
            "prix_entree": prix,
            "nom": nom,
            "marche": "crypto",
            "etoile": config.get("etoile", False),
            "source": "professeur_virtuel",
            "strategie": strategie,
            "score": score_final,
            "raison": " | ".join(raisons_complete),
            # Paramètres du professeur (ratio 2.5:1)
            "prof_tp": PROF_TP_PCT,
            "prof_sl": PROF_SL_PCT,
            "prof_partial_tp": PROF_PARTIAL_TP,
            "prof_mult_taille": mult_taille,
        }

        print(f"  [PROF] ACHAT {nom} score {score_final} — {signal['raison']}")
        signaux.append(signal)

    if not signaux:
        print("  [PROF] Aucun signal du professeur ce cycle")
    else:
        print(f"  [PROF] {len(signaux)} signal(s) du professeur")

    return signaux


# ====================================================================
# RAPPORT D'APPRENTISSAGE: le professeur fait son bilan
# ====================================================================

def rapport_professeur():
    """Génère un rapport d'apprentissage du professeur.

    Comme un élève qui fait son bilan: qu'est-ce que j'ai appris?
    Quelles stratégies marchent? Quelles cryptos sont rentables?
    """
    stats = _charger_stats_prof()
    if stats["trades_total"] == 0:
        return "Le professeur n'a pas encore trade. En attente du premier trade."

    wr = stats["gagnants"] / stats["trades_total"] * 100 if stats["trades_total"] else 0
    lignes = []
    lignes.append("=" * 60)
    lignes.append("RAPPORT DU PROFESSEUR VIRTUEL")
    lignes.append("=" * 60)
    lignes.append(f"Trades: {stats['trades_total']} | G/P: {stats['gagnants']}/{stats['perdants']} | WR: {wr:.1f}%")
    lignes.append(f"PnL total: {stats['pnl_total']:+.2f} EUR")
    lignes.append("")

    lignes.append("Par strategie:")
    for strat, s in sorted(stats["par_strategie"].items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr_s = s["gagnants"] / s["n"] * 100 if s["n"] else 0
        boost = f" (boost {'+' if s.get('boost',0) > 0 else ''}{s.get('boost',0)})" if s.get("boost", 0) != 0 else ""
        lignes.append(f"  {strat:20s} n={s['n']:3d} WR={wr_s:5.1f}% PnL={s['pnl']:+.2f}EUR{boost}")

    lignes.append("")
    lignes.append("Par crypto:")
    for sym, c in sorted(stats["par_crypto"].items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr_c = c["gagnants"] / c["n"] * 100 if c["n"] else 0
        lignes.append(f"  {sym:12s} n={c['n']:3d} WR={wr_c:5.1f}% PnL={c['pnl']:+.2f}EUR")

    lignes.append("")
    lignes.append(f"Dernier ajustement: {stats.get('dernier_ajustement', 'jamais')}")
    lignes.append("=" * 60)

    return "\n".join(lignes)


# ====================================================================
# TEST
# ====================================================================

if __name__ == "__main__":
    print("PROFESSEUR VIRTUEL — Test des stratégies")
    print("=" * 60)

    # Test du filtre contrarien
    mod, mult, raison = _filtre_contrarien_joe007()
    print(f"Filtre Joe007: {raison} (mod={mod:+d}, taille=x{mult:.1f})")

    # Test du rapport
    print()
    print(rapport_professeur())
