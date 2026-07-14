#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch idempotent: integre meta_tuning (TP/SL par actif) dans verifier_sorties."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "paper_trading.py")
MARKER = "META-TUNING-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch meta_tuning deja installe. Rien a faire.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.tuning")
print("[i] Backup: paper_trading.py.bak.tuning")

ANCRE = (
    '        # Take-profit serre: encaisse des que +1.5%\n'
    '        if variation >= TAKE_PROFIT_PCT:\n'
    '            positions_a_fermer.append((pos, prix_actuel, "TAKE-PROFIT", variation))\n'
    '        # Stop-loss serre: coupe des que -1.5%\n'
    '        elif variation <= -STOP_LOSS_PCT:\n'
    '            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))\n'
)

NOUV = (
    '        # ' + MARKER + ' : TP/SL par actif (fallback constantes globales)\n'
    '        try:\n'
    '            from meta_tuning import tp_sl_actif\n'
    '            _tp, _sl = tp_sl_actif(sym)\n'
    '        except Exception:\n'
    '            _tp, _sl = TAKE_PROFIT_PCT, STOP_LOSS_PCT\n'
    '        # Take-profit: encaisse des que +_tp%\n'
    '        if variation >= _tp:\n'
    '            positions_a_fermer.append((pos, prix_actuel, "TAKE-PROFIT", variation))\n'
    '        # Stop-loss: coupe des que -_sl%\n'
    '        elif variation <= -_sl:\n'
    '            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))\n'
)

if ANCRE not in code:
    print("[ECHEC] Ancrage verifier_sorties introuvable. Verifier paper_trading.py")
    raise SystemExit(1)
code = code.replace(ANCRE, NOUV, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Patch meta_tuning installe dans paper_trading.py (verifier_sorties)")
