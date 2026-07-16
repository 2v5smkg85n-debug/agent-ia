#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Affiche le solde complet (paper + Revolut reel)."""
import json, os

DOSSIER = os.getcwd()

print("=" * 50)
print("PORTEFEUILLE PAPER")
print("=" * 50)
d = json.load(open(os.path.join(DOSSIER, "paper_trading.json")))
cap_init = d.get("capital_initial", 0)
liq = d.get("liquidites", 0)
pic = d.get("pic_capital", 0)
frais = d.get("total_frais", 0)
pos = d.get("positions", [])
tf = d.get("trades_fermes", [])
valeur_pos = sum(p.get("montant_eur", 0) for p in pos)
total = liq + valeur_pos
pnl = total - cap_init
print(f"Capital initial  : {cap_init:.2f} EUR")
print(f"Liquidites       : {liq:.2f} EUR")
print(f"Valeur positions : {valeur_pos:.2f} EUR")
print(f"Total (cash+pos) : {total:.2f} EUR")
print(f"PnL              : {pnl:+.2f} EUR")
print(f"Pic capital      : {pic:.2f} EUR")
print(f"Frais cumules    : {frais:.2f} EUR")
print(f"Dernier tick     : {d.get('dernier_tick')}")
print(f"Positions ouvertes: {len(pos)}")
for p in pos:
    print(f"  - {p.get('symbole')} ({p.get('nom')}) | {p.get('quantite',0):.6f} @ {p.get('prix_entree')} | {p.get('montant_eur',0):.2f} EUR | depuis {p.get('date_ouverture')}")
print(f"Trades fermes    : {len(tf)}")
if tf:
    wins = [t for t in tf if t.get("variation_pct", 0) > 0]
    wr = 100 * len(wins) / len(tf) if tf else 0
    print(f"Win rate         : {len(wins)}/{len(tf)} = {wr:.0f}%")
    last = tf[-1]
    print(f"Dernier trade    : {last.get('symbole','?')} | {last.get('raison','?')} | var {last.get('variation_pct',0):+.2f}%")

print()
print("=" * 50)
print("SOLDE REVOLUT REEL")
print("=" * 50)
try:
    r = json.load(open(os.path.join(DOSSIER, "revolut_mirror.json")))
    print(f"Live depuis : {r.get('debut_live')}")
    print(f"Mode live   : {r.get('live')}")
    achats = r.get("achats", [])
    ventes = r.get("ventes", [])
    print(f"Achats reels: {len(achats)}")
    print(f"Ventes reelles: {len(ventes)}")
    for a in achats[-3:]:
        q = a.get("quote_size", a.get("montant", "?"))
        print(f"  ACHAT {a.get('symbol','?')} | {q} EUR")
    for v in ventes[-3:]:
        q = v.get("quote_size", v.get("montant", "?"))
        print(f"  VENTE {v.get('symbol','?')} | {q} EUR")
except Exception as e:
    print(f"revolut_mirror indispo: {e}")

print()
print("=" * 50)
print("SERVICES")
print("=" * 50)
import subprocess
for s in ["paper_trading", "pont_revolut", "protection", "dashboard", "telegram_monitor"]:
    try:
        st = subprocess.check_output(["systemctl", "is-active", s], text=True).strip()
    except Exception:
        st = "?"
    print(f"  {s}: {st}")
