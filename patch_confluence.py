#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_confluence.py - integre le filtre de confluence HTF dans ouvrir_position.

Insere une porte apres les gardes cheap (anti-corr, anti-gap, circuit breaker,
plugins) et avant le sizing. Fail-open. Toggle CONF_MULTI_TF=0. Idempotent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()

if "CONF_MULTI_TF" in src:
    print("[paper] porte CONFLUENCE DEJA presente -> skip")
    raise SystemExit(0)

ANCRE = '    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire'
if ANCRE not in src:
    print("[paper] ERREUR: ancre SIZING introuvable")
    raise SystemExit(1)

GATE = "\n".join([
    '    # FILTRE CONFLUENCE MULTI-TF: bloque les entrees contre-tendance (HTF opposee).',
    '    # Ameliore le win rate en n acceptant que les trades alignes avec la tendance',
    '    # de la timeframe superieure. Fail-open sur erreur API. Toggle: CONF_MULTI_TF=0.',
    '    if os.getenv("CONF_MULTI_TF", "1") != "0":',
    '        try:',
    '            from filtre_confluence_htf import _entree_bloquee_confluence',
    '            _blk_conf, _raison_conf = _entree_bloquee_confluence(signal)',
    '            if _blk_conf:',
    '                print("  [CONFLUENCE] " + str(signal.get("nom", signal.get("strategie", signal.get("symbole", "?")))) + ": entree bloquee (" + str(_raison_conf) + ")")',
    '                return False',
    '        except Exception:',
    '            pass',
    '',
]) + ANCRE

src = src.replace(ANCRE, GATE, 1)
open(P, "w").write(src)
print("[paper] porte CONFLUENCE inseree avant le sizing (fail-open, toggle CONF_MULTI_TF)")
