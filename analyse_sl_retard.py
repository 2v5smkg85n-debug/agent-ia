#!/usr/bin/env python3
"""Analyse les SL-RETARD recents (apres 24/08)."""
import json

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])

# SL-RETARD depuis le 24/08 (jour du fix 60s)
sl_retard = [t for t in trades if "SL-RETARD" in t.get("raison", "") and t.get("date_fermeture", "") >= "2026-08-24"]

print(f"=== SL-RETARD depuis le 24/08 ({len(sl_retard)}) ===")
print(f"{'Date':<18} {'Symbole':<12} {'Gain':>8} {'Variation':>10} {'Montant':>8} {'Raison'}")
print("-" * 80)
for t in sl_retard:
    print(f'{t["date_fermeture"]:<18} {t["symbole"]:<12} {t["gain_eur"]:+8.2f}EUR {t["variation_pct"]:+9.2f}% {t["montant_eur"]:7.0f}EUR {t["raison"][:50]}')

print()
total_perte = sum(t["gain_eur"] for t in sl_retard)
print(f"Total pertes SL-RETARD: {total_perte:+.2f}EUR")

# Stats
overshoots = [t["variation_pct"] for t in sl_retard]
if overshoots:
    print(f"Overshoot moyen: {sum(overshoots)/len(overshoots):+.2f}% (SL a -1.0%)")
    print(f"Overshoot max: {min(overshoots):+.2f}%")
    print(f"Overshoot min: {max(overshoots):+.2f}%")

# Comparaison avec avant le fix
sl_avant = [t for t in trades if "SL-RETARD" in t.get("raison", "") and t.get("date_fermeture", "") < "2026-08-24"]
print(f"\n=== Avant le fix ({len(sl_avant)} SL-RETARD) ===")
if sl_avant:
    overshoots_avant = [t["variation_pct"] for t in sl_avant]
    print(f"Overshoot moyen: {sum(overshoots_avant)/len(overshoots_avant):+.2f}%")
    print(f"Overshoot max: {min(overshoots_avant):+.2f}%")
    print(f"Total pertes: {sum(t['gain_eur'] for t in sl_avant):+.2f}EUR")

# Par symbole
print(f"\n=== SL-RETARD par symbole (depuis 24/08) ===")
par_sym = {}
for t in sl_retard:
    sym = t["symbole"]
    if sym not in par_sym:
        par_sym[sym] = {"count": 0, "perte": 0}
    par_sym[sym]["count"] += 1
    par_sym[sym]["perte"] += t["gain_eur"]
for sym, data in sorted(par_sym.items(), key=lambda x: x[1]["perte"]):
    print(f"  {sym:<12} {data['count']} trade(s) | {data['perte']:+.2f}EUR")
