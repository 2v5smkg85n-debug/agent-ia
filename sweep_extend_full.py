#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sweep_extend_full.py — Validation elargie de EXTEND_TP sur TOUS les marches.

Teste si monter le TP en profit (SL fixe, pas de breakeven) tient sur un grand
echantillon. tp_ext pousse jusqu'a 6 pour voir si la courbe plafonne (edge reel)
ou continue de monter (outliers). Breakdown par actif pour detecter la concentration.
"""
import os, sys, logging
os.chdir(os.path.dirname(os.path.abspath("backtest_trailing.py")) or ".")
sys.path.insert(0, ".")

import backtest_trailing as bt
TP = getattr(bt, "TP", 2.0)
SL = getattr(bt, "SL", 2.5)
DEBUT = getattr(bt, "DEBUT", 60)
MAX_BARS = getattr(bt, "MAX_BARS", 48)
GATE = getattr(bt, "GATE", 1.0)
LIMITE_BARS = getattr(bt, "LIMITE_BARS", 500)

from indicateurs import historique_ohlcv
from signaux_gagnants import signal_strategie, calculer_donnees
from regime import fit_multi_tf

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")


def entrees_actif(actif, strats):
    bougies = historique_ohlcv(actif, "1h", LIMITE_BARS)
    if not bougies or len(bougies) < DEBUT + 10:
        return None, None
    closes = [b["cloture"] for b in bougies]
    entrees = []
    ouvert = None
    for i in range(DEBUT, len(closes)):
        px = closes[i]
        if ouvert:
            var = (px - ouvert["px"]) / ouvert["px"] * 100
            age = i - ouvert["bar"]
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                entrees.append((ouvert["bar"], ouvert["px"]))
                ouvert = None
        if ouvert:
            continue
        clotures_i = closes[: i + 1]
        try:
            donnees = calculer_donnees(clotures_i)
        except Exception:
            continue
        achats = []
        for s in strats:
            nom = s["strategie"]
            try:
                sig = signal_strategie(nom, donnees)
            except Exception:
                sig = None
            if sig == "ACHAT":
                achats.append((nom, s["retour_pct"]))
        if not achats:
            continue
        passed = []
        for nom, r in achats:
            try:
                fit_avg, _, _ = fit_multi_tf(nom, clotures_i)
            except Exception:
                fit_avg = 1.0
            if fit_avg >= GATE:
                passed.append((nom, r * fit_avg))
        if not passed:
            continue
        nom, _ = max(passed, key=lambda x: x[1])
        ouvert = {"px": px, "bar": i, "strat": nom}
    if ouvert:
        entrees.append((ouvert["bar"], ouvert["px"]))
    return closes, entrees


def simule_mode(closes, entrees, activate, tp_ext):
    res = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
    for bar_e, px_e in entrees:
        fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
        peak = 0.0
        ex = None
        for j in range(bar_e + 1, fin + 1):
            var = (closes[j] - px_e) / px_e * 100
            peak = max(peak, var)
            age = j - bar_e
            in_profit = peak >= activate
            tp_niv = tp_ext if in_profit else TP
            if var >= tp_niv:
                ex = var; break
            if var <= -SL:
                ex = var; break
            if age >= MAX_BARS and var > 0:
                ex = var; break
        if ex is None:
            ex = (closes[fin] - px_e) / px_e * 100
        res["pnl"] += ex; res["n"] += 1
        if ex > 0:
            res["wins"] += 1; res["sum_win"] += ex
            res["max_win"] = max(res["max_win"], ex)
    res["win_rate"] = round(100 * res["wins"] / res["n"], 1) if res["n"] else 0
    res["avg_win"] = round(res["sum_win"] / res["wins"], 2) if res["wins"] else 0
    res["pnl"] = round(res["pnl"], 2)
    return res


# TOUS les marches avec strategies
strats_par_actif = bt._load_strategies()
actifs = list(strats_par_actif.keys())
print(f"Marches testes: {len(actifs)} -> {actifs}\n")

cache = {}
for a in actifs:
    print(f"  -> {a} ...", flush=True)
    try:
        c, e = entrees_actif(a, strats_par_actif[a])
        if c and e is not None:
            cache[a] = (c, e)
    except Exception as ex:
        print(f"     {a}: indispo ({ex})")

ACTIVATE = 0.5  # seuil fixe (le sweep precedent a montre que le seuil importe peu)

print("\n" + "=" * 72)
print(f"VALIDATION EXTEND_TP sur {len(cache)} marches (activate={ACTIVATE}%)")
print("=" * 72)

# FIXE baseline (tp_ext = TP, jamais d'extension)
base = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
for a, (c, e) in cache.items():
    r = simule_mode(c, e, 999.0, TP)
    for k in base:
        base[k] += r[k]
base["win_rate"] = round(100 * base["wins"] / base["n"], 1) if base["n"] else 0
base["avg_win"] = round(base["sum_win"] / base["wins"], 2) if base["wins"] else 0
base["pnl"] = round(base["pnl"], 2)
print(f"\n{'tp_ext':<8} {'PnL%':>8} {'Trades':>7} {'Win%':>6} {'AvgWin':>8} {'MaxWin':>8} {'ΔvsFIXE':>9}")
print("-" * 72)
print(f"{'FIXE':<8} {base['pnl']:>8.2f} {base['n']:>7} {base['win_rate']:>5.1f}% {base['avg_win']:>+7.2f}% {base['max_win']:>+7.2f}% {0:>+8.2f}")

best = None
for tp_ext in [2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0]:
    tot = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
    for a, (c, e) in cache.items():
        r = simule_mode(c, e, ACTIVATE, tp_ext)
        for k in tot:
            tot[k] += r[k]
    tot["win_rate"] = round(100 * tot["wins"] / tot["n"], 1) if tot["n"] else 0
    tot["avg_win"] = round(tot["sum_win"] / tot["wins"], 2) if tot["wins"] else 0
    tot["pnl"] = round(tot["pnl"], 2)
    d = tot["pnl"] - base["pnl"]
    print(f"{tp_ext:<8} {tot['pnl']:>8.2f} {tot['n']:>7} {tot['win_rate']:>5.1f}% {tot['avg_win']:>+7.2f}% {tot['max_win']:>+7.2f}% {d:>+8.2f}")
    if best is None or d > best[1]:
        best = (tp_ext, d, tot["pnl"], tot["win_rate"], tot["avg_win"])

# Breakdown par actif pour le meilleur tp_ext
print("-" * 72)
print(f"\nBREAKDOWN PAR ACTIF (FIXE vs EXTEND_TP tp_ext={best[0]})")
print(f"{'Actif':<12} {'FIXE':>8} {'EXTEND':>8} {'Δ':>8} {'n':>5}")
print("-" * 48)
for a, (c, e) in cache.items():
    rf = simule_mode(c, e, 999.0, TP)
    re = simule_mode(c, e, ACTIVATE, best[0])
    print(f"{a:<12} {rf['pnl']:>8.2f} {re['pnl']:>8.2f} {re['pnl']-rf['pnl']:>+8.2f} {rf['n']:>5}")

print("-" * 72)
n_trades = base["n"]
print(f"\nEchantillon: {n_trades} trades sur {len(cache)} marches")
if best and best[1] > 0:
    print(f"Meilleur: tp_ext={best[0]} -> PnL {best[2]:.2f}% (Δ {best[1]:+.2f}% vs FIXE, win {best[3]}%, avgwin {best[4]}%)")
if n_trades >= 40 and best and best[1] > 1.0:
    print("\n✅ ECHANTILLON SUFFISANT + AMELIORATION POSITIVE -> a implementer dans protection.py")
elif n_trades < 40:
    print(f"\n⚠️ Echantillon encore faible ({n_trades} trades) ->amelioration prometteuse mais a confirmer")
else:
    print("\n❌ Pas d'amelioration robuste -> garder TP fixe")
