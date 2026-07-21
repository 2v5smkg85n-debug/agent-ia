#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_strategies_genetic.py — Ajoute 3 strategies + rend bb_ecart tunable
dans test_moteur.py. Prepare le terrain pour genetic_optimizer.py.

Nouvelles strategies:
  - Donchian Breakout (breakout canal 20)
  - Stochastic (%K/%D crossover en zone extreme)
  - EMA Crossover (EMA12/EMA26)

+ bb_ecart maintenant lu depuis strat_params.json (pour optimisation genetique)."""
import os, sys

f = "backtest_moteur.py"
src = open(f, encoding="utf-8").read()
orig = src

# ---- 1. Ajoute indicateurs apres bollinger_series ----
ANCHOR_IND = '''    hauts[i] = moyenne + ecart * e
        bas[i] = moyenne - ecart * e
    return hauts, bas'''
IND_ADD = '''    hauts[i] = moyenne + ecart * e
        bas[i] = moyenne - ecart * e
    return hauts, bas

def donchian_series(clotures, periode=20):
    """Retourne (haut, bas) rolling max/min sur periode, decales d'une bougie (breakout)."""
    hauts = [None] * len(clotures)
    bas = [None] * len(clotures)
    for i in range(periode, len(clotures)):
        fen = clotures[i-periode:i]  # exclut la bougie courante
        hauts[i] = max(fen)
        bas[i] = min(fen)
    return hauts, bas

def stochastic_series(clotures, periode=14, smooth=3):
    """Retourne (k, d). %K = position dans le range; %D = SMA de %K."""
    k = [None] * len(clotures)
    for i in range(periode - 1, len(clotures)):
        fen = clotures[i-periode+1:i+1]
        hh = max(fen); ll = min(fen)
        k[i] = 100.0 * (clotures[i] - ll) / (hh - ll) if hh != ll else 50.0
    d = [None] * len(clotures)
    for i in range(periode - 1 + smooth - 1, len(clotures)):
        fen = [x for x in k[i-smooth+1:i+1] if x is not None]
        if len(fen) == smooth:
            d[i] = sum(fen) / smooth
    return k, d

def ema_simple_series(clotures, periode):
    """EMA simple sur la serie complete."""
    out = [None] * len(clotures)
    if len(clotures) < periode:
        return out
    mult = 2 / (periode + 1)
    out[periode-1] = sum(clotures[:periode]) / periode
    for i in range(periode, len(clotures)):
        out[i] = (clotures[i] - out[i-1]) * mult + out[i-1]
    return out'''

assert ANCHOR_IND in src, "ANCHOR_IND introuvable"
src = src.replace(ANCHOR_IND, IND_ADD, 1)
print("OK indicateurs ajoutes (donchian, stochastic, ema)")

# ---- 2. Ajoute _bb_ecart apres _strat_params ----
ANCHOR_SP = '''    v = _SP_CACHE["vals"] or {}
    return v.get("rsi_achat", 35), v.get("rsi_vente", 70)'''
SP_ADD = '''    v = _SP_CACHE["vals"] or {}
    return v.get("rsi_achat", 35), v.get("rsi_vente", 70)

