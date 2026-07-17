#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Récupère le vrai solde du compte Revolut X (toutes devises + crypto)."""
import os
from revolut_x import RevolutX

# charge .env
ENV = {}
env_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(env_path):
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip().strip('"').strip("'")

api_key = ENV.get("REVOLUT_X_API_KEY", os.getenv("REVOLUT_X_API_KEY"))
key_path = ENV.get("REVOLUT_X_PRIVATE_KEY", os.getenv("REVOLUT_X_PRIVATE_KEY"))

print("=== SOLDE COMPTE REVOLUT X ===")
client = RevolutX()

try:
    bal = client.get_balances()
    data = bal.get("balances", bal) if isinstance(bal, dict) else bal
    total_eur = 0.0
    if isinstance(data, list):
        for b in data:
            if not isinstance(b, dict):
                continue
            c = b.get("currency", "?")
            amt = b.get("amount") or b.get("balance") or b.get("available")
            try:
                amt = float(amt)
            except Exception:
                amt = amt
            print(f"  {c}: {amt}")
            if c == "EUR":
                total_eur += float(amt) if amt else 0
        print(f"\n  EUR disponible: {total_eur:.2f} EUR")
    else:
        print(json.dumps(bal, indent=2, ensure_ascii=False)[:1500])
except Exception as e:
    print(f"ERREUR get_balances: {e}")

# Vérifie aussi les ordres historiques (le dernier)
print("\n=== DERNIERS ORDRES ===")
try:
    hist = client.get_historical_orders()
    orders = hist.get("orders", hist) if isinstance(hist, dict) else hist
    if isinstance(orders, list) and orders:
        for o in orders[-3:]:
            print(f"  {o.get('symbol','?')} {o.get('side','?')} qty={o.get('quantity',o.get('amount','?'))} "
                  f"statut={o.get('status', o.get('state','?'))} id={o.get('id','?')}")
    else:
        print("  (aucun ordre historique ou format inattendu)")
        print(f"  raw: {str(hist)[:400]}")
except Exception as e:
    print(f"  ERREUR historical_orders: {e}")
