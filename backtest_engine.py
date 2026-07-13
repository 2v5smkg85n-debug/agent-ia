#!/usr/bin/env python3
"""Moteur de backtest serieux (Phase 3) — vraies donnees de marche (Yahoo Finance).
Backteste des strategies parametriques en walk-forward et calcule de vraies métriques.
Sortie: backtests_reels_pro.json (remplace les évaluations IA à 1 essai)."""
import json
import math
import os
import datetime

try:
    import yfinance as yf
except ImportError:
    yf = None


# ============ DATA ============
CACHE = "price_cache.json"


def load_cache():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def save_cache(c):
    with open(CACHE, "w") as f:
        json.dump(c, f)


def fetch(sym, period="2y"):
    """Récupère OHLCV daily via Yahoo Finance."""
    df = yf.download(sym, period=period, interval="1d", progress=False, auto_adjust=False)
    if df is None or len(df) == 0:
        return []
    if df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    candles = []
    for idx, row in df.iterrows():
        try:
            o = float(row["Open"]); h = float(row["High"])
            l = float(row["Low"]); c = float(row["Close"])
            v = float(row["Volume"]) if "Volume" in row else 0.0
        except (ValueError, TypeError):
            continue
        if math.isnan(c) or c <= 0:
            continue
        candles.append({"date": str(idx.date()), "o": o, "h": h, "l": l, "c": c, "v": v})
    return candles


def get_candles(sym, period="2y"):
    cache = load_cache()
    key = f"{sym}:{period}"
    if key in cache:
        return cache[key]
    if yf is None:
        return []
    cl = fetch(sym, period)
    cache[key] = cl
    save_cache(cache)
    return cl


# ============ INDICATEURS ============
def sma(values, n):
    out = [None] * len(values)
    for i in range(n - 1, len(values)):
        out[i] = sum(values[i - n + 1:i + 1]) / n
    return out


def ema(values, n):
    out = [None] * len(values)
    k = 2 / (n + 1)
    prev = None
    for i, v in enumerate(values):
        if i < n - 1:
            continue
        if prev is None:
            prev = sum(values[i - n + 1:i + 1]) / n
        else:
            prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, n=14):
    out = [None] * len(values)
    if len(values) < n + 1:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    ag = gains / n
    al = losses / n
    rs = ag / al if al > 0 else 999
    out[n] = 100 - 100 / (1 + rs)
    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        g = d if d > 0 else 0
        l = -d if d < 0 else 0
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
        rs = ag / al if al > 0 else 999
        out[i] = 100 - 100 / (1 + rs)
    return out


def bollinger(values, n=20, k=2.0):
    upper = [None] * len(values)
    lower = [None] * len(values)
    mid = sma(values, n)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1:i + 1]
        m = mid[i]
        var = sum((x - m) ** 2 for x in window) / n
        sd = math.sqrt(var)
        upper[i] = m + k * sd
        lower[i] = m - k * sd
    return upper, lower, mid


# ============ STRATEGIES (signal: 1=long, 0=flat) ============
def strat_sma_cross(c):
    closes = [x["c"] for x in c]
    f = sma(closes, 20); s = sma(closes, 50)
    sig = [0] * len(c)
    for i in range(len(c)):
        if f[i] is not None and s[i] is not None:
            sig[i] = 1 if f[i] > s[i] else 0
    return sig, "SMA Crossover"


def strat_ema_cross(c):
    closes = [x["c"] for x in c]
    f = ema(closes, 12); s = ema(closes, 26)
    sig = [0] * len(c)
    for i in range(len(c)):
        if f[i] is not None and s[i] is not None:
            sig[i] = 1 if f[i] > s[i] else 0
    return sig, "EMA Crossover"


def strat_rsi_reversion(c):
    closes = [x["c"] for x in c]
    r = rsi(closes, 14)
    sig = [0] * len(c)
    pos = 0
    for i in range(len(c)):
        if r[i] is None:
            sig[i] = pos
            continue
        if r[i] < 30:
            pos = 1
        elif r[i] > 50:
            pos = 0
        sig[i] = pos
    return sig, "RSI Mean Reversion"


