#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test ordre reel: achat 2€ BTC-EUR pour valider le format symbole."""
from revolut_x import RevolutX
import json

r = RevolutX()

PAIRE = "BTC-EUR"
MONTANT = "2"  # EUR

print(f"Test ordre: ACHAT {MONTANT}€ {PAIRE}")
print("-" * 45)

# soldes avant
b = r.get_balances()
eur_av = next((x for x in b if x["currency"] == "EUR"), {})
btc_av = next((x for x in b if x["currency"] == "BTC"), {})
print(f"Avant: EUR={eur_av.get('available')} BTC={btc_av.get('available')}")

try:
    resp = r.place_market_order(PAIRE, "buy", quote_size=MONTANT)
    print("\nREPONSE ORDRE:")
    print(json.dumps(resp, indent=2, ensure_ascii=False)[:800])
    oid = resp.get("id") or resp.get("order_id")
    if oid:
        print(f"\nOrder ID: {oid}")
        # recuperer les fills
        try:
            fills = r.get_order_fills(oid)
            print("Fills:", json.dumps(fills, indent=2, ensure_ascii=False)[:600])
        except Exception as e:
            print(f"(fills indispo: {e})")
    print("\n[OK] Format symbole BTC-EUR valide.")
except Exception as e:
    print(f"\n[ECHEC] {e}")
    print("-> Format BTC-EUR refuse. Il faudra essayer BTC/EUR (slash).")

# soldes apres
import time
time.sleep(2)
b2 = r.get_balances()
eur_ap = next((x for x in b2 if x["currency"] == "EUR"), {})
btc_ap = next((x for x in b2 if x["currency"] == "BTC"), {})
print(f"\nApres: EUR={eur_ap.get('available')} BTC={btc_ap.get('available')}")
