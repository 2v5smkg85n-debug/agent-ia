#!/usr/bin/env python3
"""Verifie la taille des positions ouvertes."""
import json
pf = json.load(open("paper_trading.json"))
positions = pf.get("positions", [])
print(f"=== POSITIONS OUVERTES ({len(positions)}) ===")
try:
    import paper_trading as pt
    _max = pt.MAX_POSITIONS
    _risk = pt.RISK_PAR_TRADE * 100
except Exception:
    _max = 5
    _risk = 8.0
print(f"MAX_POSITIONS: {_max} | RISK_PAR_TRADE: {_risk:.0f}%")
print(f"Liquidites: {pf.get('liquidites', 0):.2f}EUR")
print()
for p in positions:
    montant = p.get("montant_eur", 0)
    qte = p.get("quantite", 0)
    prix = p.get("prix_entree", 0)
    sym = p.get("symbole", "?")
    print(f"  {sym}: {montant:.2f}EUR | qte {qte:.6f} @ {prix:.4f}")
print()
capital = pf.get('liquidites', 0) + sum(p.get('montant_eur', 0) for p in positions)
print(f"Capital total: {capital:.2f}EUR")
