#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_live_feedback.py — Injecte la boucle d'auto-apprentissage live dans l'evolver.
Après sagesse_prompt (mutation + fresh), injecte live_lessons_prompt() qui extrait
les leçons de perf live. Avant l'appel LLM."""
import sys

ef = "strategy_evolver.py"
e = open(ef, encoding="utf-8").read()

ANCHOR = ('                      "cassure de canal, momentum sur retournement. Max 2 conditions, declencheable souvent.")\n'
          '    texte, llm_source = call_llm(prompt)')
INJECT = ('                      "cassure de canal, momentum sur retournement. Max 2 conditions, declencheable souvent.")\n'
          '    # LIVE FEEDBACK LOOP: injecte les lecons de perf live (auto-apprentissage)\n'
          '    # Avant l\'evolver n\'apprenait pas de ses trades live. Maintenant si.\n'
          '    try:\n'
          '        from live_lessons import live_lessons_prompt as _llp\n'
          '        _ll = _llp()\n'
          '        if _ll:\n'
          '            prompt += _ll\n'
          '            log("Lecons live injectees dans le prompt")\n'
          '    except Exception as _e:\n'
          '        pass\n'
          '    texte, llm_source = call_llm(prompt)')

if "live_lessons_prompt as _llp" in e:
    print("[evo] live_lessons injection deja presente - skip")
elif ANCHOR in e:
    e = e.replace(ANCHOR, INJECT, 1)
    print("[evo] live_lessons_prompt injecte avant call_llm")
else:
    print("[evo] ERREUR ancre call_llm introuvable"); sys.exit(1)

open(ef, "w", encoding="utf-8").write(e)
print("\n=== PATCH LIVE FEEDBACK APPLIQUE ===")
print("L'evolver apprend maintenant de la perf live (trades_fermes + classement + lecons)")
