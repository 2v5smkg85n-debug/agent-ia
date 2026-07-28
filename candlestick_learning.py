#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CANDLESTICK LEARNING MODULE - Detection de motifs de chandeliers japonais
+ apprentissage des performances par motif/actif.

Detecte les patterns classiques (marteau, engulfing, morning/evening star,
three white soldiers/black crows, piercing line, dark cloud cover, harami,
doji, spinning top) sur les dernieres bougies fournies par historique_ohlcv()
(indicateurs.py). Chaque trade cloture peut etre enregistre via
enregistrer_resultat() pour apprendre, motif par motif et actif par actif,
quels patterns predisent vraiment des trades gagnants.

Le score appris (score_motif) sert d'ajustement de confiance (-1.0 a +1.0)
qui peut etre ajoute au score technique de analyser_actif() (indicateurs.py).

Usage:
    python candlestick_learning.py                  # test detection en direct (BTCUSDT)
    python candlestick_learning.py --resume         # resume de l'apprentissage
    python candlestick_learning.py --test BTCUSDT   # detecte motifs sur un actif precis
"""
import os
import sys
import json
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Fichier d'apprentissage (chemin absolu /tmp comme demande, avec repli DOSSIER)
FICHIER_APPRENTISSAGE = os.path.join(DOSSIER, "pattern_learning.json")
FICHIER_APPRENTISSAGE_REPLI = os.path.join(DOSSIER, "pattern_learning.json")

# Import de historique_ohlcv / analyser_actif depuis indicateurs.py (meme dossier)
try:
    sys.path.insert(0, DOSSIER)
    from indicateurs import historique_ohlcv, analyser_actif, SYMBOLES_SUIVIS, NOMS
except Exception:
    # Repli minimal si indicateurs.py indisponible (ne doit jamais planter)
    historique_ohlcv = None
    analyser_actif = None
    SYMBOLES_SUIVIS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    NOMS = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana",
            "BNBUSDT": "BNB", "XRPUSDT": "XRP"}


# ============================================
# OUTILS BOUGIES (extraction OHLC)
# ============================================
def _ohlc(b):
    """Extrait (open, high, low, close) d'une bougie au format historique_ohlcv."""
    try:
        o = float(b.get("ouverture", 0) or 0)
        h = float(b.get("haut", 0) or 0)
        l = float(b.get("bas", 0) or 0)
        c = float(b.get("cloture", 0) or 0)
        return o, h, l, c
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _corps(o, c):
    """Taille du corps de la bougie (valeur absolue)."""
    return abs(c - o)


def _amplitude(o, h, l, c):
    """Amplitude totale de la bougie (high-low), jamais nulle."""
    return max(h - l, 1e-9)


def _meche_haute(o, h, l, c):
    return h - max(o, c)


def _meche_basse(o, h, l, c):
    return min(o, c) - l


def _est_verte(o, c):
    return c > o


def _est_rouge(o, c):
    return c < o


