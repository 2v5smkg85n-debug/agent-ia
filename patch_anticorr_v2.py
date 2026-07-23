#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_anticorr_v2.py - resserre la garde ANTI-CORR.

Le 23/07 a 19:26, la meme strategie (Bollinger Breakout) a re-ouvert ARB pile
60min apres la 1ere position -> la garde <60min n a pas bloque (cas limite).
On resserre: meme strategie sur meme actif -> bloque 120min (anti-pyramiding
correle), strategie differente -> 60min. Borne inclusive (<=). Idempotent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()

NOUVEAU = "\n".join([
    '            _sym = signal["symbole"]',
    '            _sig_strat = signal.get("strategie") or signal.get("source") or ""',
    '            _maint = datetime.now()',
    '            _FEN_MEME_STRAT = 120  # meme strategie sur meme actif: bloque 2h (anti-pyramiding correle)',
    '            for _p in pf["positions"]:',
    '                if _p["symbole"] != _sym:',
    '                    continue',
    '                try:',
    '                    _dt = datetime.strptime(_p.get("date_ouverture",""), "%Y-%m-%d %H:%M")',
    '                    _age = (_maint - _dt).total_seconds() / 60',
    '                    _meme_strat = bool(_sig_strat) and _p.get("strategie","") == _sig_strat',
    '                    _fen = _FEN_MEME_STRAT if _meme_strat else FENETRE_CORRELATION_MIN',
    '                    if _age <= _fen:',
    '                        print("  [ANTI-CORR] " + str(signal.get("nom",_sym)) + ": actif deja ouvert (" + str(int(_age)) + "min<=" + str(_fen) + "min) -> entree bloquee (evite double-exposition)")',
    '                        return False',
    '                except Exception:',
    '                    pass',
])

ANCIEN = "\n".join([
    '            _sym = signal["symbole"]',
    '            _maint = datetime.now()',
    '            for _p in pf["positions"]:',
    '                if _p["symbole"] != _sym:',
    '                    continue',
    '                try:',
    '                    _dt = datetime.strptime(_p.get("date_ouverture",""), "%Y-%m-%d %H:%M")',
    '                    _age = (_maint - _dt).total_seconds() / 60',
    '                    if _age < FENETRE_CORRELATION_MIN:',
    '                        print(f"  [ANTI-CORR] {signal.get(\'nom\',_sym)}: actif déjà ouvert ({_age:.0f}min<{FENETRE_CORRELATION_MIN}min) -> entrée bloquée (évite double-exposition corrélée)")',
    '                        return False',
    '                except Exception:',
    '                    pass',
])

if "_FEN_MEME_STRAT" in src:
    print("[paper] garde ANTI-CORR v2 DEJA presente -> skip")
elif ANCIEN in src:
    src = src.replace(ANCIEN, NOUVEAU, 1)
    open(P, "w").write(src)
    print("[paper] garde ANTI-CORR resserree: meme strat 120min (inclusive), strat diff 60min")
else:
    print("[paper] ERREUR: ancre introuvable")
    raise SystemExit(1)
