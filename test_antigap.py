#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_antigap.py - valide la garde anti-gap week-end."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import paper_trading
importlib.reload(paper_trading)

# Vendredi 24/07/2026, Mercredi 22/07, Samedi 25/07, Lundi 20/07
VEN = datetime(2026, 7, 24, 15, 0)   # weekday 4 (vendredi)
MER = datetime(2026, 7, 22, 15, 0)   # weekday 2 (mercredi)
SAM = datetime(2026, 7, 25, 12, 0)   # weekday 5 (samedi)
LUN = datetime(2026, 7, 20, 9, 0)    # weekday 0 (lundi)

def sig(marche): return {"symbole": "X", "nom": "X", "marche": marche, "action": "ACHAT"}

f = paper_trading._entree_bloquee_weekend
ok = True

# Cas1: vendredi + forex -> bloque
r = f(sig("forex"), VEN)
print(f"Cas1 (vendredi forex): bloque={r} -> attendu True")
assert r is True, "ECHEC Cas1"

# Cas2: mercredi + forex -> autorise
r = f(sig("forex"), MER)
print(f"Cas2 (mercredi forex): bloque={r} -> attendu False")
assert r is False, "ECHEC Cas2"

# Cas3: vendredi + crypto -> autorise (24/7)
r = f(sig("crypto"), VEN)
print(f"Cas3 (vendredi crypto): bloque={r} -> attendu False")
assert r is False, "ECHEC Cas3"

# Cas4: samedi + forex -> bloque
r = f(sig("forex"), SAM)
print(f"Cas4 (samedi forex): bloque={r} -> attendu True")
assert r is True, "ECHEC Cas4"

# Cas5: lundi + forex -> autorise
r = f(sig("forex"), LUN)
print(f"Cas5 (lundi forex): bloque={r} -> attendu False")
assert r is False, "ECHEC Cas5"

# Cas6: vendredi + indice (non-crypto) -> bloque
r = f(sig("indice"), VEN)
print(f"Cas6 (vendredi indice): bloque={r} -> attendu True")
assert r is True, "ECHEC Cas6"

# Cas7: marche absent -> traite comme non-crypto -> bloque vendredi
r = f({"symbole":"X"}, VEN)
print(f"Cas7 (vendredi marche absent): bloque={r} -> attendu True (defensif)")
assert r is True, "ECHEC Cas7"

print("\n=== TESTS ANTI-GAP PASSÉS ===")
