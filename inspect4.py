#!/usr/bin/env python3
"""Dump des champs d'evaluation de strategies.json pour construire le filtre de coupe."""
import json
from collections import Counter


def load(n, d):
    try:
        return json.load(open(n))
    except Exception:
        return d


strats = load("strategies.json", [])
print(f"Stratégies: {len(strats)}\n")

# Distribution des champs d'évaluation
print("=== DISTRIBUTION ===")
for champ in ("evaluee", "resultat", "modele", "marche"):
    vals = Counter(str(s.get(champ)) for s in strats if isinstance(s, dict))
    print(f"{champ}: {dict(vals)}")

print("\n=== WIN RATE distribution ===")
wrs = [s.get("win_rate") for s in strats if isinstance(s, dict)]
print(f"win_rate valeurs: {sorted(set(str(w) for w in wrs))}")

print("\n=== DÉTAIL PAR STRATÉGIE ===")
print(f"{'idx':>3} {'evaluee':<8} {'win_rate':>9} {'evals':>5} {'resultat':<12} marche     raison_eval")
for i, s in enumerate(strats):
    if not isinstance(s, dict):
        continue
    ev = s.get("evaluee", "?")
    wr = s.get("win_rate", "?")
    evs = s.get("evaluations", "?")
    res = str(s.get("resultat", "?"))[:12]
    m = str(s.get("marche", "?"))[:9]
    r = str(s.get("raison_eval", ""))[:40]
    print(f"{i:>3} {str(ev):<8} {str(wr):>9} {str(evs):>5} {res:<12} {m:<9} {r}")

# Resume: combien coupables selon win_rate
print("\n=== SYNTHÈSE coupable (win_rate < 0.4 ET evaluee) ===")
coups = []
for i, s in enumerate(strats):
    if not isinstance(s, dict):
        continue
    ev = s.get("evaluee")
    wr = s.get("win_rate")
    try:
        wrf = float(wr)
        wr_ok = wrf < 0.4 if wrf <= 1 else wrf < 40
    except (ValueError, TypeError):
        wr_ok = False
    if ev and wr_ok:
        coups.append(i)
print(f"Stratégies coupables (win_rate faible + évaluées): {len(coups)} -> indices {coups}")
