#!/usr/bin/env python3
"""Reset le portefeuille a 1000EUR, 0 positions, trades fermes conserves pour l'apprentissage."""
import json
import os
from datetime import datetime

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.json")

# Charge l'ancien portefeuille pour garder l'historique d'apprentissage
ancien = {}
if os.path.exists(FICHIER):
    try:
        with open(FICHIER) as f:
            ancien = json.load(f)
    except Exception:
        pass

trades_fermes = ancien.get("trades_fermes", [])

nouveau = {
    "capital_initial": 1000.0,
    "liquidites": 1000.0,
    "positions": [],
    "trades_fermes": trades_fermes,  # garde l'historique pour l'apprentissage
    "total_frais": 0.0,
    "historique": [],
    "dernier_tick": datetime.now().strftime("%Y-%m-%d %H:%M") + " (RESET)",
    "circuit_breaker": {"consecutive_losses": 0},
}

# Sauvegarde l'ancien
if ancien:
    with open(FICHIER + ".bak", "w") as f:
        json.dump(ancien, f, indent=2, ensure_ascii=False)

with open(FICHIER, "w") as f:
    json.dump(nouveau, f, indent=2, ensure_ascii=False)

print(f"Reset complete!")
print(f"  Capital: 1000.00EUR")
print(f"  Positions: 0")
print(f"  Trades fermes conserves: {len(trades_fermes)} (pour l'apprentissage)")
print(f"  Sauvegarde ancien: {FICHIER}.bak")
