#!/usr/bin/env python3
"""Analyse profonde pour trouver des ameliorations."""
import json
import re
from collections import defaultdict

pf = json.load(open('paper_trading.json'))
ts = pf.get('trades_fermes', [])

# 1. Performance par heure d'ouverture
by_hour = defaultdict(lambda: {'n':0, 'g':0, 'pnl':0, 'gains':[], 'pertes':[]})
for t in ts:
    heure_str = t.get('date_ouverture', t.get('date', ''))
    try:
        h = int(heure_str[11:13])
    except:
        continue
    raison = t.get('raison_fermeture', t.get('raison',''))
    m = re.search(r'([+-][\d.]+)%', raison)
    var = float(m.group(1)) if m else 0
    gain = t.get('gain_eur', 0)
    by_hour[h]['n'] += 1
    by_hour[h]['pnl'] += gain
    if gain > 0:
        by_hour[h]['g'] += 1
        by_hour[h]['gains'].append(var)
    else:
        by_hour[h]['pertes'].append(var)

print("=== PERFORMANCE PAR HEURE D OUVERTURE ===")
for h in sorted(by_hour.keys()):
    d = by_hour[h]
    wr = d['g']/d['n']*100 if d['n'] else 0
    avg_g = sum(d['gains'])/len(d['gains']) if d['gains'] else 0
    avg_p = sum(d['pertes'])/len(d['pertes']) if d['pertes'] else 0
    print(f"  {h:2d}h n={d['n']:3d} WR={wr:5.1f}% PnL={d['pnl']:+.2f} avg_g={avg_g:+.2f}% avg_p={avg_p:+.2f}%")

# 2. Score vs resultat
print()
print("=== SCORE vs RESULTAT ===")
by_score = defaultdict(lambda: {'n':0, 'g':0, 'pnl':0})
for t in ts:
    s = t.get('score', t.get('score_final', 0))
    try: s = int(s)
    except: s = 0
    bucket = (s // 2) * 2
    by_score[bucket]['n'] += 1
    by_score[bucket]['pnl'] += t.get('gain_eur', 0)
    if t.get('gain_eur', 0) > 0: by_score[bucket]['g'] += 1
for s in sorted(by_score.keys()):
    d = by_score[s]
    wr = d['g']/d['n']*100 if d['n'] else 0
    print(f"  score {s:2d}-{s+1:2d} n={d['n']:3d} WR={wr:5.1f}% PnL={d['pnl']:+.2f}")

# 3. Analyser la duree de detention
print()
print("=== DUREE DE DETENTION (via raison TEMPS) ===")
temps_trades = [t for t in ts if 'TEMPS' in t.get('raison_fermeture', t.get('raison',''))]
for t in temps_trades:
    sym = t.get('symbole','?')
    gain = t.get('gain_eur', 0)
    raison = t.get('raison_fermeture', t.get('raison','?'))[:35]
    print(f"  {sym:12s} gain={gain:+.2f} {raison}")

# 4. Correlation: nombre de positions ouvertes simultanement vs gain
print()
print("=== CRYPTO LES PLUS VOLATILES (gains extremes) ===")
all_vars = []
for t in ts:
    raison = t.get('raison_fermeture', t.get('raison',''))
    m = re.search(r'([+-][\d.]+)%', raison)
    if m:
        all_vars.append((t.get('symbole','?'), float(m.group(1)), t.get('gain_eur',0)))
all_vars.sort(key=lambda x: x[1], reverse=True)
print("  Top gains %:")
for sym, var, gain in all_vars[:5]:
    print(f"    {sym:12s} var={var:+.2f}% gain={gain:+.2f}")
print("  Top pertes %:")
for sym, var, gain in all_vars[-5:]:
    print(f"    {sym:12s} var={var:+.2f}% gain={gain:+.2f}")

# 5. Analyser les frais
print()
print("=== FRAIS ===")
total_frais = pf.get('total_frais', 0)
total_pnl = sum(t.get('gain_eur', 0) for t in ts)
print(f"  Frais totaux: {total_frais:.2f}EUR")
print(f"  PnL brut: {total_pnl:.2f}EUR")
print(f"  PnL net (avec frais): {total_pnl - total_frais:.2f}EUR")
print(f"  Frais par trade: {total_frais/len(ts):.3f}EUR" if ts else "")
print(f"  Impact frais sur PnL: {total_frais/(abs(total_pnl)+0.01)*100:.0f}%")

# 6. Quelle proportion du TP est atteinte?
print()
print("=== TP ATTEINT? ===")
tp_hits = sum(1 for t in ts if 'TAKE-PROFIT' in t.get('raison_fermeture', t.get('raison','')))
partial_hits = sum(1 for t in ts if 'PARTIAL' in t.get('raison_fermeture', t.get('raison','')))
temps_benefice = sum(1 for t in ts if 'TEMPS+benefice' in t.get('raison_fermeture', t.get('raison','')))
sl_hits = sum(1 for t in ts if 'STOP' in t.get('raison_fermeture', t.get('raison','')))
temps_stale = sum(1 for t in ts if 'TEMPS-stale' in t.get('raison_fermeture', t.get('raison','')))
autres = len(ts) - tp_hits - partial_hits - temps_benefice - sl_hits - temps_stale
print(f"  TAKE-PROFIT: {tp_hits} ({tp_hits/len(ts)*100:.0f}%)" if ts else "")
print(f"  PARTIAL-TP: {partial_hits} ({partial_hits/len(ts)*100:.0f}%)" if ts else "")
print(f"  TEMPS+benefice: {temps_benefice} ({temps_benefice/len(ts)*100:.0f}%)" if ts else "")
print(f"  STOP-LOSS/SL: {sl_hits} ({sl_hits/len(ts)*100:.0f}%)" if ts else "")
print(f"  TEMPS-stale: {temps_stale} ({temps_stale/len(ts)*100:.0f}%)" if ts else "")
print(f"  Autres: {autres} ({autres/len(ts)*100:.0f}%)" if ts else "")
