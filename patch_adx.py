#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_adx.py
1) regime.py: ajoute adx() (Wilder), STRATEGIES_TREND_FOLLOWING, SEUIL_ADX_TREND, adx_actif()
2) signaux_gagnants.py: gate ADX (coupe trend-following si ADX<25)
3) test: calcule l'ADX réel des marchés actuels (vérifie valeurs sensées en QUIET)
"""
import os, sys

DOSSIER = os.getcwd()

# ============================================================
# 1) PATCH regime.py
# ============================================================
RP = os.path.join(DOSSIER, "regime.py")
src = open(RP, encoding="utf-8").read()

R_ANCHOR = """    return (f1 + f4) / 2.0, reg_1h, reg_4h


def regimes_actuels(marches=None):"""

R_INSERT = '''    return (f1 + f4) / 2.0, reg_1h, reg_4h


# --- ADX (force de tendance, Welles Wilder) ---
# Strategies trend-following qui ont besoin d'une tendance nette (ADX eleve).
# Si ADX < SEUIL_ADX_TREND, on coupe leurs signaux (marche sans tendance).
STRATEGIES_TREND_FOLLOWING = {"MACD Momentum", "SMA Crossover", "EMA Crossover",
                              "Donchian", "Bollinger Breakout"}
SEUIL_ADX_TREND = 25.0   # ADX<25 = pas de tendance nette (regle Wilder standard)


def adx(bougies, period=14):
    """ADX de Wilder (force de tendance, independant de la direction).
    bougies: liste de dicts avec cles haut/bas/cloture (ou high/low/close).
    Retourne float (0-100) ou None si donnees insuffisantes.
    >25 = tendance nette, <20 = pas de tendance."""
    if not bougies or len(bougies) < period * 3:
        return None

    def _val(b, cles):
        for k in cles:
            if k in b:
                return float(b[k])
        return None
    H = [_val(b, ("haut", "high", "High")) for b in bougies]
    L = [_val(b, ("bas", "low", "Low")) for b in bougies]
    C = [_val(b, ("cloture", "close", "Close")) for b in bougies]
    for i in range(len(bougies)):
        if H[i] is None:
            H[i] = C[i]
        if L[i] is None:
            L[i] = C[i]

    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, len(bougies)):
        h, l, c, pc = H[i], L[i], C[i], C[i - 1]
        tr_i = max(h - l, abs(h - pc), abs(l - pc))
        up = H[i] - H[i - 1]
        down = L[i - 1] - L[i]
        pdm = up if (up > down and up > 0) else 0.0
        mdm = down if (down > up and down > 0) else 0.0
        tr.append(tr_i); plus_dm.append(pdm); minus_dm.append(mdm)
    if len(tr) < period:
        return None

    def _wilder(arr, p):
        sm = [sum(arr[:p])]
        for i in range(p, len(arr)):
            sm.append(sm[-1] - sm[-1] / p + arr[i])
        return sm

    atr = _wilder(tr, period)
    s_pdm = _wilder(plus_dm, period)
    s_mdm = _wilder(minus_dm, period)
    dx = []
    for i in range(len(atr)):
        if atr[i] > 0:
            pdi = 100 * s_pdm[i] / atr[i]
            mdi = 100 * s_mdm[i] / atr[i]
            denom = pdi + mdi
            dx.append(100 * abs(pdi - mdi) / denom if denom > 0 else 0.0)
        else:
            dx.append(0.0)
    if len(dx) < period:
        return None
    val = sum(dx[:period]) / period
    for i in range(period, len(dx)):
        val = (val * (period - 1) + dx[i]) / period
    return round(val, 2)


def adx_actif(symbole, intervalle="1h", limite=100, period=14):
    """ADX actuel d'un actif (fetch OHLCV + calcul)."""
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, intervalle, limite)
        return adx(bougies, period)
    except Exception as e:
        log.warning("adx_actif %s indispo: %s", symbole, e)
        return None


def regimes_actuels(marches=None):'''

if "def adx(bougies" not in src:
    assert R_ANCHOR in src, "regime.py: ancrage fit_multi_tf introuvable"
    src = src.replace(R_ANCHOR, R_INSERT, 1)
    open(RP, "w", encoding="utf-8").write(src)
    print("✅ regime.py: adx() + constantes + adx_actif() ajoutés")
else:
    print("ℹ️ regime.py: adx() déjà présent")

# ============================================================
# 2) PATCH signaux_gagnants.py — gate ADX
# ============================================================
SP = os.path.join(DOSSIER, "signaux_gagnants.py")
src2 = open(SP, encoding="utf-8").read()

S_OLD = '''                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    if _mtf_ok:'''
S_NEW = '''                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    # ADX-GATE: coupe les strategies trend-following si pas de tendance (ADX<25)
                    try:
                        from regime import (STRATEGIES_TREND_FOLLOWING,
                                            SEUIL_ADX_TREND, adx as _calc_adx)
                        if nom in STRATEGIES_TREND_FOLLOWING:
                            _adx_val = _calc_adx(bougies)
                            if _adx_val is not None and _adx_val < SEUIL_ADX_TREND:
                                print(f"[ADX faible {_adx_val:.0f}] ", end="", flush=True)
                                continue
                    except Exception:
                        pass
                    if _mtf_ok:'''
if "ADX-GATE" not in src2:
    assert S_OLD in src2, "signaux_gagnants.py: ancrage sig==ACHAT introuvable"
    src2 = src2.replace(S_OLD, S_NEW, 1)
    open(SP, "w", encoding="utf-8").write(src2)
    print("✅ signaux_gagnants.py: gate ADX installée")
else:
    print("ℹ️ signaux_gagnants.py: gate ADX déjà présente")

# ============================================================
# 3) VÉRIFICATION + TEST ADX réel
# ============================================================
import py_compile
for f in (RP, SP):
    try:
        py_compile.compile(f, doraise=True)
        print(f"✅ compile OK: {os.path.basename(f)}")
    except py_compile.PyCompileError as e:
        print(f"❌ syntaxe {os.path.basename(f)}: {e}")
        sys.exit(1)

sys.path.insert(0, DOSSIER)
import importlib
import regime
importlib.reload(regime)
print("\n=== TEST ADX RÉEL (marchés actuels, 1h) ===")
for sym in ["BTCUSDT", "ETHUSDT", "EURUSD=X", "^GSPC", "GC=F"]:
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(sym, "1h", 100)
        a = regime.adx(bougies)
        cle = list(bougies[0].keys()) if bougies else []
        verdict = "TENDANCE" if (a and a >= 25) else ("QUIET/range" if a else "?")
        print(f"  {sym}: ADX={a} {verdict}  (clés bougie: {cle[:4]})")
    except Exception as e:
        print(f"  {sym}: err {e}")
