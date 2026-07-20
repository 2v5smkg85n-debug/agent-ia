#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_strat_params.py — Rend strat_rsi_reversion paramétrable via strat_params.json.
Ajoute un helper cache + modifie la fonction pour lire le seuil depuis le fichier.
auto_sweep.py mettra a jour strat_params.json pour auto-optimiser le seuil RSI."""
import os, re

f = "backtest_moteur.py"
src = open(f, encoding="utf-8").read()

# 1. Helper cache (a inserer avant strat_rsi_reversion)
helper = '''# --- Auto-tunable params (auto_sweep.py met a jour strat_params.json) ---
import json as _sp_json, os as _sp_os, time as _sp_time
_SP_CACHE = {"vals": None, "mtime": 0.0}
def _strat_params():
    """Lit strat_params.json avec cache (recharge si mtime change). Fallback safe."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strat_params.json")
        mt = os.path.getmtime(p)
        if _SP_CACHE["vals"] is None or mt != _SP_CACHE["mtime"]:
            _SP_CACHE["vals"] = _sp_json.load(open(p, encoding="utf-8"))
            _SP_CACHE["mtime"] = mt
    except Exception:
        _SP_CACHE["vals"] = {}
    v = _SP_CACHE["vals"] or {}
    return v.get("rsi_achat", 35), v.get("rsi_vente", 70)

'''

# 2. Nouvelle fonction strat_rsi_reversion
new_func = '''def strat_rsi_reversion(i, d):
    """Achat quand RSI < seuil (survente); vente quand RSI > seuil_haut.
    Seuil auto-ajuste par auto_sweep.py via strat_params.json."""
    r = d["rsi"][i]
    if r is None:
        return None
    achat, vente = _strat_params()
    if r < achat:
        return "ACHAT"
    if r > vente:
        return "VENTE"
    return None
'''

# Remplace l'ancienne fonction (regex: def ... return None final de la fonction)
pat = re.compile(r'def strat_rsi_reversion\(i, d\):.*?\n    return None\n', re.DOTALL)
if not pat.search(src):
    print("ERREUR: strat_rsi_reversion introuvable")
    raise SystemExit(1)

# Evite double-patch
if "_strat_params()" in src:
    print("deja patche (_strat_params present) - rien a faire")
    raise SystemExit(0)

src = pat.sub(new_func, src)
# Insere le helper avant la fonction
src = src.replace("def strat_rsi_reversion(i, d):",
                  helper + "def strat_rsi_reversion(i, d):", 1)

open(f, "w", encoding="utf-8").write(src)
print("OK backtest_moteur.py: strat_rsi_reversion lit maintenant strat_params.json")
print("  seuils externalises -> auto_sweep peut les optimiser sans toucher au code")
