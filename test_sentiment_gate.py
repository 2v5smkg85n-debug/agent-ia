#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sentiment_gate.py — Tests du gate d'entrée sentiment."""
import os, sys, json, types, tempfile

sys.path.insert(0, "/tmp/agent-ia-inspect")
import sentiment_gate as sg

# --- mock sentiment_marche.fetch_fear_greed ---
mock_sm = types.ModuleType("sentiment_marche")
_FNG = [None]
def _fetch(limit=30): return [{"value": str(_FNG[0])}] if _FNG[0] is not None else []
mock_sm.fetch_fear_greed = _fetch
sys.modules["sentiment_marche"] = mock_sm

# reset cache mémoire + cache web fichier temp
def reset(fng=None, web=None):
    _FNG[0] = fng
    sg._FNG_CACHE["v"] = None
    sg._FNG_CACHE["t"] = 0.0
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    if web is not None:
        json.dump(web, f)
    else:
        f.write("{}")
    f.close()
    sg.CACHE_WEB = f.name

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

print("=" * 60)
print("SENTIMENT GATE — Feature 2")

print("\nTEST 1: Extreme Greed (F&G=85) → BLOCK (euphorie sommet)")
reset(fng=85, web={"BTCUSDT": {"biais": 0.2, "confiance": 0.5}})
a, r = sg.gate_achat("BTCUSDT")
check("bloqué", not a, r)
check("raison mentionne Greed", "Greed" in r, r)

print("\nTEST 2: F&G neutre + web baissier fort → BLOCK (actu défavorable)")
reset(fng=50, web={"BTCUSDT": {"biais": -0.7, "confiance": 0.8}})
a, r = sg.gate_achat("BTCUSDT")
check("bloqué", not a, r)
check("raison mentionne baissier", "baissier" in r, r)

print("\nTEST 3: web baissier MAIS confiance faible → ALLOW")
reset(fng=50, web={"BTCUSDT": {"biais": -0.6, "confiance": 0.4}})
a, r = sg.gate_achat("BTCUSDT")
check("autorisé", a, r)

print("\nTEST 4: F&G bas (Fear=20) + web haussier → ALLOW (zone achat)")
reset(fng=20, web={"BTCUSDT": {"biais": 0.5, "confiance": 0.9}})
a, r = sg.gate_achat("BTCUSDT")
check("autorisé en Fear", a, r)

print("\nTEST 5: F&G=70 (Greed, pas extreme) + web neutre → ALLOW")
reset(fng=70, web={"BTCUSDT": {"biais": 0.0, "confiance": 0.0}})
a, r = sg.gate_achat("BTCUSDT")
check("autorisé (Greed<80)", a, r)

print("\nTEST 6: F&G indispo (None) → ALLOW (fail-open)")
reset(fng=None, web={"BTCUSDT": {"biais": 0.0, "confiance": 0.0}})
a, r = sg.gate_achat("BTCUSDT")
check("autorisé même si F&G indispo", a, r)

print("\nTEST 7: cache web absent → ALLOW (fail-open, pas de crash)")
reset(fng=50, web=None)  # {} écrit
a, r = sg.gate_achat("BTCUSDT")
check("autorisé, pas de crash", a, r)

print("\nTEST 8: euphorie + web baissier → BLOCK (règle F&G prioritaire)")
reset(fng=90, web={"BTCUSDT": {"biais": -0.8, "confiance": 0.9}})
a, r = sg.gate_achat("BTCUSDT")
check("bloqué", not a, r)
check("raison = Greed (prioritaire)", "Greed" in r, r)

print("\nTEST 9: symbole absent du cache web → ALLOW (pas d'info, fail-open)")
reset(fng=50, web={"ETHUSDT": {"biais": -0.9, "confiance": 0.9}})
a, r = sg.gate_achat("BTCUSDT")  # BTCUSDT pas dans le cache
check("autorisé (pas d'info sur cet actif)", a, r)

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
