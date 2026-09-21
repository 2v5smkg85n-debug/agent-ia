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
PROF_TP_PCT = 1.5       # +1.5% (atteignable: LIVE-EXIT ferme deja a +1.5% parfois)
PROF_SL_PCT = 1.0       # -1.0% (300€ × 1% = 3.00€ perte max)
PROF_PARTIAL_TP = 999   # desactive (999 = jamais atteint) — laisse la position entiere courir vers TP

# Score minimum du professeur (plus exigeant que le score normal)
PROF_SCORE_MIN = 3

# ====================================================================
# STRATÉGIE 1: DOWNSHIFT RIDER (MACD momentum, 4h, PF 3.26)
# Inspiré de: anny.trade backtest — DOT short, MACD 4h, +230%
# Adapté pour long: détecte le momentum haussier MACD sur 4h
# ====================================================================

def _garde_btc(prix_actuels, marches_paper):
    """Garde BTC: si BTC baisse fortement, tout le marché suit.

    Vérifie:
    1. Variation BTC sur 1h (seuil -0.5%)
    2. Momentum BTC sur 5 min (seuil -0.3%) — corrige les chutes soudaines
    3. Dernière bougie 1h BTC baissière

    Returns: (ok, raison) — ok=False si BTC en chute
    """
    try:
        from indicateurs import historique_ohlcv
        # Check 1: variation 1h
        bougies_btc = historique_ohlcv('BTCUSDT', '1hour', 5)
        if bougies_btc and len(bougies_btc) >= 2:
            derniere = bougies_btc[-1]
            precedente = bougies_btc[-2]
            var_1h = ((derniere['cloture'] - precedente['cloture']) / precedente['cloture']) * 100
            if var_1h < -0.5:
                return False, f"BTC en chute (-{abs(var_1h):.2f}% en 1h) — marché risk-off"
            # Check 3: dernière bougie 1h baissière de plus de 0.3%
            var_bougie = ((derniere['cloture'] - derniere['ouverture']) / derniere['ouverture']) * 100
            if var_bougie < -0.3:
                return False, f"BTC bougie 1h baissière ({var_bougie:.2f}%) — momentum négatif"
        # Check 2: momentum 5 min (chute soudaine)
        bougies_5m = historique_ohlcv('BTCUSDT', '5min', 12)
        if bougies_5m and len(bougies_5m) >= 12:
            prix_5m_ago = bougies_5m[-12]['cloture']
            prix_now = bougies_5m[-1]['cloture']
            var_5m = ((prix_now - prix_5m_ago) / prix_5m_ago) * 100
            if var_5m < -0.3:
                return False, f"BTC en chute soudaine (-{abs(var_5m):.2f}% en 5 min) — risk-off immédiat"
        return True, ""
    except Exception:
        return True, ""


def _momentum_1h_porteur(bougies_1h):
    """Vérifie si la dernière bougie 1h est porteuse (pas un couteau qui tombe).

    Returns: True si la dernière bougie 1h est positive ou neutre.
    Filtre renforcé: exige que la bougie 1h ne soit pas baissière du tout.
    """
    if not bougies_1h or len(bougies_1h) < 2:
        return True  # si indispo, laisse passer
    derniere = bougies_1h[-1]
    var_bougie = ((derniere['cloture'] - derniere['ouverture']) / derniere['ouverture']) * 100
    # Filtre renforcé: bloque si la bougie 1h est baissière de plus de 0.2%
    if var_bougie < -0.2:
        return False  # bougie 1h rouge (> 0.2% baissière)
    return True

def _momentum_1h_positif(bougies_1h):
    """Vérifie si le momentum 1h est positif (au moins une des 2 dernières bougies verte).

    Filtre strict pour downshift_rider: exige un momentum positif récent.
    """
    if not bougies_1h or len(bougies_1h) < 3:
        return True
    # Au moins une des 2 dernières bougies doit être verte
    for i in range(-2, 0):
        b = bougies_1h[i]
        var = ((b['cloture'] - b['ouverture']) / b['ouverture']) * 100
        if var > 0.1:  # bougie verte significative
            return True
    return False

