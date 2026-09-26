#!/usr/bin/env python3
"""Repare les positions IA autonome cassees (quantite=0, PnL -100%)."""
import json, os

FICHIER = os.path.expanduser("~/agent-ia/paper_trading.json")

with open(FICHIER) as f:
    pf = json.load(f)

positions = pf.get("positions", [])
fixes = 0
for pos in positions:
    if pos.get("source") == "ouverture_ia_chat" or pos.get("strategie") == "ia_autonome":
        quantite = pos.get("quantite", 0)
        montant = pos.get("montant_eur", 0)
        prix_entree = pos.get("prix_entree", 0)
        # Si quantite = 0 ou manquante, on la recalcule
        if quantite == 0 and montant > 0 and prix_entree > 0:
            frais = montant * 0.002
            pos["quantite"] = (montant - frais) / prix_entree
            fixes += 1
            print(f"  Fix {pos['symbole']}: quantite -> {pos['quantite']:.6f}")
        # Ajoute date_ouverture si manquante
        if not pos.get("date_ouverture"):
            ts = pos.get("timestamp", "")
            if ts:
                pos["date_ouverture"] = ts[:16].replace("T", " ")
            else:
                pos["date_ouverture"] = "2026-09-26 00:00"
            print(f"  Fix {pos['symbole']}: date_ouverture -> {pos['date_ouverture']}")

pf["positions"] = positions
with open(FICHIER, "w") as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print(f"\n{fixes} position(s) reparee(s). Capital devrait revenir a la normale.")
