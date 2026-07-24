#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test intégration: sentiment_gate <-> paper_trading.ouvrir_position."""
import os, sys, types, io, contextlib

# --- mock agent + backtest ---
mock_agent = types.ModuleType("agent")
mock_agent.disponible = lambda m: False
mock_agent.appeler_ia = lambda m, p, t=1: ("", m)
mock_agent.notify_ifft = lambda *a, **k: None
mock_agent.ajouter = lambda *a, **k: None
sys.modules["agent"] = mock_agent
mock_bt = types.ModuleType("backtest")
mock_bt.charger_backtests = lambda: {}
sys.modules["backtest"] = mock_bt

sys.path.insert(0, "/tmp/agent-ia-inspect")
import paper_trading as pt

# --- fake sentiment_gate module (contrôlable) ---
fake_sg = types.ModuleType("sentiment_gate")
_CALLS = {"n": 0}
_RET = [True, "ok"]
def gate_achat(symbole):
    _CALLS["n"] += 1
    if _RET[0] == "RAISE":
        raise RuntimeError("boom test")
    return _RET[0], _RET[1]
fake_sg.gate_achat = gate_achat
sys.modules["sentiment_gate"] = fake_sg

os.environ["PROTECTION_CAPITAL"] = "0"  # isole le gate (skip circuit breaker)
os.environ["ANTI_CORR"] = "0"
os.environ["ANTI_GAP_WEEKEND"] = "0"
PF = {"positions": [], "capital": 1000.0, "solde": 1000.0, "historique": []}
SIG = {"symbole": "BTCUSDT", "nom": "Bitcoin", "marche": "crypto",
       "prix_entree": 60000.0, "source": "binance", "strategie": "technique"}

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

def run():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            ret = pt.ouvrir_position(PF, SIG, 60000.0)
        except Exception as e:
            ret = f"ERR:{e}"
    return ret, buf.getvalue()

print("=" * 60)
print("INTÉGRATION: ouvrir_position x sentiment_gate")

print("\nTEST 1: SENTIMENT_GATE=1 + block → return False + log")
os.environ["SENTIMENT_GATE"] = "1"
_RET[0] = False; _RET[1] = "Extreme Greed (F&G=88)"; _CALLS["n"] = 0
ret, out = run()
check("gate appelé", _CALLS["n"] == 1, f"calls={_CALLS['n']}")
check("retourne False", ret is False, str(ret))
check("log SENTIMENT GATE bloquée", "SENTIMENT GATE" in out and "bloquée" in out, out[-120:])

print("\nTEST 2: SENTIMENT_GATE=0 (defaut) → gate NON appelé (comportement original)")
os.environ["SENTIMENT_GATE"] = "0"
_RET[0] = "RAISE"; _RET[1] = "x"; _CALLS["n"] = 0  # si appelé -> raise (prouve fail)
ret, out = run()
check("gate skip (0 appel)", _CALLS["n"] == 0, f"calls={_CALLS['n']}")
check("pas de log SENTIMENT GATE", "SENTIMENT GATE" not in out, out[-100:])

print("\nTEST 3: SENTIMENT_GATE=1 + gate raise → fail-open (pas de crash, log erreur)")
os.environ["SENTIMENT_GATE"] = "1"
_RET[0] = "RAISE"; _CALLS["n"] = 0
ret, out = run()
check("gate appelé", _CALLS["n"] == 1, f"calls={_CALLS['n']}")
check("log erreur fail-open", "SENTIMENT GATE erreur" in out, out[-120:])
check("pas d exception non catchée", not str(ret).startswith("ERR:"), str(ret))

print("\nTEST 4: SENTIMENT_GATE=1 sur actif NON-crypto → gate NON appelé (F&G=crypto)")
os.environ["SENTIMENT_GATE"] = "1"
_RET[0] = "RAISE"; _CALLS["n"] = 0
sig2 = dict(SIG); sig2["marche"] = "actions"; sig2["symbole"] = "AAPL"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try: pt.ouvrir_position(PF, sig2, 190.0)
    except Exception: pass
check("gate skip hors crypto", _CALLS["n"] == 0, f"calls={_CALLS['n']}")

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
