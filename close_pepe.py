#!/usr/bin/env python3
"""Ferme la position PEPE restante (ou n'importe quel symbole manuellement)."""
import json
from datetime import datetime

pf = json.load(open("paper_trading.json"))
pepe = next((p for p in pf.get("positions", []) if "PEPE" in p.get("symbole", "")), None)

if pepe:
    print(f"Fermeture PEPE: {pepe.get('montant_eur', 0):.2f}EUR @ {pepe.get('prix_entree', 0)}")
    pf["positions"] = [p for p in pf.get("positions", []) if "PEPE" not in p.get("symbole", "")]
    pf["liquidites"] += pepe.get("montant_eur", 0)
    # Enregistrer dans trades_fermes pour l'audit
    pf.setdefault("trades_fermes", []).append({
        **pepe,
        "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "gain_eur": 0,
        "prix_sortie": pepe.get("prix_entree", 0),
        "raison": "Fermeture manuelle PEPE",
        "variation_pct": 0,
        "frais_total": 0,
    })
else:
    print("Aucune position PEPE trouvee")

json.dump(pf, open("paper_trading.json", "w"), ensure_ascii=False, indent=2)
print("PEPE ferme")
