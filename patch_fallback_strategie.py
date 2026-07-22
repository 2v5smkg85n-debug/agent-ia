#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_fallback_strategie.py — Les signaux de fallback (technique/IA) n'avaient
pas de champ 'strategie'. Avant: trades fallback enregistres avec strategie VIDE
(ou 'indicateurs'/'ia' via fuite du champ source). Maintenant: etiquette explicite
'technique' / 'ia' -> la boucle live_lessons peut apprendre quelle CLASSE de
signaux (backtest-gagnant vs technique vs ia) performe en live."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()

# 1. technique signal: ajoute strategie
OLD_T = '''                signaux.append({
                    "symbole": sym,
                    "prix_entree": prix_actuels[sym],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "indicateurs",
                    "score": score,
                    "raison": "; ".join(analyse["signaux"][:2])
                })'''
NEW_T = '''                signaux.append({
                    "symbole": sym,
                    "prix_entree": prix_actuels[sym],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "indicateurs",
                    "strategie": "technique",
                    "score": score,
                    "raison": "; ".join(analyse["signaux"][:2])
                })'''
if '"strategie": "technique"' in p:
    print("[paper] strategie technique deja present - skip")
elif OLD_T in p:
    p = p.replace(OLD_T, NEW_T, 1)
    print("[paper] strategie 'technique' ajoute aux signaux indicateurs")
else:
    print("[paper] ERREUR ancre technique"); sys.exit(1)

# 2. IA signal: ajoute strategie
OLD_IA = '''            signaux.append({
                "symbole": symbole_trouve,
                "prix_entree": prix_actuels[symbole_trouve],
                "nom": MARCHES_PAPER[symbole_trouve]["nom"],
                "marche": MARCHES_PAPER[symbole_trouve]["marche"],
                "source": "ia",
                "score": 0,
                "raison": "signal IA"
            })'''
NEW_IA = '''            signaux.append({
                "symbole": symbole_trouve,
                "prix_entree": prix_actuels[symbole_trouve],
                "nom": MARCHES_PAPER[symbole_trouve]["nom"],
                "marche": MARCHES_PAPER[symbole_trouve]["marche"],
                "source": "ia",
                "strategie": "ia",
                "score": 0,
                "raison": "signal IA"
            })'''
if '"strategie": "ia"' in p:
    print("[paper] strategie ia deja present - skip")
elif OLD_IA in p:
    p = p.replace(OLD_IA, NEW_IA, 1)
    print("[paper] strategie 'ia' ajoutee aux signaux IA")
else:
    print("[paper] ERREUR ancre ia"); sys.exit(1)

open(f, "w", encoding="utf-8").write(p)
print("\n=== PATCH FALLBACK STRATEGIE APPLIQUE ===")
print("Signaux technique/IA ont maintenant un champ strategie explicite")
