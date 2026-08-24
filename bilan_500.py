#!/usr/bin/env python3
"""Bilan depuis le deploiement des positions 500EUR (23 aug 22h)."""
import json
from datetime import datetime

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])
positions = pf.get("positions", [])

# Filtrer les trades depuis le 23 aug 22h (deploiement 500EUR)
trades_500 = [t for t in trades if t.get("date_fermeture", "") >= "2026-08-23 22"]
trades_old = [t for t in trades if t.get("date_fermeture", "") < "2026-08-23 22"]

print("=" * 55)
print("  BILAN DEPUIS POSITIONS 500EUR (23/08 22h)")
print("=" * 55)
print()

# Trades fermes depuis 500EUR
total_gain = sum(t.get("gain_eur", 0) for t in trades_500)
gagnants = [t for t in trades_500 if t.get("gain_eur", 0) > 0]
perdants = [t for t in trades_500 if t.get("gain_eur", 0) <= 0]
frais = sum(t.get("frais_total", 0) for t in trades_500)

print(f"Trades fermes (depuis 500EUR): {len(trades_500)}")
print(f"  Gagnants: {len(gagnants)}")
print(f"  Perdants: {len(perdants)}")
if trades_500:
    wr = len(gagnants) / len(trades_500) * 100
    print(f"  Win rate: {wr:.1f}%")
print(f"  Gain brut: {total_gain:+.2f}EUR")
print(f"  Frais: {frais:.2f}EUR")
print(f"  Net: {total_gain - frais:+.2f}EUR")
print()

# Detail des trades
if trades_500:
    print("DETAIL DES TRADES:")
    print("-" * 55)
    for t in trades_500:
        sym = t.get("symbole", "?")
        gain = t.get("gain_eur", 0)
        var = t.get("variation_pct", 0)
        montant = t.get("montant_eur", 0)
        raison = t.get("raison", "?")[:30]
        print(f"  {sym}: {gain:+.2f}EUR ({var:+.2f}%) | {montant:.0f}EUR | {raison}")
    print()

# Positions ouvertes
print("POSITIONS OUVERTES:")
print("-" * 55)
for p in positions:
    sym = p.get("symbole", "?")
    montant = p.get("montant_eur", 0)
    prix_entree = p.get("prix_entree", 0)
    print(f"  {sym}: {montant:.2f}EUR @ {prix_entree:.4f}")
print()

# Capital
liquidites = pf.get("liquidites", 0)
valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
capital = liquidites + valeur_pos
print(f"CAPITAL:")
print("-" * 55)
print(f"  Liquidites: {liquidites:.2f}EUR")
print(f"  Valeur positions: {valeur_pos:.2f}EUR")
print(f"  Capital total: {capital:.2f}EUR")
print(f"  Capital initial: 1000.00EUR")
print(f"  Rendement: {(capital-1000)/1000*100:+.2f}%")
print()

# Comparaison avant/apres
old_gain = sum(t.get("gain_eur", 0) for t in trades_old)
print("COMPARAISON AVANT/APRES 500EUR:")
print("-" * 55)
print(f"  Avant (80EUR): {len(trades_old)} trades, {old_gain:+.2f}EUR net")
print(f"  Apres (500EUR): {len(trades_500)} trades, {total_gain-frais:+.2f}EUR net")
if trades_500:
    gain_moyen_500 = (total_gain - frais) / len(trades_500)
    gain_moyen_80 = old_gain / max(len(trades_old), 1)
    print(f"  Gain moyen/trade avant: {gain_moyen_80:+.2f}EUR")
    print(f"  Gain moyen/trade apres: {gain_moyen_500:+.2f}EUR")
    if gain_moyen_80 != 0:
        print(f"  Ratio: {gain_moyen_500/gain_moyen_80:.1f}x")
