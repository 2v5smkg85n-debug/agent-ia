#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyse_positions.py — analyse positions ouvertes + trades fermés + pertes."""
import json, os
from datetime import datetime

PF = "paper_trading.json"
pf = json.load(open(PF))

print("=" * 60)
print("ANALYSE PAPER TRADING")
print("=" * 60)
cap = pf.get("capital_initial", 1000)
liq = pf.get("liquidites", 0)
pos = pf.get("positions", [])
val = liq + sum(p.get("quantite", 0) * p.get("prix_actuel", p.get("prix_entree", 0)) for p in pos)
print(f"Capital initial: {cap:.2f}EUR")
print(f"Liquidités: {liq:.2f}EUR")
print(f"Positions ouvertes: {len(pos)}")
print(f"Valeur totale: {val:.2f}EUR")
print(f"PnL: {val-cap:+.2f}EUR ({(val/cap-1)*100:+.2f}%)")
print(f"Frais payés: {pf.get('total_frais', 0):.2f}EUR")

# --- positions ouvertes ---
print("\n" + "=" * 60)
print("POSITIONS OUVERTES")
print("=" * 60)
if not pos:
    print("  Aucune position ouverte.")
now = datetime.now()
for p in pos:
    pe = p.get("prix_entree", 0)
    pa = p.get("prix_actuel", pe)
    var = (pa/pe - 1)*100 if pe else 0
    var_pic = (p.get("prix_peak", pa)/pe - 1)*100 if pe else 0
    try:
        dt = datetime.strptime(p.get("date_ouverture", ""), "%Y-%m-%d %H:%M")
        age_min = (now - dt).total_seconds() / 60
    except Exception:
        age_min = -1
    print(f"  {p.get('nom','?'):14s} {p.get('symbole','?'):10s} strat={p.get('strategie','?'):20s}")
    print(f"    entrée {pe:.4f} | actuel {pa:.4f} | pic {p.get('prix_peak',pe):.4f}")
    print(f"    var {var:+.2f}% | pic {var_pic:+.2f}% | age {age_min:.0f}min | qty {p.get('quantite',0):.6f}")
    print(f"    SL {p.get('sl','?')} | TP {p.get('tp','?')} | montant {p.get('montant_eur',0):.2f}EUR")

# --- trades fermés ---
print("\n" + "=" * 60)
print("TRADES FERMÉS")
print("=" * 60)
hist = pf.get("historique", [])
print(f"Total fermés: {len(hist)}")
if hist:
    # par raison de sortie
    par_raison = {}
    for t in hist:
        r = t.get("raison", "?")
        # normalise (enlève le %)
        rk = r.split("(")[0].strip() if "(" in r else r.strip()
        par_raison.setdefault(rk, []).append(t)
    print(f"\n  {'Raison':22s} {'n':>3s} {'PnL total':>10s} {'avg':>8s} {'win%':>6s}")
    print("  " + "-" * 55)
    for rk in sorted(par_raison, key=lambda k: sum(t.get('gain_eur',0) for t in par_raison[k])):
        ts = par_raison[rk]
        pnls = [t.get("gain_eur", 0) for t in ts]
        tot = sum(pnls)
        avg = tot/len(ts) if ts else 0
        wins = sum(1 for x in pnls if x > 0)
        wr = wins/len(ts)*100 if ts else 0
        print(f"  {rk:22s} {len(ts):3d} {tot:+9.2f}€ {avg:+7.2f}€ {wr:5.0f}%")

# --- détail des PERTES ---
print("\n" + "=" * 60)
print("DÉTAIL DES PERTES (trades négatifs)")
print("=" * 60)
pertes = [t for t in hist if t.get("gain_eur", 0) < 0]
print(f"Total pertes: {len(pertes)} trades, {sum(t.get('gain_eur',0) for t in pertes):+.2f}€")
for t in sorted(pertes, key=lambda x: x.get('gain_eur',0)):
    r = t.get("raison", "?")
    rk = r.split("(")[0].strip() if "(" in r else r.strip()
    var = t.get("variation_pct", 0)
    print(f"  {t.get('nom','?'):14s} {rk:22s} var {var:+.2f}% pnl {t.get('gain_eur',0):+.2f}€ | strat={t.get('strategie','?')}")

# --- focus temps ---
print("\n" + "=" * 60)
print("FOCUS: exits liés au TEMPS")
print("=" * 60)
temps = [t for t in hist if "TEMPS" in t.get("raison", "")]
if temps:
    pnls = [t.get("gain_eur",0) for t in temps]
    print(f"Trades fermés par TEMPS: {len(temps)}")
    print(f"  PnL total: {sum(pnls):+.2f}€ | avg {sum(pnls)/len(temps):+.2f}€")
    print(f"  Gagnants: {sum(1 for x in pnls if x>0)} | Perdants: {sum(1 for x in pnls if x<0)}")
    perdants_temps = [t for t in temps if t.get("gain_eur",0) < 0]
    if perdants_temps:
        print(f"\n  PERTES par temps ({len(perdants_temps)}):")
        for t in perdants_temps:
            print(f"    {t.get('nom','?'):14s} {t.get('raison','?'):30s} pnl {t.get('gain_eur',0):+.2f}€ strat={t.get('strategie','?')}")
else:
    print("Aucun trade fermé par TEMPS.")
