#!/usr/bin/env python3
"""Bilan rapide du bot."""
import json
pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])
ps = pf.get('positions', [])
liq = pf.get('liquidites', 0)
frais = pf.get('total_frais', 0)
cap = liq + sum(p.get('montant_eur', 0) for p in ps)
print(f"Capital: {cap:.2f}EUR PnL: {cap-1000:+.2f}EUR | Trades: {len(ts)} | Positions: {len(ps)} | Liq: {liq:.0f}EUR | Frais: {frais:.2f}EUR")
if ts:
    g = sum(1 for t in ts if t.get('gain_eur', 0) > 0)
    p = sum(1 for t in ts if t.get('gain_eur', 0) <= 0)
    print(f"WR: {g}/{len(ts)} = {g/len(ts)*100:.0f}%")
    gains = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) > 0]
    pertes = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) <= 0]
    if gains:
        print(f"Gain moyen: +{sum(gains)/len(gains):.2f}EUR | Perte moyenne: {sum(pertes)/len(pertes):.2f}EUR" if pertes else f"Gain moyen: +{sum(gains)/len(gains):.2f}EUR")
    print("Derniers trades:")
    for t in ts[-10:]:
        print(f"  {t.get('symbole','?'):12s} {t.get('gain_eur',0):+.2f}EUR var={t.get('variation_pct',0):+.2f}% {t.get('raison',t.get('raison_fermeture','?'))[:40]}")
if ps:
    print("Positions ouvertes:")
    for p in ps:
        print(f"  {p.get('symbole','?'):12s} {p.get('montant_eur',0):.0f}EUR TP={p.get('tp_adaptatif',0)}% SL={p.get('sl_adaptatif',0)}%")
