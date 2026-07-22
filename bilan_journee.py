#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bilan_journee.py — bilan paper trading (portefeuille + trades du jour + sorties)."""
import json, os
from collections import Counter
os.chdir(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv()
except: pass

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])
positions = pf.get("positions", [])
liquidites = pf.get("liquidites", 0)
cap0 = pf.get("capital_initial", 1000)

val_pos = sum(p["quantite"] * p.get("prix_actuel", p["prix_entree"]) for p in positions)
valeur = liquidites + val_pos
pnl = valeur - cap0
wins = [t for t in trades if t["gain_eur"] > 0]
losses = [t for t in trades if t["gain_eur"] <= 0]
wr = len(wins)/len(trades)*100 if trades else 0

print("=" * 54)
print("              BILAN PAPER TRADING")
print("=" * 54)
print(f"Capital initial : {cap0:.0f}€")
print(f"Valeur actuelle  : {valeur:.2f}€")
print(f"PnL total        : {pnl:+.2f}€ ({pnl/cap0*100:+.2f}%)")
print(f"Liquidités       : {liquidites:.2f}€")
print(f"Positions ouvertes: {len(positions)}")
print(f"Frais cumulés    : {pf.get('total_frais',0):.2f}€")
print(f"Trades fermés    : {len(trades)}  ({len(wins)}g / {len(losses)}p, {wr:.0f}% win)")
if wins:
    print(f"Gain moyen/gagnant : {sum(t['gain_eur'] for t in wins)/len(wins):+.3f}€")
if losses:
    print(f"Perte moyenne/perdant: {sum(t['gain_eur'] for t in losses)/len(losses):+.3f}€")

# === AUJOURD'HUI (depuis le déploiement exit avancé, 2026-07-22) ===
auj = [t for t in trades if t.get("date_fermeture","").startswith("2026-07-22")]
print("\n" + "-" * 54)
print(f"  JOURNÉE DU 2026-07-22 (depuis exit avancé)")
print("-" * 54)
print(f"Trades fermés aujourd'hui : {len(auj)}")
if auj:
    pnl_auj = sum(t["gain_eur"] for t in auj)
    wg = [t for t in auj if t["gain_eur"]>0]; pg=[t for t in auj if t["gain_eur"]<=0]
    print(f"PnL du jour : {pnl_auj:+.2f}€  ({len(wg)}g/{len(pg)}p)")
    print("Sorties par raison :")
    rc = Counter(t.get("raison","?") for t in auj)
    for r,n in rc.most_common():
        pr = sum(t["gain_eur"] for t in auj if t.get("raison")==r)
        print(f"  {r:18s}: {n:2d} trades, {pr:+.2f}€")
    print("Détail (10 derniers) :")
    for t in auj[-10:]:
        print(f"  {t.get('date_fermeture','')[-5:]} {t.get('symbole','')[:11]:11s} {t.get('raison','?')[:16]:16s} {t['gain_eur']:+.2f}€ ({t.get('variation_pct',0):+.1f}%)")
else:
    print("(aucun trade fermé aujourd'hui)")

# === HISTORIQUE COMPLET par raison ===
print("\n" + "-" * 54)
print("  HISTORIQUE COMPLET — sorties par raison")
print("-" * 54)
rc = Counter(t.get("raison","?") for t in trades)
for r,n in rc.most_common():
    pr = sum(t["gain_eur"] for t in trades if t.get("raison")==r)
    print(f"  {r:18s}: {n:3d} trades, total {pr:+.2f}€ (avg {pr/n:+.3f}€)")

# === CLASSEMENT STRATÉGIES ===
print("\n" + "-" * 54)
print("  TOP STRATÉGIES (live)")
print("-" * 54)
try:
    cs = json.load(open("classement_strategies.json"))
    rows = []
    for actif, d in cs.items():
        for s in d.get("strategies", []):
            rows.append((s.get("strategie","?"), actif, s.get("live_n",0), s.get("live_wr",0), s.get("live_pnl",0)))
    rows.sort(key=lambda x: x[4], reverse=True)
    for nom,actif,n,wr_,p in rows[:8]:
        print(f"  {nom[:22]:22s} {actif[:8]:8s} n={n:2d} wr={wr_:.0f}% pnl={p:+.2f}€")
    print(f"  ... ({len(rows)} stratégies au total)")
except Exception as e:
    print(f"  (classement indispo: {e})")

# === POSITIONS OUVERTES ===
if positions:
    print("\n" + "-" * 54)
    print("  POSITIONS OUVERTES")
    print("-" * 54)
    for p in positions:
        var = (p.get("prix_actuel",p["prix_entree"]) - p["prix_entree"])/p["prix_entree"]*100
        pic = (p.get("prix_peak",p["prix_entree"]) - p["prix_entree"])/p["prix_entree"]*100
        pc = " [partial]" if p.get("partiellement_clote") else ""
        print(f"  {p['symbole'][:11]:11s} {p.get('strategie','?')[:16]:16s} var {var:+.2f}% pic {pic:+.2f}%{pc}")

print("\n" + "=" * 54)
