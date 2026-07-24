#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fermer_arb_concentration.py - ferme la position ARB la plus recente.

Reduit la concentration (2 positions ARB meme strategie -> 1).
A lancer APRES avoir stoppe le service systemd (race condition sinon):
  sudo systemctl stop paper_trading.service
  python fermer_arb_concentration.py
  sudo systemctl start paper_trading.service
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_trading as pt

pf = pt.charger_portefeuille()
arb = [p for p in pf["positions"] if p["symbole"] == "ARBUSDT"]
print(f"Positions ARB: {len(arb)}")
for p in arb:
    print(f"  {p.get('strategie','?')} {p.get('montant_eur',0):.2f}EUR ouvert {p.get('date_ouverture','?')} entry {p.get('prix_entree',0):.5f}")

if len(arb) < 2:
    print("\nMoins de 2 positions ARB -> rien a fermer (deja reduit).")
    sys.exit(0)

# la plus recente (date_ouverture la plus tardive)
arb.sort(key=lambda p: p.get("date_ouverture", ""))
target = arb[-1]
print(f"\nFermeture de la plus recente: {target.get('strategie','?')} {target.get('montant_eur',0):.2f}EUR ouvert {target.get('date_ouverture')}")

prix = pt.prix_binance("ARBUSDT")
if not prix:
    print("ERREUR: prix ARB introuvable (Binance). Abandon.")
    sys.exit(1)
print(f"Prix actuel ARB: {prix:.5f}")

# securite: frais_entree doit exister
if "frais_entree" not in target:
    target["frais_entree"] = target.get("montant_eur", 0) * pt.FRAIS_TRANSACTION

variation = (prix - target["prix_entree"]) / target["prix_entree"] * 100
print(f"Variation: {variation:+.2f}%")

pt.fermer_position(pf, target, prix, "FERMETURE MANUELLE (reduction concentration ARB)", variation)
pt.sauver_portefeuille(pf)

print(f"\n=== FERME ===")
print(f"Positions restantes: {len(pf['positions'])}")
print(f"Liquidites: {pf['liquidites']:.2f}EUR")
arb_restant = [p for p in pf["positions"] if p["symbole"] == "ARBUSDT"]
print(f"Positions ARB restantes: {len(arb_restant)}")