def strat_bollinger_breakout(c):
    closes = [x["c"] for x in c]
    up, lo, mid = bollinger(closes, 20, 2.0)
    sig = [0] * len(c)
    pos = 0
    for i in range(len(c)):
        if up[i] is None:
            sig[i] = pos
            continue
        if closes[i] > up[i]:
            pos = 1
        elif closes[i] < mid[i]:
            pos = 0
        sig[i] = pos
    return sig, "Bollinger Breakout"


def strat_donchian(c, n=20):
    closes = [x["c"] for x in c]
    highs = [x["h"] for x in c]
    sig = [0] * len(c)
    pos = 0
    for i in range(n, len(c)):
        hh = max(highs[i - n:i])
        if closes[i] > hh:
            pos = 1
        elif closes[i] < min(closes[i - n:i]):
            pos = 0
        sig[i] = pos
    return sig, "Donchian Breakout"


STRATEGIES = [strat_sma_cross, strat_ema_cross, strat_rsi_reversion,
              strat_bollinger_breakout, strat_donchian]

ACTIFS = {
    "BTC-USD": ("crypto", "Bitcoin"),
    "ETH-USD": ("crypto", "Ethereum"),
    "AAPL": ("actions", "Apple"),
    "MSFT": ("actions", "Microsoft"),
    "EURUSD=X": ("forex", "EUR/USD"),
    "JPY=X": ("forex", "USD/JPY"),
    "^GSPC": ("indices", "S&P 500"),
    "^FCHI": ("indices", "CAC 40"),
    "GC=F": ("matieres", "Or"),
    "CL=F": ("matieres", "Pétrole WTI"),
}


# ============ BACKTEST ============
def backtest(candles, signals, capital=1000.0, fee_pct=0.1):
    """Retourne (trades, equity_curve, metrics)."""
    if len(candles) < 60:
        return [], [], {}
    fee = fee_pct / 100
    cash = capital
    pos = 0  # 0 flat, 1 long
    qty = 0.0
    entry = 0.0
    trades = []
    equity = [capital]
    for i in range(1, len(candles)):
        price = candles[i]["c"]
        sig = signals[i]
        # clôture si signal flat et en position
        if pos == 1 and sig == 0:
            proceeds = qty * price
            cost_fee = proceeds * fee
            cash += proceeds - cost_fee
            pnl = (price - entry) * qty - entry * qty * fee - cost_fee
            trades.append({"pnl": pnl, "retour": pnl / (entry * qty) * 100 if entry * qty else 0})
            pos = 0; qty = 0.0
        # ouverture si signal long et flat
        if pos == 0 and sig == 1:
            cost = cash
            entry = price
            qty = (cost * (1 - fee)) / price
            cash = 0.0
            pos = 1
        # equity mark-to-market
        eq = cash + qty * price if pos == 1 else cash
        equity.append(eq)
    # clôture finale
    if pos == 1:
        price = candles[-1]["c"]
        proceeds = qty * price
        cost_fee = proceeds * fee
        cash += proceeds - cost_fee
        pnl = (price - entry) * qty - entry * qty * fee - cost_fee
        trades.append({"pnl": pnl, "retour": pnl / (entry * qty) * 100 if entry * qty else 0})
        equity[-1] = cash
    return trades, equity, compute_metrics(trades, equity, capital, fee_pct)


def compute_metrics(trades, equity, capital, fee_pct):
    if not equity:
        return {}
    gains = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    gross_win = sum(gains)
    gross_loss = abs(sum(losses))
    n = len(trades)
    wins = len(gains)
    final = equity[-1]
    retour = (final - capital) / capital * 100
    # drawdown
    peak = equity[0]; mdd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (e - peak) / peak * 100 if peak else 0
        if dd < mdd:
            mdd = dd
    # sharpe (rendements journaliers)
    rets = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            rets.append(equity[i] / equity[i - 1] - 1)
    if len(rets) > 1:
        m = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
        sharpe = m / sd * math.sqrt(252) if sd > 0 else 0
    else:
        sharpe = 0
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0)
    expectancy = sum(t["pnl"] for t in trades) / n if n else 0
    return {
        "trades": n, "gagnes": wins, "perdus": n - wins,
        "win_rate": wins / n * 100 if n else 0,
        "retour_pct": retour, "profit_factor": pf if pf != float("inf") else 99.0,
        "drawdown_max": abs(mdd), "sharpe": sharpe,
        "expectancy": expectancy, "capital_final": final,
        "frais_effectif_pct": fee_pct,
    }


