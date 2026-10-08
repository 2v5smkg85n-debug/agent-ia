#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bougies_patterns.py — Lecture des chandeliers japonais (candlestick patterns).

Detecte les patterns classiques sur les dernieres bougies et retourne un biais
haussier/baissier + confiance. Inspire du guide de reference sur les bougies
japonaises (Marubozu, Marteau, Etoile filante, Pendu, Doji, Piercing Line,
Nuage sombre, Avalement, Chandelier Maitre, etc.).

biais: -1.0 (tres baissier) .. +1.0 (tres haussier)
confiance: 0.0 .. 1.0 (nombre/poids des patterns detectes)

CRITERES DE FIABILITE (valides contextuellement):
  1. Tendance dominante: le pattern prend du poids s'il apparait au bon endroit
     (marteau en fin de baisse = haussier, pendu en fin de hausse = baissier)
  2. Support/resistance: un pattern proche d'un niveau cle est plus fiable
  3. Volume: un volume eleve confirme l'engagement des participants
  4. Volatilite: une volatilite moderee donne des signaux plus robustes

MODE DETECTEUR + BACKTEST: on valide d'abord que le biais predit l'issue des
trades avant d'integrer (discipline = ADX/trailing/EXTEND).
"""
import os, sys


def _ohlc(b):
    """Extrait OHLC d'une bougie (FR ou EN).
    Gere tous les formats: haut/plus_haut/high, bas/plus_bas/low.
    """
    o = float(b.get("ouverture", b.get("open", 0)) or 0)
    h = float(b.get("haut", b.get("plus_haut", b.get("high", 0))) or 0)
    l = float(b.get("bas", b.get("plus_bas", b.get("low", 0))) or 0)
    c = float(b.get("cloture", b.get("close", 0)) or 0)
    return o, h, l, c


def _vol(b):
    """Extrait le volume d'une bougie (FR ou EN)."""
    return float(b.get("volume", 0) or 0)


def _body(o, c):
    return abs(c - o)


def _range(o, h, l, c):
    return max(h - l, 1e-9)


# ---- ANALYSE CONTEXTUELLE ----

def _tendance(bougies, n=15):
    """Identifie la tendance dominante sur les n dernieres bougies.
    Retourne: ('haussiere'|'baissiere'|'range', force 0..1)
    """
    if len(bougies) < 5:
        return "range", 0.0
    recentes = bougies[-n:] if len(bougies) >= n else bougies
    closes = [_ohlc(b)[3] for b in recentes]
    if len(closes) < 3:
        return "range", 0.0
    # Pente lineaire simplifiee: (fin - debut) / (debut * nb)
    debut = closes[0]
    fin = closes[-1]
    if debut <= 0:
        return "range", 0.0
    pente_pct = (fin - debut) / debut
    # Force basee sur la pente et la regularite
    hausses = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
    baisses = sum(1 for i in range(1, len(closes)) if closes[i] < closes[i-1])
    total = len(closes) - 1
    if total <= 0:
        return "range", 0.0
    if pente_pct > 0.01 and hausses > baisses:
        force = min(1.0, abs(pente_pct) * 100 + hausses / total * 0.3)
        return "haussiere", force
    if pente_pct < -0.01 and baisses > hausses:
        force = min(1.0, abs(pente_pct) * 100 + baisses / total * 0.3)
        return "baissiere", force
    return "range", 0.0


def _support_resistance(bougies, n=20):
    """Trouve le support et la resistance sur les n dernieres bougies."""
    if len(bougies) < 5:
        return 0.0, float('inf')
    recentes = bougies[-n:] if len(bougies) >= n else bougies
    bas = [_ohlc(b)[2] for b in recentes]
    hauts = [_ohlc(b)[1] for b in recentes]
    return min(bas), max(hauts)


