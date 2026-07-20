#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose_aave.py — Pourquoi AAVE (RSI 27, zone d'achat) ne declenche pas d'ACHAT?
Decortique: biais bougie, signal RSI, regime_fit, score classement, gate."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

from indicateurs import historique_ohlcv
from signaux_gagnants import signal_strategie, calculer_donnees, strategies_gagnantes_par_actif, generer_signaux_gagnants
from regime import regime_actif, fit_multi_tf
from bougies_patterns import analyser_patterns, biais_bougies

for sym in ["AAVEUSDT", "BTCUSDT", "LDOUSDT"]:
    print(f"\n{'='*60}")
    print(f"DIAGNOSTIC {sym}")
    print(f"{'='*60}")
    bougies = historique_ohlcv(sym, "1h", 100)
    if not bougies:
        print("  pas de donnees")
        continue
    closes = [b["cloture"] for b in bougies]

    # RSI
    gains, losses = [], []
    for j in range(1, min(15, len(closes))):
        d = closes[j] - closes[j-1]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains)/14 if gains else 0
    al = sum(losses)/14 if losses else 0
    rsi = 100 if al == 0 else (100 - 100/(1 + ag/al))
    print(f"  RSI(14) = {rsi:.1f}  (zone achat mean-reversion: 20-30)")

    # Biais bougies (le gate dip-buying)
    try:
        biais = biais_bougies(bougies[-5:])
        patterns = analyser_patterns(bougies[-5:])
        print(f"  biais bougies = {biais:.2f}  (gate bloque si > 0 = haussier)")
        print(f"  patterns: {patterns.get('patterns', [])}")
    except Exception as e:
        print(f"  biais KO: {e}")

    # Regime + fit
    try:
        r = regime_actif(sym)
        reg = r.get("REGIME", "?") if isinstance(r, dict) else "?"
        print(f"  regime = {reg}")
    except Exception as e:
        print(f"  regime KO: {e}")
    try:
        fit = fit_multi_tf("RSI Mean Reversion", closes)
        print(f"  fit RSI = {fit}")
    except Exception as e:
        print(f"  fit KO: {e}")

    # Signal RSI direct
    try:
        donnees = calculer_donnees(closes)
        sig = signal_strategie("RSI Mean Reversion", donnees)
        print(f"  signal RSI Mean Reversion = {sig}")
    except Exception as e:
        print(f"  signal RSI KO: {e}")

    # Strategie gagnante presente?
    try:
        strats = strategies_gagnantes_par_actif()
        s_gagn = strats.get(sym) or strats.get(sym.replace("USDT",""), {})
        if isinstance(s_gagn, dict):
            s_list = s_gagn.get("1h", []) or s_gagn.get("4h", [])
        else:
            s_list = s_gagn or []
        noms = [s.get("strategie") for s in s_list]
        print(f"  strategies GAGNANTE pour {sym}: {noms}")
        if "RSI Mean Reversion" not in noms:
            print(f"  --> RSI Mean Reversion PAS gagnante pour {sym} -> pas de signal possible!")
    except Exception as e:
        print(f"  strats KO: {e}")

    # Signal global (generer_signaux_gagnants)
    try:
        prix = {sym: closes[-1]}
        marches = {sym: {"nom": sym, "marche": "crypto", "source": "binance"}}
        sigs = generer_signaux_gagnants(prix, marches)
        s = sigs.get(sym, {})
        print(f"  signal final generer_signaux_gagnants = {s}")
    except Exception as e:
        print(f"  signal global KO: {e}")

print(f"\n{'='*60}")
print("Si RSI est en zone achat mais signal=NEUTRE, causes possibles:")
print("1. Strategie RSI pas GAGNANTE pour cet actif (pas dans le pool)")
print("2. Dip-buying gate bloque (biais bougie > 0)")
print("3. regime_fit trop faible (strategie non adaptee au regime)")
print("4. Score classement insuffisant")
print(f"{'='*60}")
