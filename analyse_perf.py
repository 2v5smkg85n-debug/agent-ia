#!/usr/bin/env python3
"""Analyse des performances par crypto et par raison de fermeture."""
import json
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])
ps = pf.get('positions', [])
liq = pf.get('liquidites', 0)
frais = pf.get('total_frais', 0)
cap = liq + sum(p.get('montant_eur', 0) for p in ps)

print("=" * 75)
print("ANALYSE DES PERFORMANCES")
print("=" * 75)
print(f"Capital: {cap:.2f}EUR | PnL: {cap-1000:+.2f}EUR | Trades: {len(ts)} | Frais: {frais:.2f}EUR")
print(f"Positions ouvertes: {len(ps)} | Liquidites: {liq:.0f}EUR")
print()

# === 1. PAR CRYPTO ===
print("=" * 75)
print("1. PERFORMANCE PAR CRYPTO")
print("=" * 75)
by_crypto = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0, 'gains':[], 'pertes':[]})
for t in ts:
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    by_crypto[sym]['n'] += 1
    by_crypto[sym]['pnl'] += gain
    if gain > 0:
        by_crypto[sym]['g'] += 1
        by_crypto[sym]['gains'].append(gain)
    else:
        by_crypto[sym]['p'] += 1
        by_crypto[sym]['pertes'].append(gain)

print(f"{'Crypto':<12} {'N':>4} {'WR':>6} {'G':>3} {'P':>3} {'PnL':>8} {'GainMoy':>8} {'PerteMoy':>9} {'Ratio':>6}")
print("-" * 75)
for sym, d in sorted(by_crypto.items(), key=lambda x: x[1]['pnl'], reverse=True):
    wr = d['g']/d['n']*100 if d['n'] else 0
    gm = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    pm = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    ratio = abs(gm/pm) if pm != 0 else 0
    print(f"{sym:<12} {d['n']:>4} {wr:>5.1f}% {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {gm:>+7.2f} {pm:>+8.2f} {ratio:>5.2f}:1")

# Totaux
total_g = sum(1 for t in ts if t.get('gain_eur', 0) > 0)
total_p = sum(1 for t in ts if t.get('gain_eur', 0) <= 0)
total_pnl = sum(t.get('gain_eur', 0) for t in ts)
all_gains = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) > 0]
all_pertes = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) <= 0]
gm_total = sum(all_gains)/len(all_gains) if all_gains else 0
pm_total = sum(all_pertes)/len(all_pertes) if all_pertes else 0
ratio_total = abs(gm_total/pm_total) if pm_total != 0 else 0
print("-" * 75)
print(f"{'TOTAL':<12} {len(ts):>4} {total_g/len(ts)*100:>5.1f}% {total_g:>3} {total_p:>3} {total_pnl:>+7.2f} {gm_total:>+7.2f} {pm_total:>+8.2f} {ratio_total:>5.2f}:1")

# === 2. PAR RAISON DE FERMETURE ===
print()
print("=" * 75)
print("2. PERFORMANCE PAR RAISON DE FERMETURE")
print("=" * 75)
by_r = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0, 'gains':[], 'pertes':[]})
for t in ts:
    r = t.get('raison', t.get('raison_fermeture', '?'))
    # Simplifier
    if 'TEMPS+benefice' in r:
        r = 'TEMPS+benefice'
    elif 'TEMPS-stale' in r:
        r = 'TEMPS-stale'
    elif 'SL-URGENCE-ABSOLU' in r:
        r = 'SL-URGENCE-ABSOLU'
    elif 'SL-RETARD' in r:
        r = 'SL-RETARD'
    elif 'STOP-LOSS' in r:
        r = 'STOP-LOSS'
    elif 'STOP-FIXE' in r:
        r = 'STOP-FIXE'
    elif 'PARTIAL-TP' in r:
        r = 'PARTIAL-TP'
    elif 'TAKE-PROFIT' in r:
        r = 'TAKE-PROFIT'
    elif 'PATTERN-SORTIE' in r:
        r = 'PATTERN-SORTIE'
    elif 'LIVE-EXIT' in r:
        r = 'LIVE-EXIT'
    elif 'LIVE-PARTIAL' in r:
        r = 'LIVE-PARTIAL'
    elif 'STOP-SUIVEUR' in r:
        r = 'STOP-SUIVEUR'
    elif 'FERMETURE MANUELLE' in r:
        r = 'FERMETURE MANUELLE'

    gain = t.get('gain_eur', 0)
    by_r[r]['n'] += 1
    by_r[r]['pnl'] += gain
    if gain > 0:
        by_r[r]['g'] += 1
        by_r[r]['gains'].append(gain)
    else:
        by_r[r]['p'] += 1
        by_r[r]['pertes'].append(gain)

print(f"{'Raison':<25} {'N':>4} {'G':>3} {'P':>3} {'PnL':>8} {'GainMoy':>8} {'PerteMoy':>9} {'%PnL':>7}")
print("-" * 75)
for r, d in sorted(by_r.items(), key=lambda x: x[1]['pnl'], reverse=True):
    gm = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    pm = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    pct = d['pnl']/total_pnl*100 if total_pnl else 0
    print(f"{r:<25} {d['n']:>4} {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {gm:>+7.2f} {pm:>+8.2f} {pct:>+6.0f}%")

# === 3. DETAIL DES PERTES ===
print()
print("=" * 75)
print("3. DETAIL DES PERTES")
print("=" * 75)
pertes = sorted([t for t in ts if t.get('gain_eur', 0) <= 0], key=lambda x: x.get('gain_eur', 0))
print(f"{'Crypto':<12} {'Gain':>7} {'Var%':>7} {'Raison':<40}")
print("-" * 70)
for t in pertes:
    print(f"{t.get('symbole','?'):<12} {t.get('gain_eur',0):>+6.2f} {t.get('variation_pct',0):>+6.2f}% {(t.get('raison',t.get('raison_fermeture','?')))[:39]}")

# === 4. TOP GAINS ===
print()
print("=" * 75)
print("4. TOP GAINS")
print("=" * 75)
gains = sorted([t for t in ts if t.get('gain_eur', 0) > 0], key=lambda x: x.get('gain_eur', 0), reverse=True)[:15]
print(f"{'Crypto':<12} {'Gain':>7} {'Var%':>7} {'Raison':<40}")
print("-" * 70)
for t in gains:
    print(f"{t.get('symbole','?'):<12} {t.get('gain_eur',0):>+6.2f} {t.get('variation_pct',0):>+6.2f}% {(t.get('raison',t.get('raison_fermeture','?')))[:39]}")

# === 5. POSITIONS OUVERTES ===
if ps:
    print()
    print("=" * 75)
    print(f"5. POSITIONS OUVERTES ({len(ps)})")
    print("=" * 75)
    for p in ps:
        print(f"  {p.get('symbole','?'):<12} {p.get('montant_eur',0):.0f}EUR TP={p.get('tp_adaptatif',0)}% SL={p.get('sl_adaptatif',0)}% {p.get('strategie','?')}")

print()
print("=" * 75)
print("FIN")
print("=" * 75)
