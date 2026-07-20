#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dump_revolut_candles.py — Format de get_candles + toutes les bases EUR."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")
from revolut_x import RevolutX

client = RevolutX()
pairs = client.get_pairs()

# Toutes les paires EUR actives + leurs bases
eur = [(sym, info.get("base","")) for sym, info in pairs.items()
       if isinstance(info, dict) and info.get("quote")=="EUR" and info.get("status")=="active"]
print(f"=== {len(eur)} BASES EUR ACTIVES SUR REVOLUT X ===")
for sym, base in sorted(eur, key=lambda x: x[1]):
    print(f"  {base:<12} {sym}")

# Dump format candles pour BTC/EUR
print(f"\n=== FORMAT get_candles('BTC/EUR') ===")
try:
    c = client.get_candles("BTC/EUR")
    print(f"TYPE: {type(c)}")
    if isinstance(c, list):
        print(f"LISTE de {len(c)} elements")
        if c:
            print(f"PREMIER (type {type(c[0])}):")
            print(json.dumps(c[0], indent=2, default=str)[:500])
            print(f"DERNIER:")
            print(json.dumps(c[-1], indent=2, default=str)[:500])
    elif isinstance(c, dict):
        print(json.dumps(c, indent=2, default=str)[:1000])
except Exception as e:
    print(f"ERREUR: {e}")

# essai aussi format avec tiret
print(f"\n=== essai get_candles('BTC-EUR') ===")
try:
    c = client.get_candles("BTC-EUR")
    print(f"TYPE: {type(c)}, len={len(c) if hasattr(c,'__len__') else '?'}")
    if isinstance(c, list) and c:
        print(f"PREMIER: {json.dumps(c[0], default=str)[:300]}")
except Exception as e:
    print(f"ERREUR: {e}")
