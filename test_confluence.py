#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_confluence.py - valide le filtre de confluence HTF."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import filtre_confluence_htf as fc
importlib.reload(fc)

def _sig(sym="BTCUSDT", marche="crypto", action="ACHAT", interv="1h", strat="Bollinger Breakout"):
    return {"symbole": sym, "nom": sym, "marche": marche, "action": action,
            "strategie": strat, "backtest_stats": {"intervalle": interv}}

# ---- Partie A: logique de la porte (mock _trend_htf) ----
def run_gate(sig, trend):
    fc._trend_htf = lambda s, m, t: trend
    return fc._entree_bloquee_confluence(sig)

ok = True
_REAL_TREND = fc._trend_htf  # sauvegarde avant monkeypatch de la partie A
blk, _ = run_gate(_sig(action="ACHAT"), "basse")
print(f"A1 ACHAT + HTF basse -> bloque={blk}"); assert blk
blk, _ = run_gate(_sig(action="ACHAT"), "haute")
print(f"A2 ACHAT + HTF haute -> bloque={blk}"); assert not blk
blk, _ = run_gate(_sig(action="ACHAT"), "neutre")
print(f"A3 ACHAT + HTF neutre -> bloque={blk}"); assert not blk
blk, _ = run_gate(_sig(action="ACHAT"), None)
print(f"A4 ACHAT + HTF None (API fail) -> bloque={blk} (fail-open)"); assert not blk
blk, _ = run_gate(_sig(action="VENTE"), "haute")
print(f"A5 VENTE + HTF haute -> bloque={blk}"); assert blk
blk, _ = run_gate(_sig(action="VENTE"), "basse")
print(f"A6 VENTE + HTF basse -> bloque={blk}"); assert not blk
blk, raison = run_gate(_sig(action="ACHAT"), "basse")
print(f"A7 raison contient 'contre-tendance': {'contre-tendance' in raison}"); assert "contre-tendance" in raison

# ---- Partie B: vraie detection de tendance (mock historique_ohlcv) ----
fc._trend_htf = _REAL_TREND  # restaure la vraie fonction (clobber par partie A)
def _mock_ohlcv(rising=True, n=120):
    base = 100.0
    bougies = []
    for i in range(n):
        c = base + i if rising else base - i
        bougies.append({"cloture": c})
    return bougies

import indicateurs
indicateurs.historique_ohlcv = lambda sym, interv, lim: _mock_ohlcv(rising=True, n=lim)
t = fc._trend_htf("BTCUSDT", "crypto", "1h")
print(f"B1 crypto 1h prix montant -> trend={t} (attendu haute)"); assert t == "haute"

indicateurs.historique_ohlcv = lambda sym, interv, lim: _mock_ohlcv(rising=False, n=lim)
t = fc._trend_htf("BTCUSDT", "crypto", "1h")
print(f"B2 crypto 1h prix baissant -> trend={t} (attendu basse)"); assert t == "basse"

indicateurs.historique_ohlcv = lambda sym, interv, lim: _mock_ohlcv(rising=True, n=10)  # trop peu
t = fc._trend_htf("BTCUSDT", "crypto", "1h")
print(f"B3 trop peu de bougies -> trend={t} (attendu None fail-open)"); assert t is None

indicateurs.historique_ohlcv = lambda sym, interv, lim: []  # API vide
t = fc._trend_htf("BTCUSDT", "crypto", "1h")
print(f"B4 API vide -> trend={t} (attendu None fail-open)"); assert t is None

# base 1d crypto -> pas de HTF superieure -> neutre (autorise)
indicateurs.historique_ohlcv = lambda sym, interv, lim: _mock_ohlcv(rising=True, n=lim)
t = fc._trend_htf("BTCUSDT", "crypto", "1d")
print(f"B5 crypto 1d (pas de HTF) -> trend={t} (attendu neutre)"); assert t == "neutre"

# mapping: crypto 1h -> HTF 4h, non-crypto 1h -> HTF 1d (pas de 4h sur Yahoo)
calls = []
def spy(sym, interv, lim):
    calls.append(interv); return _mock_ohlcv(rising=True, n=lim)
indicateurs.historique_ohlcv = spy
fc._trend_htf("BTCUSDT", "crypto", "1h")
fc._trend_htf("EURUSD=X", "forex", "1h")
print(f"B6 mapping: crypto 1h->HTF={calls[0]} (attendu 4h), forex 1h->HTF={calls[1]} (attendu 1d)")
assert calls[0] == "4h" and calls[1] == "1d"

print("\n=== TESTS CONFLUENCE HTF PASSES (13 checks) ===")
