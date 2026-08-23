#!/usr/bin/env python3
"""Verifie la taille des positions ouvertes."""
import json
pf = json.load(open("paper_trading.json"))
positions = pf.get("positions", [])
print(f"=== POSITIONS OUVERTES ({len(positions)}) ===")
print(f"MAX_POSITIONS: 3 | RISK_PAR_TRADE: 50%")
print(f"Liquidites: {pf.get('liquidites', 0):.2f}EUR")
print()
for p in positions:
    montant = p.get("montant_eur", 0)
    qte = p.get("quantite", 0)
    prix = p.get("prix_entree", 0)
    sym = p.get("symbole", "?")
    print(f"  {sym}: {montant:.2f}EUR | qte {qte:.6f} @ {prix:.4f}")
print()
print(f"Capital total: {pf.get('liquidites', 0) + sum(p.get('montant_eur', 0) for p in positions):.2f}EUR")
