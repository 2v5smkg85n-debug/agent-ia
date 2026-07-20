#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sagesse_prompt.py — Restaure sagesse_prompt() dans sagesse_traders.py.

reflection_gemini.py fait `from sagesse_traders import sagesse_prompt` et
injecte le resultat dans son prompt. La fonction a ete ecrasee lors du rewrite.
On la reajoute (retourne la sagesse formatee pour la reflection).
"""
import os

F = "sagesse_traders.py"
s = open(F, encoding="utf-8").read()

if "def sagesse_prompt" in s:
    print("sagesse_prompt deja presente, rien a faire")
    raise SystemExit(0)

# inserer la fonction avant le bloc if __name__
anchor = 'if __name__ == "__main__":'
assert anchor in s, "bloc __main__ introuvable"

func = '''def sagesse_prompt():
    """Retourne la sagesse des maitres traders formatee pour le prompt de reflection."""
    L = ["Sagesse des 10 maitres traders (principes + application au systeme):"]
    for nom, s in SAGESSE.items():
        L.append(f"- {nom}: {s['principe']}")
        L.append(f"    applique: {s['application_ia']}")
        L.append(f"    alignement: {s['aligne']}")
    L.append("")
    L.append("Tests backtest realises (backtest_sagesse.py):")
    for key, src, q in A_TESTER:
        L.append(f"- {key} [{src}]: {q}")
    L.append("Resultats:")
    L.append("- deep_contrarian REJETE: RSI<20 = couteau tombant (33% win). RSI 20-30 (creux modere) gagne 83%.")
    L.append("- cut_losers REJETE: couper les perdants vite detruit le PnL (-7%). La patience paie en mean-reversion.")
    L.append("- turtle_breakout NUANCE: expectancy positive (55% win) mais qualite 4x inferieure en QUIET. Piste regime TREND uniquement.")
    L.append("")
    L.append("META-PATTERN CRITICAL: le systeme est MEAN-REVERSION. La sagesse classique du trading est")
    L.append("souvent INVERSEE ici: il faut de la PATIENCE et des creux MODERES, pas les extremes ni les")
    L.append("coupes rapides. Le trend-following (ADX, trailing, bougies haussieres, Turtle) nuit en QUIET.")
    L.append("Le contrarian modere (RSI 20-30, gate dip-buying) est valide. Ne re-propose PAS les principes")
    L.append("deja rejetes (deep contrarian, cut losers fast, trend en QUIET).")
    return "\\n".join(L)


'''
s = s.replace(anchor, func + anchor, 1)
open(F, "w", encoding="utf-8").write(s)
print("OK sagesse_prompt() restauree dans sagesse_traders.py")
