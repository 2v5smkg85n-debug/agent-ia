#!/usr/bin/env python3
import json
d = json.load(open("paper_trading.json"))
tf = d.get("trades_fermes", [])
print(f"Trades fermes: {len(tf)}")
wins = 0
losses = 0
total_pnl = 0
for t in tf[-10:]:
    sym = t.get("symbole", "?")
    pnl = t.get("pnl_eur", t.get("pnl", "?"))
    raison = t.get("raison_fermeture", t.get("raison", "?"))
    var = t.get("variation_pct", t.get("variation", "?"))
    print(f"  {sym} pnl={pnl} var={var} raison={raison}")
    try:
        p = float(pnl)
        total_pnl += p
        if p > 0:
            wins += 1
        elif p < 0:
            losses += 1
    except:
        pass
# Stats globales
for t in tf:
    try:
        p = float(t.get("pnl_eur", t.get("pnl", 0)))
        total_pnl += 0 if t in tf[-10:] else p  # evite double compte
    except:
        pass
print(f"\nWins: {wins} Losses: {losses} (sur 10 derniers)")
print(f"Total trades fermes: {len(tf)}")
