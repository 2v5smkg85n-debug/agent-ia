#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GESTION POSITION LIVE - Analyse continue des positions ouvertes.

Au lieu de fixer TP/SL et attendre, le bot re-analyse chaque position ouverte
à chaque cycle et prend des décisions adaptatives:
- Momentum inversé → fermer ou serrer le SL
- RSI surachat → prendre profit partiel
- Volume qui s'effondre → fermer
- Support/resistance atteint → ajuster TP
- Multi-timeframe contradictoire → exit prudent
"""
import os
import sys
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)


def _get_indicateurs(symbole):
    """Récupère les indicateurs techniques actuels pour un symbole."""
    try:
        from indicateurs import historique_ohlcv, rsi, macd, moyennes_mobiles
        bougies = historique_ohlcv(symbole, "1h", 60)
        if not bougies or len(bougies) < 30:
            return None
        clotures = [b["cloture"] for b in bougies]
        hauts = [b["haut"] for b in bougies]
        bas = [b["bas"] for b in bougies]
        volumes = [b.get("volume", 0) for b in bougies]
        # RSI
        rsi_val = rsi(clotures, 14)
        # MACD
        macd_line, signal_line, histo = macd(clotures)
        # SMA
        sma20, sma50 = moyennes_mobiles(clotures, 20, 50)
        # Volume actuel vs moyen
        vol_actuel = volumes[-1] if volumes else 0
        vol_moyen = sum(volumes[-20:-1]) / 20 if len(volumes) >= 21 else 0
        # Support/Résistance
        support = min(bas[-20:]) if len(bas) >= 20 else min(bas)
        resistance = max(hauts[-20:]) if len(hauts) >= 20 else max(hauts)
        prix = clotures[-1]
        return {
            "prix": prix,
            "rsi": rsi_val,
            "macd_line": macd_line,
            "signal_line": signal_line,
            "macd_histo": histo,
            "sma20": sma20,
            "sma50": sma50,
            "vol_actuel": vol_actuel,
            "vol_moyen": vol_moyen,
            "support": support,
            "resistance": resistance,
            "bougies": bougies,
        }
    except Exception as e:
        return None


def analyser_position_live(position, prix_actuel):
    """Analyse une position ouverte en temps réel.
    Retourne une recommandation: ('HOLD', raison) | ('FERMER', raison) | ('TIGHTEN_SL', nouveau_sl_pct) | ('PARTIAL_TP', raison)
    """
    sym = position["symbole"]
    prix_entree = position.get("prix_entree", prix_actuel)
    variation = ((prix_actuel - prix_entree) / prix_entree) * 100 if prix_entree > 0 else 0

    indic = _get_indicateurs(sym)
    if not indic:
        return ("HOLD", "Indicateurs indisponibles")

    rsi_val = indic["rsi"]
    macd_histo = indic["macd_histo"]
    macd_line = indic["macd_line"]
    signal_line = indic["signal_line"]
    sma20 = indic["sma20"]
    sma50 = indic["sma50"]
    vol_actuel = indic["vol_actuel"]
    vol_moyen = indic["vol_moyen"]
    support = indic["support"]
    resistance = indic["resistance"]

    # Évaluations
    momentum_positif = macd_line is not None and signal_line is not None and macd_line > signal_line and macd_histo > 0
    momentum_negatif = macd_line is not None and signal_line is not None and macd_line < signal_line and macd_histo < 0
    rsi_surachat = rsi_val is not None and rsi_val > 72
    rsi_survente = rsi_val is not None and rsi_val < 35
    tendance_haussiere = sma20 is not None and sma50 is not None and sma20 > sma50
    tendance_baissiere = sma20 is not None and sma50 is not None and sma20 < sma50
    vol_faible = vol_moyen > 0 and vol_actuel < vol_moyen * 0.5
    proche_resistance = resistance and prix_actuel > 0 and abs(resistance - prix_actuel) / prix_actuel * 100 < 0.8
    proche_support = support and prix_actuel > 0 and abs(prix_actuel - support) / prix_actuel * 100 < 1.0

    # === LOGIQUE DE DÉCISION ADAPTATIVE ===

    # POSITION EN PROFIT
    if variation > 0:
        # Momentum inversé + profit → fermer (ne pas laisser le gain fondre)
        if momentum_negatif and variation >= 1.0:
            return ("FERMER", f"Momentum inversé (MACD<signal) en profit +{variation:.1f}% → encaisser")

        # RSI surachat + profit significatif → prendre profit partiel
        if rsi_surachat and variation >= 2.0 and not position.get("partiellement_clote"):
            return ("PARTIAL_TP", f"RSI surachat ({rsi_val:.0f}) + profit +{variation:.1f}% → encaisser 50%")

        # Proche résistance + profit → fermer (risque de rebond baissier)
        if proche_resistance and variation >= 1.5:
            return ("FERMER", f"Proche résistance ({resistance:.2f}) + profit +{variation:.1f}% → encaisser")

        # Volume qui s'effondre + profit → serrer le SL (le move perd de la force)
        if vol_faible and variation >= 1.5:
            return ("TIGHTEN_SL", f"Volume faible ({vol_actuel:.0f} vs {vol_moyen:.0f}) → SL serré à {max(variation - 0.5, 0.3):.1f}%")

        # Tendance toujours haussière + profit modéré → HOLD (laisser courir)
        if tendance_haussiere and momentum_positif and variation < 5.0:
            return ("HOLD", f"Tendance haussière confirmée (SMA20>SMA50) → laisser courir +{variation:.1f}%")

        # Profit important sans momentum → serrer le SL au breakeven
        if variation >= 3.0 and not momentum_positif:
            return ("TIGHTEN_SL", f"Profit +{variation:.1f}% sans momentum → SL au breakeven")

        return ("HOLD", f"Profit +{variation:.1f}%, conditions neutres")

    # POSITION EN PERTE
    else:
        # Momentum inversé + perte → fermer (ne pas attendre le SL)
        if momentum_negatif and variation <= -0.5:
            return ("FERMER", f"Momentum inversé (MACD<signal) en perte {variation:.1f}% → couper avant SL")

        # Tendance baissière + perte → fermer si proche du SL
        if tendance_baissiere and variation <= -0.5:
            return ("FERMER", f"Tendance baissière (SMA20<SMA50) en perte {variation:.1f}% → couper")

        # RSI survente + petite perte → HOLD (rebond probable)
        if rsi_survente and variation > -1.0:
            return ("HOLD", f"RSI survente ({rsi_val:.0f}) → attendre rebond ({variation:.1f}%)")

        # Proche support + petite perte → HOLD (le support devrait tenir)
        if proche_support and variation > -0.8:
            return ("HOLD", f"Proche support ({support:.2f}) → attendre rebond ({variation:.1f}%)")

        # Perte modérée + volume faible → HOLD (pas de panique, le move manque de force)
        if vol_faible and variation > -0.8:
            return ("HOLD", f"Volume faible + perte modérée {variation:.1f}% → attendre")

        return ("HOLD", f"Perte {variation:.1f}%, SL toujours valide")
