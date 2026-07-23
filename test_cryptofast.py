#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_cryptofast.py — valide le check crypto SL mi-boucle.

Cas 1: position BTCUSDT en perte > SL (-3%) + prix_binance mocké -> fermée STOP
Cas 2: position forex EURUSD en perte -> NON touchée (pas fetchée, pas crypto)
"""
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib
import paper_trading
importlib.reload(paper_trading)

# état capturé
_saved = {}

def _pos(sym, nom, marche, entry, qty, peak=None):
    peak = peak if peak is not None else entry
    return {
        "symbole": sym, "nom": nom, "marche": marche, "strategie": "TestStrat",
        "prix_entree": entry, "prix_peak": peak, "quantite": qty,
        "montant_eur": entry * qty, "frais_entree": entry * qty * 0.001,
        "frais_total": entry * qty * 0.002,
        "date_ouverture": (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M"),
    }

def _pf(positions):
    return {"capital_initial": 1000.0, "liquidites": 500.0,
            "positions": positions, "historique": [],
            "total_frais": 0.0, "dernier_tick": ""}

# mocks
paper_trading.charger_portefeuille = lambda: _cur_pf
def _sauver(pf): _saved["pf"] = pf
paper_trading.sauver_portefeuille = _sauver
def _prix_binance(sym):
    # BTC en forte perte (-3%), autres -> pas mocké (None)
    return 97.0 if sym == "BTCUSDT" else None
paper_trading.prix_binance = _prix_binance
paper_trading.notify_ifft = lambda *a, **k: None  # mock: pas de notif reseau

# --- Cas 1: BTC en perte > SL -> fermé ---
_cur_pf = _pf([_pos("BTCUSDT", "Bitcoin", "crypto", 100.0, 1.0)])
paper_trading._check_crypto_sl_rapide()
pf_after = _saved.get("pf", _cur_pf)
nb_ouverts = len([p for p in pf_after["positions"] if p["symbole"] == "BTCUSDT"])
nb_fermes = len([h for h in pf_after.get("historique", []) if h.get("symbole") == "BTCUSDT"])
raison = ""
for h in pf_after.get("historique", []):
    if h.get("symbole") == "BTCUSDT":
        raison = h.get("raison", "")
print(f"Cas1 (BTC -3%): ouverts={nb_ouverts} fermés={nb_fermes} raison='{raison}'")
assert nb_fermes == 1 and "STOP" in raison, "ECHEC Cas1: BTC aurait dû être fermé par STOP"
print("  OK BTC fermé par SL mi-boucle")

# --- Cas 2: forex EURUSD en perte -> NON touché ---
_cur_pf = _pf([_pos("EURUSD", "EUR/USD", "forex", 1.10, 100.0)])
_saved.clear()
paper_trading._check_crypto_sl_rapide()
pf_after = _saved.get("pf", _cur_pf)
nb_eur_ouverts = len([p for p in pf_after["positions"] if p["symbole"] == "EURUSD"])
print(f"Cas2 (EURUSD forex -3%): encore ouverts={nb_eur_ouverts}")
assert nb_eur_ouverts == 1, "ECHEC Cas2: EURUSD ne devrait pas être touché (non-crypto)"
print("  OK EURUSD non touché (pas fetché)")

print("\n=== TESTS CRYPTO-FAST PASSÉS ===")
