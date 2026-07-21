#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategies_evolved.py — Stratégies générées par strategy_evolver.py.
NE PAS ÉDITER MANUELLEMENT — géré par strategy_evolver.py."""

def strat_evolved_00955(i, d):
    # RSI: survente <35 (achat) / surachat >70 (vente)
    rsi = d["rsi"][i]
    if rsi is None:
        return None

    # Donchian breakout: cassure du haut (vente) / cassure du bas (achat)
    donch_haut = d["donchian_haut"][i]
    donch_bas = d["donchian_bas"][i]
    prix = d["clotures"][i]

    if donch_haut is None or donch_bas is None:
        return None

    # ACHAT: RSI survente (<35) + cassure du bas Donchian (prix < donch_bas)
    # -> "sang dans les rues" (Rogers) + confirmation breakout baissier manqué = retournement
    if rsi < 35 and prix < donch_bas:
        return "ACHAT"

    # VENTE: RSI surachat (>70) + cassure du haut Donchian (prix > donch_haut)
    # -> euphorie extrême + breakout haussier = épuisement du momentum
    if rsi > 70 and prix > donch_haut:
        return "VENTE"

    return None

EVOLVED_STRATEGIES = {
    "Evolved 00955": strat_evolved_00955,
}