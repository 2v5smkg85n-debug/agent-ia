#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dump_revolut_pairs.py — Diagnostique le format de get_pairs() Revolut X
pour pouvoir parser correctement le catalogue."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")
from revolut_x import RevolutX

client = RevolutX()
pairs = client.get_pairs()

print(f"TYPE: {type(pairs)}")
if isinstance(pairs, dict):
    print(f"DICT avec {len(pairs)} cles. Premieres cles: {list(pairs.keys())[:5]}")
    first_key = list(pairs.keys())[0]
    val = pairs[first_key]
    print(f"\nVALEUR pour cle '{first_key}': type={type(val)}")
    if isinstance(val, list):
        print(f"  liste de {len(val)} elements")
        print(f"  PREMIER ELEMENT (type {type(val[0])}):")
        print(json.dumps(val[0], indent=2, default=str)[:800] if val else "vide")
    else:
        print(json.dumps(val, indent=2, default=str)[:800])
elif isinstance(pairs, list):
    print(f"LISTE de {len(pairs)} elements")
    print(f"\nPREMIER ELEMENT (type {type(pairs[0])}):")
    print(json.dumps(pairs[0], indent=2, default=str)[:800] if pairs else "vide")
    if len(pairs) > 1:
        print(f"\nDEUXIEME ELEMENT:")
        print(json.dumps(pairs[1], indent=2, default=str)[:800])
    print(f"\n--- TOUS LES SYMBOLES ({len(pairs)}) ---")
    for p in pairs:
        if isinstance(p, dict):
            print(f"  {p}")
        else:
            print(f"  {p}")
