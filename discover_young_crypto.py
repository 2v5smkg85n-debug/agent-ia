#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discover_young_crypto.py — Scan Binance pour trouver les jeunes crypto a potentiel.

Filtres:
  - paire USDT spot, status=TRADING, hors tokens leverages (UP/DOWN/BULL/BEAR)
  - jeune: < 365 jours d'historique 1d (recentement liste)
  - liquide: volume 24h > $10M (evite les illiquides/pump-dump)
  - momentum: performance 30j positive
Output: top 15 candidates avec age, volume, perf, volatilite, RSI, regime.
"""
import os, sys, json, urllib.request, time, math
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

API = "https://api.binance.com"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=20))

# 1) exchangeInfo: paires USDT spot TRADING
print("Recuperation exchangeInfo Binance...")
ei = get(f"{API}/api/v3/exchangeInfo")
usdt = []
for s in ei["symbols"]:
    if (s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed")):
        base = s["baseAsset"]
        if any(t in base for t in ["UP", "DOWN", "BULL", "BEAR"]) and len(base) > 3:
            continue  # tokens leverage
        usdt.append(s["symbol"])
print(f"  {len(usdt)} paires USDT spot TRADING")

# 2) ticker 24h: volume
print("Recuperation tickers 24h...")
tk = get(f"{API}/api/v3/ticker/24hr")
vol = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in tk}

# 3) Pour chaque paire, age (nb jours 1d) + perf + volatilite
print("Scan age/perf des candidates liquides...")
cands = []
for i, sym in enumerate(usdt):
    if vol.get(sym, 0) < 10_000_000:  # liquide mini $10M
        continue
    try:
        # 1d klines (max 1000) -> age + perf
        kl = get(f"{API}/api/v3/klines?symbol={sym}&interval=1d&limit=400")
        if len(kl) < 20:
            continue
        age = len(kl)
        closes = [float(k[4]) for k in kl]
        # perf 30j
        p30 = (closes[-1] / closes[-30] - 1) * 100 if len(closes) >= 30 else 0
        # perf 7j
        p7 = (closes[-1] / closes[-7] - 1) * 100 if len(closes) >= 7 else 0
        # volatilite 30j (ecart-type rendements)
        rets = [(closes[j]/closes[j-1]-1) for j in range(max(1,len(closes)-30), len(closes))]
        vola = (sum(r*r for r in rets)/len(rets))**0.5 * 100 if rets else 0
        # RSI 14
        gains, losses = [], []
        for j in range(1, min(15, len(closes))):
            d = closes[j] - closes[j-1]
            (gains if d > 0 else losses).append(abs(d))
        ag = sum(gains)/14 if gains else 0
        al = sum(losses)/14 if losses else 0
        rsi = 100 if al == 0 else (100 - 100/(1 + ag/al))
        # regime simple: trend_strength = abs(SMA20-SMA50)/SMA50
        sma20 = sum(closes[-20:])/20 if len(closes) >= 20 else closes[-1]
        sma50 = sum(closes[-50:])/50 if len(closes) >= 50 else sma20
        ts = abs(sma20 - sma50)/sma50 * 100 if sma50 else 0
        regime = "TREND" if ts > 3 else ("VOL" if vola > 5 else "QUIET")
        cands.append({
            "sym": sym, "age_j": age, "vol24m": vol[sym],
            "p7": p7, "p30": p30, "vola": vola, "rsi": rsi,
            "regime": regime, "px": closes[-1], "ts": ts,
        })
    except Exception as e:
        continue
    if i % 50 == 0:
        print(f"  ... {i}/{len(usdt)} traitees, {len(cands)} candidates")

# 4) Jeunes (< 365j) + classement
jeunes = [c for c in cands if c["age_j"] < 365]
# score: jeunesse (moins de jours = mieux) + volume + momentum30
for c in jeunes:
    c["score"] = (1 / max(c["age_j"], 5)) * 100 + math.log10(c["vol24m"]/1e6) + c["p30"]/5
jeunes.sort(key=lambda x: x["score"], reverse=True)

print("\n" + "=" * 96)
print(f"JEUNES CRYPTO (< 365j) LIQUIDES (> $10M vol24h) — {len(jeunes)} trouvees")
print("=" * 96)
print(f"{'#':<3}{'Symbole':<12}{'Age(j)':>7}{'Vol24h$M':>10}{'P7%':>7}{'P30%':>8}{'Vola%':>7}{'RSI':>6}  {'Regime':<7}")
print("-" * 96)
for i, c in enumerate(jeunes[:15]):
    print(f"{i+1:<3}{c['sym']:<12}{c['age_j']:>7}{c['vol24m']/1e6:>10.1f}"
          f"{c['p7']:>7.1f}{c['p30']:>8.1f}{c['vola']:>7.2f}{c['rsi']:>6.0f}  {c['regime']:<7}")

# 5) Cross-ref fondamentaux (de la recherche web)
print("\n--- CROSS-REF fondamentaux (recherche web) ---")
fonds = ["HUMA", "TAC", "RE", "XPL", "APRO", "PRL", "ALLO", "ESP", "LUMIA", "ACU", "HEI"]
for f in fonds:
    match = [c for c in cands if c["sym"].startswith(f)]
    if match:
        c = match[0]
        print(f"  {f:<6} {c['sym']:<12} age={c['age_j']}j vol=${c['vol24m']/1e6:.1f}M p30={c['p30']:+.1f}% regime={c['regime']}")
    else:
        print(f"  {f:<6} NON trouve sur Binance (ou < $10M vol)")

# sauvegarde
with open("young_crypto_candidates.json", "w") as f:
    json.dump(jeunes[:30], f, indent=2, ensure_ascii=False)
print(f"\nTop 30 sauvegarde dans young_crypto_candidates.json")
print("=" * 96)
