"""Stockage d'historique de prix depuis le batch CoinGecko.
Construit l'historique 1h/4h/1d progressivement, sans appels API supplementaires."""
import os, json, time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "historique_prix.json")

def stocker_prix(prix_actuels):
    """Stocke les prix actuels dans l'historique. A appeler chaque cycle.
    prix_actuels: dict {symbole: prix_eur}"""
    try:
        hist = {}
        if os.path.exists(FICHIER):
            with open(FICHIER) as f:
                hist = json.load(f)
        now = int(time.time())
        for sym, prix in prix_actuels.items():
            if not prix or prix <= 0:
                continue
            if sym not in hist:
                hist[sym] = {"1h": [], "4h": [], "1d": []}
            # 1h: stocke si >= 3600s depuis derniere entree
            if hist[sym]["1h"]:
                last_ts = hist[sym]["1h"][-1]["ts"]
                if now - last_ts >= 3600:
                    hist[sym]["1h"].append({"ts": now, "prix": prix})
            else:
                hist[sym]["1h"].append({"ts": now, "prix": prix})
            hist[sym]["1h"] = hist[sym]["1h"][-50:]  # garde 50 max
            # 4h: stocke si >= 14400s depuis derniere entree
            if hist[sym]["4h"]:
                last_ts = hist[sym]["4h"][-1]["ts"]
                if now - last_ts >= 14400:
                    hist[sym]["4h"].append({"ts": now, "prix": prix})
            else:
                hist[sym]["4h"].append({"ts": now, "prix": prix})
            hist[sym]["4h"] = hist[sym]["4h"][-50:]
            # 1d: stocke si >= 86400s depuis derniere entree
            if hist[sym]["1d"]:
                last_ts = hist[sym]["1d"][-1]["ts"]
                if now - last_ts >= 86400:
                    hist[sym]["1d"].append({"ts": now, "prix": prix})
            else:
                hist[sym]["1d"].append({"ts": now, "prix": prix})
            hist[sym]["1d"] = hist[sym]["1d"][-50:]
        with open(FICHIER, "w") as f:
            json.dump(hist, f)
    except Exception:
        pass

def get_historique(symbole, timeframe="1h"):
    """Retourne la liste des prix stockes pour un symbole/timeframe.
    Retourne [] si pas assez de donnees."""
    try:
        if not os.path.exists(FICHIER):
            return []
        with open(FICHIER) as f:
            hist = json.load(f)
        if symbole not in hist:
            return []
        return [e["prix"] for e in hist[sym].get(timeframe, [])]
    except Exception:
        return []

def rsi_simple(clotures, periode=14):
    """RSI calcule sur les prix stockes."""
    if len(clotures) < periode + 2:
        return None
    gains, pertes = [], []
    for i in range(1, periode + 1):
        diff = clotures[-(i+1)] - clotures[-(i+2)]
        if diff > 0:
            gains.append(diff)
        else:
            pertes.append(-diff)
    gain_moyen = sum(gains) / periode if gains else 0
    perte_moyenne = sum(pertes) / periode if pertes else 0
    if perte_moyenne == 0:
        if gain_moyen == 0:
            return 50.0
        return 100.0
    rs = gain_moyen / perte_moyenne
    return 100 - (100 / (1 + rs))

def sma_simple(clotures, periode=20):
    """SMA calcule sur les prix stockes."""
    if len(clotures) < periode:
        return None
    return sum(clotures[-periode:]) / periode
