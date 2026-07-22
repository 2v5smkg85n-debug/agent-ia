#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_backtest_long.py — BACKTEST LONG TERME (2 ans).
1. backtest_moteur.simuler: ajoute donchian/stoch/ema au dict donnees (CRITICAL fix).
   Avant simuler n'avait que 8 indicateurs -> les strat evolved (donchian) crashaient
   en KeyError dans walk_forward. Maintenant simuler matche causal_test/sanity_test.
2. indicateurs: historique_ohlcv_long() = fetch pagine Binance (startTime) pour >1000 bougies.
   Avant: plafonne a 1000 bougies (~41j en 1h). Maintenant: 2 ans possibles.
3. evolver: N_BOUGIES 800->17520 (~2 ans 1h), OOS ~730j au lieu de 10j. Utilise le fetch pagine.
Tous les patches sont idempotents (verif source avant application)."""
import sys

# ---------- 1. backtest_moteur.py: simuler donnees completes ----------
bf = "backtest_moteur.py"
b = open(bf, encoding="utf-8").read()

ANCHOR_SIM = '    donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)'
ADD_SIM = '''    donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)
    # INDICATEURS COMPLETS (evolved strategies + strat Phase 7 utilisent ces cles)
    # sinon KeyError dans simuler sur d["donchian_haut"] etc.
    donnees["donchian_haut"], donnees["donchian_bas"] = donchian_series(clotures, 20)
    donnees["stoch_k"], donnees["stoch_d"] = stochastic_series(clotures, 14, 3)
    donnees["ema12"] = ema_simple_series(clotures, 12)
    donnees["ema26"] = ema_simple_series(clotures, 26)'''
if 'donnees["donchian_haut"], donnees["donchian_bas"] = donchian_series' in b:
    print("[bt] simuler deja patche (donchian present) - skip")
elif ANCHOR_SIM in b:
    b = b.replace(ANCHOR_SIM, ADD_SIM, 1)
    print("[bt] simuler: donchian/stoch/ema ajoutes au dict donnees")
else:
    print("[bt] ERREUR ancre simuler _macd_full"); sys.exit(1)
open(bf, "w", encoding="utf-8").write(b)

# ---------- 2. indicateurs.py: historique_ohlcv_long (pagination) ----------
if_ = "indicateurs.py"
ind = open(if_, encoding="utf-8").read()

LONG_FN = '''

def historique_ohlcv_long(symbole="BTCUSDT", intervalle="1h", nb_bougies=17520):
    """Fetch >1000 bougies via PAGINATION Binance (startTime).
    Permet des backtests long terme (1-3 ans). Yahoo/coingecko: limite a 1000 (pas de pagination).
    Deduplique par temps, trie, trim au nb_bougies demande."""
    if _est_symbole_yahoo(symbole):
        return historique_ohlcv(symbole, intervalle, min(nb_bougies, 1000))
    import time as _t
    interval_ms = {"15m": 900000, "30m": 1800000, "1h": 3600000,
                   "4h": 14400000, "1d": 86400000}.get(intervalle, 3600000)
    now_ms = int(_t.time() * 1000)
    start_ms = now_ms - nb_bougies * interval_ms
    bougies = []
    calls = 0
    while start_ms < now_ms and len(bougies) < nb_bougies and calls < 40:
        calls += 1
        try:
            url = (f"https://api.binance.com/api/v3/klines?symbol={symbole}"
                   f"&interval={intervalle}&startTime={start_ms}&limit=1000")
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            chunk = [{"temps": x[0], "ouverture": float(x[1]), "haut": float(x[2]),
                      "bas": float(x[3]), "cloture": float(x[4]), "volume": float(x[5])} for x in data]
            bougies.extend(chunk)
            start_ms = chunk[-1]["temps"] + interval_ms  # avance apres la derniere
            if len(chunk) < 1000:
                break  # plus de donnees dispo (coin recent)
            _t.sleep(0.1)  # rate-limit friendly
        except Exception:
            break
    # dedup par temps + tri + trim
    seen = {}
    for x in bougies:
        seen[x["temps"]] = x
    bougies = sorted(seen.values(), key=lambda x: x["temps"])
    return bougies[-nb_bougies:] if len(bougies) > nb_bougies else bougies
'''
if "def historique_ohlcv_long" in ind:
    print("[ind] historique_ohlcv_long deja present - skip")
elif "def _historique_coingecko(symbole, intervalle, limite):" in ind:
    ind = ind.replace("def _historique_coingecko(symbole, intervalle, limite):",
                      LONG_FN.lstrip("\n") + "\ndef _historique_coingecko(symbole, intervalle, limite):", 1)
    print("[ind] historique_ohlcv_long (pagination) ajoute")
else:
    print("[ind] ERREUR ancre _historique_coingecko"); sys.exit(1)
open(if_, "w", encoding="utf-8").write(ind)

# ---------- 3. strategy_evolver.py: N_BOUGIES + fetch long ----------
ef = "strategy_evolver.py"
e = open(ef, encoding="utf-8").read()

# import
OLD_IMP = "from indicateurs import historique_ohlcv"
NEW_IMP = "from indicateurs import historique_ohlcv, historique_ohlcv_long"
if "historique_ohlcv_long" in e:
    print("[evo] import long deja present - skip")
elif OLD_IMP in e:
    e = e.replace(OLD_IMP, NEW_IMP, 1)
    print("[evo] import historique_ohlcv_long ajoute")
else:
    print("[evo] ERREUR ancre import"); sys.exit(1)

# N_BOUGIES
OLD_NB = "N_BOUGIES = 800   # fenetre plus large: OOS = 240 bougies (~10j) au lieu de 150 (~6j)"
NEW_NB = "N_BOUGIES = 17520  # BACKTEST LONG TERME: ~2 ans en 1h. OOS = ~730j (au lieu de 10j). Fetch pagine."
if "N_BOUGIES = 17520" in e:
    print("[evo] N_BOUGIES=17520 deja present - skip")
elif OLD_NB in e:
    e = e.replace(OLD_NB, NEW_NB, 1)
    print("[evo] N_BOUGIES 800->17520 (~2 ans)")
else:
    print("[evo] ERREUR ancre N_BOUGIES"); sys.exit(1)

# fetch line
OLD_FETCH = "            b = historique_ohlcv(sym, INTERVALLE, N_BOUGIES)"
NEW_FETCH = "            b = historique_ohlcv_long(sym, INTERVALLE, N_BOUGIES)"
if "historique_ohlcv_long(sym, INTERVALLE, N_BOUGIES)" in e:
    print("[evo] fetch long deja present - skip")
elif OLD_FETCH in e:
    e = e.replace(OLD_FETCH, NEW_FETCH, 1)
    print("[evo] fetch -> historique_ohlcv_long (pagination)")
else:
    print("[evo] ERREUR ancre fetch"); sys.exit(1)
open(ef, "w", encoding="utf-8").write(e)

print("\n=== PATCH BACKTEST LONG TERME APPLIQUE ===")
print("1. simuler: 14 indicateurs (donchian/stoch/ema ajoutes)")
print("2. indicateurs: historique_ohlcv_long (pagination Binance, max 40 calls)")
print("3. evolver: N_BOUGIES=17520 (~2 ans), fetch pagine")
