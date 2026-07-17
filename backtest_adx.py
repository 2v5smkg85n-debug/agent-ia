#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_adx.py — Mesure l'impact du filtre ADX sur les stratégies.

Pour chaque actif + stratégie:
  - BASE: signaux bruts de la stratégie
  - GATE: entrées trend-following supprimées si ADX<25 (règle Wilder)
Compare PnL%, win rate, nb trades. Aggrégé + par stratégie.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
sys.path.insert(0, os.getcwd())

from backtest_engine import (get_candles, ACTIFS, STRATEGIES, backtest)
from regime import STRATEGIES_TREND_FOLLOWING, SEUIL_ADX_TREND

CAPITAL = 1000.0
FEE = 0.1


def adx_series(highs, lows, closes, period=14):
    """Série ADX de Wilder par barre (None avant ~2*period)."""
    n = len(closes)
    out = [None] * n
    if n < period * 3:
        return out
    tr = [0.0] * n; pdm = [0.0] * n; mdm = [0.0] * n
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        pdm[i] = up if (up > down and up > 0) else 0.0
        mdm[i] = down if (down > up and down > 0) else 0.0

    def smooth(arr, p):
        s = [None] * n
        if n < p + 1:
            return s
        val = sum(arr[1:p + 1])
        s[p] = val
        for i in range(p + 1, n):
            val = val - val / p + arr[i]
            s[i] = val
        return s

    atr = smooth(tr, period)
    s_pdm = smooth(pdm, period)
    s_mdm = smooth(mdm, period)
    dx = [None] * n
    for i in range(n):
        if atr[i] and atr[i] > 0:
            pdi = 100 * s_pdm[i] / atr[i]
            mdi = 100 * s_mdm[i] / atr[i]
            denom = pdi + mdi
            dx[i] = 100 * abs(pdi - mdi) / denom if denom > 0 else 0.0
    # ADX = moyenne lissée des DX (Wilder)
    valid = [i for i in range(n) if dx[i] is not None]
    if len(valid) < period:
        return out
    first_adx_idx = valid[period - 1]
    s = sum(dx[valid[k]] for k in range(period))
    out[first_adx_idx] = s / period
    last = first_adx_idx
    for k in range(period, len(valid)):
        i = valid[k]
        out[i] = (out[last] * (period - 1) + dx[i]) / period
        last = i
    return out


def gate_signaux(sig, nom, adx_vals):
    """Supprime les entrées des stratégies trend-following si ADX<25.
    sig = signal de position (1=long, 0=flat). Les sorties sont préservées."""
    gated = []
    in_pos = False
    is_tf = nom in STRATEGIES_TREND_FOLLOWING
    for i in range(len(sig)):
        want = sig[i]
        if not in_pos and want == 1:
            if is_tf and adx_vals[i] is not None and adx_vals[i] < SEUIL_ADX_TREND:
                want = 0  # pas de tendance -> on n'entre pas
            else:
                in_pos = True
        elif in_pos and want == 0:
            in_pos = False
        gated.append(want)
    return gated


def stats(trades, equity):
    n = len(trades)
    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    pct = (equity[-1] / CAPITAL - 1) * 100 if equity else 0
    wr = wins / n * 100 if n else 0
    return {"n": n, "pnl_pct": round(pct, 2), "win_rate": round(wr, 1), "pnl_eur": round(pnl, 2)}


print("=" * 60)
print("BACKTEST FILTRE ADX (coupe trend-following si ADX<25)")
print("=" * 60)
print(f"Capital: {CAPITAL}€ | Frais: {FEE}%/trade | Données: 2 ans daily\n")

tot_base = {"n": 0, "pnl_eur": 0.0, "wins": 0}
tot_gate = {"n": 0, "pnl_eur": 0.0, "wins": 0}
par_strat = {}  # nom -> {"base": stats, "gate": stats}

