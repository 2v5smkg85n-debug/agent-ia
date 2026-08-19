#!/usr/bin/env python3
"""Nettoie les trades corrompus par les faux prix Revolut X (LDO a 10€, etc.)."""
import json

DATA_FILE = "portefeuille_paper.json"

pf = json.load(open(DATA_FILE))
trades = pf.get("trades_fermes", [])
historique = pf.get("historique", [])

print(f"Avant: {len(trades)} trades fermes, {len(historique)} historique")

# Detecter les trades corrompus: gain > 500% ou perte > 50% (irrealiste)
trades_propres = []
trades_supprimes = []
for t in trades:
    var = abs(t.get("variation_pct", 0))
    gain = abs(t.get("gain_eur", 0))
    if var > 500 or gain > 500:
        trades_supprimes.append(t)
    else:
        trades_propres.append(t)

# Pareil pour l'historique
hist_propre = []
for t in historique:
    var = abs(t.get("variation_pct", 0))
    gain = abs(t.get("gain_eur", 0))
    if var > 500 or gain > 500:
        continue
    hist_propre.append(t)

print(f"Supprime: {len(trades_supprimes)} trades corrompus")
for t in trades_supprimes:
    print(f"  {t.get('symbole','?')}: var {t.get('variation_pct',0):+.1f}% gain {t.get('gain_eur',0):+.2f}€")

pf["trades_fermes"] = trades_propres
pf["historique"] = hist_propre

json.dump(pf, open(DATA_FILE, "w"), ensure_ascii=False, indent=2)
print(f"Apres: {len(trades_propres)} trades fermes, {len(hist_propre)} historique")
print("OK - Trades corrompus supprimes")
