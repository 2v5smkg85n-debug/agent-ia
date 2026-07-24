#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_const_anticorr.py — ajoute SEULEMENT la constante manquante.

edit2 (la garde) est déjà appliqué sur le VPS, mais edit1 (la constante)
a échoué car MAX_POSITIONS vaut 8 sur le VPS (pas 5). La garde référence
donc FENETRE_CORRELATION_MIN sans qu'elle existe -> NameError -> except:pass
-> garde désactivée silencieusement. Ce patch fixe ça avec un regex robuste.

Idempotent: check "FENETRE_CORRELATION_MIN = 60" (la définition, pas juste le nom).
"""
import os, re

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()

if "FENETRE_CORRELATION_MIN = 60" in src:
    print("[paper] constante FENETRE_CORRELATION_MIN=60 DÉJÀ présente -> skip")
else:
    src2, n = re.subn(
        r'(MAX_POSITIONS\s*=\s*\d+[^\n]*)',
        r'\1\nFENETRE_CORRELATION_MIN = 60     # anti-double-exposition: bloque 2e entree sur actif ouvert <60min',
        src, count=1)
    if n:
        open(P, "w").write(src2)
        print(f"[paper] constante FENETRE_CORRELATION_MIN=60 ajoutée après MAX_POSITIONS (match {n})")
    else:
        print("[paper] ERREUR: ligne MAX_POSITIONS introuvable!")
        raise SystemExit(1)

# vérif
import importlib
import paper_trading
importlib.reload(paper_trading)
print(f"VÉRIF: FENETRE_CORRELATION_MIN = {paper_trading.FENETRE_CORRELATION_MIN}")