for sym, (marche, nom_actif) in ACTIFS.items():
    try:
        c = get_candles(sym, "2y")
    except Exception as e:
        print(f"  {sym}: fetch impossible ({e})")
        continue
    if not c or len(c) < 100:
        print(f"  {sym}: pas assez de données ({len(c) if c else 0})")
        continue
    highs = [x["h"] for x in c]
    lows = [x["l"] for x in c]
    closes = [x["c"] for x in c]
    adx_vals = adx_series(highs, lows, closes)

    for strat in STRATEGIES:
        sig, nom = strat(c)
        gated = gate_signaux(sig, nom, adx_vals)
        tb, eb, _ = backtest(c, sig, CAPITAL, FEE)
        tg, eg, _ = backtest(c, gated, CAPITAL, FEE)
        sb = stats(tb, eb)
        sg = stats(tg, eg)
        tot_base["n"] += sb["n"]; tot_base["pnl_eur"] += sb["pnl_eur"]; tot_base["wins"] += sum(1 for t in tb if t["pnl"] > 0)
        tot_gate["n"] += sg["n"]; tot_gate["pnl_eur"] += sg["pnl_eur"]; tot_gate["wins"] += sum(1 for t in tg if t["pnl"] > 0)
        d = par_strat.setdefault(nom, {"base": {"n":0,"pnl_eur":0.0,"wins":0}, "gate": {"n":0,"pnl_eur":0.0,"wins":0}})
        d["base"]["n"] += sb["n"]; d["base"]["pnl_eur"] += sb["pnl_eur"]; d["base"]["wins"] += sum(1 for t in tb if t["pnl"]>0)
        d["gate"]["n"] += sg["n"]; d["gate"]["pnl_eur"] += sg["pnl_eur"]; d["gate"]["wins"] += sum(1 for t in tg if t["pnl"]>0)

print("\n=== PAR STRATÉGIE ===")
print(f"{'Stratégie':<22} {'BASE PnL€':>10} {'GATE PnL€':>10} {'Δ':>8} {'BASE n':>7} {'GATE n':>7} {'BASE WR%':>8} {'GATE WR%':>8} TF?")
for nom, d in par_strat.items():
    b, g = d["base"], d["gate"]
    wrb = b["wins"]/b["n"]*100 if b["n"] else 0
    wrg = g["wins"]/g["n"]*100 if g["n"] else 0
    delta = g["pnl_eur"] - b["pnl_eur"]
    tf = "✂️" if nom in STRATEGIES_TREND_FOLLOWING else "—"
    print(f"{nom:<22} {b['pnl_eur']:>10.2f} {g['pnl_eur']:>10.2f} {delta:>+8.2f} {b['n']:>7} {g['n']:>7} {wrb:>8.1f} {wrg:>8.1f}  {tf}")

b, g = tot_base, tot_gate
wrb = b["wins"]/b["n"]*100 if b["n"] else 0
wrg = g["wins"]/g["n"]*100 if g["n"] else 0
delta = g["pnl_eur"] - b["pnl_eur"]
print("\n" + "=" * 60)
print("TOTAL AGGRÉGÉ")
print("=" * 60)
print(f"  BASE (sans ADX): PnL {b['pnl_eur']:+.2f}€ | {b['n']} trades | win {wrb:.1f}%")
print(f"  GATE (avec ADX): PnL {g['pnl_eur']:+.2f}€ | {g['n']} trades | win {wrg:.1f}%")
print(f"  DELTA: {delta:+.2f}€ ({delta/CAPITAL*100:+.2f}%) | trades {g['n']-b['n']:+d} | win {wrg-wrb:+.1f}pt")
print()
if delta > 0:
    print("✅ Le filtre ADX AMÉLIORE le PnL — à garder déployé.")
elif delta > -5:
    print("⚠️ Le filtre ADX est ~neutre — règle Wilder standard, à garder.")
else:
    print("❌ Le filtre ADX DÉGRADE le PnL — revoir le seuil (25) ou désactiver.")
