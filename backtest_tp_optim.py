#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_tp_optim.py — Grid search TP x SL pour maximiser le PnL.

Calcule les entrees (signaux + gate regime MTF) une fois, puis simule
toutes les combinaisons TP x SL et classe par PnL.
Si le combo optimal != 1.5/1.5, on peut ajuster les defaults / meta_tuning.
"""
import os
import json
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))

TPS = [1.0, 1.5, 2.0, 2.5, 3.0]
SLS = [1.0, 1.5, 2.0, 2.5]
MAX_BARS = 48
GATE = 1.0
LIMITE_BARS = 500
DEBUT = 60
FACTOR_4H = 4
ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bt_tp")


def _downsample(c, f):
    return [c[i] for i in range(f - 1, len(c), f)]


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


def collecter_entrees(actif, strats):
    """Retourne liste de (bar_entree, px_entree) avec gate regime MTF."""
    try:
        from indicateurs import historique_ohlcv
        from signaux_gagnants import signal_strategie, calculer_donnees
        from regime import fit_multi_tf
    except Exception as e:
        log.warning("imports indispo: %s", e)
        return None, None
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
            if var >= 1.5 or var <= -1.5 or (age >= MAX_BARS and var > 0):
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
        ouvert = {"px": px, "bar": i}
    if ouvert:
        entrees.append((ouvert["bar"], ouvert["px"]))
    return closes, entrees


def simuler_combo(closes, entrees, tp, sl):
    pnl = 0.0
    n = 0
    wins = 0
    for bar_e, px_e in entrees:
        fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
        exit_var = None
        for j in range(bar_e + 1, fin + 1):
            var = (closes[j] - px_e) / px_e * 100
            age = j - bar_e
            if var >= tp:
                exit_var = var
                break
            if var <= -sl:
                exit_var = var
                break
            if age >= MAX_BARS and var > 0:
                exit_var = var
                break
        if exit_var is None:
            exit_var = (closes[fin] - px_e) / px_e * 100
        pnl += exit_var
        n += 1
        if exit_var > 0:
            wins += 1
    return {"pnl": round(pnl, 2), "n": n,
            "win_rate": round(100 * wins / n, 1) if n else 0.0,
            "wins": wins}


def main():
    strats_par_actif = _load_strategies()
    if not strats_par_actif:
        log.error("Aucune stratégie chargée. Abandon.")
        return
    actifs = [a for a in ACTIFS_TEST if a in strats_par_actif] or list(strats_par_actif.keys())[:5]
    log.info("Grid search TP/SL sur: %s", actifs)
    # accumuler entrees et closes de tous les actifs
    toutes_entrees = []  # (closes_ref, bar, px) -> on regroupe par actif
    actifs_data = {}
    for actif in actifs:
        log.info("  -> %s ...", actif)
        closes, entrees = collecter_entrees(actif, strats_par_actif[actif])
        if closes and entrees:
            actifs_data[actif] = (closes, entrees)
    if not actifs_data:
        log.error("Aucune entrée collectée. Abandon.")
        return
    # grid search: pour chaque combo, simuler sur tous les actifs
    resultats = []
    for tp in TPS:
        for sl in SLS:
            tot_pnl = 0.0
            tot_n = 0
            tot_wins = 0
            for actif, (closes, entrees) in actifs_data.items():
                r = simuler_combo(closes, entrees, tp, sl)
                tot_pnl += r["pnl"]
                tot_n += r["n"]
                tot_wins += r["wins"]
            resultats.append({"tp": tp, "sl": sl, "pnl": round(tot_pnl, 2),
                              "n": tot_n,
                              "win_rate": round(100 * tot_wins / tot_n, 1) if tot_n else 0.0})
    resultats.sort(key=lambda x: x["pnl"], reverse=True)
    print("\n" + "=" * 60)
    print("GRID SEARCH TP x SL — top 8 par PnL")
    print("=" * 60)
    print(f"{'Rang':<5} {'TP%':>5} {'SL%':>5} {'PnL%':>8} {'Trades':>7} {'Win%':>6}")
    print("-" * 60)
    for i, r in enumerate(resultats[:8]):
        marker = "  ← actuel" if r["tp"] == 1.5 and r["sl"] == 1.5 else ""
        print(f"{i+1:<5} {r['tp']:>5.1f} {r['sl']:>5.1f} {r['pnl']:>+8.2f} "
              f"{r['n']:>7} {r['win_rate']:>5.1f}%{marker}")
    print("=" * 60)
    best = resultats[0]
    actuel = next((r for r in resultats if r["tp"] == 1.5 and r["sl"] == 1.5), None)
    print(f"\nVERDICT:")
    print(f"  Optimal: TP={best['tp']}% SL={best['sl']}% -> PnL {best['pnl']}% (win {best['win_rate']}%)")
    if actuel:
        print(f"  Actuel : TP=1.5% SL=1.5% -> PnL {actuel['pnl']}% (win {actuel['win_rate']}%)")
        diff = best["pnl"] - actuel["pnl"]
        if best["tp"] != 1.5 or best["sl"] != 1.5:
            print(f"  Gain potentiel: {diff:+.2f}% en passant a TP={best['tp']}% SL={best['sl']}%")
            print("  → Ajuster les defaults (TAKE_PROFIT_PCT/STOP_LOSS_PCT) ou meta_tuning.")
        else:
            print("  → Le combo actuel 1.5/1.5 est déjà optimal: rien à changer.")
    json.dump({"resultats": resultats, "actifs": list(actifs_data.keys())},
              open(os.path.join(DOSSIER, "backtest_tp_optim_resultats.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\nRésultats: {os.path.join(DOSSIER, 'backtest_tp_optim_resultats.json')}")


if __name__ == "__main__":
    main()
