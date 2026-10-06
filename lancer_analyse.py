#!/usr/bin/env python3
"""Lance une analyse du marche via l'IA autonome + sous-agents."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import chat_naturel as cn

print("Analyse du marche en cours...")
resultat = cn._analyser_marche_auto()
if resultat:
    print(resultat)
    try:
        cn._telegram_send(resultat)
    except Exception:
        pass
else:
    print("L'IA a analyse le marche: aucune opportunite pour le moment.")
