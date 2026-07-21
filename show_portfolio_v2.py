#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""show_portfolio_v2.py — Lit paper_trading.json (positions = liste)."""
import os, sys, json
from datetime import datetime
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

d = json.load(open("paper_trading.json", encoding="utf-8"))
print(f"=== Portefeuille paper ({datetime.utcnow():%Y-%m-%d %H:%M} UTC) ===")
cap_init = d.get("capital_initial", 1000)
liq = d.get("liquidites", 0)
pic = d.get("pic_capital", cap_init)
print(f"  Capital initial: {cap_init:.2f}€")
print(f"  Liquidites: {liq:.2f}€")
print(f"  Pic capital: {pic:.2f}€")

pos = d.get("positions", [])
# positions peut etre list ou dict
if isinstance(pos, dict):
    pos = list(pos.values())
print(f"\nPositions ouvertes ({len(pos)}):")
valo = 0
for v in pos:
    if not isinstance(v, dict):
        continue
    sym = v.get("symbole", v.get("actif", v.get("nom", "?")))
    qty = v.get("quantite", v.get("qty", 0))
    prix = v.get("prix_entree", v.get("prix_moyen", v.get("prix", 0)))
    actuel = v.get("prix_actuel", v.get("actuel", prix))
    if qty and qty > 0:
        val = qty * (actuel or prix or 0)
        valo += val
        pnl_pct = ((actuel - prix) / prix * 100) if prix and actuel and prix > 0 else 0
        print(f"  {sym}: {qty:.4f} @ {prix:.4f} | actuel {actuel:.4f} ({pnl_pct:+.2f}%) = {val:.2f}€")

total = liq + valo
pnl = total - cap_init
print(f"\nValorisation positions: {valo:.2f}€")
print(f"TOTAL (liquidites + positions): {total:.2f}€")
print(f"PnL: {pnl:+.2f}€ ({pnl/cap_init*100:+.2f}%)")
print(f"Trades fermes: {d.get('trades_fermes', '?')}")
