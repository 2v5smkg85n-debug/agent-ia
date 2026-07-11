#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode chat interactif.
Parle a ton agent en direct: tu poses une question, il repond.
Il se souvient de la conversation et apprend au fil de l'echange.

Usage:
    python chat.py
"""
import os
import sys
import json
import time
from datetime import datetime

from agent import (
    agent, charger_memoire, sauver_memoire, ajouter,
    instruction_memoire, charger_lecons, disponible, notify_ifft
)

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_CONVERSATIONS = os.path.join(DOSSIER, "conversations.json")

# ============================================
# SAUVEGARDE DES CONVERSATIONS
# ============================================
def charger_conversations():
    if os.path.exists(FICHIER_CONVERSATIONS):
        try:
            with open(FICHIER_CONVERSATIONS, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def sauver_conversation(conversation):
    conversations = charger_conversations()
    conversations.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": conversation
    })
    conversations = conversations[-20:]  # garde les 20 dernieres conversations
    with open(FICHIER_CONVERSATIONS, "w") as f:
        json.dump(conversations, f, ensure_ascii=False, indent=2)

# ============================================
# COMMANDES SPECIALES
# ============================================
def aide():
    print("""
COMMANDES DISPONIBLES:
  /memoire     - Affiche ce que l'agent sait de toi
  /lecons      - Affiche les lecons apprises
  /reset       - Reinitialise la memoire (nouveau depart)
  /save        - Sauvegarde la conversation
  /aide        - Cette aide
  /quit        - Quitter
""")

def afficher_memoire():
    m = charger_memoire()
    print("\n" + "="*50)
    print("MEMOIRE DE L'AGENT")
    print("="*50)
    for cat in ["profil","interets","objectifs","preferences","apprentissages"]:
        items = m.get(cat, [])
        if items:
            print(f"\n{cat.upper()}:")
            for item in items[-5:]:
                txt = item["contenu"] if isinstance(item, dict) else item
                print(f"  - {txt[:150]}")
    print("="*50 + "\n")

def afficher_lecons():
    from agent import charger_lecons
    lecons = charger_lecons()
    print("\n" + "="*50)
    print(f"LECONS APPRISES ({len(lecons)})")
    print("="*50)
    for l in lecons[-10:]:
        print(f"  - {l.get('contenu','')[:150]}")
    print("="*50 + "\n")

# ============================================
# BOUCLE PRINCIPALE
# ============================================
def chat():
    print("="*55)
    print(f"CHAT IA - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*55)
    m = charger_memoire()
    total = sum(len(m.get(k,[])) for k in m)
    from agent import charger_lecons
    lecons = charger_lecons()
    print(f"Memoire: {total} elements | Lecons: {len(lecons)}")
    ias = [n for n in ["perplexity","gemini","claude","chatgpt"] if disponible(n)]
    print(f"IA disponibles: {', '.join(ias) if ias else 'AUCUNE'}")
    print("")
    print("Tape ta question. Commandes: /aide /memoire /lecons /save /quit")
    print("-"*55)

    conversation = []
    nb_messages = 0

    while True:
        try:
            question = input("\nToi> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nFermeture du chat.")
            break

        if not question:
            continue

        # Commandes speciales
        if question.lower() in ["/quit", "/exit", "/q"]:
            print("Fermeture du chat. Au revoir!")
            break
        elif question.lower() == "/aide":
            aide()
            continue
        elif question.lower() == "/memoire":
            afficher_memoire()
            continue
        elif question.lower() == "/lecons":
            afficher_lecons()
            continue
        elif question.lower() == "/save":
            if conversation:
                sauver_conversation(conversation)
                print("Conversation sauvegardee dans conversations.json")
            else:
                print("Rien a sauvegarder.")
            continue
        elif question.lower() == "/reset":
            sauver_memoire({"profil":[],"interets":[],"objectifs":[],"apprentissages":[],"preferences":[]})
            print("Memoire reinitialisee.")
            continue

        # Appel a l'agent
        print("Agent> ", end="", flush=True)
        try:
            t = time.time()
            res = agent(question, reflechir=True)
            duree = time.time() - t
            print(f"\r[{res['mode']}] ({int(duree)}s)")
            print(res["final"])
            conversation.append({"role":"user","content":question})
            conversation.append({"role":"agent","content":res["final"],"mode":res["mode"]})
            nb_messages += 1
            if res.get("extrait"):
                print("  (memoire mise a jour)")
        except KeyboardInterrupt:
            print("\n(Interrompu. Tu peux reposer ta question.)")
            continue
        except Exception as e:
            print(f"\nErreur: {e}")

    # Sauvegarde auto a la sortie
    if conversation:
        sauver_conversation(conversation)
        print(f"\nConversation sauvegardee ({nb_messages} echanges).")

if __name__ == "__main__":
    chat()
