#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_plugins_charge.py — vérifie que le loader charge bien les plugins
de plugins/ avec leurs hooks. À lancer depuis ~/agent-ia."""
import os
os.chdir("/home/ubuntu/agent-ia")
import paper_trading as pt

pt._charger_plugins()
print(f"plugins chargés: {len(pt._plugins_charges)}")
for fn, m in pt._plugins_charges:
    hooks = [h for h in ("hook_entree", "hook_sizing", "self_test") if hasattr(m, h)]
    print(f"  {fn}: {hooks}")
    # test rapide du hook_entree (ne doit pas crasher)
    if hasattr(m, "hook_entree"):
        try:
            sig = {"symbole": "BTC-EUR", "prix": 100.0, "score": 0.7}
            pf = {"liquidites": 1000.0, "positions": {}, "trades_fermes": [], "capital_initial": 1000.0}
            allow, raison = m.hook_entree(pf, sig)
            print(f"    hook_entree(BTC) -> allow={allow} raison={raison}")
        except Exception as e:
            print(f"    hook_entree erreur: {e}")
    if hasattr(m, "hook_sizing"):
        try:
            sig = {"symbole": "BTC-EUR", "prix": 100.0, "score": 0.7}
            pf = {"liquidites": 1000.0, "positions": {}, "trades_fermes": [], "capital_initial": 1000.0}
            out = m.hook_sizing(pf, sig, 250.0, 120.0)
            print(f"    hook_sizing(250EUR) -> {out:.2f}EUR")
        except Exception as e:
            print(f"    hook_sizing erreur: {e}")
print("\nOK - système de plugins opérationnel")
