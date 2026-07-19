#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_trailing.py — Compare TP fixe vs trailing stop (laisser courir les gagnants).

Strategie live (signaux + gate regime MTF) avec 2 modes de sortie:
  FIXE    : TP +1.5% / SL -1.5% (comportement actuel)
  TRAIL   : SL -1.5%, trailing (active a +0.5%, ferme si retrait 0.8% du pic), hard cap +3%

Si TRAIL > FIXE en PnL (surtout avg win), le trailing aide -> l'activer en live.
"""
import os
import json
import math
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))

TP, SL = 1.5, 1.5
TRAIL_ACTIVATE = 0.5
TRAIL_PCT = 0.8
# EXTEND: stop breakeven + TP dynamique (stop positif -> TP monte)
BREAKEVEN_ACTIVATE = 0.5   # active breakeven + TP etend a +0.5% de gain
TP_EXTEND = 3.0            # TP monte une fois en profit
HARD_CAP = 3.0
MAX_BARS = 48
GATE = 1.0
LIMITE_BARS = 500
DEBUT = 60
FACTOR_4H = 4
ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bt_trail")


def _downsample(closes_1h, factor):
    return [closes_1h[i] for i in range(factor - 1, len(closes_1h), factor)]


def _load_strategies():
    try:
        from signaux_gagnants import strategies_gagnantes_par_actif
        par_actif = strategies_gagnantes_par_actif() or {}
    except Exception as e:
        log.warning("strategies indispo: %s", e)
        return {}
    out = {}
    for actif, par_interv in par_actif.items():
        strats = []
        if isinstance(par_interv, dict):
            strats = par_interv.get("1h", []) or par_interv.get("15m", [])
        elif isinstance(par_interv, list):
            strats = par_interv
        if strats:
            out[actif] = [{"strategie": s.get("strategie"),
                           "retour_pct": float(s.get("retour_pct", 0) or 0)}
                          for s in strats if s.get("strategie")]
    return out


def simuler_actif(actif, strats):
    """Simule les 2 modes (FIXE, TRAIL) en parallele sur le meme actif."""
    try:
        from indicateurs import historique_ohlcv
        from signaux_gagnants import signal_strategie, calculer_donnees
        from regime import fit_multi_tf
    except Exception as e:
        log.warning("imports indispo: %s", e)
        return None
    bougies = historique_ohlcv(actif, "1h", LIMITE_BARS)
    if not bougies or len(bougies) < DEBUT + 10:
        return None
    closes = [b["cloture"] for b in bougies]
    # entrees identiques pour les 2 modes (meme signaux + gate) -> on calcule les barres d'entree
    entrees = []  # (bar_entree, strat)
    ouvert = None
    for i in range(DEBUT, len(closes)):
        px = closes[i]
        if ouvert:
            var = (px - ouvert["px"]) / ouvert["px"] * 100
            age = i - ouvert["bar"]
            # sortie fixe pour determiner la fenetre d'entree (TP/SL/time)
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                entrees.append((ouvert["bar"], ouvert["strat"], ouvert["px"]))
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
        entrees.append((ouvert["bar"], ouvert["strat"], ouvert["px"]))
    # maintenant simuler les 2 modes de sortie sur chaque entree
    res = {m: {"pnl": 0.0, "n": 0, "wins": 0, "max_win": 0.0, "sum_win": 0.0}
           for m in ("FIXE", "TRAIL", "EXTEND")}
    for bar_e, strat, px_e in entrees:
        fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
        peak = 0.0
        exit_fixe = None
        exit_trail = None
        exit_ext = None
        for j in range(bar_e + 1, fin + 1):
            px = closes[j]
            var = (px - px_e) / px_e * 100
            peak = max(peak, var)
            # FIXE
            if exit_fixe is None:
                age = j - bar_e
                if var >= TP:
                    exit_fixe = (j, var, "TP")
                elif var <= -SL:
                    exit_fixe = (j, var, "SL")
                elif age >= MAX_BARS and var > 0:
                    exit_fixe = (j, var, "TEMPS")
            # TRAIL
            if exit_trail is None:
                age = j - bar_e
                if var <= -SL:
                    exit_trail = (j, var, "SL")
                elif peak >= TRAIL_ACTIVATE and var <= peak - TRAIL_PCT:
                    exit_trail = (j, var, "TRAIL")
                elif var >= HARD_CAP:
                    exit_trail = (j, var, "CAP")
                elif age >= MAX_BARS and var > 0:
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
                break
        if exit_fixe is None:
            exit_fixe = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        if exit_trail is None:
            exit_trail = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        if exit_ext is None:
            exit_ext = (fin, (closes[fin] - px_e) / px_e * 100, "FIN")
        for m, ex in (("FIXE", exit_fixe), ("TRAIL", exit_trail), ("EXTEND", exit_ext)):
            v = ex[1]
            res[m]["pnl"] += v
            res[m]["n"] += 1
            if v > 0:
                res[m]["wins"] += 1
                res[m]["sum_win"] += v
                res[m]["max_win"] = max(res[m]["max_win"], v)
    for m in res:
        res[m]["win_rate"] = round(100 * res[m]["wins"] / res[m]["n"], 1) if res[m]["n"] else 0.0
        res[m]["avg_win"] = round(res[m]["sum_win"] / res[m]["wins"], 2) if res[m]["wins"] else 0.0
        res[m]["max_win"] = round(res[m]["max_win"], 2)
        res[m]["pnl"] = round(res[m]["pnl"], 2)
    return res


def main():
    strats_par_actif = _load_strategies()
    if not strats_par_actif:
        log.error("Aucune stratégie chargée. Abandon.")
        return
    actifs = [a for a in ACTIFS_TEST if a in strats_par_actif] or list(strats_par_actif.keys())[:5]
    log.info("Backtest trailing sur: %s", actifs)
    tot = {m: {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
           for m in ("FIXE", "TRAIL", "EXTEND")}
    par_actif = {}
    for actif in actifs:
        log.info("  -> %s ...", actif)
        r = simuler_actif(actif, strats_par_actif[actif])
        if not r:
            continue
        par_actif[actif] = r
        for m in tot:
            for k in tot[m]:
                tot[m][k] += r[m][k]
    for m in tot:
        tot[m]["win_rate"] = round(100 * tot[m]["wins"] / tot[m]["n"], 1) if tot[m]["n"] else 0.0
        tot[m]["avg_win"] = round(tot[m]["sum_win"] / tot[m]["wins"], 2) if tot[m]["wins"] else 0.0
        tot[m]["max_win"] = round(tot[m]["max_win"], 2)
        tot[m]["pnl"] = round(tot[m]["pnl"], 2)
    print("\n" + "=" * 72)
    print("BACKTEST TP FIXE vs TRAILING STOP (stratégie live + gate regime MTF)")
    print("=" * 72)
    print(f"{'Mode':<8} {'PnL%':>8} {'Trades':>7} {'Win%':>6} {'AvgWin':>8} {'MaxWin':>8}")
    print("-" * 72)
    for m in ("FIXE", "TRAIL", "EXTEND"):
        t = tot[m]
        print(f"{m:<8} {t['pnl']:>8.2f} {t['n']:>7} {t['win_rate']:>5.1f}% "
              f"{t['avg_win']:>+7.2f}% {t['max_win']:>+7.2f}%")
    print("=" * 72)
    pf, pt, pe = tot["FIXE"]["pnl"], tot["TRAIL"]["pnl"], tot["EXTEND"]["pnl"]
    print(f"\nVERDICT:")
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
        print("  (rappel: le trailing nuit aussi -> garder le TP fixe.)")
    json.dump({"totaux": tot, "par_actif": par_actif,
               "config": {"TP": TP, "SL": SL, "TRAIL_ACTIVATE": TRAIL_ACTIVATE,
                          "TRAIL_PCT": TRAIL_PCT, "HARD_CAP": HARD_CAP}},
              open(os.path.join(DOSSIER, "backtest_trailing_resultats.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\nRésultats: {os.path.join(DOSSIER, 'backtest_trailing_resultats.json')}")


if __name__ == "__main__":
    main()
