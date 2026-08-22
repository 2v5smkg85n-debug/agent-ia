#!/usr/bin/env python3
"""Analyse les pertes recentes."""
import json
from datetime import datetime, timedelta

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])

# Aujourd'hui et hier
auj = datetime.now().strftime("%Y-%m-%d")
hier = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

print("=== ANALYSE DES PERTES ===\n")

for jour in [auj, hier]:
    trades_jour = [t for t in trades if t.get("date_fermeture", "").startswith(jour)]
    if not trades_jour:
        print(f"{jour}: aucun trade\n")
        continue
    
    gagnes = [t for t in trades_jour if t.get("gain_eur", 0) >= 0]
    perdus = [t for t in trades_jour if t.get("gain_eur", 0) < 0]
    
    total_g = sum(t.get("gain_eur", 0) for t in gagnes)
    total_p = sum(t.get("gain_eur", 0) for t in perdus)
    net = total_g + total_p
    
    print(f"--- {jour} ---")
    print(f"Trades: {len(trades_jour)} ({len(gagnes)} gagnes, {len(perdus)} pertes)")
    print(f"Gagnes: +{total_g:.2f}EUR | Pertes: {total_p:.2f}EUR | Net: {net:+.2f}EUR")
    print(f"Win rate: {len(gagnes)/len(trades_jour)*100:.0f}%")
    
    if perdus:
        print(f"\n  Pertes detaillees:")
        for t in sorted(perdus, key=lambda x: x.get("gain_eur", 0)):
            print(f"    {t.get('symbole','?')}: {t.get('gain_eur',0):+.2f}EUR | {t.get('raison','?')} | var {t.get('variation_pct',0):+.2f}% | {t.get('date_fermeture','?')}")
    
    # Stats par raison
    print(f"\n  Stats par raison:")
    raisons = {}
    for t in perdus:
        r = t.get("raison", "?")
        if r not in raisons:
            raisons[r] = {"count": 0, "total": 0}
        raisons[r]["count"] += 1
        raisons[r]["total"] += t.get("gain_eur", 0)
    for r, s in sorted(raisons.items(), key=lambda x: x[1]["total"]):
        print(f"    {r}: {s['count']} trades | {s['total']:+.2f}EUR")
    print()

print(f"Capital total: {pf.get('liquidites',0) + sum(p.get('montant_eur',0) for p in pf.get('positions',[])):.2f}EUR")
print(f"Performance globale: {(pf.get('liquidites',0) + sum(p.get('montant_eur',0) for p in pf.get('positions',[])) - pf.get('capital_initial',1000)) / pf.get('capital_initial',1000) * 100:+.2f}%")
