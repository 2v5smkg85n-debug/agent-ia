#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch: augmente le depot de capital (VOL_CIBLE + CAP_SECTEUR).
Regex-based (robuste aux variations de commentaires)."""
import os, re, shutil

FICHIER = os.path.join(os.getcwd(), "gestion_risque.py")
MARKER = "CAPITAL-DEPLOI-INSTALLE"

code = open(FICHIER, encoding="utf-8").read()
if MARKER in code:
    print("[OK] Patch capital-deploi deja installe.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.deploi")
print("[i] Backup: gestion_risque.py.bak.deploi")

changes = [
    (r'VOL_CIBLE_JOUR\s*=\s*[\d.]+', 'VOL_CIBLE_JOUR = 0.03', '0.02', '0.03'),
    (r'CAP_SECTEUR\s*=\s*[\d.]+', 'CAP_SECTEUR = 0.40', '0.25', '0.40'),
]
for pat, repl, avant, apres in changes:
    avant_val = re.search(pat, code)
    if not avant_val:
        print(f"[ECHEC] motif introuvable: {pat}")
        raise SystemExit(1)
    print(f"  {avant_val.group(0)}  ->  {repl}")
    code = re.sub(pat, repl, code, count=1)

code = code + f"\n# {MARKER}: VOL_CIBLE_JOUR 0.02->0.03, CAP_SECTEUR 0.25->0.40 (deploiement capital)\n"
open(FICHIER, "w", encoding="utf-8").write(code)
print("[OK] Depot de capital augmente. Positions ~50% plus grosses, jusqu'a 40% par secteur.")
