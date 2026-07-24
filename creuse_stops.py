#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""creuse_stops.py — détail complet des trades fermés par STOP-LOSS / STOP-FIXE."""
import json
from datetime import datetime

pf = json.load(open("paper_trading.json"))
hist = pf.get("historique", [])

stops = [t for t in hist if "STOP" in t.get("raison", "")]
print("=" * 70)
print(f"DÉTAIL DES STOPS ({len(stops)} trades)")
print("=" * 70)

for i, t in enumerate(stops, 1):
    print(f"\n--- Stop #{i} ---")
    print(f"  Actif:     {t.get('nom','?')} ({t.get('symbole','?')}) | marché {t.get('marche','?')}")
    print(f"  Stratégie: {t.get('strategie','?')}")
    print(f"  Signal:    {t.get('signal_raison','?')}")
    print(f"  Raison sortie: {t.get('raison','?')}")
    pe = t.get('prix_entree', 0); ps = t.get('prix_sortie', 0)
    print(f"  Prix:      entrée {pe:.4f} -> sortie {ps:.4f} | var {t.get('variation_pct',0):+.2f}%")
    print(f"  P&L:       {t.get('gain_eur',0):+.2f}€ | montant {t.get('montant_eur',0):.2f}€ | frais {t.get('frais_total',0):.2f}€")
    # durée
    try:
        d1 = datetime.strptime(t.get('date_ouverture',''), "%Y-%m-%d %H:%M")
        d2 = datetime.strptime(t.get('date_fermeture',''), "%Y-%m-%d %H:%M")
        age = (d2 - d1).total_seconds() / 60
        print(f"  Durée:     {age:.0f} min | ouvert {t.get('date_ouverture','')} fermé {t.get('date_fermeture','')}")
    except Exception:
        print(f"  Ouvert {t.get('date_ouverture','')} fermé {t.get('date_fermeture','')}")

# synthèse
print("\n" + "=" * 70)
print("SYNTHÈSE")
print("=" * 70)
print(f"Total stops: {len(stops)} | P&L: {sum(t.get('gain_eur',0) for t in stops):+.2f}€")
par_strat = {}
for t in stops:
    s = t.get('strategie','?') or '(inconnu)'
    par_strat.setdefault(s, []).append(t)
print("\nPar stratégie:")
for s, ts in sorted(par_strat.items(), key=lambda x: sum(t.get('gain_eur',0) for t in x[1])):
    print(f"  {s:24s} {len(ts)} trade(s) {sum(t.get('gain_eur',0) for t in ts):+.2f}€")
par_actif = {}
for t in stops:
    a = t.get('nom','?')
    par_actif.setdefault(a, []).append(t)
print("\nPar actif:")
for a, ts in sorted(par_actif.items(), key=lambda x: sum(t.get('gain_eur',0) for t in x[1])):
    print(f"  {a:14s} {len(ts)} trade(s) {sum(t.get('gain_eur',0) for t in ts):+.2f}€ | var moy {sum(t.get('variation_pct',0) for t in ts)/len(ts):+.2f}%")
