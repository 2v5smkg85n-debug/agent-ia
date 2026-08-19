#!/usr/bin/env python3
"""Bilan quotidien du paper trading."""
import json
from datetime import datetime

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])
auj = datetime.now().strftime("%Y-%m-%d")

gagnes = perdus = 0
nb_g = nb_p = 0
for t in trades:
    if t.get("date_fermeture", "").startswith(auj):
        g = t.get("gain_eur", 0)
        if g >= 0:
            gagnes += g
            nb_g += 1
        else:
            perdus += g
            nb_p += 1

net = gagnes + perdus
total_trades = nb_g + nb_p

print("=" * 40)
print(f"BILAN DU {auj}")
print("=" * 40)
print(f"Trades fermes aujourd hui: {total_trades}")
print(f"  Gagnes: {nb_g} trades | +{gagnes:.2f} EUR")
print(f"  Perdus: {nb_p} trades | {perdus:.2f} EUR")
print(f"  Net journee: {net:+.2f} EUR")
print()
print(f"Frais totaux: {pf.get('total_frais', 0):.2f} EUR")
print(f"Liquidites: {pf.get('liquidites', 0):.2f} EUR")
print(f"Positions ouvertes: {len(pf.get('positions', []))}")

# P&L latent sur positions ouvertes
positions = pf.get("positions", [])
investi = sum(p.get("montant_eur", 0) for p in positions)
print(f"Montant investi: {investi:.2f} EUR")
print(f"Capital total: {pf.get('liquidites', 0) + investi:.2f} EUR")
print(f"Capital initial: {pf.get('capital_initial', 1000):.2f} EUR")
perf = (pf.get("liquidites", 0) + investi - pf.get("capital_initial", 1000)) / pf.get("capital_initial", 1000) * 100
print(f"Performance globale: {perf:+.2f}%")
