#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""list_revolut_young_v2.py — Parse CORRECTEMENT le catalogue Revolut X (517 paires)
et identifie les jeunes crypto negociables en argent reel.

get_pairs() = dict {"LINK/USD": {base, quote, status, ...}, ...}
"""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")
from revolut_x import RevolutX

client = RevolutX()
pairs = client.get_pairs()  # dict symbol -> info

# 1) Parse correct
all_pairs = []
for symbol, info in pairs.items():
    if not isinstance(info, dict):
        continue
    all_pairs.append({
        "symbol": symbol,
        "base": info.get("base", ""),
        "quote": info.get("quote", ""),
        "status": info.get("status", ""),
        "min_quote": info.get("min_order_size_quote", ""),
    })

actives = [p for p in all_pairs if p["status"] == "active"]
print(f"=" * 80)
print(f"CATALOGUE REVOLUT X: {len(all_pairs)} paires total, {len(actives)} actives")
print(f"=" * 80)

# Grouper par quote
from collections import Counter
quotes = Counter(p["quote"] for p in actives)
print(f"\nRepartition par devise de cotation:")
for q, n in quotes.most_common():
    print(f"  {q}: {n} paires actives")

# 2) Cross-ref avec jeunes Binance + fondamentaux
print(f"\n--- CROSS-REF jeunes crypto Binance + fondamentaux ---")
binance_bases = ["BANK", "KITE", "OPN", "RE", "RLUSD", "TOWNS"]
fonds = ["HUMA", "TAC", "RE", "XPL", "APRO", "PRL", "ALLO", "ESP", "LUMIA", "ACU", "HEI"]
revolut_bases = {p["base"] for p in actives}
print(f"Revolut X a {len(revolut_bases)} bases distinctes")
print(f"\nJeunes Binance sur Revolut X:")
for b in binance_bases:
    matched = [p for p in actives if p["base"] == b]
    if matched:
        for p in matched:
            print(f"  ✅ {b:<8} {p['symbol']:<14} quote={p['quote']} min={p['min_quote']}")
    else:
        print(f"  ❌ {b:<8} NON sur Revolut X")
print(f"\nFondamentaux sur Revolut X:")
for f in fonds:
    matched = [p for p in actives if p["base"] == f]
    if matched:
        for p in matched:
            print(f"  ✅ {f:<8} {p['symbol']:<14} quote={p['quote']}")
    else:
        print(f"  ❌ {f:<8} NON sur Revolut X")

# 3) AGE des paires EUR actives (directement negociables en EUR)
print(f"\n--- AGE des paires EUR actives (negociables directement en euros) ---")
eur_pairs = [p for p in actives if p["quote"] == "EUR"]
print(f"{len(eur_pairs)} paires EUR actives — calcul age via get_candles...")

resultats = []
for p in eur_pairs:
    sym = p["symbol"]
    try:
        c = client.get_candles(sym)
        closes = []
        if isinstance(c, list):
            for row in c:
                if isinstance(row, dict):
                    closes.append(float(row.get("close") or row.get("price") or row.get("last") or 0))
                elif isinstance(row, (list, tuple)) and len(row) >= 5:
                    closes.append(float(row[4]))
        closes = [x for x in closes if x > 0]
        if len(closes) < 10:
            continue
        age = len(closes)
        p30 = (closes[-1]/closes[-30]-1)*100 if len(closes) >= 30 else 0
        p7 = (closes[-1]/closes[-7]-1)*100 if len(closes) >= 7 else 0
        rets = [(closes[j]/closes[j-1]-1) for j in range(max(1,len(closes)-30), len(closes))]
        vola = (sum(r*r for r in rets)/len(rets))**0.5*100 if rets else 0
        sma20 = sum(closes[-20:])/20 if len(closes) >= 20 else closes[-1]
        sma50 = sum(closes[-50:])/50 if len(closes) >= 50 else sma20
        ts = abs(sma20-sma50)/sma50*100 if sma50 else 0
        regime = "TREND" if ts > 3 else ("VOL" if vola > 5 else "QUIET")
        resultats.append({"symbol": sym, "base": p["base"], "age_j": age,
                          "p7": p7, "p30": p30, "vola": vola, "regime": regime,
                          "px": closes[-1], "jeune": age < 365})
    except Exception as e:
        pass

jeunes = sorted([r for r in resultats if r["jeune"]], key=lambda x: x["age_j"])
print(f"\n{'='*80}")
print(f"JEUNES CRYPTO (< 365j) DISPONIBLES SUR REVOLUT X EN EUR: {len(jeunes)}")
print(f"{'='*80}")
print(f"{'#':<3}{'Paire':<16}{'Base':<8}{'Age(j)':>7}{'P7%':>7}{'P30%':>8}{'Vola%':>7}  {'Regime':<7}")
print("-"*80)
for i, r in enumerate(jeunes[:25]):
    print(f"{i+1:<3}{r['symbol']:<16}{r['base']:<8}{r['age_j']:>7}{r['p7']:>7.1f}{r['p30']:>8.1f}{r['vola']:>7.2f}  {r['regime']:<7}")

# aussi: jeunes en USD (potentiellement negociables via conversion)
print(f"\n--- Aussi: top 15 jeunes en USD (via conversion EUR->USD si besoin) ---")
usd_pairs = [p for p in actives if p["quote"] == "USD"]
usd_results = []
for p in usd_pairs:
    sym = p["symbol"]
    try:
        c = client.get_candles(sym)
        closes = []
        if isinstance(c, list):
            for row in c:
                if isinstance(row, dict):
                    closes.append(float(row.get("close") or row.get("price") or 0))
                elif isinstance(row, (list, tuple)) and len(row) >= 5:
                    closes.append(float(row[4]))
        closes = [x for x in closes if x > 0]
        if len(closes) < 10:
            continue
        age = len(closes)
        p30 = (closes[-1]/closes[-30]-1)*100 if len(closes) >= 30 else 0
        usd_results.append({"symbol": sym, "base": p["base"], "age_j": age, "p30": p30})
    except Exception:
        pass
jeunes_usd = sorted([r for r in usd_results if r["age_j"] < 365], key=lambda x: x["age_j"])
print(f"{len(jeunes_usd)} jeunes en USD. Top 15:")
for i, r in enumerate(jeunes_usd[:15]):
    print(f"  {i+1}. {r['symbol']:<16} base={r['base']:<8} age={r['age_j']}j p30={r['p30']:+.1f}%")

with open("revolut_catalogue.json", "w") as f:
    json.dump({"total": len(all_pairs), "actives": len(actives),
               "jeunes_eur": jeunes, "jeunes_usd": jeunes_usd}, f, indent=2, default=str)
print(f"\nSauvegarde: revolut_catalogue.json")
print("="*80)
