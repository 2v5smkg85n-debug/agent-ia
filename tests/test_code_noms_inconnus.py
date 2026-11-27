"""Garde-fou « sans bug » : aucun nom inconnu dans le code du bot.

Un nom inconnu (variable ou fonction qui n'existe pas) ne se voit pas a la compilation : il plante seulement
quand la ligne s'execute, et un try/except peut l'avaler pendant des semaines (STAGNATION_PERTE_SEULE en octobre,
`pe` dans page_porte.py en novembre : la ligne des filtres desarmes ne s'affichait jamais sur le dashboard).
pyflakes lit le code sans l'executer. Le test est saute si pyflakes n'est pas installe (il ne l'est pas sur le VPS).
"""
import os
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAVES = ("undefined name", "referenced before assignment", "syntax error", "invalid syntax")


def _fichiers():
    try:
        sortie = subprocess.run(["git", "ls-files", "*.py"], cwd=RACINE, capture_output=True, text=True, timeout=30).stdout.split()
    except Exception:
        sortie = []
    if not sortie:
        sortie = [f for f in os.listdir(RACINE) if f.endswith(".py")]
    return [f for f in sortie if not f.startswith(("archive/", "archives/")) and os.path.exists(os.path.join(RACINE, f))]


def test_aucun_nom_inconnu():
    pytest.importorskip("pyflakes")
    fichiers = _fichiers()
    assert len(fichiers) > 50
    r = subprocess.run([sys.executable, "-m", "pyflakes"] + fichiers, cwd=RACINE, capture_output=True, text=True, timeout=300)
    graves = [l for l in (r.stdout + r.stderr).splitlines() if any(g in l.lower() for g in GRAVES)]
    assert not graves, "noms inconnus ou erreurs de syntaxe :\n" + "\n".join(graves[:20])
