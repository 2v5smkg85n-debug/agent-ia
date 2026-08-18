#!/usr/bin/env python3
import json
d = json.load(open("paper_trading.json"))
print("Positions:", len(d.get("positions", [])))
print("Trades fermes:", len(d.get("trades_fermes", [])))
for p in d.get("positions", []):
    sym = p["symbole"]
    entree = p["prix_entree"]
    peak = p.get("prix_peak", "?")
    tp = p.get("tp_adaptatif", "?")
    sl = p.get("sl_adaptatif", "?")
    print(f"  {sym} entree={entree} peak={peak} tp={tp} sl={sl}")
