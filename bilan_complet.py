#!/usr/bin/env python3
"""Bilan complet: apprentissage du professeur + gains du bot."""
import json
import os
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])
ps = pf.get('positions', [])
liq = pf.get('liquidites', 0)
frais = pf.get('total_frais', 0)
cap = liq + sum(p.get('montant_eur', 0) for p in ps)

print("=" * 75)
print("BILAN COMPLET — APPRENTISSAGE & GAINS")
print("=" * 75)
print(f"Capital: {cap:.2f}EUR | PnL net: {cap-1000:+.2f}EUR")
print(f"Trades fermes: {len(ts)} | Positions ouvertes: {len(ps)}")
print(f"Liquidites: {liq:.0f}EUR | Frais totaux: {frais:.2f}EUR")
print()

# === 1. PERFORMANCE GLOBALE ===
print("=" * 75)
print("1. PERFORMANCE GLOBALE")
print("=" * 75)
if ts:
    g = sum(1 for t in ts if t.get('gain_eur', 0) > 0)
    p = sum(1 for t in ts if t.get('gain_eur', 0) <= 0)
    gains = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) > 0]
    pertes = [t.get('gain_eur', 0) for t in ts if t.get('gain_eur', 0) <= 0]
    pnl = sum(t.get('gain_eur', 0) for t in ts)
    gm = sum(gains)/len(gains) if gains else 0
    pm = sum(pertes)/len(pertes) if pertes else 0
    ratio = abs(gm/pm) if pm != 0 else 0
    wr = g/len(ts)*100 if ts else 0
    esperance = (g/len(ts)) * gm - (p/len(ts)) * pm if ts else 0
    print(f"Win Rate: {wr:.1f}% ({g}G / {p}P)")
    print(f"Gain moyen: +{gm:.2f}EUR | Perte moyenne: {pm:.2f}EUR")
    print(f"Ratio gain/perte: {ratio:.2f}:1")
    print(f"PnL trades: {pnl:+.2f}EUR | Frais: {frais:.2f}EUR")
    print(f"Esperance par trade: {esperance:+.2f}EUR")
    print(f"Meilleur trade: +{max(gains):.2f}EUR | Pire trade: {min(pertes):.2f}EUR")
print()

# === 2. APPRENTISSAGE DU PROFESSEUR ===
print("=" * 75)
print("2. APPRENTISSAGE DU PROFESSEUR VIRTUEL")
print("=" * 75)

# Stats du professeur
prof_stats_file = 'professeur_stats.json'
if os.path.exists(prof_stats_file):
    stats = json.load(open(prof_stats_stats_file))
else:
    stats = {}

# Par strategie
print("\n  PAR STRATEGIE:")
strats = stats.get('par_strategie', {})
for s, d in sorted(strats.items(), key=lambda x: x[1].get('pnl', 0), reverse=True):
    n = d.get('n', 0)
    wr_s = d.get('wr', 0)
    pnl_s = d.get('pnl', 0)
    boost = d.get('boost', 0)
    print(f"    {s:30s} n={n:3d} WR={wr_s:5.1f}% PnL={pnl_s:+.2f}EUR boost={boost:+d}")

# Par crypto
print("\n  PAR CRYPTO (apprentissage professeur):")
cryptos = stats.get('par_crypto', {})
for c, d in sorted(cryptos.items(), key=lambda x: x[1].get('pnl', 0), reverse=True):
    n = d.get('n', 0)
    wr_c = d.get('wr', 0)
    pnl_c = d.get('pnl', 0)
    bloque = "BLOQUE" if (n >= 15 and wr_c < 50 and pnl_c < 0) else ""
    print(f"    {c:14s} n={n:3d} WR={wr_c:5.1f}% PnL={pnl_c:+.2f}EUR {bloque}")

# === 3. PERFORMANCE PAR CRYPTO (trades reels) ===
print()
print("=" * 75)
print("3. PERFORMANCE PAR CRYPTO (trades reels)")
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

