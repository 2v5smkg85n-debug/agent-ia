#!/usr/bin/env python3
"""Vérifie le solde EUR et les paires BTC disponibles sur Revolut X."""
from revolut_x import RevolutX

c = RevolutX()

# 1. Soldes : cherche EUR, USD et les crypto non-nulles
print("=== SOLDES NON NULS ===")
balances = c.get_balances()
if isinstance(balances, list):
    for b in balances:
        try:
            total = float(b.get("total", 0))
            if total > 0:
                print(f"  {b['currency']}: disponible={b.get('available')} | reserve={b.get('reserved')} | total={b.get('total')}")
        except (ValueError, TypeError):
            pass

# 2. Paires contenant BTC
print("\n=== PAIRES BTC ===")
pairs = c.get_pairs()
if isinstance(pairs, dict):
    for key, p in pairs.items():
        if "BTC" in key and p.get("status") == "active":
            print(f"  {key}: base={p.get('base')} quote={p.get('quote')} | min_quote={p.get('min_order_size_quote')} | step={p.get('quote_step')} | {p.get('status')}")

# 3. Paires cotées en EUR (actives)
print("\n=== PAIRES COTEES EN EUR (actives) ===")
if isinstance(pairs, dict):
    for key, p in pairs.items():
        if p.get("quote") == "EUR" and p.get("status") == "active":
            print(f"  {key}: min_quote={p.get('min_order_size_quote')} | step={p.get('quote_step')}")
