#!/usr/bin/env python3
"""Ferme toutes les positions manuellement."""
import json, os, sys
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
f = os.path.join(DOSSIER, "paper_trading.json")
pf = json.load(open(f))

# Recuperer les prix actuels
sys.path.insert(0, DOSSIER)
from paper_trading import tous_les_prix
prix = tous_les_prix()

fermees = []
for pos in list(pf.get("positions", [])):
    sym = pos["symbole"]
    p = prix.get(sym, pos["prix_entree"])
    qte = pos["quantite"]
    montant = pos.get("montant_eur", pos["prix_entree"] * qte)
    valeur = p * qte
    frais = valeur * 0.001
    gain = valeur - montant - frais
    pf["liquidites"] += valeur - frais
    trade = dict(pos)
    trade["gain_eur"] = round(gain, 2)
    trade["gain_pct"] = round(gain / montant * 100, 2) if montant else 0
    trade["date_fermeture"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    trade["raison"] = "Fermeture manuelle"
    trade["prix_sortie"] = p
    pf.setdefault("trades_fermes", []).append(trade)
    nom = pos.get("nom", sym)
    pct = gain / montant * 100 if montant else 0
    fermees.append(f"  {nom}: {gain:+.2f}EUR ({pct:+.1f}%)")

pf["positions"] = []
pf["dernier_tick"] = datetime.now().strftime("%Y-%m-%d %H:%M")
json.dump(pf, open(f, "w"), indent=2, default=str)

print(f"Positions fermees: {len(fermees)}")
for ligne in fermees:
    print(ligne)
print(f"Liquidites: {pf['liquidites']:.2f}EUR")
print(f"Capital total: {pf['liquidites']:.2f}EUR")