print(f"  {'Crypto':<12} {'N':>4} {'WR':>6} {'G':>3} {'P':>3} {'PnL':>8} {'GainMoy':>8} {'PerteMoy':>9} {'Ratio':>6}")
print("  " + "-" * 70)
for sym, d in sorted(by_crypto.items(), key=lambda x: x[1]['pnl'], reverse=True):
    wr = d['g']/d['n']*100 if d['n'] else 0
    gm = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    pm = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    ratio = abs(gm/pm) if pm != 0 else 0
    print(f"  {sym:<12} {d['n']:>4} {wr:>5.1f}% {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {gm:>+7.2f} {pm:>+8.2f} {ratio:>5.2f}:1")

# === 4. RAISONS DE FERMETURE ===
print()
print("=" * 75)
print("4. RAISONS DE FERMETURE")
print("=" * 75)
by_r = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0})
for t in ts:
    r = t.get('raison', t.get('raison_fermeture', '?'))
    if 'TEMPS+benefice' in r: r = 'TEMPS+benefice'
    elif 'TEMPS-stale' in r: r = 'TEMPS-stale'
    elif 'SL-URGENCE-ABSOLU' in r: r = 'SL-URGENCE-ABSOLU'
    elif 'SL-RETARD' in r: r = 'SL-RETARD'
    elif 'STOP-LOSS' in r: r = 'STOP-LOSS'
    elif 'STOP-FIXE' in r: r = 'STOP-FIXE'
    elif 'PARTIAL-TP' in r: r = 'PARTIAL-TP'
    elif 'TAKE-PROFIT' in r: r = 'TAKE-PROFIT'
    elif 'PATTERN-SORTIE' in r: r = 'PATTERN-SORTIE'
    elif 'LIVE-EXIT' in r: r = 'LIVE-EXIT'
    elif 'LIVE-PARTIAL' in r: r = 'LIVE-PARTIAL'
    elif 'STOP-SUIVEUR' in r: r = 'STOP-SUIVEUR'
    elif 'FERMETURE MANUELLE' in r: r = 'FERMETURE MANUELLE'
    gain = t.get('gain_eur', 0)
    by_r[r]['n'] += 1
    by_r[r]['pnl'] += gain
    if gain > 0: by_r[r]['g'] += 1
    else: by_r[r]['p'] += 1

total_pnl = sum(t.get('gain_eur', 0) for t in ts)
print(f"  {'Raison':<25} {'N':>4} {'G':>3} {'P':>3} {'PnL':>8} {'%PnL':>7}")
print("  " + "-" * 55)
for r, d in sorted(by_r.items(), key=lambda x: x[1]['pnl'], reverse=True):
    pct = d['pnl']/total_pnl*100 if total_pnl else 0
    print(f"  {r:<25} {d['n']:>4} {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {pct:>+6.0f}%")

# === 5. EVOLUTION TEMPORELLE ===
print()
print("=" * 75)
print("5. EVOLUTION (par jour)")
print("=" * 75)
by_day = defaultdict(lambda: {'n':0, 'g':0, 'p':0, 'pnl':0})
for t in ts:
    date = t.get('date_fermeture', t.get('date_ouverture', ''))[:10]
    if not date:
        date = t.get('date_ouverture', '')[:10]
    gain = t.get('gain_eur', 0)
    by_day[date]['n'] += 1
    by_day[date]['pnl'] += gain
    if gain > 0: by_day[date]['g'] += 1
    else: by_day[date]['p'] += 1

print(f"  {'Date':<12} {'N':>4} {'G':>3} {'P':>3} {'PnL':>8} {'WR':>6}")
print("  " + "-" * 45)
cumul = 0
for date in sorted(by_day.keys()):
    d = by_day[date]
    wr = d['g']/d['n']*100 if d['n'] else 0
    cumul += d['pnl']
    print(f"  {date:<12} {d['n']:>4} {d['g']:>3} {d['p']:>3} {d['pnl']:>+7.2f} {wr:>5.0f}%  (cumul: {cumul:+.2f})")

# === 6. POSITIONS OUVERTES ===
if ps:
    print()
    print("=" * 75)
    print(f"6. POSITIONS OUVERTES ({len(ps)})")
    print("=" * 75)
    for p in ps:
        print(f"  {p.get('symbole','?'):<12} {p.get('montant_eur',0):.0f}EUR TP={p.get('tp_adaptatif',0)}% SL={p.get('sl_adaptatif',0)}% {p.get('strategie','?')}")

print()
print("=" * 75)
print("FIN DU BILAN")
print("=" * 75)
