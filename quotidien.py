#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode autonome quotidien.
Lance une analyse de marche + briefing chaque jour.
A utiliser avec cron (voir instructions fournies).

Usage:
    python quotidien.py            # lance le briefing du jour
    python quotidien.py --voir    # affiche le dernier briefing
"""
import os
import sys
import json
import time
from datetime import datetime

# Importe les fonctions de l'agent
from agent import (
    charger_memoire, sauver_memoire, ajouter, instruction_memoire,
    MODELS, disponible, meilleur_defaut, appeler_ia,
    perplexity, gemini, claude, chatgpt,
    notify_ifft, lecons_recentes
)

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BRIEFINGS = os.path.join(DOSSIER, "briefings.json")

# ============================================
# SAUVEGARDE DES BRIEFINGS
# ============================================
def charger_briefings():
    if os.path.exists(FICHIER_BRIEFINGS):
        try:
            with open(FICHIER_BRIEFINGS, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def sauver_briefing(texte):
    briefings = charger_briefings()
    briefings.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "contenu": texte
    })
    # Garde seulement les 30 derniers
    briefings = briefings[-30:]
    with open(FICHIER_BRIEFINGS, "w") as f:
        json.dump(briefings, f, ensure_ascii=False, indent=2)

# ============================================
# ANALYSE DE MARCHE (temps reel via Perplexity)
# ============================================
def analyser_marche():
    """Recupere les donnees de marche en direct."""
    questions = [
        "Prix actuel du Bitcoin (BTC) et Ethereum (ETH) en USD et EUR, avec variation 24h. Donne des chiffres precis.",
        "Top 3 actualites crypto et marches financiers aujourd'hui, impact sur les prix. Sois concis."
    ]
    analyses = []
    ia = "perplexity" if disponible("perplexity") else meilleur_defaut()
    for q in questions:
        print(f"  -> Analyse: {q[:60]}...", end=" ", flush=True)
        try:
            rep, modele = appeler_ia(ia, q)
            if not rep.startswith("[Erreur"):
                print("OK")
                analyses.append({"question": q, "reponse": rep})
            else:
                print("echec")
        except Exception as e:
            print(f"erreur: {e}")
        time.sleep(2)
    return analyses

# ============================================
# BRIEFING QUOTIDIEN (synthese intelligente)
# ============================================
def generer_briefing(analyses):
    """Synthetise les analyses en un briefing clair et actionnable."""
    memoire = instruction_memoire()
    lecons = lecons_recentes()
    donnees = "\n\n".join(f"### {a['question']}\n{a['reponse']}" for a in analyses)

    prompt = (
        f"Tu es l'assistant IA personnel d'un utilisateur interesse par le trading crypto et les bots Python.\n"
        f"{memoire}{lecons}"
        f"Voici les donnees de marche recuperees en direct aujourd'hui:\n\n{donnees}\n\n"
        f"Produis un BRIEFING QUOTIDIEN concis et actionnable avec ce format:\n"
        f"1. **Resume du marche** (2-3 lignes)\n"
        f"2. **Prix cles** (BTC, ETH en USD/EUR + variation 24h)\n"
        f"3. **Opportunites/risques** (2-3 points concrets)\n"
        f"4. **Recommandation du jour** (1 action a envisager)\n\n"
        f"Sois direct, precis et utile. Pas de bla-bla. Max 250 mots."
    )
    ia_synthese = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else meilleur_defaut())
    print(f"  -> Synthese via {ia_synthese}...", end=" ", flush=True)
    try:
        briefing, modele = appeler_ia(ia_synthese, prompt)
        if not briefing.startswith("[Erreur"):
            print("OK")
            return briefing, modele
        print("echec")
        return briefing, modele
    except Exception as e:
        print(f"erreur: {e}")
        return f"[Erreur synthese: {e}]", ia_synthese

# ============================================
# ROUTINE PRINCIPALE
# ============================================
def routine_quotidienne():
    print("="*55)
    print(f"BRIEFING QUOTIDIEN - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*55)

    m = charger_memoire()
    print(f"Memoire: {sum(len(m[k]) for k in m)} elements")
    ias = [n for n in ["perplexity","gemini","claude","chatgpt"] if disponible(n)]
    print(f"IA: {', '.join(ias)}")
    print("")

    print("[1/3] Analyse du marche...")
    analyses = analyser_marche()
    if not analyses:
        print("ERREUR: aucune donnee recuperee. Verifie les cles API.")
        return

    print("\n[2/3] Synthese du briefing...")
    briefing, modele = generer_briefing(analyses)

    print("\n[3/3] Sauvegarde + notification...")
    sauver_briefing(briefing)
    # Apprend le contexte du jour
    ajouter("apprentissages", f"Briefing {datetime.now().strftime('%d/%m')}: " + briefing[:200])
    # Notifie l'utilisateur (si IFTTT configure)
    notify_ifft("Briefing quotidien", briefing)

    print("\n" + "="*55)
    print("BRIEFING DU JOUR:")
    print("="*55)
    print(briefing)
    print("="*55)
    print(f"\nBriefing sauvegarde dans briefings.json")

if __name__ == "__main__":
    if "--voir" in sys.argv:
        briefings = charger_briefings()
        if not briefings:
            print("Aucun briefing enregistre pour le moment.")
        else:
            dernier = briefings[-1]
            print(f"\nDernier briefing ({dernier['date']}):\n")
            print("="*55)
            print(dernier["contenu"])
            print("="*55)
    else:
        routine_quotidienne()
