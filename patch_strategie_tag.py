#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_strategie_tag.py — Corrige le bug du tag strategie manquant.
ouvrir_position stocke maintenant signal["strategie"] dans la position.
fermer_position le propage au trade ferme. Les positions sans strategie
(chemins indicateurs/ia) fallback sur source."""
import os, re

f = "paper_trading.py"
src = open(f, encoding="utf-8").read()

# 1. Ajoute "strategie" dans le dict position de ouvrir_position
old_pos = '''        "signal_raison": signal.get("raison", ""),
        "source": signal.get("source", "")
    }
    pf["positions"].append(position)'''

new_pos = '''        "signal_raison": signal.get("raison", ""),
        "source": signal.get("source", ""),
        "strategie": signal.get("strategie") or signal.get("source") or "inconnu"
    }
    pf["positions"].append(position)'''

if old_pos in src:
    src = src.replace(old_pos, new_pos, 1)
    print("OK ouvrir_position: ajout champ strategie")
elif '"strategie": signal.get("strategie")' in src:
    print("deja patche (ouvrir_position) - skip")
else:
    print("ERREUR: bloc ouvrir_position introuvable")
    raise SystemExit(1)

# 2. fermer_position: propage strategie au trade ferme (si pas deja)
# Cherche le dict du trade ferme dans fermer_position
old_ferm = '"signal_raison": position.get("signal_raison", ""),'
new_ferm = ('"signal_raison": position.get("signal_raison", ""),\n'
            '        "strategie": position.get("strategie", position.get("source", "")),')

if old_ferm in src and '"strategie": position.get("strategie"' not in src:
    src = src.replace(old_ferm, new_ferm, 1)
    print("OK fermer_position: propagation strategie au trade ferme")
elif '"strategie": position.get("strategie"' in src:
    print("deja patche (fermer_position) - skip")
else:
    print("INFO: bloc fermer_position non matche (format different) - verifie manuellement")

open(f, "w", encoding="utf-8").write(src)
print("\nVerifie:")
import subprocess
r = subprocess.run(["grep", "-n", "strategie", f], capture_output=True, text=True)
print(r.stdout)
