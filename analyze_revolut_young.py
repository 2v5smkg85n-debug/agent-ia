#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_revolut_young.py — Parmi les 58 crypto EUR de Revolut X, identifie
les jeunes (< 365j) a potentiel en utilisant les donnees Binance (OHLCV).

Pour chaque base Revolut EUR:
  - fetch Binance 1d klines (BASE+USDT)
  - calcule age, perf 7j/30j, volatilite, RSI, regime, liquidite
  - filtre jeunes (< 365j)
Output: jeunes crypto a potentiel negociables en argent reel sur Revolut X.
"""
import os, json, urllib.request, math

API = "https://api.binance.com"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=20))

# Les 58 bases EUR de Revolut X
BASES = ["1INCH","AAVE","ADA","ALGO","APT","ARB","ATOM","AVAX","AVNT","BCH","BNB",
         "BONK","BTC","CHZ","CRV","DOGE","DOT","ENA","ETC","ETH","FET","FIDA","FIL",
         "FLOKI","HBAR","HYPE","ICP","INJ","JASMY","LDO","LINK","LTC","MAGIC","NEAR",
         "ONDO","OP","PENDLE","PENGU","PEPE","POL","RENDER","SEI","SHIB","SOL","SPX",
         "STRK","STX","SUI","TIA","TON","TRUMP","TRX","UNI","WIF","XLM","XRP","ZRO"]

# volumes 24h Binance (pour liquidite)
print("Recuperation volumes 24h Binance...")
tk = get(f"{API}/api/v3/ticker/24hr")
vol = {t["symbol"]: float(t.get("quoteVolume",0)) for t in tk}

print(f"Analyse de {len(BASES)} bases Revolut EUR via Binance...\n")
resultats = []
for base in BASES:
    sym = base + "USDT"
    try:
        kl = get(f"{API}/api/v3/klines?symbol={sym}&interval=1d&limit=1000")
        if len(kl) < 20:
            print(f"  {base:<8} pas assez d'historique Binance ({len(kl)} j) — skip")
            continue
        closes = [float(k[4]) for k in kl]
        age = len(kl)
        p7 = (closes[-1]/closes[-7]-1)*100 if len(closes)>=7 else 0
        p30 = (closes[-1]/closes[-30]-1)*100 if len(closes)>=30 else 0
        p90 = (closes[-1]/closes[-90]-1)*100 if len(closes)>=90 else 0
        rets = [(closes[j]/closes[j-1]-1) for j in range(max(1,len(closes)-30),len(closes))]
        vola = (sum(r*r for r in rets)/len(rets))**0.5*100 if rets else 0
        gains, losses = [], []
        for j in range(1, min(15,len(closes))):
            d = closes[j]-closes[j-1]
            (gains if d>0 else losses).append(abs(d))
        ag = sum(gains)/14 if gains else 0
        al = sum(losses)/14 if losses else 0
        rsi = 100 if al==0 else (100-100/(1+ag/al))
        sma20 = sum(closes[-20:])/20 if len(closes)>=20 else closes[-1]
        sma50 = sum(closes[-50:])/50 if len(closes)>=50 else sma20
        ts = abs(sma20-sma50)/sma50*100 if sma50 else 0
        regime = "TREND" if ts>3 else ("VOL" if vola>5 else "QUIET")
        v24 = vol.get(sym, 0)
        resultats.append({
            "base": base, "sym_binance": sym, "age_j": age,
            "p7": p7, "p30": p30, "p90": p90, "vola": vola, "rsi": rsi,
            "regime": regime, "vol24m": v24, "px": closes[-1], "ts": ts,
            "jeune": age < 365,
        })
    except Exception as e:
        print(f"  {base:<8} Binance KO: {e}")

# Jeunes uniquement
jeunes = sorted([r for r in resultats if r["jeune"]], key=lambda x: x["age_j"])
print("=" * 100)
print(f"JEUNES CRYPTO (< 365j) NEGOCIABLES SUR REVOLUT X (EUR, argent reel): {len(jeunes)}/{len(resultats)} analysables")
print("=" * 100)
print(f"{'#':<3}{'Base':<8}{'Age(j)':>7}{'Vol24$M':>9}{'P7%':>7}{'P30%':>8}{'P90%':>8}{'Vola%':>7}{'RSI':>5}  {'Regime':<7}")
print("-" * 100)
for i, r in enumerate(jeunes):
    print(f"{i+1:<3}{r['base']:<8}{r['age_j']:>7}{r['vol24m']/1e6:>9.1f}{r['p7']:>7.1f}{r['p30']:>8.1f}{r['p90']:>8.1f}{r['vola']:>7.2f}{r['rsi']:>5.0f}  {r['regime']:<7}")

# Score potentiel: jeunesse + momentum30 + liquidite - vola excessive
for r in jeunes:
    r["pot"] = (1/max(r["age_j"],5))*50 + math.log10(max(r["vol24m"]/1e6,1)) + r["p30"]/10 - (r["vola"]/5 if r["vola"]>8 else 0)
jeunes.sort(key=lambda x: x["pot"], reverse=True)
print(f"\n--- TOP 10 par SCORE POTENTIEL (jeunesse + momentum + liquidite) ---")
for i, r in enumerate(jeunes[:10]):
    print(f"  {i+1}. {r['base']:<8} age={r['age_j']}j vol=${r['vol24m']/1e6:.1f}M p30={r['p30']:+.1f}% p90={r['p90']:+.1f}% regime={r['regime']} score={r['pot']:.1f}")

# Aussi: les etablies (age >= 365) pour reference
print(f"\n--- Pour reference: crypto ETABLIES (>= 365j) sur Revolut EUR ---")
etab = sorted([r for r in resultats if not r["jeune"]], key=lambda x: x["p30"], reverse=True)
for r in etab[:8]:
    print(f"  {r['base']:<8} age={r['age_j']}j p30={r['p30']:+.1f}% regime={r['regime']} vol=${r['vol24m']/1e6:.1f}M")

with open("revolut_young_analyzed.json", "w") as f:
    json.dump({"jeunes": jeunes, "etablies": etab}, f, indent=2, default=str)
print(f"\nSauvegarde: revolut_young_analyzed.json")
print("=" * 100)
