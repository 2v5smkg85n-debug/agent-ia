#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_sentiment_reflection.py
Cable sentiment_web dans reflection_gemini.py:
1) import digest_sentiment
2) ctx['sentiment_web'] = digest_sentiment() dans gather_contexte
3) section 'SENTIMENT WEB' dans le prompt (apres positions, avant lecons)
4) Test: sentiment_actif('BTCUSDT') (1 requete web) pour verifier l'API.
"""
import os, sys

DOSSIER = os.getcwd()
RG = os.path.join(DOSSIER, "reflection_gemini.py")
src = open(RG, encoding="utf-8").read()

# 1) import digest_sentiment apres sagesse
IMP_OLD = "from sagesse_traders import sagesse_prompt"
IMP_NEW = "from sagesse_traders import sagesse_prompt\nfrom sentiment_web import digest_sentiment"
if "from sentiment_web import digest_sentiment" not in src:
    assert IMP_OLD in src, "ancrage import sagesse introuvable"
    src = src.replace(IMP_OLD, IMP_NEW, 1)
    print("✅ import digest_sentiment ajoute")
else:
    print("ℹ️ import deja present")

# 2) ctx['sentiment_web'] dans gather_contexte (avant la fermeture du return)
CTX_OLD = '''                               for p in positions],
    }'''
CTX_NEW = '''                               for p in positions],
        "sentiment_web": digest_sentiment(),
    }'''
if '"sentiment_web"' not in src:
    assert CTX_OLD in src, "ancrage return gather_contexte introuvable"
    src = src.replace(CTX_OLD, CTX_NEW, 1)
    print("✅ ctx['sentiment_web'] ajoute dans gather_contexte")
else:
    print("ℹ️ ctx['sentiment_web'] deja present")

# 3) section SENTIMENT WEB dans le prompt avant LECONS
P_OLD = '''POSITIONS OUVERTES ACTUELLES:
{json.dumps(ctx['positions_ouvertes'], ensure_ascii=False, indent=2) or '(aucune)'}

LECONS APPRISES (NE RE-PROPOSE PAS CES IDEES, deja rejetees par backtest):'''
P_NEW = '''POSITIONS OUVERTES ACTUELLES:
{json.dumps(ctx['positions_ouvertes'], ensure_ascii=False, indent=2) or '(aucune)'}

SENTIMENT WEB (actualite recente, biais court terme hausse/baisse par marche):
{ctx['sentiment_web']}

LECONS APPRISES (NE RE-PROPOSE PAS CES IDEES, deja rejetees par backtest):'''
if "SENTIMENT WEB" not in src:
    assert P_OLD in src, "ancrage prompt positions/lecons introuvable"
    src = src.replace(P_OLD, P_NEW, 1)
    print("✅ section SENTIMENT WEB ajoutee au prompt")
else:
    print("ℹ️ section SENTIMENT WEB deja presente")

open(RG, "w", encoding="utf-8").write(src)

import py_compile
py_compile.compile(RG, doraise=True)
print("✅ compile OK reflection_gemini.py")

# 4) Test: 1 requete web reelle sur BTCUSDT (verifie API + parsing)
sys.path.insert(0, DOSSIER)
import sentiment_web
print("\n=== TEST: sentiment web BTCUSDT (1 requete sonar) ===")
r = sentiment_web.sentiment_actif("BTCUSDT")
if r:
    print("symbole :", r.get("symbole"))
    print("biais   :", r.get("biais"), "(>0 haussier, <0 baissier)")
    print("confiance:", r.get("confiance"))
    print("resume  :", r.get("resume"))
    print("catalyseurs:", r.get("catalyseurs"))
    print("\n✅ Le web est accessible — l'IA verra le sentiment BTC dans sa reflexion")
else:
    print("❌ echec requete (quota PPLX epuise ou erreur) — le module retombe sur '(indispo)'")
