#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic Phase 5: état de l'observabilité actuelle."""
import json, os, glob
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def safe_load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return {"_err": str(e)}


print("=" * 64)
print(f"DIAGNOSTIC OBSERVABILITÉ — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print("=" * 64)

# 1. paper_trading.json
pf = safe_load(os.path.join(DOSSIER, "paper_trading.json"))
liq = pf.get("liquidites", 0)
pos = pf.get("positions", [])
val_pos = sum(p.get("montant_eur", 0) for p in pos)
capital = pf.get("capital", liq + val_pos)
trades = pf.get("trades_fermes", [])
print(f"\n1. PORTEFEUILLE")
print(f"   Capital: {capital:.2f}€ | Liquidités: {liq:.2f}€ | Positions: {len(pos)}")
print(f"   Trades fermés: {len(trades)}")
if trades:
    print(f"   PnL fermé cumulé: {sum(t.get('gain_eur',0) for t in trades):+.2f}€")
    print(f"   Champs d'un trade fermé: {list(trades[-1].keys())}")
    print(f"   Dernier trade: {trades[-1].get('symbole')} {trades[-1].get('gain_eur',0):+.2f}€ {str(trades[-1].get('date_fermeture',''))[:19]}")

# 2. Historiques
print(f"\n2. FICHIERS D'HISTORIQUE")
for f in ["backtests_history.jsonl", "equity_history.jsonl", "trades_history.jsonl",
          "performance.json", "backtests_reels_pro.json"]:
    p = os.path.join(DOSSIER, f)
    if os.path.exists(p):
        sz = os.path.getsize(p)
        lignes = sum(1 for _ in open(p)) if f.endswith(".jsonl") else "-"
        print(f"   {f}: {sz} octets, lignes={lignes}")
    else:
        print(f"   {f}: ABSENT")

# 3. Modules existants
print(f"\n3. MODULES PYTHON PRÉSENTS")
for f in sorted(glob.glob(os.path.join(DOSSIER, "*.py"))):
    sz = os.path.getsize(f)
    print(f"   {os.path.basename(f):<30} {sz:>6} octets")

# 4. backtests_history.jsonl — dernières entrées (equity tracking?)
bh = os.path.join(DOSSIER, "backtests_history.jsonl")
if os.path.exists(bh):
    lignes = open(bh).read().strip().split("\n")
    print(f"\n4. backtests_history.jsonl — {len(lignes)} entrées")
    if lignes:
        last = json.loads(lignes[-1])
        print(f"   Dernier snapshot champs: {list(last.keys())}")
        print(f"   Dernier snapshot date: {last.get('date','?')}")
        print(f"   Dernier snapshot capital: {last.get('capital', last.get('capital_total','?'))}")

# 5. Aperçu dashboard /perf — existe-t-il une route perf?
print(f"\n5. DASHBOARD — routes détectées")
ds = os.path.join(DOSSIER, "dashboard_server.py")
if os.path.exists(ds):
    src = open(ds, encoding="utf-8").read()
    for route in ["'/perf'", '"/perf"', "perf", "/metrics", "/equity", "/strategies"]:
        if route in src:
            print(f"   {route}: TROUVÉ")
