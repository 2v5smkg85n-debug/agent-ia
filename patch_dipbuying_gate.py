#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_dipbuying_gate.py — Integre le gate dip-buying dans signaux_gagnants.py.

Gate: on n'achete PAS dans la force confirmee (bougie haussiere, biais>0).
Autorise neutre + baissier (achat de creux). Valide backtest: entrees biais>0
= 50% win (pire groupe), biais<=0 = 68.4% win.

Affecte l'argent reel (selection d'entree -> pont_revolut). A valider via
confirm_action avant deploiement.
"""
import os

F = "signaux_gagnants.py"
s = open(F, encoding="utf-8").read()

# 1) Constante DIP_BUYING_GATE apres LIMITE_LIVE
old1 = 'LIMITE_LIVE = {"1h": 200, "4h": 200, "15m": 200, "1d": 365}\n'
new1 = old1 + '\n# DIP-BUYING-GATE: bloque les entrees sur bougie haussiere confirmee\n' \
        '# (achat dans la force = pire groupe backtest 50% win). Autorise creux+neutre.\n' \
        'DIP_BUYING_GATE = True\n'
assert old1 in s, "LIMITE_LIVE introuvable"
s = s.replace(old1, new1, 1)

# 2) Calcul du biais + gate apres donnees = calculer_donnees(clotures)
old2 = '            clotures = [b["cloture"] for b in bougies]\n            donnees = calculer_donnees(clotures)\n'
new2 = old2 + (
    '            # DIP-BUYING-GATE: biais des chandeliers (achat de creux).\n'
    '            # Backtest: biais>0 (force) = 50% win (pire), biais<=0 (creux) = 68.4%.\n'
    '            _biais_bougies = 0.0\n'
    '            try:\n'
    '                from bougies_patterns import biais_bougies as _bb_fn\n'
    '                _biais_bougies = _bb_fn(bougies)\n'
    '            except Exception:\n'
    '                _biais_bougies = 0.0\n'
    '            if DIP_BUYING_GATE and _biais_bougies > 0:\n'
    '                continue  # bougie haussiere confirmee -> achat dans la force -> skip\n'
)
assert old2 in s, "bloc clotures/donnees introuvable"
s = s.replace(old2, new2, 1)

# 3) Ajout biais dans meilleure_strat
old3 = ('                        meilleure_strat = {**strat, "intervalle_live": interv_live,\n'
        '                                           "regime_1h": _r1h.get("regime"),\n'
        '                                           "regime_4h": _r4h.get("regime"),\n'
        '                                           "regime_fit": round(_fit_avg, 3),\n'
        '                                           "live_mult": round(_live_mult, 3)}\n')
new3 = ('                        meilleure_strat = {**strat, "intervalle_live": interv_live,\n'
        '                                           "regime_1h": _r1h.get("regime"),\n'
        '                                           "regime_4h": _r4h.get("regime"),\n'
        '                                           "regime_fit": round(_fit_avg, 3),\n'
        '                                           "live_mult": round(_live_mult, 3),\n'
        '                                           "biais_bougies": round(_biais_bougies, 2)}\n')
assert old3 in s, "bloc meilleure_strat introuvable"
s = s.replace(old3, new3, 1)

# 4) Affichage du biais dans le print ACHAT
old4 = ('            _lm = meilleure_strat.get("live_mult", 1.0)\n'
        '            _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""\n'
        '            print(f"ACHAT ({meilleure_strat[\'strategie\']} [{interv_aff}], "\n'
        '                  f"backtest {meilleur_retour:+.1f}%{_lm_str})")\n')
new4 = ('            _lm = meilleure_strat.get("live_mult", 1.0)\n'
        '            _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""\n'
        '            _bb_s = meilleure_strat.get("biais_bougies", 0.0)\n'
        '            _bb_str = f", dip {_bb_s:+.2f}" if _bb_s != 0 else ""\n'
        '            print(f"ACHAT ({meilleure_strat[\'strategie\']} [{interv_aff}], "\n'
        '                  f"backtest {meilleur_retour:+.1f}%{_lm_str}{_bb_str})")\n')
assert old4 in s, "bloc print ACHAT introuvable"
s = s.replace(old4, new4, 1)

open(F, "w", encoding="utf-8").write(s)
print("OK patch dip-buying gate applique a signaux_gagnants.py")
print("  - DIP_BUYING_GATE = True (constante ajoutee)")
print("  - biais calcule apres bougies, gate bloque biais>0")
print("  - biais affiche dans le print ACHAT")
