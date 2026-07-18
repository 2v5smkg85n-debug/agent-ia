#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_extend.py — Ajoute le mode EXTEND a backtest_trailing.py.
EXTEND = idee utilisateur: stop passe en positif (breakeven a +0.5%) -> TP monte a +3%.
Compare FIXE vs TRAIL vs EXTEND."""
import os, sys

D = os.getcwd()
BT = os.path.join(D, "backtest_trailing.py")
src = open(BT, encoding="utf-8").read()

edits = []

# 1) Constantes EXTEND apres TRAIL_PCT
edits.append((
"""TRAIL_ACTIVATE = 0.5
TRAIL_PCT = 0.8""",
"""TRAIL_ACTIVATE = 0.5
TRAIL_PCT = 0.8
# EXTEND: stop breakeven + TP dynamique (stop positif -> TP monte)
BREAKEVEN_ACTIVATE = 0.5   # active breakeven + TP etend a +0.5% de gain
TP_EXTEND = 3.0            # TP monte une fois en profit"""))

# 2) res init simuler_actif
edits.append((
"""    res = {m: {"pnl": 0.0, "n": 0, "wins": 0, "max_win": 0.0, "sum_win": 0.0}
           for m in ("FIXE", "TRAIL")}""",
"""    res = {m: {"pnl": 0.0, "n": 0, "wins": 0, "max_win": 0.0, "sum_win": 0.0}
           for m in ("FIXE", "TRAIL", "EXTEND")}"""))

# 3) init exit_ext + bloc EXTEND + break
edits.append((
"""        peak = 0.0
        exit_fixe = None
        exit_trail = None
        for j in range(bar_e + 1, fin + 1):""",
"""        peak = 0.0
        exit_fixe = None
        exit_trail = None
        exit_ext = None
        for j in range(bar_e + 1, fin + 1):"""))

edits.append((
"""                elif age >= MAX_BARS and var > 0:
                    exit_trail = (j, var, "TEMPS")
            if exit_fixe and exit_trail:
                break""",
"""                elif age >= MAX_BARS and var > 0:
                    exit_trail = (j, var, "TEMPS")
            # EXTEND: breakeven stop + TP etend une fois en profit
            if exit_ext is None:
                age = j - bar_e
                active_be = peak >= BREAKEVEN_ACTIVATE
                sl_niv = 0.0 if active_be else -SL
                tp_niv = TP_EXTEND if active_be else TP
                if var <= sl_niv:
                    exit_ext = (j, var, "BE" if active_be else "SL")
                elif var >= tp_niv:
                    exit_ext = (j, var, "TP_EXT" if active_be else "TP")
                elif age >= MAX_BARS and var > 0:
                    exit_ext = (j, var, "TEMPS")
            if exit_fixe and exit_trail and exit_ext:
                break"""))

# 4) fallback + boucle resultats
edits.append((
"""        if exit_trail is None:
            exit_trail = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        for m, ex in (("FIXE", exit_fixe), ("TRAIL", exit_trail)):""",
"""        if exit_trail is None:
            exit_trail = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        if exit_ext is None:
            exit_ext = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        for m, ex in (("FIXE", exit_fixe), ("TRAIL", exit_trail), ("EXTEND", exit_ext)):"""))

# 5) main() tot init
edits.append((
"""    tot = {m: {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
           for m in ("FIXE", "TRAIL")}""",
"""    tot = {m: {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
           for m in ("FIXE", "TRAIL", "EXTEND")}"""))

# 6) print loop
edits.append((
"""    print("=" * 72)
    print(f"{'Mode':<8} {'PnL%':>8} {'Trades':>7} {'Win%':>6} {'AvgWin':>8} {'MaxWin':>8}")
    print("-" * 72)
    for m in ("FIXE", "TRAIL"):""",
"""    print("=" * 72)
    print(f"{'Mode':<8} {'PnL%':>8} {'Trades':>7} {'Win%':>6} {'AvgWin':>8} {'MaxWin':>8}")
    print("-" * 72)
    for m in ("FIXE", "TRAIL", "EXTEND"):"""))

# 7) verdict
edits.append((
"""    pf, pt = tot["FIXE"]["pnl"], tot["TRAIL"]["pnl"]
    print(f"\\nVERDICT:")
    print(f"  TRAIL vs FIXE: {pt-pf:+.2f}% PnL")
    print(f"  AvgWin: FIXE {tot['FIXE']['avg_win']}% -> TRAIL {tot['TRAIL']['avg_win']}%")
    if pt > pf + 0.5:
        print("  → Le trailing AIDE (gains plus gros sans plus de pertes): l'activer en live.")
    elif pt < pf - 0.5:
        print("  → Le trailing NUIT (marché trop rangeant): garder le TP fixe.")
    else:
        print("  → Neutre: le trailing ne change pas grand-chose.")""",
"""    pf, pt, pe = tot["FIXE"]["pnl"], tot["TRAIL"]["pnl"], tot["EXTEND"]["pnl"]
    print(f"\\nVERDICT:")
    print(f"  TRAIL  vs FIXE: {pt-pf:+.2f}% PnL")
    print(f"  EXTEND vs FIXE: {pe-pf:+.2f}% PnL  (stop breakeven + TP {TP_EXTEND}%)")
    print(f"  AvgWin: FIXE {tot['FIXE']['avg_win']}% | TRAIL {tot['TRAIL']['avg_win']}% | EXTEND {tot['EXTEND']['avg_win']}%")
    if pe > pf + 0.5:
        print("  -> EXTEND AIDE: activer le stop breakeven + TP dynamique en live.")
    elif pe < pf - 0.5:
        print("  -> EXTEND NUIT (marche rangeant, breakeven coupe les gagnants): garder le TP fixe.")
    else:
        print("  -> EXTEND neutre.")
    if pt < pf - 0.5:
        print("  (rappel: le trailing nuit aussi -> garder le TP fixe.)")"""))

for old, new in edits:
    if new.split('\n')[0] in src and old not in src:
        # deja applique partiellement
        pass
    assert old in src, "ANCRAGE INTROUVABLE:\n" + old[:80]
    src = src.replace(old, new, 1)

open(BT, "w", encoding="utf-8").write(src)
import py_compile
py_compile.compile(BT, doraise=True)
print("✅ backtest_trailing.py: mode EXTEND ajoute (3 modes: FIXE/TRAIL/EXTEND)")
print("✅ compile OK")
