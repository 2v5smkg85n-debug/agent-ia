#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_anticorr.py — garde anti-double-exposition corrélée.

Problème: 2 stratégies différentes entrent sur le MÊME actif au MÊME moment
(ex: ARB Evolved + ARB RSI à 12:41). Quand l'actif chute, les 2 stoppent ensemble
= perte doublée (-2.28€ d'un coup le 23/07).

Solution: bloque une 2e entrée sur un actif déjà ouvert dans les dernières
FENETRE_CORRELATION_MIN minutes. Les entrées simultanées corrélées sont éliminées,
sans toucher au conviction sizing ni limiter un seul position forte.

Idempotent: skip si FENETRE_CORRELATION_MIN déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: constante (ancrée sur MAX_POSITIONS qui existe réellement) ---
ancien_c = 'MAX_POSITIONS = 5               # 5 positions (plus de diversification)'
nouveau_c = (
    'MAX_POSITIONS = 5               # 5 positions (plus de diversification)\n'
    'FENETRE_CORRELATION_MIN = 60     # anti-double-exposition: bloque 2e entrée sur actif ouvert <60min'
)
if ancien_c in src and "FENETRE_CORRELATION_MIN" not in src:
    src = src.replace(ancien_c, nouveau_c)
    edits += 1
    print("[paper] edit1: constante FENETRE_CORRELATION_MIN=60")

# --- Edit 2: garde anti-corrélation en début de ouvrir_position ---
ancien_g = (
    'def ouvrir_position(pf, signal, prix_actuel):\n'
    '    if len(pf["positions"]) >= MAX_POSITIONS:\n'
    '        return False'
)
nouveau_g = (
    'def ouvrir_position(pf, signal, prix_actuel):\n'
    '    if len(pf["positions"]) >= MAX_POSITIONS:\n'
    '        return False\n'
    '    # ANTI-DOUBLE-EXPOSITION: bloque une 2e entrée sur un actif déjà ouvert récemment\n'
    '    # (2 stratégies sur le même actif au même moment = perte corrélée doublée quand ça chute)\n'
    '    if os.getenv("ANTI_CORR", "1") != "0":\n'
    '        try:\n'
    '            _sym = signal["symbole"]\n'
    '            _maint = datetime.now()\n'
    '            for _p in pf["positions"]:\n'
    '                if _p["symbole"] != _sym:\n'
    '                    continue\n'
    '                try:\n'
    '                    _dt = datetime.strptime(_p.get("date_ouverture",""), "%Y-%m-%d %H:%M")\n'
    '                    _age = (_maint - _dt).total_seconds() / 60\n'
    '                    if _age < FENETRE_CORRELATION_MIN:\n'
    '                        print(f"  [ANTI-CORR] {signal.get(\'nom\',_sym)}: actif déjà ouvert ({_age:.0f}min<{FENETRE_CORRELATION_MIN}min) -> entrée bloquée (évite double-exposition corrélée)")\n'
    '                        return False\n'
    '                except Exception:\n'
    '                    pass\n'
    '        except Exception:\n'
    '            pass'
)
if ancien_g in src and "ANTI-CORR" not in src:
    src = src.replace(ancien_g, nouveau_g)
    edits += 1
    print("[paper] edit2: garde anti-corrélation dans ouvrir_position")

open(P, "w").write(src)
print(f"\n=== ANTI-CORR APPLIQUÉ ===  ({edits} edits)")
print("2e entrée sur actif ouvert <60min = bloquée (évite perte corrélée doublée)")