def _proximite_niveau(prix, support, resistance):
    """Evalue si le prix actuel est proche d'un support ou resistance.
    Retourne: ('support'|'resistance'|'milieu', proximite 0..1)
    """
    if resistance <= support or prix <= 0:
        return "milieu", 0.0
    range_total = resistance - support
    pos = (prix - support) / range_total if range_total > 0 else 0.5
    if pos < 0.2:  # proche du support
        return "support", 1.0 - pos / 0.2
    if pos > 0.8:  # proche de la resistance
        return "resistance", (pos - 0.8) / 0.2
    return "milieu", 0.0


def _ratio_volume(bougies, n=10):
    """Compare le volume de la derniere bougie a la moyenne.
    Retourne: ratio (1.0 = normal, >1.5 = spike haussier, <0.5 = faible)
    """
    if len(bougies) < 3:
        return 1.0
    recentes = bougies[-n-1:] if len(bougies) >= n+1 else bougies
    vols = [_vol(b) for b in recentes[:-1]]  # moyenne sans la derniere
    vol_actuel = _vol(recentes[-1])
    if not vols or sum(vols) == 0:
        return 1.0
    vol_moyen = sum(vols) / len(vols)
    if vol_moyen <= 0:
        return 1.0
    return vol_actuel / vol_moyen


def _volatilite(bougies, n=14):
    """ATR simplifie: amplitude moyenne des n dernieres bougies.
    Retourne: volatilite_pct (0.01 = 1%)
    """
    if len(bougies) < 5:
        return 0.01
    recentes = bougies[-n:] if len(bougies) >= n else bougies
    amplitudes = []
    for b in recentes:
        o, h, l, c = _ohlc(b)
        ref = (o + c) / 2 if (o + c) > 0 else 1
        amplitudes.append((h - l) / ref)
    return sum(amplitudes) / len(amplitudes) if amplitudes else 0.01


# ---- DETECTION DES PATTERNS ----

