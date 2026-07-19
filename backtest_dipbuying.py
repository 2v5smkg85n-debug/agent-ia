#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_dipbuying.py — Filtre dip-buying: n'entrer que sur bougie baissiere.

Hypothese (issue du rejet bougies): le systeme est mean-reversion, donc acheter
un creux (bougie baissiere a l'entree) = meilleure qualite d'entree.

Test: comparer FIXE (toutes entrees) vs FILTRE DIP (biais < seuil) sur:
  - n trades, win%, avg PnL, total PnL
  - qualite (avg PnL/trade) — important sous caps (10€/trade, 30€ max):
    mieux vaut moins de trades mais meilleurs, que du volume perdant.

Seuils testes: biais < 0, < -0.1, < -0.2.
"""
import os, sys, logging
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from backtest_bougies import entrees_actif, issue_entree, ACTIFS_TEST, bt
import backtest_trailing as bt2

strats_par_actif = bt2._load_strategies()
logging.basicConfig(level=logging.WARNING)


def collecter():
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
    return tous


def stats(g, nom):
    if not g:
        print(f"{nom:<28}{'0':>4}{'-':>9}{'-':>10}{'-':>10}")
        return
    w = sum(1 for e in g if e["gagne"])
    p = sum(e["var"] for e in g)
    n = len(g)
    print(f"{nom:<28}{n:>4}{100*w/n:>8.1f}%{p:>10.2f}{p/n:>10.3f}")


def main():
    tous = collecter()
    if not tous:
        print("Aucune entree."); return
    n = len(tous)
    wins = sum(1 for e in tous if e["gagne"])
    pnl = sum(e["var"] for e in tous)

    print("\n" + "=" * 78)
    print(f"FILTRE DIP-BUYING (achat de creux = bougie baissiere) — {n} entrees")
    print("=" * 78)
    print(f"{'Config':<28}{'N':>4}{'Win%':>9}{'PnL%':>10}{'AvgPnL':>10}")
    print("-" * 78)
    stats(tous, "FIXE (toutes entrees)")
    stats([e for e in tous if e["biais"] < 0], "DIP biais<0")
    stats([e for e in tous if e["biais"] <= -0.1], "DIP biais<=-0.1")
    stats([e for e in tous if e["biais"] <= -0.2], "DIP biais<=-0.2")
    stats([e for e in tous if e["biais"] > 0], "  (ref) biais>0")

    print("-" * 78)
    # verdict sur le seuil < 0
    dip = [e for e in tous if e["biais"] < 0]
    if dip:
        wd = sum(1 for e in dip if e["gagne"])
        pd = sum(e["var"] for e in dip)
        d_win = (100*wd/len(dip)) - (100*wins/n)
        d_avg = (pd/len(dip)) - (pnl/n)
        d_pnl = pd - pnl
        print(f"\nDelta DIP(biais<0) vs FIXE:")
        print(f"  win rate : {100*wins/n:.1f}% -> {100*wd/len(dip):.1f}% ({d_win:+.1f}pt)")
        print(f"  avg PnL  : {pnl/n:.3f} -> {pd/len(dip):.3f} ({d_avg:+.3f})")
        print(f"  total PnL: {pnl:.2f} -> {pd:.2f} ({d_pnl:+.2f})  [{len(dip)}/{n} trades gardes]")
        print("=" * 78)
        # sous caps (10€/trade, 30€ max = 3 positions), la qualite > volume
        if d_win > 3 and d_avg > 0.05 and len(dip) >= 10:
            print("VERDICT: filtre dip-buying ameliore qualite (win+avgPnL) sous caps.")
            print("         -> A integrer comme gate d'entree (biais bougie < 0 requis).")
        elif d_win > 0 and d_avg > 0:
            print("VERDICT: legerement positif mais faible -> a confirmer sur plus de trades.")
        else:
            print("VERDICT: pas d'amelioration fiable -> ne pas integrer.")
    else:
        print("Aucune entree baissiere.")


if __name__ == "__main__":
    main()
