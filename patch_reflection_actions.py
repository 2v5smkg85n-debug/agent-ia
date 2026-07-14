#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch idempotent: enrichit le prompt de reflection_gemini.py pour demander
un champ 'actions' structure (desactiver_strategie / ajuster_tp / ajuster_sl)
avec confiance + raison. La boucle fermee (actions_executor) le consomme."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "reflection_gemini.py")
MARKER = "ACTIONS-FIELD-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Patch actions-field deja installe. Rien a faire.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.actions")
print("[i] Backup: reflection_gemini.py.bak.actions")

ANCRE = (
    '  "priorite": "la suggestion la plus importante a court terme"\n'
    '}}\n'
    'Reponds UNIQUEMENT avec le JSON."""'
)

if ANCRE not in code:
    print("[ECHEC] Ancrage prompt introuvable. Verifier reflection_gemini.py")
    raise SystemExit(1)

NOUV = (
    '  "priorite": "la suggestion la plus importante a court terme",\n'
    '  "actions": [\n'
    '    {{"type": "desactiver_strategie", "strategie": "MACD Momentum", "actif": "SOLUSDT", "confiance": 0.8, "raison": "..."}},\n'
    '    {{"type": "ajuster_tp", "actif": "SOLUSDT", "tp": 1.0, "confiance": 0.7, "raison": "..."}},\n'
    '    {{"type": "ajuster_sl", "actif": "SOLUSDT", "sl": 2.0, "confiance": 0.7, "raison": "..."}}\n'
    '  ]\n'
    '}}\n'
    'IMPORTANT: chaque action doit reposer sur les donnees reelles fournies. '
    'Ne propose une desactivation QUE pour une strategie avec pnl negatif. '
    'confiance entre 0.0 et 1.0. Liste vide [] si aucune action justifiee. '
    '# ' + MARKER + '\n'
    'Reponds UNIQUEMENT avec le JSON."""'
)

code = code.replace(ANCRE, NOUV, 1)
with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Prompt reflection enrichi avec champ 'actions' structure.")