# ============================================
# 1. DETECTION DE MOTIFS (candlestick patterns)
# ============================================
def detecter_motif(bougies):
    """
    Analyse les 3-4 dernieres bougies et retourne la liste des motifs detectes.
    bougies: liste de dicts au format historique_ohlcv
             (cles: "ouverture", "haut", "bas", "cloture", "volume")

    Retourne une liste de dicts:
        {"pattern": "HAMMER", "direction": "bullish", "force": 0.7, "bougies": 1}
    """
    motifs = []
    try:
        if not bougies or len(bougies) < 2:
            return motifs

        # On prend jusqu'a 4 dernieres bougies pour couvrir les patterns 3-bougies
        recentes = bougies[-4:] if len(bougies) >= 4 else bougies[-3:] if len(bougies) >= 3 else bougies[-2:]

        # Bougie courante (derniere) + precedente + (avant-precedente si dispo)
        c2 = recentes[-1]
        c1 = recentes[-2]
        c0 = recentes[-3] if len(recentes) >= 3 else None

        o1, h1, l1, cl1 = _ohlc(c1)
        o2, h2, l2, cl2 = _ohlc(c2)
        corps1 = _corps(o1, cl1)
        corps2 = _corps(o2, cl2)
        ampl1 = _amplitude(o1, h1, l1, cl1)
        ampl2 = _amplitude(o2, h2, l2, cl2)
        meche_h2 = _meche_haute(o2, h2, l2, cl2)
        meche_b2 = _meche_basse(o2, h2, l2, cl2)

        # ---------- DOJI (neutre) ----------
        # Corps quasi nul (< 5% de l'amplitude) -> pure indecision open ~= close
        if corps2 < 0.05 * ampl2:
            motifs.append({"pattern": "DOJI", "direction": "neutral",
                            "force": 0.3, "bougies": 1})

        # ---------- SPINNING TOP ----------
        # Petit corps (5-30% de l'amplitude) avec meches significatives des 2 cotes
        elif corps2 < 0.30 * ampl2 and meche_h2 > 0.8 * corps2 and meche_b2 > 0.8 * corps2:
            motifs.append({"pattern": "SPINNING_TOP", "direction": "neutral",
                            "force": 0.3, "bougies": 1})

        # ---------- HAMMER (marteau) haussier ----------
        # Petit corps en haut, longue meche basse (>=2x corps), meche haute courte
        if corps2 > 0 and meche_b2 >= 2 * corps2 and meche_h2 <= 0.5 * corps2:
            motifs.append({"pattern": "HAMMER", "direction": "bullish",
                            "force": 0.7, "bougies": 1})

        # ---------- SHOOTING STAR baissier ----------
        # Petit corps en bas, longue meche haute (>=2x corps), meche basse courte
        if corps2 > 0 and meche_h2 >= 2 * corps2 and meche_b2 <= 0.5 * corps2:
            motifs.append({"pattern": "SHOOTING_STAR", "direction": "bearish",
                            "force": 0.7, "bougies": 1})

        # ---------- BULLISH ENGULFING ----------
        # Bougie 2 verte englobe le corps rouge de la bougie 1
        if _est_verte(o2, cl2) and _est_rouge(o1, cl1) and o2 <= cl1 and cl2 >= o1 and corps2 > corps1:
            motifs.append({"pattern": "BULLISH_ENGULFING", "direction": "bullish",
                            "force": 0.8, "bougies": 2})

        # ---------- BEARISH ENGULFING ----------
        # Bougie 2 rouge englobe le corps vert de la bougie 1
        if _est_rouge(o2, cl2) and _est_verte(o1, cl1) and o2 >= cl1 and cl2 <= o1 and corps2 > corps1:
            motifs.append({"pattern": "BEARISH_ENGULFING", "direction": "bearish",
                            "force": 0.8, "bougies": 2})

        # ---------- BULLISH HARAMI ----------
        # Petite bougie verte a l'interieur du grand corps rouge precedent
        if _est_rouge(o1, cl1) and _est_verte(o2, cl2) and corps1 > 0 and corps2 < corps1 \
                and o2 >= min(o1, cl1) and cl2 <= max(o1, cl1):
            motifs.append({"pattern": "BULLISH_HARAMI", "direction": "bullish",
                            "force": 0.5, "bougies": 2})

        # ---------- BEARISH HARAMI ----------
        # Petite bougie rouge a l'interieur du grand corps vert precedent
        if _est_verte(o1, cl1) and _est_rouge(o2, cl2) and corps1 > 0 and corps2 < corps1 \
                and o2 <= max(o1, cl1) and cl2 >= min(o1, cl1):
            motifs.append({"pattern": "BEARISH_HARAMI", "direction": "bearish",
                            "force": 0.5, "bougies": 2})

        # ---------- PIERCING LINE (haussier) ----------
        # Bougie rouge suivie d'une verte qui ouvre sous le bas precedent
        # et cloture au-dessus du milieu du corps rouge
        if _est_rouge(o1, cl1) and _est_verte(o2, cl2):
            milieu1 = (o1 + cl1) / 2
            if o2 < l1 and cl2 > milieu1 and cl2 < o1:
                motifs.append({"pattern": "PIERCING_LINE", "direction": "bullish",
                                "force": 0.65, "bougies": 2})

        # ---------- DARK CLOUD COVER (baissier) ----------
        # Bougie verte suivie d'une rouge qui ouvre au-dessus du haut precedent
        # et cloture sous le milieu du corps vert
        if _est_verte(o1, cl1) and _est_rouge(o2, cl2):
            milieu1 = (o1 + cl1) / 2
            if o2 > h1 and cl2 < milieu1 and cl2 > o1:
                motifs.append({"pattern": "DARK_CLOUD_COVER", "direction": "bearish",
                                "force": 0.65, "bougies": 2})

        # ---------- Patterns 3 bougies (necessitent c0) ----------
        if c0 is not None:
            o0, h0, l0, cl0 = _ohlc(c0)
            corps0 = _corps(o0, cl0)
            ampl0 = _amplitude(o0, h0, l0, cl0)

            # MORNING STAR: rouge -> petit corps (indecision/gap bas) -> verte forte
            if _est_rouge(o0, cl0) and corps1 < 0.35 * ampl1 and _est_verte(o2, cl2) \
                    and cl2 > (o0 + cl0) / 2:
                motifs.append({"pattern": "MORNING_STAR", "direction": "bullish",
                                "force": 0.85, "bougies": 3})

            # EVENING STAR: verte -> petit corps (indecision/gap haut) -> rouge forte
            if _est_verte(o0, cl0) and corps1 < 0.35 * ampl1 and _est_rouge(o2, cl2) \
                    and cl2 < (o0 + cl0) / 2:
                motifs.append({"pattern": "EVENING_STAR", "direction": "bearish",
                                "force": 0.85, "bougies": 3})

            # THREE WHITE SOLDIERS: 3 bougies vertes consecutives, clotures croissantes
            if _est_verte(o0, cl0) and _est_verte(o1, cl1) and _est_verte(o2, cl2) \
                    and cl1 > cl0 and cl2 > cl1 \
                    and o1 > o0 and o2 > o1:
                motifs.append({"pattern": "THREE_WHITE_SOLDIERS", "direction": "bullish",
                                "force": 0.9, "bougies": 3})

            # THREE BLACK CROWS: 3 bougies rouges consecutives, clotures decroissantes
            if _est_rouge(o0, cl0) and _est_rouge(o1, cl1) and _est_rouge(o2, cl2) \
                    and cl1 < cl0 and cl2 < cl1 \
                    and o1 < o0 and o2 < o1:
                motifs.append({"pattern": "THREE_BLACK_CROWS", "direction": "bearish",
                                "force": 0.9, "bougies": 3})

    except Exception:
        return motifs

    return motifs


