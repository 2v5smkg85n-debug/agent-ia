#!/usr/bin/env python3
"""Analyse les trades historiques pour identifier les patterns gagnants/perdants."""
import json
import os
from collections import defaultdict

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.json")

with open(FICHIER) as f:
    d = json.load(f)

trades = d.get("trades_fermes", [])
g = [t for t in trades if t.get("gain_eur", 0) > 0]
p = [t for t in trades if t.get("gain_eur", 0) <= 0]

print(f"=== ANALYSE COMPLETE — {len(trades)} trades ===")
print(f"WR: {len(g)/len(trades)*100:.1f}% | PnL total: {sum(t.get('gain_eur',0) for t in trades):+.2f}EUR")
print(f"Gain moyen: +{sum(t.get('gain_eur',0) for t in g)/max(len(g),1):.2f}EUR | Perte moyenne: {sum(t.get('gain_eur',0) for t in p)/max(len(p),1):.2f}EUR")
print()

# Par strategie
strats = defaultdict(lambda: {"n":0, "w":0, "pnl":0})
for t in trades:
    s = t.get("strategie", "?") or "?"
    strats[s]["n"] += 1
    strats[s]["pnl"] += t.get("gain_eur", 0)
    if t.get("gain_eur", 0) > 0:
        strats[s]["w"] += 1
print("=== PAR STRATEGIE ===")
for s, st in sorted(strats.items(), key=lambda x: x[1]["pnl"], reverse=True):
    wr = st["w"]/st["n"]*100 if st["n"] else 0
    print(f"  {s[:30]:30s} n={st['n']:3d} WR={wr:5.1f}% PnL={st['pnl']:+7.2f}")

# Par crypto
print()
cryptos = defaultdict(lambda: {"n":0, "w":0, "pnl":0})
for t in trades:
    c = t.get("symbole", "?")
    cryptos[c]["n"] += 1
    cryptos[c]["pnl"] += t.get("gain_eur", 0)
    if t.get("gain_eur", 0) > 0:
        cryptos[c]["w"] += 1
print("=== PAR CRYPTO ===")
for c, st in sorted(cryptos.items(), key=lambda x: x[1]["pnl"], reverse=True):
    wr = st["w"]/st["n"]*100 if st["n"] else 0
    print(f"  {c:12s} n={st['n']:3d} WR={wr:5.1f}% PnL={st['pnl']:+7.2f}")

# Par raison de fermeture
print()
raisons = defaultdict(lambda: {"n":0, "w":0, "pnl":0})
for t in trades:
    r = t.get("raison", "?")[:30]
    raisons[r]["n"] += 1
    raisons[r]["pnl"] += t.get("gain_eur", 0)
    if t.get("gain_eur", 0) > 0:
        raisons[r]["w"] += 1
print("=== PAR RAISON DE FERMETURE ===")
for r, st in sorted(raisons.items(), key=lambda x: x[1]["n"], reverse=True)[:15]:
    wr = st["w"]/st["n"]*100 if st["n"] else 0
    print(f"  {r:30s} n={st['n']:3d} WR={wr:5.1f}% PnL={st['pnl']:+7.2f}")

# Par heure
print()
heures = defaultdict(lambda: {"n":0, "w":0, "pnl":0})
for t in trades:
    dt = t.get("date_fermeture", t.get("date", ""))
    h = dt[11:13] if len(dt) > 13 else "?"
    heures[h]["n"] += 1
    heures[h]["pnl"] += t.get("gain_eur", 0)
    if t.get("gain_eur", 0) > 0:
        heures[h]["w"] += 1
print("=== PAR HEURE (UTC) ===")
for h, st in sorted(heures.items()):
    if st["n"] >= 3:
        wr = st["w"]/st["n"]*100 if st["n"] else 0
        print(f"  {h}h UTC | n={st['n']:3d} WR={wr:5.1f}% PnL={st['pnl']:+7.2f}")

# Par jour de la semaine
print()
jours_nom = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
jours = defaultdict(lambda: {"n":0, "w":0, "pnl":0})
for t in trades:
    dt = t.get("date_fermeture", t.get("date", ""))
    if len(dt) >= 10:
        from datetime import datetime
        try:
            ddt = datetime.fromisoformat(dt[:19])
            j = ddt.weekday()
            jours[j]["n"] += 1
            jours[j]["pnl"] += t.get("gain_eur", 0)
            if t.get("gain_eur", 0) > 0:
                jours[j]["w"] += 1
        except Exception:
            pass
print("=== PAR JOUR ===")
for j in range(7):
    st = jours.get(j, {"n":0, "w":0, "pnl":0})
    if st["n"] >= 3:
        wr = st["w"]/st["n"]*100 if st["n"] else 0
        print(f"  {jours_nom[j]} | n={st['n']:3d} WR={wr:5.1f}% PnL={st['pnl']:+7.2f}")

# Taille des positions
print()
gains_200 = [t for t in g if t.get("montant_eur", 0) <= 250]
gains_500 = [t for t in g if 250 < t.get("montant_eur", 0) <= 600]
gains_1000 = [t for t in g if t.get("montant_eur", 0) > 600]
pertes_200 = [t for t in p if t.get("montant_eur", 0) <= 250]
pertes_500 = [t for t in p if 250 < t.get("montant_eur", 0) <= 600]
pertes_1000 = [t for t in p if t.get("montant_eur", 0) > 600]
print("=== PAR TAILLE DE POSITION ===")
print(f"  Petit (<=250EUR):  {len(gains_200)} gains ({sum(t.get('gain_eur',0) for t in gains_200):+.2f}) | {len(pertes_200)} pertes ({sum(t.get('gain_eur',0) for t in pertes_200):+.2f})")
print(f"  Moyen (250-600):   {len(gains_500)} gains ({sum(t.get('gain_eur',0) for t in gains_500):+.2f}) | {len(pertes_500)} pertes ({sum(t.get('gain_eur',0) for t in pertes_500):+.2f})")
print(f"  Grand (>600):      {len(gains_1000)} gains ({sum(t.get('gain_eur',0) for t in gains_1000):+.2f}) | {len(pertes_1000)} pertes ({sum(t.get('gain_eur',0) for t in pertes_1000):+.2f})")
