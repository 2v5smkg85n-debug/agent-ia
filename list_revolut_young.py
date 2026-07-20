#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""list_revolut_young.py — Liste les crypto disponibles sur Revolut X (argent reel)
et identifie les jeunes a potentiel negociables.

Etapes:
  1. get_pairs() -> catalogue complet Revolut X (paires actives)
  2. get_candles() pour chaque paire -> age (nb jours) + perf + regime
  3. cross-ref avec young_crypto_candidates.json (scan Binance) -> jeunes negociables
  4. cross-ref avec fondamentaux (HUMA, TAC, etc.)
Output: jeunes crypto disponibles sur Revolut X, pretes pour backtest + integration.
"""
import os, sys, json, math
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from revolut_x import RevolutX

print("Connexion Revolut X...")
client = RevolutX()
try:
    bal = client.get_balances()
    print(f"  connexion OK (balances: {len(bal) if isinstance(bal,list) else '?'} comptes)")
except Exception as e:
    print(f"  ATTENTION get_balances: {e} (continue quand meme)")

# 1) Catalogue paires Revolut X
print("\nRecuperation catalogue paires Revolut X...")
pairs = client.get_pairs()
if isinstance(pairs, dict):
    pairs_list = list(pairs.values()) if pairs and isinstance(list(pairs.values())[0], list) else [{"raw": k, "v": v} for k,v in pairs.items()]
else:
    pairs_list = pairs if isinstance(pairs, list) else []

print(f"  {len(pairs_list)} paires retournees par get_pairs()")
print(f"  type: {type(pairs)}")

# Normaliser: extraire symbol/base/quote/status
norm = []
for p in pairs_list:
    if isinstance(p, dict):
        sym = p.get("symbol") or p.get("id") or p.get("name", "")
        base = p.get("base_asset") or p.get("baseAsset") or p.get("base", "")
        quote = p.get("quote_asset") or p.get("quoteAsset") or p.get("quote", "")
        status = p.get("status") or p.get("state", "")
        norm.append({"symbol": sym, "base": base, "quote": quote, "status": status, "raw": p})
    else:
        norm.append({"symbol": str(p), "base": "", "quote": "", "status": "", "raw": p})

# Filtrer paires EUR actives
actives = [n for n in norm if (n["quote"] == "EUR" or "-EUR" in str(n["symbol"])) and n["status"] != "CLOSED"]
print(f"  paires EUR actives: {len(actives)}")
print("\n--- Catalogue Revolut X (toutes paires actives) ---")
for n in norm:
    if n["status"] != "CLOSED":
        print(f"  {n['symbol']:<14} base={n['base']:<8} quote={n['quote']:<5} {n['status']}")

# 2) Pour chaque paire EUR active, calculer age + perf via get_candles
print("\n--- AGE & PERF des paires Revolut X ---")
resultats = []
for n in actives:
    sym = n["symbol"]
    try:
        c = client.get_candles(sym)
        # format varie: liste de {close, timestamp...} ou listes
        closes = []
        if isinstance(c, list):
            for row in c:
                if isinstance(row, dict):
                    closes.append(float(row.get("close") or row.get("price") or row.get("last") or 0))
                elif isinstance(row, (list, tuple)) and len(row) >= 5:
                    closes.append(float(row[4]))  # OHLCV close
        closes = [x for x in closes if x > 0]
        if len(closes) < 10:
            continue
        age = len(closes)
        p30 = (closes[-1]/closes[-30]-1)*100 if len(closes) >= 30 else 0
        rets = [(closes[j]/closes[j-1]-1) for j in range(max(1,len(closes)-30), len(closes))]
        vola = (sum(r*r for r in rets)/len(rets))**0.5*100 if rets else 0
        sma20 = sum(closes[-20:])/20 if len(closes) >= 20 else closes[-1]
        sma50 = sum(closes[-50:])/50 if len(closes) >= 50 else sma20
        ts = abs(sma20-sma50)/sma50*100 if sma50 else 0
        regime = "TREND" if ts > 3 else ("VOL" if vola > 5 else "QUIET")
        resultats.append({"symbol": sym, "base": n["base"], "age_j": age,
                          "p30": p30, "vola": vola, "regime": regime,
                          "px": closes[-1], "jeune": age < 365})
    except Exception as e:
        print(f"  {sym}: candles KO ({e})")

# 3) Jeunes sur Revolut X
jeunes_revolut = [r for r in resultats if r["jeune"]]
jeunes_revolut.sort(key=lambda x: x["age_j"])
print(f"\n{'='*80}")
print(f"JEUNES CRYPTO (< 365j) DISPONIBLES SUR REVOLUT X (argent reel): {len(jeunes_revolut)}")
print(f"{'='*80}")
print(f"{'#':<3}{'Paire':<14}{'Base':<8}{'Age(j)':>7}{'P30%':>8}{'Vola%':>7}  {'Regime':<7}")
print("-"*80)
for i, r in enumerate(jeunes_revolut[:20]):
    print(f"{i+1:<3}{r['symbol']:<14}{r['base']:<8}{r['age_j']:>7}{r['p30']:>8.1f}{r['vola']:>7.2f}  {r['regime']:<7}")

# 4) Cross-ref avec scan Binance (young_crypto_candidates.json)
print(f"\n--- CROSS-REF avec scan Binance (young_crypto_candidates.json) ---")
if os.path.exists("young_crypto_candidates.json"):
    binance_cands = json.load(open("young_crypto_candidates.json"))
    binance_bases = {c["sym"].replace("USDT","").replace("EUR","") for c in binance_cands}
    print(f"  {len(binance_cands)} candidates Binance, bases: {sorted(binance_bases)[:20]}")
    print("  Jeunes crypto NEGOCIABLES sur Revolut X ET presentes dans scan Binance:")
    match = 0
    for r in jeunes_revolut:
        if r["base"] in binance_bases:
            match += 1
            bc = next((c for c in binance_cands if c["sym"].replace("USDT","")==r["base"]), {})
            print(f"    ✅ {r['symbol']:<12} age={r['age_j']}j p30={r['p30']:+.1f}% regime={r['regime']} "
                  f"| Binance vol=${bc.get('vol24m',0)/1e6:.1f}M p30={bc.get('p30',0):+.1f}%")
    if match == 0:
        print("    (aucun match direct — les jeunes crypto Binance ne sont pas sur Revolut X)")
else:
    print("  young_crypto_candidates.json absent — lance d'abord discover_young_crypto.py")

# 5) Cross-ref fondamentaux
print("\n--- CROSS-REF fondamentaux ---")
fonds = ["HUMA", "TAC", "RE", "XPL", "APRO", "PRL", "ALLO", "ESP", "LUMIA", "ACU", "HEI"]
for f in fonds:
    m = [r for r in resultats if r["base"] == f]
    if m:
        r = m[0]
        print(f"  ✅ {f:<6} {r['symbol']:<12} age={r['age_j']}j p30={r['p30']:+.1f}% regime={r['regime']}")
    else:
        print(f"  ❌ {f:<6} NON disponible sur Revolut X")

# sauvegarde
with open("revolut_young_crypto.json", "w") as f:
    json.dump({"toutes_paires": len(norm), "actives_eur": len(actives),
              "jeunes": jeunes_revolut}, f, indent=2, ensure_ascii=False)
print(f"\nSauvegarde: revolut_young_crypto.json")
print("="*80)
