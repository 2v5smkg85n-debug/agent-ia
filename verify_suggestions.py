#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_suggestions.py — Backteste les suggestions de la reflection du matin.

1. Bollinger Breakout: merite-t-il d'etre desactive? (backtest vs live 2 trades)
2. EXTEND_TP 4.5%: aide ou nuit? (re-test vs 4.0, le sweep avait montre plateau a 4)
"""
import os, sys, logging
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

import backtest_trailing as bt
from indicateurs import historique_ohlcv
from auto_pruning import stats_strategies, _cle
logging.basicConfig(level=logging.WARNING)

strats = bt._load_strategies()
TP = getattr(bt, "TP", 2.0); SL = getattr(bt, "SL", 2.5)
DEBUT = getattr(bt, "DEBUT", 60); MAX_BARS = getattr(bt, "MAX_BARS", 48)

print("=" * 74)
print("VERIFICATION DES SUGGESTIONS DE LA REFLECTION")
print("=" * 74)

# 1) Bollinger Breakout: backtest vs live
print("\n--- 1. BOLLINGER BREAKOUT: desactiver? ---")
print(f"  {'Actif':<10}{'Backtest%':>11}{'LiveN':>7}{'Win%':>7}{'LivePnL':>9}")
bt_total = 0; live_n = 0; live_pnl = 0; live_wins = 0
for actif, sl in strats.items():
    for s in sl:
        if s.get("strategie") == "Bollinger Breakout":
            bt_ret = s.get("retour_pct", 0)
            bt_total += bt_ret
            try:
                st = stats_strategies().get(_cle("Bollinger Breakout", actif), {})
            except Exception:
                st = {}
            n = st.get("n", 0); w = st.get("wins", 0); p = st.get("pnl_total", 0)
            live_n += n; live_pnl += p; live_wins += w
            wr = 100*w/n if n else 0
            print(f"  {actif:<10}{bt_ret:>11.2f}{n:>7}{wr:>6.0f}%{p:>9.2f}")
print(f"\n  TOTAL backtest Bollinger: {bt_total:.2f}%")
print(f"  TOTAL live: {live_n} trades, {live_wins} wins, PnL {live_pnl:.2f}€")
if bt_total > 0 and live_n < 5:
    print("  VERDICT: backtest POSITIF mais live sur <5 trades = BRUIT.")
    print("           NE PAS desactiver (premature). L'auto-pruning le fera si confirme.")
elif live_pnl < 0 and live_n >= 5:
    print("  VERDICT: live negatif confirme sur 5+ trades -> desactivation justifiee.")
else:
    print("  VERDICT: donnees insuffisantes -> garder.")

# 2) EXTEND_TP 4.0 vs 4.5 vs 5.0
print("\n--- 2. EXTEND_TP: 4.0 vs 4.5 vs 5.0 (re-test plateau) ---")
CRYPTOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def simule_extends(tp_fixe_pct, tp_ext_pct, seuil=0.5):
    """Simule: TP fixe normal, TP monte a tp_ext_pct si profit >= seuil."""
    from signaux_gagnants import signal_strategie, calculer_donnees
    from regime import fit_multi_tf
    total = 0; n = 0; wins = 0
    for actif in CRYPTOS:
        if actif not in strats:
            continue
        bougies = historique_ohlcv(actif, "1h", 500)
        if not bougies or len(bougies) < DEBUT + 10:
            continue
        closes = [b["cloture"] for b in bougies]
        ouvert = None
        for i in range(DEBUT, len(closes)):
            px = closes[i]
            if ouvert:
                var = (px - ouvert["px"]) / ouvert["px"] * 100
                age = i - ouvert["bar"]
                tp_cible = tp_ext_pct if var >= seuil else tp_fixe_pct
                if var >= tp_cible or var <= -SL or (age >= MAX_BARS and var > 0):
                    total += var; n += 1
                    if var > 0: wins += 1
                    ouvert = None
            if ouvert:
                continue
            donnees = calculer_donnees(closes[:i+1])
            achats = []
            for s in strats[actif]:
                nom = s["strategie"]
                try:
                    if signal_strategie(nom, donnees) == "ACHAT":
                        achats.append(nom)
                except Exception:
                    pass
            if not achats:
                continue
            ouvert = {"bar": i, "px": px}
    return total, n, wins

for tp_ext in [4.0, 4.5, 5.0]:
    t, n, w = simule_extends(TP, tp_ext)
    wr = 100*w/n if n else 0
    print(f"  tp_ext={tp_ext}%: PnL {t:.2f}% | {n} trades | win {wr:.0f}%")
print("\n  VERDICT: si PnL baisse de 4.0 -> 4.5 -> 5.0, c'est un plateau/declin.")
print("           La suggestion 'monter a 4.5%' est probablement REJETEE (deja plateau a 4).")
print("=" * 74)
