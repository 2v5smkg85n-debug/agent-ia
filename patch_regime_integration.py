#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch idempotent: integre la detection de regime dans signaux_gagnants.py.
Pondere le retour backtest par le fit strategie->regime de marche."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "signaux_gagnants.py")
MARKER = "REGIME-FIT-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch regime deja installe. Rien a faire.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.regime")
print("[i] Backup: signaux_gagnants.py.bak.regime")

# 1. init meilleur_score a cote de meilleur_retour
code = code.replace(
    "        meilleur_retour = -999\n",
    "        meilleur_retour = -999\n        meilleur_score = -999  # " + MARKER + "\n",
    1)

# 2. remplacer le bloc selection par version ponderee par regime
ANCRE = (
    "            donnees = calculer_donnees(clotures)\n\n"
    "            for strat in strats:\n"
    "                nom = strat.get(\"strategie\")\n"
    "                sig = signal_strategie(nom, donnees)\n"
    "                if sig == \"ACHAT\":\n"
    "                    if strat.get(\"retour_pct\", 0) > meilleur_retour:\n"
    "                        meilleur_retour = strat.get(\"retour_pct\", 0)\n"
    "                        meilleur_signal = sig\n"
    "                        meilleure_strat = {**strat, \"intervalle_live\": interv_live}\n"
)
NOUV = (
    "            donnees = calculer_donnees(clotures)\n"
    "            # " + MARKER + " : regime de marche pour ponderer la selection\n"
    "            try:\n"
    "                from regime import regime_depuis_clotures, strategie_regime_fit\n"
    "                _reg = regime_depuis_clotures(clotures)\n"
    "            except Exception:\n"
    "                _reg = {\"regime\": \"INCONNU\"}\n"
    "\n"
    "            for strat in strats:\n"
    "                nom = strat.get(\"strategie\")\n"
    "                sig = signal_strategie(nom, donnees)\n"
    "                if sig == \"ACHAT\":\n"
    "                    _fit = strategie_regime_fit(nom, _reg.get(\"regime\"))\n"
    "                    _score = strat.get(\"retour_pct\", 0) * _fit\n"
    "                    if _score > meilleur_score:\n"
    "                        meilleur_score = _score\n"
    "                        meilleur_retour = strat.get(\"retour_pct\", 0)\n"
    "                        meilleur_signal = sig\n"
    "                        meilleure_strat = {**strat, \"intervalle_live\": interv_live,\n"
    "                                           \"regime\": _reg.get(\"regime\"),\n"
    "                                           \"regime_fit\": round(_fit, 3)}\n"
)

if ANCRE not in code:
    print("[ECHEC] Ancrage selection introuvable. Verifier signaux_gagnants.py")
    raise SystemExit(1)
code = code.replace(ANCRE, NOUV, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Patch regime installe dans signaux_gagnants.py")
print("     La selection de strategies est desormais ponderee par le fit regime.")
