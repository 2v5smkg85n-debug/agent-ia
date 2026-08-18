#!/usr/bin/env python3
"""
Optimisation Kelly — Taille de position mathematiquement optimale.

Formule de Kelly: f* = (p * b - q) / b
  p = probabilite de gain (win rate)
  b = ratio gain moyen / perte moyenne
  q = 1 - p (probabilite de perte)

On utilise le Kelly fractionnel (1/4 Kelly) pour plus de securite:
  - Kelly plein = trop volatile
  - 1/2 Kelly = bon equilibre
  - 1/4 Kelly = conservateur (recommande)

Le module analyse les trades passes pour calculer le Kelly optimal
et ajuste la taille des positions en consequence.
"""
import json
import os
from datetime import datetime, timedelta


DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_TRADING = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_KELLY = os.path.join(DOSSIER, "kelly_state.json")

# Parametres
KELLY_FRACTION = 0.25  # 1/4 Kelly pour la securite
RISK_BASE = 0.025  # 2.5% du capital par trade (defaut)
RISK_MIN = 0.01  # 1% minimum (Kelly tres bas)
RISK_MAX = 0.05  # 5% maximum (Kelly tres haut)
MIN_TRADES = 10  # Minimum de trades pour calculer le Kelly


def charger_trades():
    """Charge les trades fermes depuis paper_trading.json."""
    try:
        with open(FICHIER_TRADING) as f:
            data = json.load(f)
        return data.get("trades_fermes", [])
    except Exception:
        return []


def charger_kelly_state():
    """Charge l'etat Kelly sauvegarde."""
    try:
        with open(FICHIER_KELLY) as f:
            return json.load(f)
    except Exception:
        return {}


