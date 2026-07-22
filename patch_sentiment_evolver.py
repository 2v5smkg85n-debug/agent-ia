#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sentiment_evolver.py — Injecte le sentiment du marché (Fear & Greed)
dans la génération evolver, après la mémoire du marché, avant call_llm.
4e couche de connaissance: sagesse + leçons live + mémoire marché + sentiment."""
import sys

ef = "strategy_evolver.py"
e = open(ef, encoding="utf-8").read()

ANCHOR = '''    # MEMOIRE DU MARCHÉ: apprentissage de l'évolution multi-années (~7 ans BTC)
    try:
        from memoire_marche import memoire_marche_prompt as _mmp
        _mm = _mmp()
        if _mm:
            prompt += _mm
            log("Memoire du marché injectee dans le prompt")
    except Exception:
        pass
    texte, llm_source = call_llm(prompt)'''

INJECT = '''    # MEMOIRE DU MARCHÉ: apprentissage de l'évolution multi-années (~7 ans BTC)
    try:
        from memoire_marche import memoire_marche_prompt as _mmp
        _mm = _mmp()
        if _mm:
            prompt += _mm
            log("Memoire du marché injectee dans le prompt")
    except Exception:
        pass
    # SENTIMENT DU MARCHÉ: Fear & Greed Index (dimension comportementale)
    try:
        from sentiment_marche import sentiment_prompt as _spt
        _sp = _spt()
        if _sp:
            prompt += _sp
            log("Sentiment du marché injecte dans le prompt")
    except Exception:
        pass
    texte, llm_source = call_llm(prompt)'''

if "from sentiment_marche import sentiment_prompt" in e:
    print("[evo] sentiment injection déjà présente - skip")
elif ANCHOR in e:
    e = e.replace(ANCHOR, INJECT, 1)
    print("[evo] sentiment_prompt injecté avant call_llm")
else:
    print("[evo] ERREUR ancre memoire/call_llm introuvable"); sys.exit(1)

open(ef, "w", encoding="utf-8").write(e)
print("\n=== PATCH SENTIMENT APPLIQUE ===")
print("4e couche de connaissance: sagesse + leçons live + mémoire marché + sentiment")