def _bb_ecart():
    """Lit bb_ecart de strat_params.json (cache partage). Fallback 2.0.
    Permet a genetic_optimizer.py d'optimiser l'ecart Bollinger."""
    if _SP_CACHE["vals"] is None:
        _strat_params()
    v = _SP_CACHE["vals"] or {}
    return v.get("bb_ecart", 2.0)'''
assert ANCHOR_SP in src, "ANCHOR_SP introuvable"
src = src.replace(ANCHOR_SP, SP_ADD, 1)
print("OK _bb_ecart ajoute")

# ---- 3. Rend bollinger ecart tunable dans simuler ----
ANCHOR_BB = 'donnees["bb_haut"], donnees["bb_bas"] = bollinger_series(clotures, 20, 2)'
BB_NEW = 'donnees["bb_haut"], donnees["bb_bas"] = bollinger_series(clotures, 20, _bb_ecart())'
assert ANCHOR_BB in src, "ANCHOR_BB introuvable"
src = src.replace(ANCHOR_BB, BB_NEW, 1)
print("OK bollinger ecart tunable dans simuler")

# ---- 4. Ajoute series au donnees dict dans simuler ----
ANCHOR_MACD = 'donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)'
MACD_NEW = '''donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)
    donnees["donchian_haut"], donnees["donchian_bas"] = donchian_series(clotures, 20)
    donnees["stoch_k"], donnees["stoch_d"] = stochastic_series(clotures, 14, 3)
    donnees["ema12"] = ema_simple_series(clotures, 12)
    donnees["ema26"] = ema_simple_series(clotures, 26)'''
assert ANCHOR_MACD in src, "ANCHOR_MACD introuvable"
src = src.replace(ANCHOR_MACD, MACD_NEW, 1)
print("OK series donchian/stoch/ema ajoutees au dict simuler")

# ---- 5. Ajoute 3 fonctions strategie apres strat_macd_momentum ----
ANCHOR_STRAT = '''    if m[i-1] >= s[i-1] and m[i] < s[i]:
        return "VENTE"
    return None

def _macd_full'''
STRAT_ADD = '''    if m[i-1] >= s[i-1] and m[i] < s[i]:
        return "VENTE"
    return None

def strat_donchian_breakout(i, d):
    """Achat quand prix casse au-dessus du plus haut 20 (breakout); vente sous le plus bas."""
    if d["donchian_haut"][i] is None or d["donchian_bas"][i] is None:
        return None
    prix = d["clotures"][i]
    if prix > d["donchian_haut"][i]:
        return "ACHAT"
    if prix < d["donchian_bas"][i]:
        return "VENTE"
    return None

def strat_stochastic(i, d):
    """Achat quand %K croise au-dessus %D en zone oversold (<20); vente inverse en overbought (>80)."""
    if i < 1:
        return None
    k, kd = d["stoch_k"], d["stoch_d"]
    if k[i] is None or kd[i] is None or k[i-1] is None or kd[i-1] is None:
        return None
    if k[i-1] <= kd[i-1] and k[i] > kd[i] and k[i] < 20:
        return "ACHAT"
    if k[i-1] >= kd[i-1] and k[i] < kd[i] and k[i] > 80:
        return "VENTE"
    return None

def strat_ema_crossover(i, d):
    """Achat quand EMA12 croise au-dessus EMA26; vente inverse."""
    if i < 1:
        return None
    e12, e26 = d["ema12"], d["ema26"]
    if e12[i] is None or e26[i] is None or e12[i-1] is None or e26[i-1] is None:
        return None
    if e12[i-1] <= e26[i-1] and e12[i] > e26[i]:
        return "ACHAT"
    if e12[i-1] >= e26[i-1] and e12[i] < e26[i]:
        return "VENTE"
    return None

def _macd_full'''
assert ANCHOR_STRAT in src, "ANCHOR_STRAT introuvable"
src = src.replace(ANCHOR_STRAT, STRAT_ADD, 1)
print("OK 3 strategies ajoutees (donchian, stochastic, ema)")

# ---- 6. Ajoute au STRATEGIES dict ----
ANCHOR_DICT = '''    "MACD Momentum":      strat_macd_momentum,
}'''
DICT_NEW = '''    "MACD Momentum":      strat_macd_momentum,
    "Donchian Breakout":  strat_donchian_breakout,
    "Stochastic":         strat_stochastic,
    "EMA Crossover":      strat_ema_crossover,
}'''
assert ANCHOR_DICT in src, "ANCHOR_DICT introuvable"
src = src.replace(ANCHOR_DICT, DICT_NEW, 1)
print("OK STRATEGIES dict mis a jour (7 strategies)")

if src == orig:
    print("ERREUR: aucune modification appliquee")
    sys.exit(1)
open(f, "w", encoding="utf-8").write(src)
print(f"\n{f} patche avec succes. Verifie:")
import subprocess
r = subprocess.run(["grep", "-n", "-E", "donchian|stochastic|ema_crossover|_bb_ecart", f],
                   capture_output=True, text=True)
print(r.stdout)
