#!/usr/bin/env python3
"""Compare les performances du bot vs Kasper Trading."""
import json
from datetime import datetime, timedelta

pf = json.load(open("paper_trading.json"))
capital_initial = 1000.0
capital_actuel = pf.get("liquidites", 0) + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
trades = pf.get("trades_fermes", [])

# Stats bot
total_trades = len(trades)
gagnants = [t for t in trades if t.get("gain_eur", 0) > 0]
perdants = [t for t in trades if t.get("gain_eur", 0) <= 0]
win_rate = len(gagnants) / total_trades * 100 if total_trades > 0 else 0
pnl_total = sum(t.get("gain_eur", 0) for t in trades)
frais = pf.get("total_fais", pf.get("total_frais", 0))
pct_total = (capital_actuel - capital_initial) / capital_initial * 100

# PnL par jour
par_jour = {}
for t in trades:
    jour = t.get("date_fermeture", "")[:10]
    if jour:
        par_jour[jour] = par_jour.get(jour, 0) + t.get("gain_eur", 0)

jours_actifs = len(par_jour)
if jours_actifs > 0:
    pnl_moy_jour = sum(par_jour.values()) / jours_actifs
    pct_moy_jour = pnl_moy_jour / capital_initial * 100
else:
    pnl_moy_jour = 0
    pct_moy_jour = 0

# Meilleur et pire jour
if par_jour:
    meilleur_jour = max(par_jour.values())
    pire_jour = min(par_jour.values())
else:
    meilleur_jour = 0
    pire_jour = 0

# Gain moyen par trade
gain_moyen = sum(t.get("gain_eur", 0) for t in gagnants) / len(gagnants) if gagnants else 0
perte_moyenne = sum(t.get("gain_eur", 0) for t in perdants) / len(perdants) if perdants else 0

print("=" * 55)
print("  COMPARAISON: BOT vs KASPER TRADING")
print("=" * 55)
print()
print(f"{'Métrique':<30} {'Bot':>12} {'Kasper':>12}")
print("-" * 55)
print(f"{'Capital initial':<30} {'1000 EUR':>12} {'~1000 EUR':>12}")
print(f"{'Capital actuel':<30} {capital_actuel:>10.2f}€ {'N/A':>12}")
print(f"{'Rendement total':<30} {pct_total:>+10.2f}% {'14%/mois':>12}")
print(f"{'Rendement jour moyen':<30} {pct_moy_jour:>+10.2f}% {'~0.47%/j':>12}")
print(f"{'PnL jour moyen':<30} {pnl_moy_jour:>+10.2f}€ {'~4.67€/j':>12}")
print(f"{'Win rate':<30} {win_rate:>10.1f}% {'~70%':>12}")
print(f"{'Nb trades':<30} {total_trades:>12} {'N/A':>12}")
print(f"{'Gain moyen/trade':<30} {gain_moyen:>+10.2f}€ {'N/A':>12}")
print(f"{'Perte moyenne/trade':<30} {perte_moyenne:>+10.2f}€ {'N/A':>12}")
print(f"{'Meilleur jour':<30} {meilleur_jour:>+10.2f}€ {'N/A':>12}")
print(f"{'Pire jour':<30} {pire_jour:>+10.2f}€ {'N/A':>12}")
print(f"{'Frais payés':<30} {frais:>10.2f}€ {'N/A':>12}")
print(f"{'Jours actifs':<30} {jours_actifs:>12} {'~30':>12}")
print()
print("ANALYSE PAR JOUR:")
print("-" * 55)
for jour in sorted(par_jour.keys())[-10:]:
    pnl = par_jour[jour]
    pct = pnl / capital_initial * 100
    print(f"  {jour}: {pnl:>+8.2f}€ ({pct:>+6.2f}%)")
print()
print("VERDICT:")
print("-" * 55)
if pct_moy_jour > 0.47:
    print(f"  Bot: {pct_moy_jour:.2f}%/jour > Kasper: ~0.47%/jour")
    print("  Le bot bat Kasper en moyenne journaliere")
elif pct_moy_jour > 0:
    print(f"  Bot: {pct_moy_jour:.2f}%/jour < Kasper: ~0.47%/jour")
    print("  Le bot est en dessous de Kasper pour l'instant")
else:
    print(f"  Bot: {pct_moy_jour:.2f}%/jour (negatif)")
    print("  Le bot perd de l'argent actuellement")
