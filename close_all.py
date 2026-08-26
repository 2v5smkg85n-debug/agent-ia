#!/usr/bin/env python3
"""Ferme toutes les positions ouvertes pour reset a 500EUR."""
import json

pf = json.load(open("paper_trading.json"))
positions = pf.get("positions", [])

for p in positions:
    pf["liquidites"] += p["montant_eur"]
    pf["trades_fermes"].append({
        **p,
        "date_fermeture": "2026-08-23 22:03",
        "gain_eur": 0,
        "prix_sortie": p["prix_entree"],
        "raison": "Fermeture manuelle pour 500EUR",
        "variation_pct": 0,
        "frais_total": 0
    })
    print(f"Ferme {p['symbole']} ({p['montant_eur']:.2f}EUR)")

pf["positions"] = []
json.dump(pf, open("paper_trading.json", "w"), indent=2, ensure_ascii=False)

print(f"\nLiquidites: {pf['liquidites']:.2f}EUR")
print(f"Prochaine position: {pf['liquidites']*0.08:.2f}EUR (8%)")
print("Redemarre le bot: sudo systemctl restart paper_trading.service")
