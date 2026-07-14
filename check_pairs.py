#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check read-only des paires Revolut X disponibles (EUR vs USD)."""
from revolut_x import RevolutX
import json

r = RevolutX()
try:
    p = r._request("GET", "configuration/pairs")
except Exception as e:
    print("Erreur configuration/pairs:", e)
    p = []

pairs = p if isinstance(p, list) else (p.get("pairs", p) if isinstance(p, dict) else [])

print("Type de reponse:", type(p).__name__)
if isinstance(p, dict):
    print("Cles:", list(p.keys())[:10])

print("\n=== Paires BTC/SOL/ETH/BNB/XRP ===")
trouve = []
for x in pairs:
    if not isinstance(x, dict):
        continue
    s = str(x.get("symbol", "")) + str(x.get("base", "")) + str(x.get("name", ""))
    if any(b in s for b in ["BTC", "SOL", "ETH", "BNB", "XRP"]):
        trouve.append(x)

for x in trouve[:20]:
    print(" ", x)

if not trouve and isinstance(pairs, list) and pairs:
    print("(aucun match, echantillon brut:)")
    for x in pairs[:5]:
        print(" ", x)

print("\nTotal paires:", len(pairs) if isinstance(pairs, list) else "?")

# aussi verifier les devises supportees
print("\n=== Devises supportees ===")
try:
    c = r._request("GET", "configuration/currencies")
    cur = c if isinstance(c, list) else (c.get("currencies", c) if isinstance(c, dict) else [])
    codes = []
    for x in cur:
        if isinstance(x, dict):
            codes.append(x.get("code", x.get("symbol", str(x))))
        elif isinstance(x, str):
            codes.append(x)
    # filtre EUR/USD/GBP
    fiat = [x for x in codes if x in ("EUR", "USD", "GBP", "CHF")]
    print("Fiat dispo:", fiat)
    print("Total devises:", len(codes))
except Exception as e:
    print("Erreur currencies:", e)
