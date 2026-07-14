#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liste les paires Revolut X disponibles pour nos 5 cryptos (read-only)."""
from revolut_x import RevolutX

r = RevolutX()
p = r._request("GET", "configuration/pairs")
pairs = p if isinstance(p, dict) else {}

print("=== Paires disponibles pour nos cryptos ===")
cibles = ["BTC", "SOL", "ETH", "BNB", "XRP"]
for base in cibles:
    matches = [k for k in pairs.keys() if k.startswith(base + "/")]
    print(f"  {base}: {matches}")

# verifier le format de symbole attendu pour un ordre
# (le module utilise BTC-USD, mais les paires sont BTC/USD)
print("\n=== Detail d'une paire (BTC/USD) ===")
if "BTC/USD" in pairs:
    print(" ", pairs["BTC/USD"])
if "BTC/EUR" in pairs:
    print("=== Detail BTC/EUR ===")
    print(" ", pairs["BTC/EUR"])

# tester un ticker pour confirmer le format qui marche
print("\n=== Test ticker BTC/USD ===")
try:
    t = r._request("GET", "tickers", params={"symbol": "BTC/USD"})
    print(" ", t)
except Exception as e:
    print("  Erreur BTC/USD:", e)

print("\n=== Test ticker BTC-EUR ===")
try:
    t = r.get_ticker("BTC-EUR")
    print(" ", t)
except Exception as e:
    print("  Erreur BTC-EUR:", e)
