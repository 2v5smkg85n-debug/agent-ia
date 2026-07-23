#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_temps_adaptatif.py — vérifie la respiration adaptative du time exit."""
import os, json
from datetime import datetime, timedelta
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import paper_trading as pt

# Classement fictif: RSI Mean Reversion BTCUSDT = prouvée (n=4, 83%, +1.32€)
cs = {"BTCUSDT": {"strategies": [
    {"strategie": "RSI Mean Reversion", "live_n": 4, "live_wr": 83, "live_pnl": 1.32},
]}}
json.dump(cs, open("classement_strategies.json", "w"))

def mk(nom, age, var, strat, sym):
    """Crée une position + son prix actuel (symbole unique par position)."""
    pe = 100.0
    pa = pe * (1 + var/100)
    dt = (datetime.now() - timedelta(minutes=age)).strftime("%Y-%m-%d %H:%M")
    pos = {"nom": nom, "symbole": sym, "marche": "crypto", "prix_entree": pe,
           "prix_peak": pa, "strategie": strat, "sl": pt.STOP_LOSS_PCT, "tp": pt.TAKE_PROFIT_PCT,
           "quantite": 1.0, "montant_eur": 100.0, "date_ouverture": dt,
           "frais_entree": 0.05, "source": "test"}
    return pos, sym, pa

# (nom, age_min, variation%, strategie, symbole) — symboles uniques
cas = [
    ("A-petit95",   95,  0.35, "",                  "SYMA"),
    ("B-petit125", 125,  0.35, "",                  "SYMB"),
    ("C-prog95",   95,  0.50, "",                  "SYMC"),
    ("D-prog185", 185,  0.50, "",                  "SYMD"),
    ("E-prot95",   95,  0.65, "",                  "SYME"),
    ("F-prot245", 245,  0.65, "",                  "SYMF"),
    ("G-stale185", 185, 0.10, "",                  "SYMG"),
    ("H-strat95",  95,  0.35, "RSI Mean Reversion", "BTCUSDT"),
    ("I-strat185", 185, 0.35, "RSI Mean Reversion", "BTCUSDT2"),
]
positions = []
prix = {}
for nom, age, var, strat, sym in cas:
    pos, _, pa = mk(nom, age, var, strat, sym)
    positions.append(pos)
    prix[sym] = pa
# H et I partagent BTCUSDT conceptuellement mais ont besoin de prix distincts -> on force le prix du bonus
# (en réalité même actif; ici on isole pour le test)
prix["BTCUSDT"] = 100 * (1 + 0.35/100)
prix["BTCUSDT2"] = 100 * (1 + 0.35/100)
# corrige le symbole de I vers BTCUSDT pour le test du bonus stratégie
positions[-1]["symbole"] = "BTCUSDT2"

pf = {"capital_initial": 1000, "liquidites": 1000, "positions": positions,
      "total_frais": 0, "historique": []}

pt.verifier_sorties(pf, prix)

fermes = {t["nom"]: t["raison"] for t in pf["historique"]}
restants = {p["nom"] for p in pf["positions"]}

attendus = {
    "A-petit95": None, "B-petit125": "TEMPS+benefice", "C-prog95": None,
    "D-prog185": "TEMPS+benefice", "E-prot95": None, "F-prot245": "TEMPS+benefice",
    "G-stale185": "TEMPS-stale", "H-strat95": None, "I-strat185": "TEMPS+benefice",
}
print("=== décisions de fermeture ===")
ok = True
for nom, age, var, strat, _ in cas:
    if nom in fermes:
        raison = fermes[nom]; etat = f"FERMÉ ({raison})"
    else:
        raison = None; etat = "respire"
    att = attendus[nom]
    ok_c = (raison is None and att is None) or (raison and att and raison.startswith(att))
    mark = "OK" if ok_c else "** FAIL **"
    if not ok_c: ok = False
    print(f"  {nom:12s} age {age:3d}min var {var:+.2f}% strat={strat or 'aucune':18s} -> {etat:26s} {mark}")

print("\n>>> CAS CLÉ A: petit gain +0.35% à 95min")
print(f"    AVANT (90min): coupé TEMPS+benefice | APRÈS (120min): respire -> {('respire ✓' if 'A-petit95' in restants else 'COUPÉ ✗')}")
print("\n>>> CAS CLÉ H: petit gain +0.35% + stratégie prouvée RSI à 95min")
print(f"    bonus +60min -> duree 180min | -> {('respire ✓' if 'H-strat95' in restants else 'COUPÉ ✗')}")
print("\n>>> CAS CLÉ I: petit gain +0.35% + stratégie prouvée à 185min")
r = fermes.get("I-strat185", "")
print(f"    120+60=180min atteint -> {('coupé TEMPS+benefice ✓' if r.startswith('TEMPS+benefice') else 'MAUVAIS: '+r)}")

try: os.remove("classement_strategies.json")
except: pass
print("\n" + ("OK - temps adaptatif validé" if ok else "** ÉCHEC **"))
