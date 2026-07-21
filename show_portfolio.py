#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""show_portfolio.py — Lit le VRAI portefeuille paper_trading.json correctement."""
import os, sys, json
from datetime import datetime
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

f = "paper_trading.json"
d = json.load(open(f, encoding="utf-8"))
print(f"=== Portefeuille paper ({datetime.utcnow():%Y-%m-%d %H:%M} UTC) ===")
print(f"Cles: {list(d.keys())}")
# Cherche le solde/capital
for k in ["solde", "capital", "capital_dispo", "liquidites", "cash", "capital_total", "solde_total"]:
    if k in d:
        print(f"  {k}: {d[k]}")
# Positions
pos = d.get("positions", d.get("portefeuille", {}))
print(f"\nPositions ({len(pos)}):")
valo = 0
for sym, v in pos.items():
    if isinstance(v, dict):
        qty = v.get("quantite", v.get("qty", v.get("quantite_totale", 0)))
        prix = v.get("prix_entree", v.get("prix_moyen", v.get("prix", 0)))
        actuel = v.get("prix_actuel", v.get("actuel", prix))
        if qty and qty > 0:
            val = qty * (actuel or prix)
            valo += val
            pnl_pct = ((actuel - prix) / prix * 100) if prix and actuel else 0
            print(f"  {sym}: {qty:.4f} @ {prix} | actuel {actuel} ({pnl_pct:+.2f}%) = {val:.2f}€")
print(f"\nValorisation positions: {valo:.2f}€")
# Capital total
for k in d:
    if isinstance(d[k], (int, float)) and "capital" in k.lower():
        print(f"  {k} = {d[k]}")
