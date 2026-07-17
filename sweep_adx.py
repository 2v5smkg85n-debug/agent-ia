#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sweep_adx.py — Test plusieurs seuils ADX pour trouver celui qui aide."""
import os, sys
os.chdir(os.path.dirname(os.path.abspath("regime.py")) or ".")
sys.path.insert(0, ".")
from backtest_engine import get_candles, ACTIFS, STRATEGIES, backtest
from regime import STRATEGIES_TREND_FOLLOWING

CAPITAL = 1000.0
FEE = 0.1


def adx_series(h, l, c, p=14):
    n = len(c); out = [None] * n
    if n < p * 3:
        return out
    tr = [0.0] * n; pd = [0.0] * n; md = [0.0] * n
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        u = h[i] - h[i - 1]; d = l[i - 1] - l[i]
        pd[i] = u if (u > d and u > 0) else 0.0
        md[i] = d if (d > u and d > 0) else 0.0

    def sm(a, p):
        s = [None] * n; v = sum(a[1:p + 1]); s[p] = v
        for i in range(p + 1, n):
            v = v - v / p + a[i]; s[i] = v
        return s
    atr = sm(tr, p); spd = sm(pd, p); smd = sm(md, p); dx = [None] * n
    for i in range(n):
        if atr[i] and atr[i] > 0:
            pi = 100 * spd[i] / atr[i]; mi = 100 * smd[i] / atr[i]; den = pi + mi
            dx[i] = 100 * abs(pi - mi) / den if den > 0 else 0.0
    val = [i for i in range(n) if dx[i] is not None]
    if len(val) < p:
        return out
    fa = val[p - 1]; sv = sum(dx[val[k]] for k in range(p)); out[fa] = sv / p; last = fa
    for k in range(p, len(val)):
        i = val[k]; out[i] = (out[last] * (p - 1) + dx[i]) / p; last = i
    return out


def gate(sig, nom, adv, seuil):
    g = []; ip = False; tf = nom in STRATEGIES_TREND_FOLLOWING
    for i in range(len(sig)):
        w = sig[i]
        if not ip and w == 1:
            if tf and adv[i] is not None and adv[i] < seuil:
                w = 0
            else:
                ip = True
        elif ip and w == 0:
            ip = False
        g.append(w)
    return g


cache = {}
for sym in ACTIFS:
    try:
        c = get_candles(sym, "2y")
        if c and len(c) > 100:
            cache[sym] = (c, adx_series([x["h"] for x in c], [x["l"] for x in c], [x["c"] for x in c]))
    except Exception:
        pass

print("=" * 62)
print("SWEEP SEUIL ADX (2 ans, 10 actifs x 5 stratégies)")
print("=" * 62)
base_pnl = 0.0; base_n = 0
for sym, (c, adv) in cache.items():
    for st in STRATEGIES:
        sig, nom = st(c)
        tb, eb, _ = backtest(c, sig, CAPITAL, FEE)
        base_pnl += sum(t["pnl"] for t in tb); base_n += len(tb)
print(f"\nBASE (sans gate): {base_pnl:+.2f}€ | {base_n} trades\n")
print(f"{'Seuil':<10} {'PnL€':>10} {'Δ vs base':>12} {'n':>8} {'verdict':>10}")
print("-" * 54)
best = None
for seuil in [10, 15, 18, 20, 25, 30, 40]:
    gp = 0.0; gn = 0
    for sym, (c, adv) in cache.items():
        for st in STRATEGIES:
            sig, nom = st(c)
            tg, eg, _ = backtest(c, gate(sig, nom, adv, seuil), CAPITAL, FEE)
            gp += sum(t["pnl"] for t in tg); gn += len(tg)
    d = gp - base_pnl
    v = "✅ aide" if d > 5 else ("≈ neutre" if d > -5 else "❌ nuit")
    print(f"ADX<{seuil:<4} {gp:>10.2f} {d:>+12.2f} {gn:>8} {v:>10}")
    if best is None or d > best[1]:
        best = (seuil, d)
print()
print(f"Meilleur seuil: ADX<{best[0]} (Δ {best[1]:+.2f}€)" if best and best[1] > 5
      else "Aucun seuil n'améliore le PnL → retirer le filtre ADX.")
