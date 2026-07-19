#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_sagesse.py — Teste les principes des maitres traders sur le systeme.

3 tests (discipline: backtest avant deploiement):
  1. deep_contrarian (Buffett/Rogers/Soros): RSI<20 (creux profond) vs RSI<30
  2. cut_losers (Soros/PTJ): exit plus rapide des perdants ameliore PnL?
  3. turtle_breakout (Dennis): Donchian 20-bar breakout (trend, test honnete)
"""
import os, sys, logging
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

import backtest_trailing as bt
from backtest_bougies import entrees_actif, issue_entree, ACTIFS_TEST
from indicateurs import historique_ohlcv, rsi

TP = getattr(bt, "TP", 2.0); SL = getattr(bt, "SL", 2.5)
MAX_BARS = getattr(bt, "MAX_BARS", 48); DEBUT = getattr(bt, "DEBUT", 60)
strats_par_actif = bt._load_strategies()
logging.basicConfig(level=logging.WARNING)


def collecter():
    data = {}  # actif -> (bougies, entrees with var/gagne)
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
                data[a] = (bougies, entrees)
        except Exception as ex:
            print(f"     {a}: {ex}")
    return data


def test_deep_contrarian(data):
    """RSI<20 (creux profond) vs RSI 20-30."""
    print("\n" + "=" * 74)
    print("TEST 1 - DEEP CONTRARIAN (Buffett/Rogers): creux profond gagne-t-il plus?")
    print("=" * 74)
    deep, shallow = [], []
    for a, (bougies, entrees) in data.items():
        closes = [b["cloture"] for b in bougies]
        for e in entrees:
            if "RSI" not in e.get("strat", ""):
                continue
            try:
                r = rsi(closes[: e["bar"] + 1], 14)
            except Exception:
                r = None
            if r is None:
                continue
            e2 = dict(e); e2["rsi"] = r
            if r < 20:
                deep.append(e2)
            else:
                shallow.append(e2)

    def stats(g, n):
        if not g:
            print(f"  {n:<22}0 entrees"); return
        w = sum(1 for x in g if x["gagne"])
        p = sum(x["var"] for x in g)
        print(f"  {n:<22}{len(g):>3} entrees | win {100*w/len(g):.1f}% | avgPnL {p/len(g):.3f}% | total {p:.2f}%")

    stats(deep, "RSI<20 (creux profond)")
    stats(shallow, "RSI 20-30 (normal)")
    if deep and shallow:
        wd = 100*sum(1 for x in deep if x["gagne"])/len(deep)
        ws = 100*sum(1 for x in shallow if x["gagne"])/len(shallow)
        ad = sum(x["var"] for x in deep)/len(deep)
        as_ = sum(x["var"] for x in shallow)/len(shallow)
        print(f"\n  Delta: win {wd-ws:+.1f}pt, avgPnL {ad-as_:+.3f}")
        if wd - ws > 5 and ad > as_:
            print("  VERDICT: creux profond gagne plus -> A INTEGRER (preference RSI<20)")
        elif wd - ws < -5:
            print("  VERDICT: creux profond ne aide pas -> REJETE")
        else:
            print("  VERDICT: neutre (echantillon faible?)")


def issue_fastcut(bougies, e, cut_bars=12):
    """Simule avec cut rapide: exit si perdant apres cut_bars."""
    closes = [b["cloture"] for b in bougies]
    bar_e, px_e = e["bar"], e["px"]
    fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
    ex = None
    for j in range(bar_e + 1, fin + 1):
        var = (closes[j] - px_e) / px_e * 100
        age = j - bar_e
        if var >= TP:
            ex = var; break
        if var <= -SL:
            ex = var; break
        if age >= cut_bars and var < 0:  # CUT: perdant apres cut_bars
            ex = var; break
        if age >= MAX_BARS and var > 0:
            ex = var; break
    if ex is None:
        ex = (closes[fin] - px_e) / px_e * 100
    return ex


def test_cut_losers(data):
    print("\n" + "=" * 74)
    print("TEST 2 - CUT LOSERS FAST (Soros/PTJ): exit rapide des perdants?")
    print("=" * 74)
    tous = [e for _, (_, es) in data.items() for e in es]
    if not tous:
        print("  Aucune entree."); return
    n = len(tous)
    pnl_normal = sum(e["var"] for e in tous)
    for cut in [12, 18, 24]:
        pnl_cut = 0; wins = 0
        for a, (bougies, entrees) in data.items():
            for e in entrees:
                v = issue_fastcut(bougies, e, cut)
                pnl_cut += v
                if v > 0: wins += 1
        print(f"  cut@{cut}bars: PnL {pnl_cut:.2f}% | win {100*wins/n:.1f}% (vs normal {pnl_normal:.2f}% / {100*sum(1 for x in tous if x['gagne'])/n:.1f}%)")
    print(f"  normal   : PnL {pnl_normal:.2f}% | win {100*sum(1 for x in tous if x['gagne'])/n:.1f}%")
    print("  VERDICT: si cut@X ameliore PnL -> integrer exit rapide des perdants")


def test_turtle(data):
    print("\n" + "=" * 74)
    print("TEST 3 - TURTLE BREAKOUT (Dennis): Donchian 20-bar (trend, honnete)")
    print("=" * 74)
    trades = []
    for a in ACTIFS_TEST:
        bougies = historique_ohlcv(a, "1h", 500)
        if not bougies or len(bougies) < 80:
            continue
        closes = [b["cloture"] for b in bougies]
        for i in range(60, len(closes) - 1):
            window = closes[i - 20:i]
            if len(window) < 20:
                continue
            don_high = max(window)
            if closes[i] > don_high:  # breakout haussier
                # simule FIXE
                px = closes[i]; ex = None
                fin = min(i + MAX_BARS + 20, len(closes) - 1)
                for j in range(i + 1, fin + 1):
                    var = (closes[j] - px) / px * 100
                    if var >= TP: ex = var; break
                    if var <= -SL: ex = var; break
                    if (j - i) >= MAX_BARS and var > 0: ex = var; break
                if ex is None: ex = (closes[fin] - px) / px * 100
                trades.append({"var": ex, "gagne": ex > 0, "actif": a})
    if not trades:
        print("  Aucun trade breakout."); return
    w = sum(1 for t in trades if t["gagne"])
    p = sum(t["var"] for t in trades)
    print(f"  Donchian breakout: {len(trades)} trades | win {100*w/len(trades):.1f}% | "
          f"PnL {p:.2f}% | avg {p/len(trades):.3f}%")
    print("  VERDICT: si win<55% ou PnL<0 -> trend rejete en QUIET (confirme meta-pattern)")


def main():
    print("Collecte des entrees...")
    data = collecter()
    tous = [e for _, (_, es) in data.items() for e in es]
    print(f"\n{len(tous)} entrees collectees.")
    test_deep_contrarian(data)
    test_cut_losers(data)
    test_turtle(data)
    print("\n" + "=" * 74)


if __name__ == "__main__":
    main()
