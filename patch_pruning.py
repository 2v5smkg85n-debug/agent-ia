#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch idempotent: integre l'auto-pruning dans signaux_gagnants.py.
Insere un check est_desactivee() dans strategies_gagnantes_par_actif()."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "signaux_gagnants.py")
MARKER = "AUTO-PRUNING-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch auto-pruning deja installe. Rien a faire.")
    raise SystemExit(0)

# backup
shutil.copy2(FICHIER, FICHIER + ".bak.pruning")
print("[i] Backup: signaux_gagnants.py.bak.pruning")

# Point d'ancrage (8 espaces d'indentation)
ANCRE = "        gagnantes.setdefault(sym, []).append(r)"

BLOC = (
    "        # " + MARKER + " : skip strategies desactivees en live (auto_pruning)\n"
    "        try:\n"
    "            from auto_pruning import est_desactivee\n"
    '            if est_desactivee(r.get("strategie", ""), r.get("actif", "")):\n'
    "                continue\n"
    "        except Exception:\n"
    "            pass\n"
    + ANCRE
)

if ANCRE not in code:
    print("[ECHEC] Ancrage introuvable. Verifier signaux_gagnants.py.")
    raise SystemExit(1)

code = code.replace(ANCRE, BLOC, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Patch auto-pruning installe dans signaux_gagnants.py")
