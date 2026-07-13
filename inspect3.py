#!/usr/bin/env python3
"""Inspection pour comprendre le lien strategies.json <-> backtests."""
import json
from collections import Counter, defaultdict


def load(n, d):
    try:
        return json.load(open(n))
    except Exception:
        return d


strats = load("strategies.json", [])
bp = load("backtests_pro.json", [])
br = load("backtests_reels.json", [])
b4 = load("backtests_phase4.json", [])
bh = load("backtests_horaires.json", [])

print("=" * 60)
print("STRATEGIES.JSON")
print("=" * 60)
print(f"Nombre: {len(strats)}")
if strats:
    print(f"Clés item[0]: {list(strats[0].keys()) if isinstance(strats[0], dict) else type(strats[0])}")
    print("\nContenu de chaque stratégie (index + 100 premiers chars):")
    for i, s in enumerate(strats):
        c = s.get("contenu", str(s)) if isinstance(s, dict) else str(s)
        # extraire le TYPE si présent
        typ = ""
        if "TYPE:" in c:
            typ = c[c.find("TYPE:"):c.find("TYPE:") + 40].replace("\n", " ")
        print(f"  [{i:2d}] {typ or c[:90]}")

print("\n" + "=" * 60)
print("BACKTESTS — noms de stratégies uniques")
print("=" * 60)
for fname, data in [("backtests_pro", bp), ("backtests_reels", br),
                    ("backtests_phase4", b4), ("backtests_horaires", bh)]:
    names = Counter(b.get("strategie", "?") for b in data if isinstance(b, dict))
    print(f"\n{fname} ({len(data)} entries, {len(names)} stratégies uniques):")
    for name, cnt in names.most_common():
        print(f"  {name:<35} x{cnt}")

print("\n" + "=" * 60)
print("TENTATIVE DE MATCHING contenu <-> nom backtest")
print("=" * 60)
bt_names = set()
for data in [bp, br, b4, bh]:
    for b in data:
        if isinstance(b, dict):
            bt_names.add(str(b.get("strategie", "")))
bt_names.discard("")
print(f"Noms backtests uniques (tous fichiers): {sorted(bt_names)}")
matched = 0
for i, s in enumerate(strats):
    c = (s.get("contenu", "") if isinstance(s, dict) else str(s))
    for bn in bt_names:
        if bn and (bn.lower() in c.lower() or c.lower()[:50] in bn.lower()):
            print(f"  MATCH strats[{i}] <-> backtest '{bn}'")
            matched += 1
print(f"\nStratégies matchées: {matched}/{len(strats)}")

print("\n" + "=" * 60)
print("VERDICTS backtests_pro (4 stratégies)")
print("=" * 60)
agg = defaultdict(list)
for b in bp:
    agg[b.get("strategie", "?")].append(b)
for name, lst in agg.items():
    rets = [float(x.get("retour_pct", 0)) for x in lst]
    pfs = [float(x.get("profit_factor", 0)) for x in lst if x.get("profit_factor") is not None]
    g = sum(1 for x in lst if x.get("verdict") == "GAGNANTE")
    avg_ret = sum(rets) / len(rets)
    avg_pf = sum(pfs) / len(pfs) if pfs else 0
    pct_g = g / len(lst) * 100
    if avg_ret > 0 and avg_pf >= 1.0 and pct_g >= 50:
        v = "GARDER"
    elif avg_ret < 0 or avg_pf < 1:
        v = "COUPER"
    else:
        v = "SURVEILLER"
    actifs = sorted(set(x.get("actif", "?") for x in lst))
    print(f"  {name:<35} {v:<11} retour={avg_ret:+.2f}% pf={avg_pf:.2f} n={len(lst)} actifs={actifs[:3]}")
