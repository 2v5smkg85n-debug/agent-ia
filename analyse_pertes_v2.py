#!/usr/bin/env python3
"""Analyse profonde des pertes par strategie et par raison de fermeture."""
import json
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])
ps = pf.get('positions', [])
liq = pf.get('liquidites', 0)
frais = pf.get('total_frais', 0)
cap = liq + sum(p.get('montant_eur', 0) for p in ps)

print("=" * 70)
print("ANALYSE DES PERTES — PAR STRATEGIE ET RAISON DE FERMETURE")
print("=" * 70)
print(f"Capital: {cap:.2f}EUR | PnL net: {cap-1000:+.2f}EUR | Trades: {len(ts)} | Frais: {frais:.2f}EUR")
print()

# === 1. PAR STRATEGIE ===
print("=" * 70)
print("1. PERFORMANCE PAR STRATEGIE")
print("=" * 70)
by_strat = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0, 'gains':[], 'pertes':[]})
for t in ts:
    s = t.get('strategie', t.get('source', '?')) or '?'
    gain = t.get('gain_eur', 0)
    by_strat[s]['n'] += 1
    by_strat[s]['pnl'] += gain
    if gain > 0:
        by_strat[s]['g'] += 1
        by_strat[s]['gains'].append(gain)
    else:
        by_strat[s]['p'] += 1
        by_strat[s]['pertes'].append(gain)

print(f"{'Strategie':<35} {'N':>4} {'WR':>6} {'G':>3} {'P':>3} {'PnL':>8} {'GainMoy':>8} {'PerteMoy':>9} {'Ratio':>6}")
print("-" * 90)
for s, d in sorted(by_strat.items(), key=lambda x: x[1]['pnl']):
    wr = d['g']/d['n']*100 if d['n'] else 0
    gm = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    pm = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    ratio = abs(gm/pm) if pm != 0 else 0
    print(f"{s:<35} {d['n']:>4} {wr:>5.1f}% {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {gm:>+7.2f} {pm:>+8.2f} {ratio:>5.2f}:1")

# === 2. PAR RAISON DE FERMETURE ===
print()
print("=" * 70)
print("2. PERFORMANCE PAR RAISON DE FERMETURE")
print("=" * 70)
by_r = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0, 'gains':[], 'pertes':[]})
for t in ts:
    r = t.get('raison', t.get('raison_fermeture', '?'))
    # Simplifier la raison (enlever les pourcentages variables)
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
print("-" * 80)
total_pnl = sum(t.get('gain_eur', 0) for t in ts)
for r, d in sorted(by_r.items(), key=lambda x: x[1]['pnl']):
    gm = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    pm = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    pct = d['pnl']/total_pnl*100 if total_pnl else 0
    print(f"{r:<25} {d['n']:>4} {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {gm:>+7.2f} {pm:>+8.2f} {pct:>+6.0f}%")

# === 3. ANALYSE DES PERTES ===
print()
print("=" * 70)
print("3. DETAIL DES PERTES (trades perdants)")
print("=" * 70)
pertes = [t for t in ts if t.get('gain_eur', 0) <= 0]
pertes.sort(key=lambda x: x.get('gain_eur', 0))
print(f"{'Symbole':<12} {'Gain':>7} {'Var%':>7} {'Strategie':<25} {'Raison':<35} {'Source'}")
print("-" * 100)
for t in pertes:
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    var = t.get('variation_pct', 0)
    strat = (t.get('strategie', '?') or '?')[:24]
    raison = (t.get('raison', t.get('raison_fermeture', '?')))[:34]
    src = (t.get('source', '?') or '?')[:15]
    print(f"{sym:<12} {gain:>+6.2f} {var:>+6.2f}% {strat:<25} {raison:<35} {src}")

# === 4. ANALYSE DES GAINS ===
print()
print("=" * 70)
print("4. DETAIL DES GAINS (trades gagnants)")
print("=" * 70)
gains = [t for t in ts if t.get('gain_eur', 0) > 0]
gains.sort(key=lambda x: x.get('gain_eur', 0), reverse=True)
print(f"{'Symbole':<12} {'Gain':>7} {'Var%':>7} {'Strategie':<25} {'Raison':<35} {'Source'}")
print("-" * 100)
for t in gains:
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    var = t.get('variation_pct', 0)
    strat = (t.get('strategie', '?') or '?')[:24]
    raison = (t.get('raison', t.get('raison_fermeture', '?')))[:34]
    src = (t.get('source', '?') or '?')[:15]
    print(f"{sym:<12} {gain:>+6.2f} {var:>+6.2f}% {strat:<25} {raison:<35} {src}")

# === 5. PAR CRYPTO ===
print()
print("=" * 70)
print("5. PERFORMANCE PAR CRYPTO")
print("=" * 70)
by_crypto = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0})
for t in ts:
    sym = t.get('symbole', '?')
    gain = t.get('gain_eur', 0)
    by_crypto[sym]['n'] += 1
    by_crypto[sym]['pnl'] += gain
    if gain > 0:
        by_crypto[sym]['g'] += 1
    else:
        by_crypto[sym]['p'] += 1

print(f"{'Crypto':<12} {'N':>4} {'WR':>6} {'G':>3} {'P':>3} {'PnL':>8}")
print("-" * 40)
for sym, d in sorted(by_crypto.items(), key=lambda x: x[1]['pnl']):
    wr = d['g']/d['n']*100 if d['n'] else 0
    print(f"{sym:<12} {d['n']:>4} {wr:>5.1f}% {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f}")

# === 6. PROFESSEUR ===
prof_trades = [t for t in ts if 'prof' in (t.get('source', '') or '').lower()]
if prof_trades:
    print()
    print("=" * 70)
    print(f"6. TRADES DU PROFESSEUR VIRTUEL ({len(prof_trades)} trades)")
    print("=" * 70)
    pg = sum(1 for t in prof_trades if t.get('gain_eur', 0) > 0)
    pp = sum(1 for t in prof_trades if t.get('gain_eur', 0) <= 0)
    ppnl = sum(t.get('gain_eur', 0) for t in prof_trades)
    print(f"WR: {pg}/{len(prof_trades)} = {pg/len(prof_trades)*100:.0f}% | PnL: {ppnl:+.2f}EUR")
    for t in prof_trades:
        print(f"  {t.get('symbole','?'):12s} {t.get('gain_eur',0):+.2f}EUR var={t.get('variation_pct',0):+.2f}% {t.get('raison',t.get('raison_fermeture','?'))[:40]} [{t.get('strategie','?')}]")

# === 7. POSITIONS OUVERTES ===
if ps:
    print()
    print("=" * 70)
    print(f"7. POSITIONS OUVERTES ({len(ps)})")
    print("=" * 70)
    for p in ps:
        print(f"  {p.get('symbole','?'):12s} {p.get('montant_eur',0):.0f}EUR TP={p.get('tp_adaptatif',0)}% SL={p.get('sl_adaptatif',0)}% {p.get('strategie','?')} [{p.get('source','?')}]")

print()
print("=" * 70)
print("FIN DE L'ANALYSE")
print("=" * 70)
