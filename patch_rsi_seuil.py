#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_rsi_seuil.py — Change le seuil RSI Mean Reversion 30 -> 35.
Cible uniquement la fonction strat_rsi_reversion (pas les autres <30)."""
import os, re

f = "backtest_moteur.py"
src = open(f, encoding="utf-8").read()

# Trouve le bloc de la fonction strat_rsi_reversion et change son seuil
def repl(m):
    bloc = m.group(0)
    avant = bloc
    bloc = bloc.replace('"""Achat quand RSI<30', '"""Achat quand RSI<35')
    bloc = bloc.replace("if r < 30:", "if r < 35:")
    bloc = bloc.replace("if r <30:", "if r < 35:")
    return bloc

pat = re.compile(r'def strat_rsi_reversion\(i, d\):.*?return None', re.DOTALL)
nouv = pat.sub(repl, src)

if nouv == src:
    print("ERREUR: aucun changement applique (fonction introuvable?)")
    raise SystemExit(1)

# Verifie qu'on n'a change que dans strat_rsi_reversion (compte des < 30 restants hors fn)
open(f, "w", encoding="utf-8").write(nouv)
print("OK backtest_moteur.py patche: strat_rsi_reversion seuil 30 -> 35")
# Affiche la fonction patchee pour verification
m = pat.search(nouv)
print("--- fonction patchee ---")
print(m.group(0) if m else "(introuvable)")
