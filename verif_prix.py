#!/usr/bin/env python3
"""Verifie les prix reels des positions ouvertes."""
import json
import time
import prix_revolut as pr

pf = json.load(open("paper_trading.json"))
print("=== VERIFICATION PRIX POSITIONS ===\n")
total_investi = 0
total_valeur = 0
for p in pf.get("positions", []):
    s = p["symbole"]
    pe = p["prix_entree"]
    qte = p.get("quantite", 0)
    montant = p.get("montant_eur", 0)
    pa = pr.get_prix_revolut(s)
    if pa and pa > 0:
        var = (pa - pe) / pe * 100
        valeur = qte * pa
        pnl = valeur - montant
        total_investi += montant
        total_valeur += valeur
        print(f"{s}: entree {pe:.4f} | actuel {pa:.4f} | {var:+.2f}% | PnL {pnl:+.2f}EUR")
    else:
        print(f"{s}: prix indispo (429)")
    time.sleep(3)

print(f"\nInvesti: {total_investi:.2f}EUR")
print(f"Valeur actuelle: {total_valeur:.2f}EUR")
print(f"PnL latent: {total_valeur - total_investi:+.2f}EUR")
print(f"Liquidites: {pf.get('liquidites', 0):.2f}EUR")
print(f"Capital total: {pf.get('liquidites', 0) + total_valeur:.2f}EUR")
