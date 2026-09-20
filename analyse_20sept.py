#!/usr/bin/env python3
"""Analyse detaillee du 20 septembre 2026."""
import json
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])

# Filtrer les trades du 20 septembre
trades_20 = []
for t in ts:
    date = t.get('date_fermeture', t.get('date_ouverture', ''))[:10]
    if not date:
        date = t.get('date_ouverture', '')[:10]
    if date == '2026-09-20':
        trades_20.append(t)

print("=" * 75)
print(f"ANALYSE DU 20 SEPTEMBRE — {len(trades_20)} trades")
print("=" * 75)

# 1. Vue d'ensemble
g = sum(1 for t in trades_20 if t.get('gain_eur', 0) > 0)
p = sum(1 for t in trades_20 if t.get('gain_eur', 0) <= 0)
pnl = sum(t.get('gain_eur', 0) for t in trades_20)
gains = [t.get('gain_eur', 0) for t in trades_20 if t.get('gain_eur', 0) > 0]
pertes = [t.get('gain_eur', 0) for t in trades_20 if t.get('gain_eur', 0) <= 0]
print(f"WR: {g}/{len(trades_20)} = {g/len(trades_20)*100:.0f}%")
print(f"PnL: {pnl:+.2f}EUR")
if gains:
    print(f"Gain moyen: +{sum(gains)/len(gains):.2f}EUR (max: +{max(gains):.2f})")
if pertes:
    print(f"Perte moyenne: {sum(pertes)/len(pertes):.2f}EUR (max: {min(pertes):.2f})")
print()

# 2. Tous les trades du 20 sept, chronologique
print("=" * 75)
print("TOUS LES TRADES (chronologique)")
print("=" * 75)
print(f"{'Heure':<6} {'Crypto':<12} {'Gain':>7} {'Var%':>7} {'Raison':<45} {'Source'}")
print("-" * 85)
for t in sorted(trades_20, key=lambda x: x.get('date_fermeture', x.get('date_ouverture', ''))):
    heure = t.get('date_fermeture', t.get('date_ouverture', ''))[11:16]
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    var = t.get('variation_pct', 0)
    raison = (t.get('raison', t.get('raison_fermeture', '?')))[:44]
    src = (t.get('source', '?') or '?')[:15]
    print(f"{heure:<6} {sym:<12} {gain:>+6.2f} {var:>+6.2f}% {raison:<45} {src}")

# 3. Par crypto
print()
print("=" * 75)
print("PAR CRYPTO")
print("=" * 75)
by_crypto = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0})
for t in trades_20:
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    by_crypto[sym]['n'] += 1
    by_crypto[sym]['pnl'] += gain
    if gain > 0: by_crypto[sym]['g'] += 1
    else: by_crypto[sym]['p'] += 1

print(f"{'Crypto':<12} {'N':>4} {'G':>3} {'P':>3} {'PnL':>8} {'WR':>6}")
print("-" * 40)
for sym, d in sorted(by_crypto.items(), key=lambda x: x[1]['pnl']):
    wr = d['g']/d['n']*100 if d['n'] else 0
    print(f"{sym:<12} {d['n']:>4} {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {wr:>5.0f}%")

# 4. Par raison
print()
print("=" * 75)
print("PAR RAISON DE FERMETURE")
print("=" * 75)
by_r = defaultdict(lambda: {'n':0, 'pnl':0})
for t in trades_20:
    r = t.get('raison', t.get('raison_fermeture', '?'))
    if 'SL-RETARD' in r: r = 'SL-RETARD'
    elif 'SL-URGENCE' in r: r = 'SL-URGENCE-ABSOLU'
    elif 'STOP-SUIVEUR' in r: r = 'STOP-SUIVEUR'
    elif 'PATTERN-SORTIE' in r: r = 'PATTERN-SORTIE'
    elif 'TEMPS-stale' in r: r = 'TEMPS-stale'
    elif 'TEMPS+benefice' in r: r = 'TEMPS+benefice'
    elif 'LIVE-EXIT' in r: r = 'LIVE-EXIT'
    elif 'LIVE-PARTIAL' in r: r = 'LIVE-PARTIAL'
    elif 'PARTIAL-TP' in r: r = 'PARTIAL-TP'
    by_r[r]['n'] += 1
    by_r[r]['pnl'] += t.get('gain_eur', 0)

print(f"{'Raison':<25} {'N':>4} {'PnL':>8}")
print("-" * 40)
for r, d in sorted(by_r.items(), key=lambda x: x[1]['pnl']):
    print(f"{r:<25} {d['n']:>4} {d['pnl']:>+7.2f}")

# 5. Comparaison 18 vs 19 vs 20
print()
print("=" * 75)
print("COMPARAISON 18 vs 19 vs 20 SEPTEMBRE")
print("=" * 75)
for jour in ['2026-09-18', '2026-09-19', '2026-09-20']:
    trades_jour = []
    for t in ts:
        date = t.get('date_fermeture', t.get('date_ouverture', ''))[:10]
        if not date:
            date = t.get('date_ouverture', '')[:10]
        if date == jour:
            trades_jour.append(t)
    if not trades_jour:
        continue
    g = sum(1 for t in trades_jour if t.get('gain_eur', 0) > 0)
    p = sum(1 for t in trades_jour if t.get('gain_eur', 0) <= 0)
    pnl = sum(t.get('gain_eur', 0) for t in trades_jour)
    sl = sum(1 for t in trades_jour if 'SL-RETARD' in t.get('raison', t.get('raison_fermeture', '')))
    suiveur = sum(1 for t in trades_jour if 'STOP-SUIVEUR' in t.get('raison', t.get('raison_fermeture', '')))
    # Cryptos uniques
    cryptos = set(t.get('symbole', '?') for t in trades_jour)
    print(f"{jour}: {len(trades_jour):3d} trades | WR {g/len(trades_jour)*100:.0f}% | PnL {pnl:+.2f}EUR | SL={sl} Suiveur={suiveur} | Cryptos: {', '.join(sorted(cryptos))}")

# 6. Heures des trades perdants
print()
print("=" * 75)
print("HEURES DES PERTES (20 sept)")
print("=" * 75)
for t in sorted(trades_20, key=lambda x: x.get('date_fermeture', '')):
    if t.get('gain_eur', 0) <= 0:
        heure = t.get('date_fermeture', t.get('date_ouverture', ''))[11:16]
        sym = t.get('symbole', '?')
        gain = t.get('gain_eur', 0)
        var = t.get('variation_pct', 0)
        raison = (t.get('raison', t.get('raison_fermeture', '?')))[:50]
        print(f"  {heure} {sym:<12} {gain:>+6.2f}EUR var={var:>+5.2f}% {raison}")

print()
print("=" * 75)
print("FIN")
print("=" * 75)
