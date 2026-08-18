#!/usr/bin/env python3
"""
Protection Anti-Flash-Crash — Circuit breaker + hedging automatique.

FONCTIONNEMENT:
  1. Surveille le prix du BTC en continu (reference du marche)
  2. Detecte les chutes brutales (>3% en 5 min = flash crash)
  3. Active le circuit breaker: arret des nouveaux trades
  4. Si crash severe (>5%): ferme les positions les plus risquees
  5. Si crash extreme (>8%): ferme toutes les positions
  6. Desactive le circuit breaker quand le marche se stabilise

Niveaux d'alerte:
  - Niveau 0: Normal
  - Niveau 1: Vigilance (chute 1.5-3% en 5 min)
  - Niveau 2: Circuit breaker (chute 3-5% en 5 min) -> stop nouveaux trades
  - Niveau 3: Hedging (chute 5-8% en 5 min) -> ferme positions risquees
  - Niveau 4: Emergency (chute >8% en 5 min) -> ferme tout
"""
import json
import os
import time
import urllib.request
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_TRADING = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_STATE = os.path.join(DOSSIER, "flash_crash_state.json")

# Seuils de detection (pourcentage de chute en 5 minutes)
SEUIL_VIGILANCE = 1.5    # Niveau 1
SEUIL_CIRCUIT = 3.0      # Niveau 2 - stop nouveaux trades
SEUIL_HEDGE = 5.0        # Niveau 3 - ferme positions risquees
SEUIL_EMERGENCY = 8.0    # Niveau 4 - ferme tout

# Duree du circuit breaker apres un crash (minutes)
DUREE_CIRCUIT_BREAKER = 30  # 30 min apres le dernier crash

# Intervalle de surveillance (secondes)
INTERVALLE_CHECK = 60  # 1 minute


def charger_state():
    """Charge l'etat du circuit breaker."""
    try:
        with open(FICHIER_STATE) as f:
            return json.load(f)
    except Exception:
        return {
            "niveau": 0,
            "dernier_check": 0,
            "dernier_crash": 0,
            "historique_prix": [],
            "crashes_detectes": [],
        }


