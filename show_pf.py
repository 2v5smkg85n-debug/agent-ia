#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os
from datetime import datetime

pf = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.json")))

liq = pf.get("liquidites", 0)
positions = pf.get("positions", [])
val_pos = sum(p.get("montant_eur", 0) for p in positions)
capital = liq + val_pos

print("=" * 64)
print(f"PORTEFEUILLE PAPER TRADING — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print("=" * 64)
print(f"Capital total      : {capital:.2f} EUR")
print(f"Liquidités         : {liq:.2f} EUR ({liq/capital*100:.1f}%)")
print(f"Positions ouvertes : {len(positions)}/{pf.get('max_positions',5)}")
print(f"Valeur investie    : {val_pos:.2f} EUR ({val_pos/capital*100:.1f}%)")

if positions:
    print("\n" + "-" * 64)
    print(f"  {'Symbole':<10} {'Marché':<9} {'Montant':>8} {'Entrée':>10} {'Source':<18}")
    print("-" * 64)
    for p in positions:
        print(f"  {p.get('symbole','?'):<10} {p.get('marche','?'):<9} "
              f"{p.get('montant_eur',0):>7.2f}€ {p.get('prix_entree',0):>10.4f} "
              f"{p.get('source','?'):<18}")
        raison = p.get("signal_raison", "") or p.get("raison","")
        if raison:
            print(f"    └─ {raison[:80]}")
else:
    print("\nAucune position ouverte.")

trades = pf.get("trades_fermes", [])
if trades:
    print("\n" + "-" * 64)
    print(f"Trades fermés: {len(trades)}")
    gains = sum(t.get("gain_eur", 0) for t in trades)
    print(f"PnL cumulé fermé: {gains:+.2f} EUR")
    print(f"  {'Symbole':<10} {'Gain':>8} {'Résultat':<10} {'Date fermeture':<20}")
    for t in trades[-5:]:
        print(f"  {t.get('symbole','?'):<10} {t.get('gain_eur',0):>+7.2f}€ "
              f"{'GAIN' if t.get('gain_eur',0)>=0 else 'PERTE':<10} "
              f"{t.get('date_fermeture','')[:19]:<20}")

# Exposition par secteur
print("\n" + "-" * 64)
print("Exposition par marché (cap 25%):")
expo = {}
for p in positions:
    m = p.get("marche","?")
    expo[m] = expo.get(m,0) + p.get("montant_eur",0)
for m, e in sorted(expo.items(), key=lambda x:-x[1]):
    print(f"  {m:<10} {e:>7.2f}€ ({e/capital*100:.1f}%)")
