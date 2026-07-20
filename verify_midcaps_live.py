#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_midcaps_live.py — Verifie que les 5 mid-caps sont actifs dans le systeme:
1. strategies GAGNANTE generees dans backtests_horaires.json
2. presents dans le classement live
"""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

MIDCAPS = ["LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]

print("=" * 70)
print("VERIFICATION MID-CAPS DANS LE SYSTEME LIVE")
print("=" * 70)

# 1) backtests_horaires.json
print("\n--- 1. Strategies GAGNANTE dans backtests_horaires.json ---")
if os.path.exists("backtests_horaires.json"):
    data = json.load(open("backtests_horaires.json"))
    for mc in MIDCAPS:
        strats = [r for r in data if r.get("actif") == mc and r.get("verdict") == "GAGNANTE"]
        if strats:
            print(f"  {mc:<12} {len(strats)} GAGNANTE: ", end="")
            print(", ".join(f"{s['strategie']}({s.get('retour_pct',0):+.1f}%)" for s in strats[:4]))
        else:
            tous = [r for r in data if r.get("actif") == mc]
            print(f"  {mc:<12} 0 GAGNANTE ({len(tous)} testees)")
else:
    print("  backtests_horaires.json absent — backtest_horaires.py pas encore termine?")

# 2) Classement live
print("\n--- 2. Classement live (calculer_classement) ---")
try:
    import classement_strategies as cs
    r = cs.calculer_classement()
    for mc in MIDCAPS:
        v = r.get(mc)
        if isinstance(v, dict) and v.get("strategies"):
            print(f"  {mc:<12} regime={v.get('regime','?')} :")
            for s in v["strategies"][:3]:
                print(f"    #{s.get('rang','?')} {s.get('strategie','?'):<22} "
                      f"score={s.get('score',0):.2f} fit={s.get('regime_fit',0):.2f} "
                      f"sag={s.get('sagesse_mult',1):.2f} ({s.get('sagesse_verdict','?')})")
        else:
            print(f"  {mc:<12} ABSENT du classement (strategies non GAGNANTE ou non generees)")
except Exception as e:
    print(f"  erreur classement: {e}")

# 3) Mapping Revolut
print("\n--- 3. Mapping Revolut X (argent reel) ---")
try:
    from pont_revolut import BINANCE_TO_REVOLUTX
    for mc in MIDCAPS:
        paire = BINANCE_TO_REVOLUTX.get(mc)
        print(f"  {mc:<12} -> {paire or 'ABSENT'}")
except Exception as e:
    print(f"  erreur: {e}")

print("\n" + "=" * 70)
print("Si les mid-caps sont dans le classement -> l'agent generera des signaux")
print("ACHAT -> le pont Revolut miroirera en vrai argent (caps 10€/30€)")
print("=" * 70)