def _sl_consecutifs_crypto(symbole):
    """Compte le nombre de SL consécutifs récents pour une crypto.

    Returns: nombre de SL consécutifs (0 si pas de série).
    Si 3+ SL consécutifs, la crypto doit être bloquée temporairement.
    """
    try:
        paper_path = os.path.join(DOSSIER, "paper_trading.json")
        if not os.path.exists(paper_path):
            return 0
        with open(paper_path) as f:
            paper = json.load(f)
        trades = paper.get("trades_fermes", [])
        # Regarde les 10 derniers trades de cette crypto
        trades_crypto = [t for t in trades if t.get("symbole") == symbole][-10:]
        if not trades_crypto:
            return 0
        nb_sl = 0
        for t in reversed(trades_crypto):
            raison = t.get("raison", t.get("raison_fermeture", ""))
            if "SL" in raison or "URGENCE" in raison:
                nb_sl += 1
            else:
                break  # un trade gagnant ou autre raison casse la série
        return nb_sl
    except Exception:
        return 0

def _lire_bougies_pro(symbole, bougies_1h, bougies_4h):
    """Le professeur lit les bougies japonaises comme un pro.

    Détecte les patterns de bougies sur 1h et 4h et retourne:
    - score -99 = BLOQUER (pattern baissier fort détecté)
    - score négatif = pénalité (pattern baissier)
    - score 0 = neutre (pas de pattern)
    - score positif = bonus (pattern haussier)

    Returns: (score, raison)
    """
    try:
        from candlestick_learning import detecter_motif
    except ImportError:
        return 0, ""
    except Exception:
        return 0, ""

    patterns_detectes = []
    score_total = 0
    raisons = []

    # Analyse sur 1h (priorité — plus réactif)
    if bougies_1h and len(bougies_1h) >= 4:
        motifs_1h = detecter_motif(bougies_1h)
        for m in motifs_1h:
            patterns_detectes.append((m, "1h"))

    # Analyse sur 4h (confirmation — plus fiable)
    if bougies_4h and len(bougies_4h) >= 4:
        motifs_4h = detecter_motif(bougies_4h)
        for m in motifs_4h:
            patterns_detectes.append((m, "4h"))

    if not patterns_detectes:
        return 0, ""

    # Évalue chaque pattern
    bearish_forts = []  # patterns baissiers qui bloquent
    for m, tf in patterns_detectes:
        pattern = m.get("pattern", "")
        direction = m.get("direction", "")
        force = m.get("force", 0)

        if direction == "bullish":
            # Bonus haussier: +1 à +2 selon la force et le timeframe
            bonus = int(force * 2)  # force 0.5→+1, force 0.8→+1, force 0.9→+1
            if tf == "4h":
                bonus += 1  # bonus supplémentaire pour 4h (plus fiable)
            score_total += bonus
            raisons.append(f"{pattern} {tf} haussier (+{bonus})")

        elif direction == "bearish":
            # Pénalité baissière
            penalite = -int(force * 2)
            if tf == "4h":
                penalite -= 1  # plus grave sur 4h
            score_total += penalite
            raisons.append(f"{pattern} {tf} baissier ({penalite})")
            # Patterns baissiers forts qui bloquent l'entrée
            if pattern in ["BEARISH_ENGULFING", "EVENING_STAR", "THREE_BLACK_CROWS", "DARK_CLOUD_COVER"]:
                bearish_forts.append(f"{pattern} {tf}")
            # Shooting star sur 4h = blocage aussi
            if pattern == "SHOOTING_STAR" and tf == "4h":
                bearish_forts.append(f"{pattern} {tf}")

    # Si un pattern baissier fort est détecté, bloque l'entrée
    if bearish_forts:
        return -99, f"Pattern(s) baissier(s) fort: {', '.join(bearish_forts)}"

    if score_total != 0:
        return score_total, " | ".join(raisons)
    return 0, ""