def walk_forward(candles, signals_fn, n_folds=4):
    """Precision = % de folds out-of-sample rentables."""
    n = len(candles)
    if n < 100:
        return 0.0, []
    fold = n // (n_folds + 1)
    if fold < 20:
        return 0.0, []
    results = []
    for k in range(1, n_folds + 1):
        start = k * fold
        end = (k + 1) * fold if k < n_folds else n
        if end <= start:
            continue
        seg = candles[start:end]
        sig, _ = signals_fn(seg)
        tr, eq, m = backtest(seg, sig)
        results.append(m.get("retour_pct", 0) > 0)
    prec = sum(1 for r in results if r) / len(results) * 100 if results else 0
    return prec, results


def main():
    print("Moteur de backtest Phase 3 — vraies données Yahoo Finance")
    print(f"Actifs: {len(ACTIFS)} | Stratégies: {len(STRATEGIES)}\n")
    results = []
    for sym, (marche, nom) in ACTIFS.items():
        cl = get_candles(sym)
        if len(cl) < 60:
            print(f"  {sym:<10} — données insuffisantes ({len(cl)})")
            continue
        for strat_fn in STRATEGIES:
            sig, sname = strat_fn(cl)
            tr, eq, m = backtest(cl, sig)
            wf, folds = walk_forward(cl, strat_fn)
            m.update({
                "strategie": sname, "actif": sym, "nom": nom,
                "marche": marche, "bougies": len(cl),
                "wf_precision": wf, "wf_folds": folds,
            })
            m["verdict"] = "GAGNANTE" if (m.get("retour_pct", 0) > 0 and m.get("profit_factor", 0) >= 1 and wf >= 50) else "PERDANTE"
            results.append(m)
            pf = m["profit_factor"]
            print(f"  {sname:<22} {sym:<10} {marche:<8} ret={m['retour_pct']:+6.2f}% pf={pf:5.2f} wr={m['win_rate']:4.0f}% dd={m['drawdown_max']:4.1f}% wf={wf:3.0f}% {m['verdict']}")
    with open("backtests_reels_pro.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    gagnantes = sum(1 for r in results if r["verdict"] == "GAGNANTE")
    print(f"\n{len(results)} backtests → {gagnantes} gagnantes ({gagnantes/len(results)*100:.0f}%)")
    print("Sauvé: backtests_reels_pro.json")
    append_history(results, gagnantes)


def append_history(results, gagnantes):
    """Ajoute un snapshot quotidien au track record (backtests_history.jsonl)."""
    if not results:
        return
    rets = [r.get("retour_pct", 0) for r in results]
    pfs = [r.get("profit_factor", 0) for r in results]
    wrs = [r.get("win_rate", 0) for r in results]
    dds = [r.get("drawdown_max", 0) for r in results]
    # top 5 strategies gagnantes
    top = sorted(results, key=lambda x: x.get("retour_pct", 0), reverse=True)[:5]
    snap = {
        "date": datetime.date.today().isoformat(),
        "n_backtests": len(results),
        "n_gagnantes": gagnantes,
        "pct_gagnantes": gagnantes / len(results) * 100,
        "retour_moyen": sum(rets) / len(rets),
        "profit_factor_moy": sum(pfs) / len(pfs),
        "win_rate_moy": sum(wrs) / len(wrs),
        "drawdown_moy": sum(dds) / len(dds),
        "top5": [{"strategie": t.get("strategie"), "actif": t.get("actif"),
                  "retour": t.get("retour_pct"), "pf": t.get("profit_factor")} for t in top],
    }
    with open("backtests_history.jsonl", "a") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print(f"Historique: backtests_history.jsonl ({snap['date']})")


if __name__ == "__main__":
    main()
