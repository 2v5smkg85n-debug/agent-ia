#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pont_guards.py - valide kill switch + limite achats/jour."""
import os, sys, io
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import pont_revolut as pr
importlib.reload(pr)

auj = datetime.now().strftime("%Y-%m-%d")

# ---- T1: _nb_achats_aujourdhui (pure) ----
mirror8 = {"achats": {f"A_{i}": {"date_miroir": auj + " 10:00:00", "vendu": False} for i in range(8)}}
mirror8["achats"]["OLD"] = {"date_miroir": "2020-01-01 10:00:00", "vendu": False}
n = pr._nb_achats_aujourdhui(mirror8)
print(f"T1 nb achats aujourd hui: {n} (attendu 8)"); assert n == 8

# ---- T2: kill switch - cycle() avec PONT_KILL=1 ne cree pas de client ----
os.environ["PONT_KILL"] = "1"
importlib.reload(pr)
client_cree = {"v": False}
class FakeRevolutX:
    def __init__(self, *a, **k):
        client_cree["v"] = True
import revolut_x
revolut_x.RevolutX = FakeRevolutX
pr._load = lambda path, default: {"positions": [{"symbole": "BTCUSDT", "source": "backtest-gagnant", "date_ouverture": auj + " 21:00"}], "trades_fermes": []}
pr.cycle()
print(f"T2 kill switch: client cree = {client_cree['v']} (attendu False)"); assert not client_cree["v"]

# ---- T3: limite achats/jour - 8 aujourd hui, 9e bloque ----
os.environ["PONT_KILL"] = "0"
os.environ["PONT_MAX_TRADES_JOUR"] = "8"
importlib.reload(pr)
pr.MAX_ACHATS_JOUR = 8
pr.DRY_RUN = True  # dry-run: place_market_order non appele, mais record ajoute si non bloque
# REDIRIGE MIRROR_FILE vers un temp pour ne pas corrompre le vrai fichier
pr.MIRROR_FILE = "/tmp/test_mirror_pont.json"
if os.path.exists(pr.MIRROR_FILE):
    os.remove(pr.MIRROR_FILE)

class FC:
    def __init__(self): self.get = 0; self.place = 0
    def get_ticker(self, p): self.get += 1; return [{"symbol": p, "last_price": 50000}]
    def place_market_order(self, *a, **k): self.place += 1; return {"id": "x"}

fc = FC()
pos = {"symbole": "BTCUSDT", "source": "backtest-gagnant", "date_ouverture": auj + " 21:30"}
n_avant = len(mirror8["achats"])
pr.miroirer_achat(fc, pos, mirror8)
n_apres = len(mirror8["achats"])
print(f"T3 max-trades: achats avant={n_avant} apres={n_apres} (attendu egaux, 9e bloque)")
assert n_apres == n_avant
print(f"T3 get_ticker appele: {fc.get} (attendu 0, garde avant le fetch prix)"); assert fc.get == 0

# ---- T4: sans limite (MAX=20), le 9e achat passe (record ajoute) ----
pr.MAX_ACHATS_JOUR = 20
fc2 = FC()
n_avant2 = len(mirror8["achats"])
pr.miroirer_achat(fc2, pos, mirror8)
n_apres2 = len(mirror8["achats"])
print(f"T4 sans limite: achats avant={n_avant2} apres={n_apres2} (attendu +1, achat passe)")
assert n_apres2 == n_avant2 + 1
print(f"T4 get_ticker appele: {fc2.get} (attendu 1)"); assert fc2.get == 1

print("\n=== TESTS GARDES PONT PASSES (4 checks) ===")
