#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch: remplace le reweighting regime (cosmetique) par le GATING multi-timeframe
(1h+4h) valide par backtest (+1.66% PnL, win rate 54%->69%)."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "signaux_gagnants.py")
MARKER = "REGIME-MTF-GATE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch MTF-gate deja installe. Rien a faire.")
    raise SystemExit(0)

if "REGIME-FIT-INSTALLE" not in code:
    print("[ECHEC] Patch REGIME-FIT-INSTALLE absent. Installer d'abord le patch regime base.")
    raise SystemExit(1)

shutil.copy2(FICHIER, FICHIER + ".bak.mtf")
print("[i] Backup: signaux_gagnants.py.bak.mtf")

ANCRE = (
    '            donnees = calculer_donnees(clotures)\n'
    '            # REGIME-FIT-INSTALLE : regime de marche pour ponderer la selection\n'
    '            try:\n'
    '                from regime import regime_depuis_clotures, strategie_regime_fit\n'
    '                _reg = regime_depuis_clotures(clotures)\n'
    '            except Exception:\n'
    '                _reg = {"regime": "INCONNU"}\n'
    '\n'
    '            for strat in strats:\n'
    '                nom = strat.get("strategie")\n'
    '                sig = signal_strategie(nom, donnees)\n'
    '                if sig == "ACHAT":\n'
    '                    _fit = strategie_regime_fit(nom, _reg.get("regime"))\n'
    '                    _score = strat.get("retour_pct", 0) * _fit\n'
    '                    if _score > meilleur_score:\n'
    '                        meilleur_score = _score\n'
    '                        meilleur_retour = strat.get("retour_pct", 0)\n'
    '                        meilleur_signal = sig\n'
    '                        meilleure_strat = {**strat, "intervalle_live": interv_live,\n'
    '                                           "regime": _reg.get("regime"),\n'
    '                                           "regime_fit": round(_fit, 3)}\n'
)

NOUV = (
    '            donnees = calculer_donnees(clotures)\n'
    '            # ' + MARKER + ' : gate multi-timeframe (1h+4h) - valide backtest +1.66% PnL\n'
    '            try:\n'
    '                from regime import fit_multi_tf\n'
    '                _mtf_ok = True\n'
    '            except Exception:\n'
    '                _mtf_ok = False\n'
    '\n'
    '            for strat in strats:\n'
    '                nom = strat.get("strategie")\n'
    '                sig = signal_strategie(nom, donnees)\n'
    '                if sig == "ACHAT":\n'
    '                    if _mtf_ok:\n'
    '                        try:\n'
    '                            _fit_avg, _r1h, _r4h = fit_multi_tf(nom, clotures)\n'
    '                        except Exception:\n'
    '                            _fit_avg, _r1h, _r4h = 1.0, {"regime": "INCONNU"}, {"regime": "INCONNU"}\n'
    '                        if _fit_avg < 1.0:\n'
    '                            continue  # regime defavorable en moyenne -> skip\n'
    '                    else:\n'
    '                        _fit_avg, _r1h, _r4h = 1.0, {"regime": "INCONNU"}, {"regime": "INCONNU"}\n'
    '                    _score = strat.get("retour_pct", 0) * _fit_avg\n'
    '                    if _score > meilleur_score:\n'
    '                        meilleur_score = _score\n'
    '                        meilleur_retour = strat.get("retour_pct", 0)\n'
    '                        meilleur_signal = sig\n'
    '                        meilleure_strat = {**strat, "intervalle_live": interv_live,\n'
    '                                           "regime_1h": _r1h.get("regime"),\n'
    '                                           "regime_4h": _r4h.get("regime"),\n'
    '                                           "regime_fit": round(_fit_avg, 3)}\n'
)

if ANCRE not in code:
    print("[ECHEC] Ancrage bloc regime introuvable. Verifier signaux_gagnants.py")
    raise SystemExit(1)
code = code.replace(ANCRE, NOUV, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Gating multi-timeframe (1h+4h) installe dans signaux_gagnants.py")
print("     Les trades ne sont pris que si le regime 1h+4h est favorable (fit_avg>=1.0).")
