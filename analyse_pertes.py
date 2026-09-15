#!/usr/bin/env python3
"""Analyse pourquoi le bot perd de l'argent."""
import json
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])

gains = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) > 0]
pertes = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) <= 0]

print("=== GAINS VS PERTES ===")
if gains:
    print(f"Gains: {len(gains)} total={sum(gains):+.2f} moyen={sum(gains)/len(gains):+.3f}")
if pertes:
    print(f"Pertes: {len(pertes)} total={sum(pertes):+.2f} moyen={sum(pertes)/len(pertes):+.3f}")
if gains and pertes:
    print(f"Ratio gain/perte: {abs(sum(gains)/sum(pertes)):.2f}x")
print()

print("=== PAR RAISON DE FERMETURE ===")
by_raison = defaultdict(lambda: {'n': 0, 'pnl': 0})
for t in ts:
    r = t.get('raison_fermeture', t.get('raison', '?'))[:25]
    by_raison[r]['n'] += 1
    by_raison[r]['pnl'] += t.get('gain_eur', 0)
for r, d in sorted(by_raison.items(), key=lambda x: x[1]['pnl']):
    print(f"  {r:27s} n={d['n']:3d} PnL={d['pnl']:+.2f}")
print()

print("=== PAR STRATEGIE ===")
by_strat = defaultdict(lambda: {'n': 0, 'g': 0, 'pnl': 0})
for t in ts:
    s = t.get('strategie', '?')
    by_strat[s]['n'] += 1
    by_strat[s]['pnl'] += t.get('gain_eur', 0)
    if t.get('gain_eur', 0) > 0:
        by_strat[s]['g'] += 1
for s, d in sorted(by_strat.items(), key=lambda x: x[1]['pnl']):
    wr = d['g'] / d['n'] * 100 if d['n'] else 0
    print(f"  {s:22s} n={d['n']:3d} WR={wr:5.1f}% PnL={d['pnl']:+.2f}")
print()

print("=== TOP 10 PERTES ===")
for t in sorted(ts, key=lambda x: x.get('gain_eur', 0))[:10]:
    print(f"  {t.get('symbole','?'):12s} {t.get('strategie','?'):20s} {t.get('gain_eur',0):+.2f} TP={t.get('tp_adaptatif','?')} SL={t.get('sl_adaptatif','?')} {t.get('raison_fermeture', t.get('raison','?'))[:25]}")
print()

print("=== TOP 10 GAINS ===")
for t in sorted(ts, key=lambda x: x.get('gain_eur', 0), reverse=True)[:10]:
    print(f"  {t.get('symbole','?'):12s} {t.get('strategie','?'):20s} {t.get('gain_eur',0):+.2f} TP={t.get('tp_adaptatif','?')} SL={t.get('sl_adaptatif','?')} {t.get('raison_fermeture', t.get('raison','?'))[:25]}")
print()

print("=== POSITIONS OUVERTES ===")
ps = pf.get('positions', [])
for p in ps:
    print(f"  {p.get('symbole','?'):12s} entry={p.get('prix_entree',0)} TP={p.get('tp_adaptatif',0)}% SL={p.get('sl_adaptatif',0)}% {p.get('strategie','?')} {p.get('montant_eur',0):.0f}EUR")
print(f"  Total: {len(ps)} positions, {pf.get('liquidites',0):.0f}EUR liquidites")