def sauver_state(state):
    """Sauvegarde l'etat du circuit breaker."""
    try:
        with open(FICHIER_STATE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


def get_prix_btc():
    """Recupere le prix actuel du BTC."""
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return float(data["price"])
    except Exception:
        # Fallback: CoinGecko
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return float(data["bitcoin"]["usd"])
        except Exception as e:
            print("  [FLASH] Erreur prix BTC: " + str(e))
            return 0


def detecter_flash_crash():
    """
    Detecte un flash crash en comparant le prix actuel avec les prix des 5 dernieres minutes.
    
    Returns:
        {
            "niveau": int (0-4),
            "variation_pct": float,
            "prix_actuel": float,
            "prix_5min": float,
            "alerte": str,
            "action": str,
        }
    """
    state = charger_state()
    now = time.time()

    prix_actuel = get_prix_btc()
    if prix_actuel == 0:
        return {"niveau": 0, "variation_pct": 0, "prix_actuel": 0, "prix_5min": 0, "alerte": "Erreur API", "action": "Aucune"}

    # Mettre a jour l'historique des prix (timestamp, prix)
    state["historique_prix"].append({"ts": now, "prix": prix_actuel})

    # Garder seulement les 30 dernieres minutes (30 entrees si check toutes les 60s)
    state["historique_prix"] = state["historique_prix"][-30:]

    # Trouver le prix d'il y a 5 minutes
    prix_5min = None
    for entry in state["historique_prix"]:
        if now - entry["ts"] >= 300:  # 5 minutes = 300 secondes
            prix_5min = entry["prix"]
            break

    # Si pas assez d'historique, utiliser le 2eme prix le plus ancien
    if prix_5min is None and len(state["historique_prix"]) >= 2:
        prix_5min = state["historique_prix"][0]["prix"]

    if prix_5min is None or prix_5min == 0:
        state["niveau"] = 0
        state["dernier_check"] = now
        sauver_state(state)
        return {"niveau": 0, "variation_pct": 0, "prix_actuel": prix_actuel, "prix_5min": 0, "alerte": "Initialisation", "action": "Aucune"}

    # Calculer la variation en 5 minutes
    variation_pct = ((prix_actuel - prix_5min) / prix_5min) * 100

    # Determiner le niveau
    chute = -variation_pct  # positive si chute

    if chute >= SEUIL_EMERGENCY:
        niveau = 4
        alerte = "EMERGENCY - Flash crash >8% en 5min"
        action = "FERMER TOUTES LES POSITIONS"
    elif chute >= SEUIL_HEDGE:
        niveau = 3
        alerte = "CRITIQUE - Chute >5% en 5min"
        action = "Fermer positions risquees"
    elif chute >= SEUIL_CIRCUIT:
        niveau = 2
        alerte = "CIRCUIT BREAKER - Chute >3% en 5min"
        action = "Stop nouveaux trades"
    elif chute >= SEUIL_VIGILANCE:
        niveau = 1
        alerte = "VIGILANCE - Chute >1.5% en 5min"
        action = "Reduire taille positions"
    else:
        # Verifier si on etait en circuit breaker et si on peut le lever
        dernier_crash = state.get("dernier_crash", 0)
        if state.get("niveau", 0) >= 2 and (now - dernier_crash) > DUREE_CIRCUIT_BREAKER * 60:
            niveau = 0
            alerte = "RECOVERY - Marche stabilise"
            action = "Reprise normale"
        else:
            niveau = max(0, state.get("niveau", 0))
            if niveau > 0:
                alerte = "En attente de stabilisation"
                action = "Circuit breaker actif"
            else:
                alerte = "Normal"
                action = "Aucune"

    # Mettre a jour le state
    if niveau >= 2:
        state["dernier_crash"] = now
        state["crashes_detectes"].append({
            "date": datetime.now().isoformat(),
            "niveau": niveau,
            "variation_pct": round(variation_pct, 2),
            "prix": prix_actuel,
        })
        state["crashes_detectes"] = state["crashes_detectes"][-20:]  # Garder 20 derniers

    state["niveau"] = niveau
    state["dernier_check"] = now
    sauver_state(state)

    result = {
        "niveau": niveau,
        "variation_pct": round(variation_pct, 2),
        "prix_actuel": prix_actuel,
        "prix_5min": prix_5min,
        "alerte": alerte,
        "action": action,
    }

    if niveau >= 2:
        print("  [FLASH] " + alerte + " (" + str(round(variation_pct, 2)) + "%) - " + action)

    return result


def circuit_breaker_actif():
    """
    Retourne True si le circuit breaker est actif (niveau >= 2).
    A utiliser dans paper_trading pour bloquer les nouveaux trades.
    """
    state = charger_state()
    now = time.time()

    # Si le dernier crash etait recent, le circuit breaker est actif
    dernier_crash = state.get("dernier_crash", 0)
    niveau = state.get("niveau", 0)

    if niveau >= 2 and (now - dernier_crash) < DUREE_CIRCUIT_BREAKER * 60:
        return True

    return False


def get_niveau_protection():
    """
    Retourne le niveau de protection actuel (0-4).
    Utilise par paper_trading pour ajuster le comportement.
    """
    state = charger_state()
    now = time.time()
    dernier_crash = state.get("dernier_crash", 0)
    niveau = state.get("niveau", 0)

    # Le circuit breaker se leve apres DUREE_CIRCUIT_BREAKER minutes
    if niveau >= 2 and (now - dernier_crash) > DUREE_CIRCUIT_BREAKER * 60:
        return 0

    return niveau


def rapport_flash_crash():
    """Genere un rapport lisible pour Telegram."""
    r = detecter_flash_crash()

    rapport = "ANTI FLASH-CRASH\n"
    rapport += "================\n\n"

    emojis = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴", 4: "💥"}
    rapport += "Niveau: " + emojis.get(r["niveau"], "⚪") + " " + str(r["niveau"]) + "/4\n"
    rapport += "Alerte: " + r["alerte"] + "\n"
    rapport += "Action: " + r["action"] + "\n"
    rapport += "Variation 5min: " + str(r["variation_pct"]) + "%\n"
    rapport += "Prix BTC: " + str(r["prix_actuel"]) + "$\n"

    state = charger_state()
    crashes = state.get("crashes_detectes", [])
    if crashes:
        rapport += "\nDerniers crashes detectes:\n"
        for c in crashes[-3:]:
            rapport += "- " + c.get("date", "?")[:16] + " | " + str(c.get("variation_pct", 0)) + "% | Niveau " + str(c.get("niveau", 0)) + "\n"

    if circuit_breaker_actif():
        rapport += "\nCIRCUIT BREAKER ACTIF - Aucun nouveau trade autorise"

    return rapport


if __name__ == "__main__":
    print(rapport_flash_crash())
