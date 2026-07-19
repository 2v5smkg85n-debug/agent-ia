#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apprentissage_recent.py — Affiche ce que l'IA a appris recemment.

Lit les journaux d'apprentissage du research_loop:
  - recherche_log.jsonl : chaque cycle (regimes, sweep, top strat, divergence)
  - classement_strategies.json : classement actuel des strategies
  - regime_history.json : regimes observes
  - lecons_apprises.jsonl : lecons accumulees
"""
import os, json, sys
from datetime import datetime

D = os.path.dirname(os.path.abspath("paper_trading.py")) or os.getcwd()


def load_jsonl(name):
    p = os.path.join(D, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_json(name):
    p = os.path.join(D, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


print("=" * 74)
print("CE QUE MON IA A APPRIS (apprentissage recent)")
print("=" * 74)

# 1) Cycles de recherche
cycles = load_jsonl("recherche_log.jsonl")
print(f"\n--- CYCLES DE RECHERCHE ({len(cycles)} au total) ---")
for c in cycles[-4:]:
    ts = c.get("ts", c.get("cycle", "?"))
    regimes = c.get("regimes", {})
    sweep = c.get("sweep", "")
    top = c.get("top_strat", "")
    div = c.get("divergence", "")
    print(f"\n  [{ts}]")
    if regimes:
        # regimes peut etre dict {sym: 'QUIET'} ou dict de dicts
        if isinstance(regimes, dict):
            rsum = {}
            for s, v in regimes.items():
                r = v if isinstance(v, str) else v.get("REGIME", "?")
                rsum[r] = rsum.get(r, 0) + 1
            print(f"    regimes: {rsum}")
    if sweep:
        print(f"    sweep: {sweep}")
    if top:
        print(f"    top strat: {top}")
    if div:
        print(f"    divergence: {div}")

# 2) Classement actuel
cl = load_json("classement_strategies.json")
print(f"\n--- CLASSEMENT ACTUEL DES STRATEGIES ---")
if cl:
    # cl peut etre une liste de dicts
    items = cl if isinstance(cl, list) else list(cl.values()) if isinstance(cl, dict) else []
    # trier par score
    try:
        items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
    except Exception:
        pass
    print(f"  {'Rang':<5}{'Actif':<10}{'Strategie':<22}{'Score':>7}{'BFit':>6}{'Live':>7}{'Regime':<8}")
    for it in items[:10]:
        print(f"  {it.get('rang','?'):<5}{str(it.get('actif','?')):<10}"
              f"{str(it.get('strategie','?')):<22}{it.get('score',0):>7.2f}"
              f"{it.get('regime_fit',0):>6.2f}x{it.get('live_mult',1.0):>5.2f}"
              f"  {str(it.get('regime','?')):<8}")
else:
    print("  (classement non disponible)")

# 3) Regime history
rh = load_json("regime_history.json")
print(f"\n--- REGIMES OBSERVES ---")
if rh and isinstance(rh, list):
    seen = {}
    for r in rh:
        reg = r.get("regime", r.get("REGIME", "?")) if isinstance(r, dict) else str(r)
        seen[reg] = seen.get(reg, 0) + 1
    print(f"  transitions: {len(rh)} | distribution: {seen}")
elif rh and isinstance(rh, dict):
    for sym, regs in list(rh.items())[:5]:
        print(f"  {sym}: {regs if isinstance(regs, list) else regs}")

# 4) Lecons
lecons = load_jsonl("lecons_apprises.jsonl")
print(f"\n--- LECONS APPRISES ({len(lecons)}) ---")
for e in lecons:
    statut = e.get("statut", "?")
    marque = "OK" if "DEPLOY" in statut.upper() else "XX"
    print(f"  [{marque}] {e.get('ts','?')[:16]} | {e.get('hypothese','?')[:60]}")
    print(f"       -> {statut[:70]}")

print("\n" + "=" * 74)
print(f"Bilan: {len(cycles)} cycles de recherche, {len(lecons)} lecons, "
      f"{len(items) if cl else 0} strategies classees.")
print("=" * 74)