def analyser_patterns(bougies, lookback=3, volumes=True):
    """Analyse les dernieres bougies. Retourne {biais, confiance, patterns, detail, contexte}.

    Args:
        bougies: liste de dicts avec ouverture/haut/bas/cloture/volume
        lookback: nombre de bougies recentes a analyser pour les patterns (min 5)
        volumes: si True, utilise les volumes pour la validation
    """
    if not bougies or len(bougies) < 3:
        return {"biais": 0.0, "confiance": 0.0, "patterns": [], "detail": []}

    # On a besoin d'au moins 5 bougies pour le contexte
    nb_contexte = min(len(bougies), 20)
    contexte_bougies = bougies[-nb_contexte:]

    o0, h0, l0, c0 = _ohlc(bougies[-3])  # avant-avant-derniere
    o1, h1, l1, c1 = _ohlc(bougies[-2])  # avant-derniere
    o2, h2, l2, c2 = _ohlc(bougies[-1])  # derniere
    b1 = _body(o1, c1)
    b2 = _body(o2, c2)
    r1 = _range(o1, h1, l1, c1)
    r2 = _range(o2, h2, l2, c2)
    meche_haute = h2 - max(o2, c2)
    meche_basse = min(o2, c2) - l2

    # --- ANALYSE CONTEXTUELLE ---
    tendance, force_tendance = _tendance(contexte_bougies, 15)
    support, resistance = _support_resistance(contexte_bougies, 20)
    niveau, proximite = _proximite_niveau(c2, support, resistance)
    vol_ratio = _ratio_volume(bougies, 10) if volumes else 1.0
    volat = _volatilite(bougies, 14)

    patterns = []
    detail = []
    score = 0.0  # + haussier, - baissier

    # Facteur de validation contextuelle (booste ou reduit le score)
    # Le reference dit: patterns valides par tendance + support/resistance + volume = plus fiable
    def _boost(base_score, pattern_nom, pattern_biais, contexte_attendu=None):
        """Ajuste le score selon le contexte.
        - pattern_biais: 'haussier' ou 'baissier'
        - contexte_attendu: 'fin_baisse', 'fin_hausse', 'continuation', None
        Retourne le score SIGNE (+ = haussier, - = baissier).
        """
        boost = 1.0
        raisons = []

        # 1. Validation par la tendance
        if pattern_biais == "haussier" and contexte_attendu == "fin_baisse":
            if tendance == "baissiere":
                boost *= 1.3
                raisons.append("fin de tendance baissiere (contexte ideal)")
            elif tendance == "haussiere":
                boost *= 0.5
                raisons.append("tendance haussiere (contexte defavorable)")
        elif pattern_biais == "baissier" and contexte_attendu == "fin_hausse":
            if tendance == "haussiere":
                boost *= 1.3
                raisons.append("fin de tendance haussiere (contexte ideal)")
            elif tendance == "baissiere":
                boost *= 0.5
                raisons.append("tendance baissiere (contexte defavorable)")

        # 2. Validation par support/resistance
        if pattern_biais == "haussier" and niveau == "support":
            boost *= 1.2
            raisons.append(f"proche support ({proximite:.0%})")
        if pattern_biais == "baissier" and niveau == "resistance":
            boost *= 1.2
            raisons.append(f"proche resistance ({proximite:.0%})")

        # 3. Validation par le volume
        if vol_ratio > 1.5:
            boost *= 1.15
            raisons.append(f"volume eleve ({vol_ratio:.1f}x)")
        elif vol_ratio < 0.5:
            boost *= 0.7
            raisons.append(f"volume faible ({vol_ratio:.1f}x)")

        score_final = base_score * boost
        # Applique le signe selon le biais
        if pattern_biais == "baissier":
            score_final = -abs(score_final)
        else:
            score_final = abs(score_final)
        if raisons:
            detail.append((pattern_nom, score_final, "; ".join(raisons)))
        else:
            detail.append((pattern_nom, score_final, ""))
        return score_final

    # ==== PATTERNS A UNE BOUGIE ====

    # 1) Marubozu haussier (corps remplit 85%+ de l'amplitude, verte)
    # Reference: "forte resistance a la vente ou soutien a l'achat"
    if r2 > 0 and b2 > 0.85 * r2 and c2 > o2:
        s = _boost(0.25, "marubozu_haussier", "haussier", "continuation")
        patterns.append("marubozu_haussier")
        score += s

    # 2) Marubozu baissier
    if r2 > 0 and b2 > 0.85 * r2 and c2 < o2:
        s = _boost(0.25, "marubozu_baissier", "baissier", "continuation")
        patterns.append("marubozu_baissier")
        score += s

    # 3) Marteau (hammer) - petit corps haut, longue meche basse (>2x corps)
    # Reference: "en fin de tendance baissiere, suggere un renversement haussier"
    if b2 > 0 and meche_basse > 2 * b2 and meche_haute < b2 and c2 >= o2:
        s = _boost(0.3, "marteau_haussier", "haussier", "fin_baisse")
        patterns.append("marteau_haussier")
        score += s

    # 4) Pendu (hanging man) - meme forme que marteau MAIS apres une hausse = baissier
    # Reference: "au sommet d'une tendance haussiere, la demande s'essouffle"
    if b2 > 0 and meche_basse > 2 * b2 and meche_haute < b2 and c2 > o2:
        if tendance == "haussiere":
            s = _boost(0.3, "pendu_baissier", "baissier", "fin_hausse")
            if "pendu_baissier" not in patterns:
                patterns.append("pendu_baissier")
            score += s

    # 5) Etoile filante (shooting star) - petit corps bas, longue meche haute (>2x corps)
    # Reference: "au sein d'une tendance haussiere, suggere un renversement baissier"
    if b2 > 0 and meche_haute > 2 * b2 and meche_basse < b2 * 0.5 and c2 <= o2:
        s = _boost(0.3, "etoile_filante", "baissier", "fin_hausse")
        patterns.append("etoile_filante")
        score += s

    # 6) Marteau inverse (inverted hammer) - meme forme que l'etoile filante MAIS apres baisse = haussier
    if b2 > 0 and meche_haute > 2 * b2 and meche_basse < b2 * 0.5 and c2 > o2:
        if tendance == "baissiere":
            s = _boost(0.25, "marteau_inverse_haussier", "haussier", "fin_baisse")
            patterns.append("marteau_inverse_haussier")
            score += s

    # 7) Doji - corps < 10% de l'amplitude = indecision
    # Reference: "indetermine, possible indicateur d'un renversement a venir"
    if r2 > 0 and b2 < 0.1 * r2:
        patterns.append("doji")
        detail.append(("doji", 0.0, "indcision (attente confirmation)"))
        # Neutre mais le contexte peut donner une indication
        if tendance == "haussiere" and niveau == "resistance":
            score -= 0.1  # leger baissier: doji en haut = essoufflement
        elif tendance == "baissiere" and niveau == "support":
            score += 0.1  # leger haussier: doji en bas = stabilisation

    # 8) Toupie (spinning top) - petit corps, meches des deux cotes
    if r2 > 0 and 0.1 < b2 / r2 < 0.3 and meche_haute > r2 * 0.3 and meche_basse > r2 * 0.3:
        patterns.append("toupie")
        detail.append(("toupie", 0.0, "indcision"))

    # ==== PATTERNS A DEUX BOUGIES ====

    # 9) Engulfing haussier: verte englobe la rouge precedente
    # Reference: "en fin de tendance baissiere, suggere un retournement"
    if c2 > o2 and c1 < o1 and o2 <= c1 and c2 >= o1 and b2 > b1:
        s = _boost(0.5, "engulfing_haussier", "haussier", "fin_baisse")
        patterns.append("engulfing_haussier")
        score += s

    # 10) Engulfing baissier: rouge englobe la verte
    # Reference: "en fin de tendance haussiere, annonce une pression vendeuse accrue"
    if c2 < o2 and c1 > o1 and o2 >= c1 and c2 <= o1 and b2 > b1:
        s = _boost(0.5, "engulfing_baissier", "baissier", "fin_hausse")
        patterns.append("engulfing_baissier")
        score += s

    # 11) Piercing Line (Ligne de percee) - rouge puis verte qui perce le milieu
    # Reference: "figure de renversement haussier, surtout pres d'un support cle"
    if (c1 < o1 and c2 > o2 and o2 < c1 and
        c2 > (o1 + c1) / 2):
        s = _boost(0.4, "piercing_line", "haussier", "fin_baisse")
        patterns.append("piercing_line")
        score += s

    # 12) Nuage sombre (Dark Cloud Cover) - verte puis rouge qui descend sous le milieu
    # Reference: "traduit l'essoufflement des acheteurs, surtout sur une resistance"
    if (c1 > o1 and c2 < o2 and o2 > c1 and
        c2 < (o1 + c1) / 2):
        s = _boost(0.4, "nuage_sombre", "baissier", "fin_hausse")
        patterns.append("nuage_sombre")
        score += s

    # 13) Harami haussier - grande rouge puis petite verte contenue
    if (c1 < o1 and c2 > o2 and c2 < o1 and o2 > c1):
        s = _boost(0.2, "harami_haussier", "haussier", "fin_baisse")
        patterns.append("harami_haussier")
        score += s

    # 14) Harami baissier - grande verte puis petite rouge contenue
    if (c1 > o1 and c2 < o2 and o2 < c1 and c2 > o1):
        s = _boost(0.2, "harami_baissier", "baissier", "fin_hausse")
        patterns.append("harami_baissier")
        score += s

    # 15) Tweezer bottom - deux bougies meme bas = support fort
    if (len(bougies) >= 2 and abs(l1 - l2) / max(l1, 0.001) < 0.002 and
        c1 < o1 and c2 > o2):
        s = _boost(0.2, "tweezer_bottom", "haussier", "fin_baisse")
        patterns.append("tweezer_bottom")
        score += s

    # 16) Tweezer top - deux bougies meme haut = resistance forte
    if (len(bougies) >= 2 and abs(h1 - h2) / max(h1, 0.001) < 0.002 and
        c1 > o1 and c2 < o2):
        s = _boost(0.2, "tweezer_top", "baissier", "fin_hausse")
        patterns.append("tweezer_top")
        score += s

    # ==== PATTERNS A TROIS BOUGIES ET PLUS ====

    # 17) Morning star (3 bougies: rouge, petite, verte qui remonte)
    # Reference: "retournement haussier potentiel"
    if (c0 < o0 and c1 < o1 and b1 < 0.3 * r1 and
        c2 > o2 and c2 > (o1 + c1) / 2):
        s = _boost(0.45, "morning_star", "haussier", "fin_baisse")
        patterns.append("morning_star")
        score += s

    # 18) Evening star (3 bougies: verte, petite, rouge qui descend)
    if (c0 > o0 and c1 > o1 and b1 < 0.3 * r1 and
        c2 < o2 and c2 < (o1 + c1) / 2):
        s = _boost(0.45, "evening_star", "baissier", "fin_hausse")
        patterns.append("evening_star")
        score += s

    # 19) Trois soldats blancs - 3 bougies vertes consecutives qui montent
    # Reference: continuation haussiere forte
    if (len(bougies) >= 3 and c0 > o0 and c1 > o1 and c2 > o2 and
        c1 > c0 and c2 > c1):
        s = _boost(0.35, "trois_soldats_blancs", "haussier", "continuation")
        patterns.append("trois_soldats_blancs")
        score += s

    # 20) Trois corbeaux noirs - 3 bougies rouges consecutives qui descendent
    if (len(bougies) >= 3 and c0 < o0 and c1 < o1 and c2 < o2 and
        c1 < c0 and c2 < c1):
        s = _boost(0.35, "trois_corbeaux_noirs", "baissier", "continuation")
        patterns.append("trois_corbeaux_noirs")
        score += s

    # 21) Chandelier Maitre (Master Candle) - grande bougie qui englobe les 4 suivantes
    # Reference: "cree une zone de consolidation dont la sortie offre une opportunite de breakout"
    # Pattern: maitre (index -6 ou -5) + 4 bougies contenues + eventuel breakout
    if len(bougies) >= 6:
        maitre = bougies[-6]
        m_o, m_h, m_l, m_c = _ohlc(maitre)
        m_corps = _body(m_o, m_c)
        # La maitre doit etre une grande bougie: on compare son corps a celui des 4 contenues
        corps_contenues = []
        for i in range(1, 5):
            _o, _h, _l, _c = _ohlc(bougies[-6 + i])
            corps_contenues.append(_body(_o, _c))
        moy_contenues = sum(corps_contenues) / len(corps_contenues) if corps_contenues else 0
        # La maitre doit etre au moins 1.5x plus grande que la moyenne des contenues
        if moy_contenues > 0 and m_corps > moy_contenues * 1.5:
            # Les 4 suivantes (indices -5 a -2) restent dans le range de la maitre
            dans_range = True
            for i in range(1, 5):
                _o, _h, _l, _c = _ohlc(bougies[-6 + i])
                if _h > m_h or _l < m_l:
                    dans_range = False
                    break
            if dans_range:
                # La derniere bougie (index -1) casse-t-elle le range?
                o_last, h_last, l_last, c_last = _ohlc(bougies[-1])
                if c_last > m_h:  # breakout haussier
                    s = _boost(0.4, "chandelier_maitre_breakout_haussier", "haussier", "continuation")
                    patterns.append("chandelier_maitre_breakout_haussier")
                    score += s
                elif c_last < m_l:  # breakout baissier
                    s = _boost(0.4, "chandelier_maitre_breakout_baissier", "baissier", "continuation")
                    patterns.append("chandelier_maitre_breakout_baissier")
                    score += s
    elif len(bougies) >= 5:
        # Pas assez pour un breakout mais on peut detecter une consolidation
        maitre = bougies[-5]
        m_o, m_h, m_l, m_c = _ohlc(maitre)
        m_corps = _body(m_o, m_c)
        dans_range = True
        for i in range(1, 5):
            _o, _h, _l, _c = _ohlc(bougies[-5 + i])
            if _h > m_h or _l < m_l:
                dans_range = False
                break
        if dans_range and m_corps > 0:
            patterns.append("chandelier_maitre_consolidation")
            detail.append(("chandelier_maitre_consolidation", 0.0,
                           "consolidation dans le range, surveiller la sortie"))

    # 22) Matin doji star - rouge, doji, verte = reversal haussier fort
    if len(bougies) >= 3:
        amp1_mds = _range(o1, h1, l1, c1)
        corps1_mds = b1
        if (c0 < o0 and amp1_mds > 0 and corps1_mds < 0.1 * amp1_mds and
            c2 > o2 and c2 > (o1 + c1) / 2):
            s = _boost(0.5, "matin_doji_star", "haussier", "fin_baisse")
            patterns.append("matin_doji_star")
            score += s

    # 23) Soir doji star - verte, doji, rouge = reversal baissier fort
    if len(bougies) >= 3:
        amp1_sds = _range(o1, h1, l1, c1)
        corps1_sds = b1
        if (c0 > o0 and amp1_sds > 0 and corps1_sds < 0.1 * amp1_sds and
            c2 < o2 and c2 < (o1 + c1) / 2):
            s = _boost(0.5, "soir_doji_star", "baissier", "fin_hausse")
            patterns.append("soir_doji_star")
            score += s

    # ==== RESULTAT ====
    biais = max(-1.0, min(1.0, score))
    confiance = min(1.0, abs(score) / 1.5)  # seuil ajuste pour plus de patterns

    return {
        "biais": round(biais, 2),
        "confiance": round(confiance, 2),
        "patterns": patterns,
        "detail": detail,
        "contexte": {
            "tendance": tendance,
            "force_tendance": round(force_tendance, 2),
            "niveau": niveau,
            "proximite_niveau": round(proximite, 2),
            "ratio_volume": round(vol_ratio, 2),
            "volatilite": round(volat, 4),
        },
    }


def biais_bougies(bougies, lookback=3):
    """Raccourci: retourne juste le biais (-1..+1)."""
    return analyser_patterns(bougies, lookback).get("biais", 0.0)


# ---- TEST standalone ----
if __name__ == "__main__":
    try:
        from indicateurs import historique_ohlcv
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "GC=F"]:
            bougies = historique_ohlcv(sym, "1h", 50)
            if bougies:
                r = analyser_patterns(bougies)
                ctx = r.get("contexte", {})
                print(f"\n{sym}: biais={r['biais']:+.2f} conf={r['confiance']:.2f}")
                print(f"  patterns={r['patterns'] or '-'}")
                print(f"  tendance={ctx.get('tendance','?')} force={ctx.get('force_tendance',0):.2f}")
                print(f"  niveau={ctx.get('niveau','?')} vol_ratio={ctx.get('ratio_volume',0):.1f}x")
                print(f"  volatilite={ctx.get('volatilite',0):.4f}")
                for d in r.get("detail", []):
                    if len(d) >= 3:
                        print(f"    {d[0]}: score={d[1]:+.3f} {d[2]}")
            else:
                print(f"{sym}: pas de donnees")
    except Exception as e:
        print(f"erreur demo: {e}")