# ============================================
# 2. SYSTEME D'APPRENTISSAGE
# ============================================
def _charger_apprentissage():
    """Charge le fichier d'apprentissage (repli sur DOSSIER si /tmp indisponible)."""
    for chemin in (FICHIER_APPRENTISSAGE, FICHIER_APPRENTISSAGE_REPLI):
        try:
            if os.path.exists(chemin):
                with open(chemin, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {}


def _sauver_apprentissage(data):
    """Sauve le fichier d'apprentissage. Essaie /tmp puis DOSSIER en repli."""
    for chemin in (FICHIER_APPRENTISSAGE, FICHIER_APPRENTISSAGE_REPLI):
        try:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            continue
    return False


def enregistrer_resultat(pattern_name, symbole, gain_pct, direction=None):
    """
    Enregistre le resultat d'un trade lie a un motif de bougie detecte.
    pattern_name: ex "HAMMER"
    symbole: ex "BTCUSDT"
    gain_pct: variation en % du trade (positif = gain, negatif = perte)
    direction: "bullish"/"bearish"/"neutral" (informatif, optionnel)

    Met a jour /tmp/pattern_learning.json avec total/wins/losses/avg_gain/win_rate.
    """
    try:
        if not pattern_name or not symbole:
            return False
        data = _charger_apprentissage()
        data.setdefault(symbole, {})
        stats = data[symbole].setdefault(pattern_name, {
            "total": 0, "wins": 0, "losses": 0, "avg_gain": 0.0, "win_rate": 0.0
        })

        gain_pct = float(gain_pct)
        ancien_total = stats["total"]
        ancien_moy = stats.get("avg_gain", 0.0)

        stats["total"] = ancien_total + 1
        if gain_pct > 0:
            stats["wins"] = stats.get("wins", 0) + 1
        else:
            stats["losses"] = stats.get("losses", 0) + 1

        # Moyenne mobile simple (recalcul exact de la moyenne cumulee)
        stats["avg_gain"] = (ancien_moy * ancien_total + gain_pct) / stats["total"]
        stats["win_rate"] = stats["wins"] / stats["total"] if stats["total"] > 0 else 0.0
        if direction:
            stats["direction"] = direction
        stats["derniere_maj"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        data[symbole][pattern_name] = stats
        _sauver_apprentissage(data)
        return True
    except Exception:
        return False


def score_motif(pattern_name, symbole):
    """
    Retourne un ajustement de confiance base sur l'historique (-1.0 a +1.0):
      - >5 trades et win_rate > 60% -> +0.5 a +1.0 (boost proportionnel)
      - >5 trades et win_rate < 40% -> -0.5 a -1.0 (penalite proportionnelle)
      - <5 trades ou motif inconnu -> 0.0 (pas assez de donnees, neutre)
    """
    try:
        data = _charger_apprentissage()
        stats = data.get(symbole, {}).get(pattern_name)
        if not stats:
            return 0.0
        total = stats.get("total", 0)
        win_rate = stats.get("win_rate", 0.0)
        if total <= 5:
            return 0.0
        if win_rate > 0.60:
            # Mappe win_rate 0.60->1.0 vers score 0.5->1.0
            proportion = min((win_rate - 0.60) / 0.40, 1.0)
            return round(0.5 + 0.5 * proportion, 3)
        if win_rate < 0.40:
            # Mappe win_rate 0.40->0.0 vers score -0.5->-1.0
            proportion = min((0.40 - win_rate) / 0.40, 1.0)
            return round(-0.5 - 0.5 * proportion, 3)
        return 0.0
    except Exception:
        return 0.0


# ============================================
# 3. INTEGRATION / HELPERS
# ============================================
def analyser_avec_apprentissage(symbole, intervalle="15m"):
    """
    Fonction principale: detecte les motifs de bougies sur un actif et
    applique le score appris a partir de l'historique des trades.

    Retourne:
        {"patterns": [...], "score_apprentissage": float,
         "direction": "bullish"/"bearish"/"neutral"}
    """
    resultat = {"patterns": [], "score_apprentissage": 0.0, "direction": "neutral"}
    try:
        if historique_ohlcv is None:
            return resultat
        bougies = historique_ohlcv(symbole, intervalle, 50)
        if not bougies or len(bougies) < 4:
            return resultat

        motifs = detecter_motif(bougies)
        if not motifs:
            return resultat

        total_score = 0.0
        bull = 0.0
        bear = 0.0
        for m in motifs:
            ajustement = score_motif(m["pattern"], symbole)
            m_avec_score = dict(m)
            m_avec_score["score_appris"] = ajustement
            resultat["patterns"].append(m_avec_score)
            total_score += ajustement
            if m["direction"] == "bullish":
                bull += m["force"]
            elif m["direction"] == "bearish":
                bear += m["force"]

        # Clamp le score total a [-1.5, +1.5]
        total_score = max(-1.5, min(1.5, total_score))
        resultat["score_apprentissage"] = round(total_score, 3)

        if bull > bear:
            resultat["direction"] = "bullish"
        elif bear > bull:
            resultat["direction"] = "bearish"
        else:
            resultat["direction"] = "neutral"

        return resultat
    except Exception:
        return resultat


def resume_apprentissage():
    """Retourne un texte-resume de l'apprentissage pour le digest."""
    try:
        data = _charger_apprentissage()
        if not data:
            return "🧠 Apprentissage bougies: aucune donnee encore."

        lignes = ["🧠 Apprentissage bougies:"]
        for symbole in sorted(data.keys()):
            motifs = data[symbole]
            if not motifs:
                continue
            parts = []
            # Trie par nombre de trades (les plus significatifs d'abord)
            for pattern_name, stats in sorted(motifs.items(), key=lambda kv: -kv[1].get("total", 0)):
                total = stats.get("total", 0)
                wins = stats.get("wins", 0)
                win_rate = stats.get("win_rate", 0.0)
                parts.append(f"{pattern_name} {win_rate*100:.0f}% ({wins}/{total})")
            if parts:
                lignes.append(f"  {symbole}: " + " | ".join(parts))
        if len(lignes) == 1:
            return "🧠 Apprentissage bougies: aucune donnee encore."
        return "\n".join(lignes)
    except Exception:
        return "🧠 Apprentissage bougies: erreur de lecture."


# ============================================
# CLI
# ============================================
def _test_detection_live(symbole="BTCUSDT", intervalle="15m"):
    """Teste la detection de motifs sur des donnees en direct."""
    try:
        print("=" * 60)
        print(f"DETECTION DE MOTIFS - {NOMS.get(symbole, symbole)} ({symbole})")
        print(f"Intervalle: {intervalle}")
        print("=" * 60)
        resultat = analyser_avec_apprentissage(symbole, intervalle)
        if not resultat["patterns"]:
            print("\nAucun motif detecte sur les dernieres bougies.")
            return
        print(f"\nDirection globale: {resultat['direction']}")
        print(f"Score d'apprentissage: {resultat['score_apprentissage']:+.3f}")
        print("\nMotifs detectes:")
        for m in resultat["patterns"]:
            print(f"  - {m['pattern']} ({m['direction']}, force {m['force']:.2f}, "
                  f"{m['bougies']} bougie(s)) -> score appris {m['score_appris']:+.3f}")
        print("=" * 60)
    except Exception as e:
        print(f"Erreur lors du test: {e}")


def main():
    """Point d'entree CLI."""
    try:
        args = sys.argv[1:]
        if not args:
            # Test par defaut: detection sur BTCUSDT en direct
            _test_detection_live("BTCUSDT", "15m")
        elif args[0] == "--resume":
            print(resume_apprentissage())
        elif args[0] == "--test":
            symbole = args[1].upper() if len(args) > 1 else "BTCUSDT"
            intervalle = args[2] if len(args) > 2 else "15m"
            _test_detection_live(symbole, intervalle)
        else:
            print(__doc__)
    except Exception as e:
        print(f"Erreur: {e}")


if __name__ == "__main__":
    main()
