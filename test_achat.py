#!/usr/bin/env python3
"""Test d'achat réel : 8€ de Bitcoin sur la paire BTC-EUR."""
from revolut_x import RevolutX

c = RevolutX()
r = c.place_market_order("BTC-EUR", "buy", quote_size=8)
print("=== REPONSE ORDRE ===")
print(r)
