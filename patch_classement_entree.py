#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_classement_entree.py — Integre le classement dans le choix d'entree.

Dans signaux_gagnants.generer_signaux_gagnants, le score de selection passe de:
    _score = retour_pct * fit_avg
a:
    _score = retour_pct * fit_avg * live_mult
ou live_mult vient de classement_strategies.json (perf live bayesienne).

HONNETE: live_mult ~= 1.0 avec peu de trades (shrink bayesien vers 0.5 ->
mult 1.0). Effet faible maintenant, grandit quand les trades live s'accumulent.
C'est le bon comportement (pas de re-classement sur 1 trade = anti-overfit).
Le regime-fit frais (calcule live) est conserve, la perf live s'ajoute.
"""
import os
D = os.getcwd()
F = os.path.join(D, "signaux_gagnants.py")
src = open(F, encoding="utf-8").read()

# 1) Helper _classement_lookup (avant generer_signaux_gagnants)
old_def = "def generer_signaux_gagnants(prix_actuels, marches_paper):"
helper = '''_CLASSEMENT_CACHE = {"data": None, "mtime": 0.0}


def _classement_lookup():
    """{(actif, strategie): entry} depuis classement_strategies.json (cache par mtime).
    Mis a jour chaque heure par research_loop. Retourne {} si absent/erreur."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "classement_strategies.json")
        mt = os.path.getmtime(p)
        if _CLASSEMENT_CACHE["data"] is None or mt != _CLASSEMENT_CACHE["mtime"]:
            import json
            d = json.load(open(p, encoding="utf-8"))
            lookup = {}
            for actif, info in d.items():
                for s in info.get("strategies", []):
                    lookup[(actif, s.get("strategie"))] = s
            _CLASSEMENT_CACHE["data"] = lookup
            _CLASSEMENT_CACHE["mtime"] = mt
        return _CLASSEMENT_CACHE["data"]
    except Exception:
        return {}


def generer_signaux_gagnants(prix_actuels, marches_paper):'''
assert old_def in src, "ancrage def generer_signaux_gagnants introuvable"
src = src.replace(old_def, helper, 1)

# 2) Score enrichi du live_mult
old_score = '''                    _score = strat.get("retour_pct", 0) * _fit_avg
                    if _score > meilleur_score:
                        meilleur_score = _score
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = {**strat, "intervalle_live": interv_live,
                                           "regime_1h": _r1h.get("regime"),
                                           "regime_4h": _r4h.get("regime"),
                                           "regime_fit": round(_fit_avg, 3)}'''
new_score = '''                    # CLASSEMENT-INSTALLE: enrichit le score avec live_mult (perf
                    # live bayesienne depuis classement_strategies.json). Effet
                    # faible avec peu de trades (shrink vers 1.0), grandit ensuite.
                    _live_mult = 1.0
                    try:
                        _cl = _classement_lookup().get((symbole, nom))
                        if _cl:
                            _live_mult = _cl.get("live_mult", 1.0)
                    except Exception:
                        pass
                    _score = strat.get("retour_pct", 0) * _fit_avg * _live_mult
                    if _score > meilleur_score:
                        meilleur_score = _score
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = {**strat, "intervalle_live": interv_live,
                                           "regime_1h": _r1h.get("regime"),
                                           "regime_4h": _r4h.get("regime"),
                                           "regime_fit": round(_fit_avg, 3),
                                           "live_mult": round(_live_mult, 3)}'''
assert old_score in src, "ancrage _score introuvable"
src = src.replace(old_score, new_score, 1)

# 3) Affichage: montre live_mult quand il pese
old_print = '''            interv_aff = meilleure_strat.get("intervalle", "?")
            print(f"ACHAT ({meilleure_strat['strategie']} [{interv_aff}], "
                  f"backtest {meilleur_retour:+.1f}%)")'''
new_print = '''            interv_aff = meilleure_strat.get("intervalle", "?")
            _lm = meilleure_strat.get("live_mult", 1.0)
            _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""
            print(f"ACHAT ({meilleure_strat['strategie']} [{interv_aff}], "
                  f"backtest {meilleur_retour:+.1f}%{_lm_str})")'''
assert old_print in src, "ancrage print ACHAT introuvable"
src = src.replace(old_print, new_print, 1)

open(F, "w", encoding="utf-8").write(src)
import py_compile
py_compile.compile(F, doraise=True)
print("✅ signaux_gagnants.py: classement integre dans le choix d'entree")
print("   _score = retour_pct * fit_avg * live_mult (live_mult depuis classement_strategies.json)")
print("✅ compile OK")