def _pertes_consecutives_prof():
    """Vérifie les derniers trades pour une série de pertes.

    Returns: (nb_pertes_consecutives, penalty)
    - 3 pertes consécutives → penalty -1 (mode prudent leger)
    - 5+ pertes consécutives → penalty -2 (mode defensif)

    IMPORTANT: regarde seulement les 10 derniers trades, pas tout l'historique.
    Comme ca, apres quelques trades gagnants, le mode prudent se desactive.
    """
    try:
        paper_path = os.path.join(DOSSIER, "paper_trading.json")
        if not os.path.exists(paper_path):
            return 0, 0
        with open(paper_path) as f:
            paper = json.load(f)
        trades = paper.get("trades_fermes", [])
        if len(trades) < 5:
            return 0, 0
        recents = trades[-10:]
        nb_pertes = 0
        for t in reversed(recents):
            gain = t.get("gain_eur", 0)
            if gain <= 0:
                nb_pertes += 1
            else:
                break
        if nb_pertes >= 5:
            return nb_pertes, -2
        elif nb_pertes >= 3:
            return nb_pertes, -1
        return 0, 0
    except Exception:
        return 0, 0


def _tendance_haussiere(symbole, bougies_4h):
    """Filtre de tendance: verifie si la tendance 4h est haussiere.

    Les strategies backtestees (Exhaustion Snap, Peak Fader) etaient SHORT-biased.
    Adaptees en LONG, elles ont besoin d'un filtre de tendance pour eviter
    d'acheter des couteaux qui tombent.

    Regle: seulement acheter quand la tendance 4h est haussiere:
    - Prix au-dessus de l'EMA 50 (tendance long terme positive)
    - EMA 20 au-dessus de l'EMA 50 (confirmation momentum)

    Returns: True si tendance haussiere, False sinon
    """
    if not bougies_4h or len(bougies_4h) < 55:
        return True  # si pas assez de donnees, laisse passer

    clotures = [b["cloture"] for b in bougies_4h]
    try:
        from indicateurs import ema as _ema
    except Exception:
        return True

    prix = clotures[-1]

    # EMA 20 et EMA 50 sur 4h
    ema20_vals = []
    ema50_vals = []
    for i in range(len(clotures)):
        v20 = _ema(clotures[:i+1], 20)
        v50 = _ema(clotures[:i+1], 50)
        if v20 is not None:
            ema20_vals.append(v20)
        if v50 is not None:
            ema50_vals.append(v50)

    ema20 = ema20_vals[-1] if ema20_vals else None
    ema50 = ema50_vals[-1] if ema50_vals else None

    if ema20 is None or ema50 is None:
        return True  # si indispo, laisse passer

    # Tendance haussiere: prix > EMA20 > EMA50
    if prix > ema20 and ema20 > ema50:
        return True
    # Tendance legerement haussiere: prix > EMA50
    elif prix > ema50:
        return True
    else:
        return False


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
    - RSI était < 35 (survente élargie) dans les 8 dernières bougies
    - RSI actuel > 30 et < 55 (sortie de survente = retournement)
    - Le prix a fait un bas plus haut (confirmation)
    - Fenêtre élargie pour plus de signaux

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

    # RSI des 8 dernières bougies (élargi de 5 à 8)
    rsi_recent = []
    for i in range(-8, 0):
        idx = len(clotures) + i
        if idx >= 14:
            v = _rsi(clotures[:idx+1], 14)
            if v is not None:
                rsi_recent.append(v)

    score = 0
    raisons = []

    # 1. RSI sort de survente (était < 35, maintenant > 30) — seuil élargi
    rsi_etait_survente = any(r < 35 for r in rsi_recent)
    if rsi_etait_survente and 30 <= rsi_actuel < 45:
        score += 3
        raisons.append(f"RSI 1h sort de survente ({rsi_actuel:.1f}, etait < 35)")
    elif rsi_etait_survente and 45 <= rsi_actuel < 55:
        score += 2
        raisons.append(f"RSI 1h en retournement ({rsi_actuel:.1f}, sorti de survente)")
    elif rsi_etait_survente and 55 <= rsi_actuel < 65:
        score += 1
        raisons.append(f"RSI 1h en récupération ({rsi_actuel:.1f}, sorti de survente)")
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

    # 3. Bonus: RSI en accélération haussière
    if len(rsi_recent) >= 2 and rsi_recent[-1] > rsi_recent[-2]:
        score += 1
        raisons.append("RSI en accélération haussière")

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
        elif s["wr"] < 30:
            s["boost"] = -3  # penalite forte pour strategies tres perdantes
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

    # Blocage dur: crypto perdante en net (WR < 50% ET 15+ trades ET PnL < 0)
    if c.get("n", 0) >= 15 and c.get("wr", 100) < 50 and c.get("pnl", 0) < 0:
        boost = -10  # blocage total
        raison = f"Prof: {symbole} BLOQUE (WR={c['wr']}% n={c['n']} PnL={c['pnl']:+.2f}EUR)"

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

    # === GARDE BTC: si BTC chute, tout le marché suit ===
    btc_ok, raison_btc = _garde_btc(prix_actuels, marches_paper)
    if not btc_ok:
        print(f"  [PROF] {raison_btc} — AUCUN signal ce cycle")
        return []

    # === PERTES CONSÉCUTIVES: mode prudent/défensif ===
    nb_pertes, penalty_pertes = _pertes_consecutives_prof()
    if penalty_pertes < 0:
        print(f"  [PROF] Mode prudent: {nb_pertes} pertes récentes, penalty {penalty_pertes}")

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

        # === STRATÉGIE 1: Downshift Rider (MACD 4h) — FILTRE RENFORCÉ ===
        score_rider, raison_rider = 0, ""
        if bougies_4h:
            # Filtre 1: bougie 1h pas baissière
            if not _momentum_1h_porteur(bougies_1h):
                print(f"  [PROF] Downshift Rider sur {nom}: SKIP (bougie 1h baissière — anti couteau)")
            # Filtre 2: momentum 1h positif (au moins une bougie verte récente)
            elif not _momentum_1h_positif(bougies_1h):
                print(f"  [PROF] Downshift Rider sur {nom}: SKIP (momentum 1h négatif — pas de confirmation)")
            else:
                score_rider, raison_rider = _downshift_rider(symbole, bougies_4h)
                if score_rider > 0:
                    print(f"  [PROF] Downshift Rider sur {nom}: score {score_rider} — {raison_rider}")

        # === STRATÉGIE 2: Exhaustion Snap — DÉSACTIVÉE ===
        # Backtest: 653 trades, 46% WR, -550€ PnL — stratégie perdante
        score_snap, raison_snap = 0, ""

        # === STRATÉGIE 3: Peak Fader (RSI 1h) — 83% WR, +11€ ===
        score_fader, raison_fader = 0, ""
        if bougies_1h:
            # Filtre de tendance: ne pas acheter en tendance baissiere
            if _tendance_haussiere(symbole, bougies_4h or bougies_1h):
                score_fader, raison_fader = _peak_fader(symbole, bougies_1h)
                if score_fader > 0:
                    print(f"  [PROF] Peak Fader sur {nom}: score {score_fader} — {raison_fader}")
            else:
                print(f"  [PROF] Peak Fader sur {nom}: SKIP (tendance baissiere)")

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

        # === FILTRE SL CONSÉCUTIFS ===
        # Si une crypto a 2 SL consécutifs récents, la bloquer temporairement
        sl_consecutifs = _sl_consecutifs_crypto(symbole)
        if sl_consecutifs >= 2:
            print(f"  [PROF] {nom} BLOQUE ({sl_consecutifs} SL consécutifs — cooldown)")
            continue

        # === LECTURE BOUGIES PRO (candlestick patterns) ===
        # Le professeur lit les bougies comme un pro avant d'entrer
        score_bougies, raison_bougies = _lire_bougies_pro(symbole, bougies_1h, bougies_4h)
        if score_bougies == -99:
            print(f"  [PROF] {nom} BLOQUE par bougies pro: {raison_bougies}")
            continue
        if score_bougies != 0:
            print(f"  [PROF] Bougies pro sur {nom}: {raison_bougies} (score {score_bougies:+d})")

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

        # Score final du professeur (inclut le score bougies pro)
        score_final = best_score + score_catalyseur + mod_score_joe + boost_prof + penalty_pertes + score_bougies

        # Blocage dur: crypto perdante (boost -10 = blocage total)
        if score_final < 0:
            print(f"  [PROF] {nom} BLOQUE par apprentissage (score {score_final})")
            continue

        if score_final < PROF_SCORE_MIN:
            continue

        # Construit la raison complète
        raisons_complete = [f"PROF {strategie} (score {best_score})"]
        if raison_catalyseur:
            raisons_complete.append(f"Catalyseur +{score_catalyseur}")
        if raison_bougies:
            raisons_complete.append(f"Bougies: {raison_bougies}")
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
