#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""revert_adx_gate.py
Retire la gate ADX de signaux_gagnants.py (backtest: dégrade le PnL à tous seuils).
Garde adx() dans regime.py (utilitaire utile pour dashboard/reflection).
Crée lecons_apprises.jsonl pour documenter la leçon (évite de re-proposer ADX).
"""
import os, json
from datetime import datetime

DOSSIER = os.getcwd()
SP = os.path.join(DOSSIER, "signaux_gagnants.py")
src = open(SP, encoding="utf-8").read()

# Retire le bloc ADX-GATE (revient à sig == "ACHAT" puis if _mtf_ok)
GATE_BLOC = '''                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    # ADX-GATE: coupe les strategies trend-following si pas de tendance (ADX<25)
                    try:
                        from regime import (STRATEGIES_TREND_FOLLOWING,
                                            SEUIL_ADX_TREND, adx as _calc_adx)
                        if nom in STRATEGIES_TREND_FOLLOWING:
                            _adx_val = _calc_adx(bougies)
                            if _adx_val is not None and _adx_val < SEUIL_ADX_TREND:
                                print(f"[ADX faible {_adx_val:.0f}] ", end="", flush=True)
                                continue
                    except Exception:
                        pass
                    if _mtf_ok:'''
ORIGINAL = '''                sig = signal_strategie(nom, donnees)
                if sig == "ACHAT":
                    if _mtf_ok:'''

if "ADX-GATE" in src:
    assert GATE_BLOC in src, "bloc ADX-GATE introuvable"
    src = src.replace(GATE_BLOC, ORIGINAL, 1)
    open(SP, "w", encoding="utf-8").write(src)
    print("✅ signaux_gagnants.py: gate ADX retirée (retour état original)")
else:
    print("ℹ️ signaux_gagnants.py: gate ADX déjà absente")

import py_compile
py_compile.compile(SP, doraise=True)
print("✅ compile OK signaux_gagnants.py")

# Documente la leçon pour la réflexion future (évite de re-proposer ADX)
LECONS = os.path.join(DOSSIER, "lecons_apprises.jsonl")
entry = {
    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "hypothese": "Filtre ADX<25 pour couper strategies trend-following sans tendance",
    "source": "suggestion IA reflection (principe Soros/expectancy)",
    "test": "backtest 2 ans, 10 actifs x 5 strategies, sweep seuils 10-40",
    "resultat": "DEGRADE le PnL a TOUS les seuils (ADX<25: -2556€, ADX<10: -193€)",
    "raison": "ADX est retardé: confirme la tendance apres le meilleur mouvement. "
              "Couper les entrees a ADX bas supprime les tendances naissantes "
              "(les plus rentables pour SMA/EMA crossover).",
    "decision": "NE PAS re-proposer de gate ADX sur les entrees trend-following.",
    "statut": "REJETEE par backtest",
}
with open(LECONS, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print(f"✅ lecon enregistree dans lecons_apprises.jsonl")
