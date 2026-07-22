#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_signaux_indicateurs.py — Fix CRITIQUE: calculer_donnees (dict d live)
ne construisait que 8 indicateurs. Manquait: donchian_haut/bas, stoch_k/d, ema12/26.
=> Evolved 00955 (et strat Donchian/Stochastic/EMA) crashaient en live (KeyError)
   et ne declenchaient JAMAIS de signal. Ce patch ajoute les 6 indicateurs manquants
   + try/except defensif dans signal_strategie."""
import sys

f = "signaux_gagnants.py"
src = open(f, encoding="utf-8").read()

# 1. ETEND L'IMPORT pour inclure les 3 nouveaux indicateurs
OLD_IMPORT = """from backtest_moteur import (
    STRATEGIES, sma_series, rsi_series, bollinger_series, _macd_full,
    strat_sma_crossover, strat_rsi_reversion, strat_bollinger_breakout,
    strat_macd_momentum, simuler
)"""
NEW_IMPORT = """from backtest_moteur import (
    STRATEGIES, sma_series, rsi_series, bollinger_series, _macd_full,
    strat_sma_crossover, strat_rsi_reversion, strat_bollinger_breakout,
    strat_macd_momentum, simuler,
    donchian_series, stochastic_series, ema_simple_series
)"""

# 2. ETEND calculer_donnees pour construire TOUS les indicateurs
OLD_CALC = '''def calculer_donnees(clotures):
    """Pre-calcule tous les indicateurs sur une serie de clotures."""
    bb_haut, bb_bas = bollinger_series(clotures, 20, 2)
    macd_line, macd_signal = _macd_full(clotures)
    return {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": bb_haut,
        "bb_bas": bb_bas,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
    }'''
NEW_CALC = '''def calculer_donnees(clotures):
    """Pre-calcule TOUS les indicateurs sur une serie de clotures.
    Doit matcher le dict d du backtest (sinon KeyError live sur strat evolved/Phase7)."""
    bb_haut, bb_bas = bollinger_series(clotures, 20, 2)
    macd_line, macd_signal = _macd_full(clotures)
    donch_haut, donch_bas = donchian_series(clotures, 20)
    stoch_k, stoch_d = stochastic_series(clotures, 14, 3)
    return {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": bb_haut,
        "bb_bas": bb_bas,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "donchian_haut": donch_haut,
        "donchian_bas": donch_bas,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "ema12": ema_simple_series(clotures, 12),
        "ema26": ema_simple_series(clotures, 26),
    }'''

# 3. TRY/EXCEPT DEFENSIF dans signal_strategie (une strat qui crash ne casse pas la boucle)
OLD_SIG = '''    i = len(donnees["clotures"]) - 1
    return fonc(i, donnees)'''
NEW_SIG = '''    i = len(donnees["clotures"]) - 1
    try:
        return fonc(i, donnees)
    except Exception as e:
        # une strategie qui crash (ex: indicateur absent) ne doit pas casser
        # la generation de signaux -> on log et on ignore cette strat
        try:
            print(f"    [signal_strategie] {nom_strat} crash: {e}", flush=True)
        except Exception:
            pass
        return None'''

changed = False
if "donchian_series, stochastic_series, ema_simple_series" in src:
    print("import deja patche - skip 1")
elif OLD_IMPORT in src:
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print("OK import etendu (3 nouveaux indicateurs)")
    changed = True
else:
    print("ERREUR: ancre import introuvable"); sys.exit(1)

if "donchian_haut" in src and "stoch_k" in src and "calculer_donnees" in src and '"ema12"' in src:
    print("calculer_donnees deja patche - skip 2")
elif OLD_CALC in src:
    src = src.replace(OLD_CALC, NEW_CALC, 1)
    print("OK calculer_donnees etendu (6 indicateurs ajoutes)")
    changed = True
else:
    print("ERREUR: ancre calculer_donnees introuvable"); sys.exit(1)

if "return fonc(i, donnees)" not in src and "signal_strategie] {nom_strat} crash" in src:
    print("signal_strategie deja patche - skip 3")
elif OLD_SIG in src:
    src = src.replace(OLD_SIG, NEW_SIG, 1)
    print("OK signal_strategie try/except defensif ajoute")
    changed = True
else:
    print("ATTENTION: ancre signal_strategie introuvable (deja patche?)")

if changed:
    open(f, "w", encoding="utf-8").write(src)
    print("\nPATCH APPLIQUE")
