#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_memoire_marche.py — Injecte la mémoire du marché dans la génération evolver.
Après live_lessons (et sagesse), injecte memoire_marche_prompt() qui apprend
~7 ans d'évolution du marché BTC à l'IA."""
import sys

ef = "strategy_evolver.py"
e = open(ef, encoding="utf-8").read()

ANCHOR = '''    # LIVE FEEDBACK LOOP: injecte les lecons de perf live (auto-apprentissage)
    # Avant l\'evolver n\'apprenait pas de ses trades live. Maintenant si.
    try:
        from live_lessons import live_lessons_prompt as _llp
        _ll = _llp()
        if _ll:
            prompt += _ll
            log("Lecons live injectees dans le prompt")
    except Exception as _e:
        pass
    texte, llm_source = call_llm(prompt)'''

INJECT = '''    # LIVE FEEDBACK LOOP: injecte les lecons de perf live (auto-apprentissage)
    # Avant l\'evolver n\'apprenait pas de ses trades live. Maintenant si.
    try:
        from live_lessons import live_lessons_prompt as _llp
        _ll = _llp()
        if _ll:
            prompt += _ll
            log("Lecons live injectees dans le prompt")
    except Exception as _e:
        pass
    # MEMOIRE DU MARCHÉ: apprentissage de l'évolution multi-années (~7 ans BTC)
    try:
        from memoire_marche import memoire_marche_prompt as _mmp
        _mm = _mmp()
        if _mm:
            prompt += _mm
            log("Memoire du marché injectee dans le prompt")
    except Exception:
        pass
    texte, llm_source = call_llm(prompt)'''

if "from memoire_marche import memoire_marche_prompt" in e:
    print("[evo] memoire_marche injection deja presente - skip")
elif ANCHOR in e:
    e = e.replace(ANCHOR, INJECT, 1)
    print("[evo] memoire_marche_prompt injecte avant call_llm")
else:
    print("[evo] ERREUR ancre live_lessons/call_llm introuvable"); sys.exit(1)

open(ef, "w", encoding="utf-8").write(e)
print("\n=== PATCH MEMOIRE DU MARCHÉ APPLIQUE ===")
print("L'evolver apprend maintenant ~7 ans d'évolution du marché crypto")