def sauver_kelly_state(state):
    """Sauvegarde l'etat Kelly."""
    try:
        with open(FICHIER_KELLY, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


def calculer_stats_trades(trades):
    """
    Calcule les statistiques des trades.
    Retourne: (win_rate, gain_moyen, perte_moyenne, ratio, nb_trades)
    """
    if not trades or len(trades) < MIN_TRADES:
        return 0.5, 0, 0, 1, 0

    # Filtrer les trades des 30 derniers jours pour la pertinence
    try:
        date_limite = datetime.now() - timedelta(days=30)
        trades_recents = []
        for t in trades:
            try:
                date_str = t.get("date_fermeture", t.get("date_ouverture", ""))
                if date_str:
                    date_t = datetime.fromisoformat(date_str.replace("Z", ""))
                    if date_t > date_limite:
                        trades_recents.append(t)
            except Exception:
                trades_recents.append(t)

        if len(trades_recents) >= MIN_TRADES:
            trades = trades_recents
    except Exception:
        pass

    gains = []
    pertes = []

    for t in trades:
        gain = t.get("gain_eur", 0)
        if gain is None:
            gain = 0
        try:
            gain = float(gain)
        except (ValueError, TypeError):
            gain = 0

        if gain > 0:
            gains.append(gain)
        elif gain < 0:
            pertes.append(abs(gain))

    nb_trades = len(trades)
    nb_gains = len(gains)
    win_rate = nb_gains / nb_trades if nb_trades > 0 else 0.5

    gain_moyen = sum(gains) / len(gains) if gains else 0
    perte_moyenne = sum(pertes) / len(pertes) if pertes else 0

    # Ratio gain/perte (b)
    if perte_moyenne > 0:
        ratio = gain_moyen / perte_moyenne
    else:
        ratio = 1.5  # Valeur par defaut si pas de pertes

    return win_rate, gain_moyen, perte_moyenne, ratio, nb_trades


def calculer_kelly():
    """
    Calcule le critere de Kelly optimal.
    
    Returns:
        {
            "win_rate": float,
            "gain_moyen": float,
            "perte_moyenne": float,
            "ratio": float,
            "nb_trades": int,
            "kelly_plein": float,  # 0 a 1
            "kelly_fractionnel": float,  # 0 a 1 (avec fraction de securite)
            "risk_recommande": float,  # % du capital par trade
            "verdict": str,
        }
    """
    trades = charger_trades()
    win_rate, gain_moyen, perte_moyenne, ratio, nb_trades = calculer_stats_trades(trades)

    if nb_trades < MIN_TRADES:
        return {
            "win_rate": 0.5,
            "gain_moyen": 0,
            "perte_moyen": 0,
            "ratio": 1.0,
            "nb_trades": nb_trades,
            "kelly_plein": 0.0,
            "kelly_fractionnel": 0.0,
            "risk_recommande": RISK_BASE,
            "verdict": "Pas assez de trades (" + str(nb_trades) + "/" + str(MIN_TRADES) + ") - risk defaut " + str(RISK_BASE * 100) + "%",
        }

    # Formule de Kelly: f* = (p * b - q) / b
    p = win_rate
    q = 1 - p
    b = ratio

    kelly_plein = (p * b - q) / b

    # Kelly ne peut pas etre negatif (si negatif = ne pas trader)
    kelly_plein = max(0, kelly_plein)

    # Kelly fractionnel pour la securite
    kelly_frac = kelly_plein * KELLY_FRACTION

    # Convertir en % du capital
    risk_recommande = max(RISK_MIN, min(RISK_MAX, kelly_frac))

    # Verdict
    if kelly_plein > 0.5:
        verdict = "EXCELLENT - Edge fort, augmenter la taille"
    elif kelly_plein > 0.2:
        verdict = "BON - Edge positif, taille optimale"
    elif kelly_plein > 0:
        verdict = "FAIBLE - Edge leger, rester prudent"
    else:
        verdict = "NEGATIF - Pas d'edge, reduire ou arreter"

    result = {
        "win_rate": round(win_rate, 3),
        "gain_moyen": round(gain_moyen, 2),
        "perte_moyenne": round(perte_moyenne, 2),
        "ratio": round(ratio, 2),
        "nb_trades": nb_trades,
        "kelly_plein": round(kelly_plein, 3),
        "kelly_fractionnel": round(kelly_frac, 3),
        "risk_recommande": round(risk_recommande, 4),
        "verdict": verdict,
    }

    # Sauvegarder
    state = charger_kelly_state()
    state["dernier_calcul"] = {
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }
    sauver_kelly_state(state)

    return result


def get_risk_optimal():
    """
    Retourne le % de risk optimal par trade (pour integration dans paper_trading).
    Si pas assez de donnees, retourne le risk par defaut.
    """
    kelly = calculer_kelly()
    return kelly.get("risk_recommande", RISK_BASE)


def ajuster_taille_position(montant_base, capital_disponible, kelly_result=None):
    """
    Ajuste la taille d'une position basee sur le Kelly.
    
    Args:
        montant_base: montant prevu par defaut (ex: 80 EUR)
        capital_disponible: capital liquide disponible
        kelly_result: resultat de calculer_kelly() (optionnel, recalcule si None)
    
    Returns:
        montant ajuste (float)
    """
    if kelly_result is None:
        kelly_result = calculer_kelly()

    risk = kelly_result.get("risk_recommande", RISK_BASE)

    # Montant = capital * risk * levier_du_signal
    montant_kelly = capital_disponible * risk

    # Ne pas depasser 2x le montant de base (limite de securite)
    montant_max = montant_base * 2

    # Ne pas descendre sous 40 EUR
    montant_min = 40

    montant_final = max(montant_min, min(montant_max, montant_kelly))

    # Si le Kelly est negatif, garder le montant minimum
    if kelly_result.get("kelly_plein", 0) <= 0:
        montant_final = montant_min

    return montant_final


def rapport_kelly():
    """Genere un rapport lisible pour Telegram."""
    k = calculer_kelly()

    rapport = "KELLY CRITERION\n"
    rapport += "===============\n\n"

    rapport += "Statistiques trades (30 derniers jours):\n"
    rapport += "  Win rate: " + str(k["win_rate"] * 100) + "%\n"
    rapport += "  Gain moyen: +" + str(k["gain_moyen"]) + " EUR\n"
    rapport += "  Perte moyenne: -" + str(k["perte_moyenne"]) + " EUR\n"
    rapport += "  Ratio gain/perte: " + str(k["ratio"]) + "\n"
    rapport += "  Trades analyses: " + str(k["nb_trades"]) + "\n\n"

    rapport += "Kelly:\n"
    rapport += "  Kelly plein: " + str(k["kelly_plein"] * 100) + "%\n"
    rapport += "  Kelly fractionnel (1/4): " + str(k["kelly_fractionnel"] * 100) + "%\n"
    rapport += "  Risk recommande: " + str(k["risk_recommande"] * 100) + "%\n\n"

    rapport += "Verdict: " + k["verdict"]

    return rapport


if __name__ == "__main__":
    print(rapport_kelly())
