#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_research_classement.py — Cable classement_strategies dans research_loop.

Ajoute un etape dans chaque cycle: calcule le classement dynamique des strategies
selon le moment (regime + live) et log le top strategie par actif.
"""
import os
D = os.getcwd()
F = os.path.join(D, "research_loop.py")
src = open(F, encoding="utf-8").read()

old = '''        else:
            log.info("Divergence EXTEND: %s", div.get("msg"))

    # 4. lecons auto (uniquement sur evenements significatifs)'''

new = '''        else:
            log.info("Divergence EXTEND: %s", div.get("msg"))

    # 4. classement strategies selon le moment (regime + perf live)
    try:
        import classement_strategies as cs
        cl = cs.calculer_classement()
        tops = []
        for actif, d in cl.items():
            s = d.get("strategies", [])
            if s and s[0].get("score", 0) > 0:
                tops.append(f"{actif}:{s[0]['strategie']}")
        if tops:
            log.info("Top strat (moment): %s", ", ".join(tops))
    except Exception:
        log.warning("classement: echec (non bloquant)")

    # 5. lecons auto (uniquement sur evenements significatifs)'''

assert old in src, "ancrage divergence->lecons introuvable"
src = src.replace(old, new, 1)
open(F, "w", encoding="utf-8").write(src)
import py_compile
py_compile.compile(F, doraise=True)
print("✅ research_loop.py: etape classement cablee (top strat/actif chaque cycle)")
print("✅ compile OK")
