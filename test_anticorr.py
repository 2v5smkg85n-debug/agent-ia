#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_anticorr.py — valide la garde anti-double-exposition (par capture stdout).

Distingue [ANTI-CORR] (garde a bloqué) de [SKIP] edge (edge gate).
Cas 1: ARB ouvert <60min -> [ANTI-CORR] bloqué
Cas 2: ARB ouvert >60min -> PAS [ANTI-CORR] (passe la garde)
Cas 3: BTC alors que ARB ouvert 10min -> PAS [ANTI-CORR]
Cas 4: ANTI_CORR=0 -> PAS [ANTI-CORR] (désactivée)
"""
import os, sys, io
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib
import paper_trading
importlib.reload(paper_trading)

print(f"FENETRE_CORRELATION_MIN = {paper_trading.FENETRE_CORRELATION_MIN}")

def _pf():
    return {"capital_initial": 1000.0, "liquidites": 1000.0, "positions": [], "historique": []}
def _sig(sym="ARBUSDT", nom="Arbitrum"):
    return {"symbole": sym, "nom": nom, "marche": "crypto", "action": "ACHAT"}
def _pos(sym, age_min):
    dt = (datetime.now() - timedelta(minutes=age_min)).strftime("%Y-%m-%d %H:%M")
    return {"symbole": sym, "nom": "X", "date_ouverture": dt, "prix_entree": 1.0,
            "montant_eur": 50.0, "quantite": 50.0, "strategie": "S1"}

def run(pf, sig, prix=1.0):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        r = paper_trading.ouvrir_position(pf, sig, prix)
    except Exception as e:
        r = f"EXC:{type(e).__name__}"
    finally:
        sys.stdout = old
    return r, buf.getvalue()

ok = True

# Cas 1: ARB <60min -> ANTI-CORR
os.environ["ANTI_CORR"] = "1"
pf = _pf(); pf["positions"].append(_pos("ARBUSDT", 10))
r, out = run(pf, _sig("ARBUSDT"))
blocked = "[ANTI-CORR]" in out
print(f"Cas1 (ARB ouvert 10min): retour={r} | ANTI-CORR={blocked}")
assert blocked, "ECHEC Cas1: aurait dû bloquer (ANTI-CORR)"

# Cas 2: ARB >60min -> passe la garde (pas ANTI-CORR)
pf = _pf(); pf["positions"].append(_pos("ARBUSDT", 70))
r, out = run(pf, _sig("ARBUSDT"))
print(f"Cas2 (ARB ouvert 70min): retour={r} | ANTI-CORR={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out, "ECHEC Cas2: ne devrait pas bloquer (>60min)"

# Cas 3: BTC alors que ARB ouvert 10min -> pas ANTI-CORR
pf = _pf(); pf["positions"].append(_pos("ARBUSDT", 10))
r, out = run(pf, _sig("BTCUSDT","Bitcoin"))
print(f"Cas3 (BTC, ARB ouvert 10min): retour={r} | ANTI-CORR={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out, "ECHEC Cas3: BTC ne devrait pas être bloqué par ARB"

# Cas 4: ANTI_CORR=0 -> désactivée
os.environ["ANTI_CORR"] = "0"
pf = _pf(); pf["positions"].append(_pos("ARBUSDT", 10))
r, out = run(pf, _sig("ARBUSDT"))
print(f"Cas4 (ANTI_CORR=0, ARB 10min): retour={r} | ANTI-CORR={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out, "ECHEC Cas4: garde devrait être désactivée"
os.environ["ANTI_CORR"] = "1"

print("\n=== TOUS LES TESTS ANTI-CORR PASSÉS ===")
