#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_bougies.py — Le biais des chandeliers predit-il l'issue des trades ?

Methode: pour chaque entree (strategie + regime gate), on calcule le biais des
bougies au moment de l'entree. On compare:
  - entrees avec biais HAUSSIER (>0)  vs  autres (<=0)
  - win rate + pnl moyen par groupe

Si le groupe haussier gagne significativement plus -> le biais predit -> on integre.
Sinon -> rejet (comme ADX, trailing).

Aussi: test d'un FILTRE (garder seulement les entrees haussieres) -> PnL/trade
ameliore-t-il vs toutes entrees ?
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
ACTIFS_TEST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
               "GC=F", "NG=F", "HG=F", "ZW=F"]

from indicateurs import historique_ohlcv
from signaux_gagnants import signal_strategie, calculer_donnees
from regime import fit_multi_tf
from bougies_patterns import analyser_patterns

logging.basicConfig(level=logging.WARNING)


def entrees_actif(actif, strats):
    """Retourne (bougies, entrees[(bar, px, biais)])."""
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
                entrees.append(ouvert)
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
        # biais des bougies au moment de l'entree
        biais = analyser_patterns(bougies[: i + 1]).get("biais", 0.0)
        ouvert = {"bar": i, "px": px, "strat": nom, "biais": biais, "actif": actif}
    if ouvert:
        entrees.append(ouvert)
    return bougies, entrees


def issue_entree(bougies, e):
    """Simule l'issue (FIXE TP/SL/temps) d'une entree -> (variation%, gagne)."""
    bar_e, px_e = e["bar"], e["px"]
    closes = [b["cloture"] for b in bougies]
    fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
    ex = None
    for j in range(bar_e + 1, fin + 1):
        var = (closes[j] - px_e) / px_e * 100
        age = j - bar_e
        if var >= TP:
            ex = var; break
        if var <= -SL:
            ex = var; break
        if age >= MAX_BARS and var > 0:
            ex = var; break
    if ex is None:
        ex = (closes[fin] - px_e) / px_e * 100
    return ex, ex > 0


def main():
    strats_par_actif = bt._load_strategies()
    tous = []
    for a in ACTIFS_TEST:
        if a not in strats_par_actif:
            continue
        print(f"  -> {a} ...", flush=True)
        try:
            bougies, entrees = entrees_actif(a, strats_par_actif[a])
            if bougies and entrees:
                for e in entrees:
                    var, gagne = issue_entree(bougies, e)
                    e["var"] = var; e["gagne"] = gagne
                    tous.append(e)
        except Exception as ex:
            print(f"     {a}: {ex}")

    if not tous:
        print("Aucune entree."); return

    n = len(tous)
    wins = sum(1 for e in tous if e["gagne"])
    pnl = sum(e["var"] for e in tous)
    print("\n" + "=" * 72)
    print(f"BACKTEST BOUGIES (biais chandeliers vs issue des trades) — {n} entrees")
    print("=" * 72)
    print(f"{'Groupe':<24}{'N':>5}{'Win%':>8}{'PnL%':>9}{'AvgPnL':>9}")
    print("-" * 72)
    print(f"{'TOUTES entrees':<24}{n:>5}{100*wins/n:>7.1f}%{pnl:>9.2f}{pnl/n:>9.2f}")

    # split par biais
    haussier = [e for e in tous if e["biais"] > 0]
    neutre = [e for e in tous if e["biais"] == 0]
    baissier = [e for e in tous if e["biais"] < 0]

    def stats(g, nom):
        if not g:
            print(f"{nom:<24}0     -        -        -"); return
        w = sum(1 for e in g if e["gagne"])
        p = sum(e["var"] for e in g)
        print(f"{nom:<24}{len(g):>5}{100*w/len(g):>7.1f}%{p:>9.2f}{p/len(g):>9.2f}")
    stats(haussier, "biais HAUSSIER (>0)")
    stats(neutre, "biais NEUTRE (=0)")
    stats(baissier, "biais BAISSIER (<0)")

    # FILTRE: seulement haussier
    print("-" * 72)
    if haussier:
        wf = sum(1 for e in haussier if e["gagne"])
        pf = sum(e["var"] for e in haussier)
        print(f"{'FILTRE (haussier seul)':<24}{len(haussier):>5}{100*wf/len(haussier):>7.1f}%{pf:>9.2f}{pf/len(haussier):>9.2f}")
        d_win = (100*wf/len(haussier)) - (100*wins/n)
        d_avg = (pf/len(haussier)) - (pnl/n)
        print(f"\nDelta filtre vs toutes: win {d_win:+.1f}pt, avgPnL {d_avg:+.2f}%")
        print("=" * 72)
        if d_win > 5 and d_avg > 0.2 and len(haussier) >= max(8, n // 3):
            print("VERDICT: biais haussier predit l'issue -> A INTEGRER comme confirmation.")
        elif d_win < -5 or d_avg < -0.2:
            print("VERDICT: biais haussier n'aide (voire nuit) -> REJETE.")
        else:
            print("VERDICT: neutre -> le biais des bougies n'ajoute pas d'edge fiable.")
    else:
        print("Aucune entree avec biais haussier (patterns rares sur cet echantillon).")
        print("VERDICT: patterns trop rares pour conclure -> a retester sur plus de donnees.")


if __name__ == "__main__":
    main()
