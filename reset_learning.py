#!/usr/bin/env python3
"""Reset complet du learning et de l'historique de trades."""
import json

f = "paper_trading.json"
d = json.load(open(f))
d["trades_fermes"] = []
d["circuit_breaker"] = {"consecutive_losses": 0}
json.dump(d, open(f, "w"), indent=2)
print("Trades fermes effaces, circuit breaker reset")

# Effacer le learning
import os
for f_name in ["learning_trader.json", "trader_pro_scores.json"]:
    try:
        os.remove(f_name)
        print(f"{f_name} efface")
    except Exception:
        pass

print("Reset complet termine!")
