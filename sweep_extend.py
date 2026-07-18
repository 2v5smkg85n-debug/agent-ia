#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sweep_extend.py — Ameliore l'idee EXTEND: monter le TP en profit SANS breakeven.

Le breakeven stop etait le coupable (win rate 75%->41.7%). Ici on garde le SL fixe
et on monte juste le TP quand le trade atteint un seuil de profit.
Sweep: seuils d'activation + niveaux de TP etendu. Compare a FIXE.
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
ACTIFS_TEST = getattr(bt, "ACTIFS_TEST", ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"])

from indicateurs import historique_ohlcv
from signaux_gagnants import signal_strategie, calculer_donnees
from regime import fit_multi_tf

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sweep")


def entrees_actif(actif, strats):
    """Calcule les barres d'entree (meme logique que backtest_trailing, SL/TP fixe)."""
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
    """EXTEND_TP: monte le TP a tp_ext quand peak>=activate. SL reste fixe."""
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
                ex = var
                break
            if var <= -SL:
                ex = var
                break
            if age >= MAX_BARS and var > 0:
                ex = var
                break
        if ex is None:
            ex = (closes[fin] - px_e) / px_e * 100
        res["pnl"] += ex
        res["n"] += 1
        if ex > 0:
            res["wins"] += 1
            res["sum_win"] += ex
            res["max_win"] = max(res["max_win"], ex)
    res["win_rate"] = round(100 * res["wins"] / res["n"], 1) if res["n"] else 0
    res["avg_win"] = round(res["sum_win"] / res["wins"], 2) if res["wins"] else 0
    res["pnl"] = round(res["pnl"], 2)
    return res


# cache entrees
strats_par_actif = bt._load_strategies()
actifs = [a for a in ACTIFS_TEST if a in strats_par_actif] or list(strats_par_actif.keys())[:5]
cache = {}
for a in actifs:
    print(f"  -> {a} ...", flush=True)
    c, e = entrees_actif(a, strats_par_actif[a])
    if c and e is not None:
        cache[a] = (c, e)

# FIXE baseline (= TP fixe, pas d'extension) = activate infinie
print("\n" + "=" * 70)
print("SWEEP EXTEND_TP (monter le TP en profit, SL fixe, pas de breakeven)")
print("=" * 70)

# baseline FIXE: simule avec activate tres haut (jamais active) = TP fixe
base = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
for a, (c, e) in cache.items():
    r = simule_mode(c, e, 999.0, TP)  # jamais active -> TP fixe
    for k in base:
        base[k] += r[k]
base["win_rate"] = round(100 * base["wins"] / base["n"], 1) if base["n"] else 0
base["avg_win"] = round(base["sum_win"] / base["wins"], 2) if base["wins"] else 0
base["pnl"] = round(base["pnl"], 2)
print(f"\n{'Config':<22} {'PnL%':>8} {'Trades':>7} {'Win%':>6} {'AvgWin':>8} {'ΔvsFIXE':>9}")
print("-" * 70)
print(f"{'FIXE (baseline)':<22} {base['pnl']:>8.2f} {base['n']:>7} {base['win_rate']:>5.1f}% {base['avg_win']:>+7.2f}% {0:>+8.2f}")

best = None
for activate in [0.3, 0.5, 1.0, 1.5]:
    for tp_ext in [2.5, 3.0, 4.0]:
        tot = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
        for a, (c, e) in cache.items():
            r = simule_mode(c, e, activate, tp_ext)
            for k in tot:
                tot[k] += r[k]
        tot["win_rate"] = round(100 * tot["wins"] / tot["n"], 1) if tot["n"] else 0
        tot["avg_win"] = round(tot["sum_win"] / tot["wins"], 2) if tot["wins"] else 0
        tot["pnl"] = round(tot["pnl"], 2)
        d = tot["pnl"] - base["pnl"]
        cfg = f"act={activate} TPext={tp_ext}"
        print(f"{cfg:<22} {tot['pnl']:>8.2f} {tot['n']:>7} {tot['win_rate']:>5.1f}% {tot['avg_win']:>+7.2f}% {d:>+8.2f}")
        if best is None or d > best[1]:
            best = (cfg, d, tot["pnl"], tot["win_rate"], tot["avg_win"])

print("-" * 70)
if best and best[1] > 0.5:
    print(f"\n✅ MEILLEUR: {best[0]} -> PnL {best[2]:.2f}% (Δ {best[1]:+.2f}% vs FIXE, win {best[3]}%, avgwin {best[4]}%)")
    print("   -> Monter le TP en profit SANS breakeven AIDE. A valider puis implementer.")
else:
    print(f"\n❌ Aucune config EXTEND_TP ne bat FIXE (meilleur: {best[0]} Δ {best[1]:+.2f}%).")
    print("   -> Confirme: en marche range, meme sans breakeven, monter le TP ne suffit pas.")
    print("   -> Piste: TP/SL conditionnel au regime (EXTEND_TP seulement en TRENDING).")
