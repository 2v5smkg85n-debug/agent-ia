#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""count_strategies.py — Compte exactement combien de strategies l'IA a
testees, validees (GAGNANTE), deployees, et ameliorees."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

print("=" * 70)
print("BILAN DES STRATEGIES DE L'IA")
print("=" * 70)

# 1) Pool de strategies GAGNANTE (fichiers lus par le classement)
print("\n--- 1. STRATEGIES GAGNANTE en stock (pool live) ---")
total_gagnantes = 0
actifs_couverts = set()
for fich in ["backtests_horaires.json", "backtests_pro.json",
             "backtests_reels.json", "backtests_phase4.json"]:
    if not os.path.exists(fich):
        continue
    try:
        data = json.load(open(fich))
        gagn = [r for r in data if r.get("verdict") == "GAGNANTE"]
        total_gagnantes += len(gagn)
        for r in gagn:
            actifs_couverts.add(r.get("actif"))
        strats_uniq = set(r.get("strategie") for r in gagn)
        print(f"  {fich:<28} {len(gagn):>3} GAGNANTE ({len(strats_uniq)} strats uniques)")
    except Exception:
        pass
print(f"  TOTAL: {total_gagnantes} strategies GAGNANTE sur {len(actifs_couverts)} actifs")

# 2) Classement live (ce qui est actif maintenant)
print("\n--- 2. CLASSEMENT LIVE (actif maintenant) ---")
try:
    import classement_strategies as cs
    r = cs.calculer_classement()
    n_strats = 0
    n_actifs = 0
    for actif, v in r.items():
        if isinstance(v, dict) and v.get("strategies"):
            n_actifs += 1
            n_strats += len(v["strategies"])
    print(f"  {n_strats} strategies classees sur {n_actifs} actifs")
    print(f"  (chaque actif a sa meilleure strategie selectionnee par regime + sagesse)")
except Exception as e:
    print(f"  erreur: {e}")

# 3) Lecons (idees testees et appris)
print("\n--- 3. LECONS (idees testees par l'IA) ---")
lecons = []
if os.path.exists("lecons_apprises.jsonl"):
    lecons = [json.loads(l) for l in open("lecons_apprises.jsonl") if l.strip()]
deployed = [l for l in lecons if "DEPLOY" in str(l.get("statut","")).upper()]
rejected = [l for l in lecons if "REJET" in str(l.get("statut","")).upper() or l.get("statut","").startswith("X")]
nuanced = [l for l in lecons if "NUANCE" in str(l.get("statut","")).upper() or l.get("statut","").startswith("~")]
print(f"  {len(lecons)} idees testees au total:")
print(f"    {len(deployed)} DEPLOYEES (ameliore le systeme)")
print(f"    {len(rejected)} REJETEES (backtest negatif -> evitees)")
print(f"    {len(nuanced)} NUANCEES (conditionnelles)")
for l in lecons:
    st = l.get("statut", "?")
    print(f"    [{st[:8]:<8}] {l.get('hypothese','?')[:60]}")

# 4) Ameliorations specifiques deployees
print("\n--- 4. AMELIORATIONS DEPLOYEES (modifs du systeme) ---")
print("  - EXTEND_TP: TP 2.0% -> 4.0% en profit (sweep optimise, +14.30% crypto)")
print("  - Dip-buying gate: bloque entrees sur bougie haussiere (biais<0 requis)")
print("  - Classement dynamique: score = backtest x regime_fit x live_mult x sagesse_mult")
print("  - Auto-pruning: elaguage auto des strategies perdantes")
print("  - Sagesse 10 maitres traders cablee (RSI x1.00, trend x0.95)")
print("  - Reflection quotidienne 08:00 UTC (hypotheses + self-improvement)")
print("  - Univers etendu: 5 -> 10 cryptos (mid-caps Revolut X)")

print("\n" + "=" * 70)
print(f"SYNTHESE: {total_gagnantes} strategies GAGNANTE en pool,")
print(f"          {n_strats} actives en live, {len(lecons)} idees testees")
print(f"          ({len(deployed)} deployees, {len(rejected)} rejetees, {len(nuanced)} nuancees)")
print("=" * 70)
