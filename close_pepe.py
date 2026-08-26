#!/usr/bin/env python3
"""Ferme la position PEPE restante."""
import json

pf = json.load(open("paper_trading.json"))
for i, p in enumerate(pf["positions"]):
    if "PEPE" in p["symbole"]:
        print(f"Fermeture PEPE: {p['montant_eur']:.2f}EUR @ {p['prix_entree']}")
        pf["positions"].pop(i)
        pf["liquidites"] += p["montant_eur"]
        break
else:
    print("Aucune position PEPE trouvee")

json.dump(pf, open("paper_trading.json", "w"), ensure_ascii=False, indent=2)
print("PEPE ferme")
