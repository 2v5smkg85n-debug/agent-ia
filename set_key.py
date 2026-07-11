#!/usr/bin/env python3
"""Met a jour ANTHROPIC_API_KEY dans .env (saisie visible, paste-friendly iPhone)."""
import sys

print("Colle ta cle Claude ci-dessous (sk-ant-...), puis Entrée :")
key = input("> ").strip()

if not key:
    print("ERREUR: cle vide. Tu n'as rien colle. Relance le script et colle la cle.")
    sys.exit(1)

if not key.startswith("sk-ant-"):
    print(f"ATTENTION: la cle ne commence pas par 'sk-ant-' (recu: {key[:15]}...)")
    print("Verifie que tu as bien colle la cle API, pas autre chose.")
    sys.exit(1)

# Lire .env, remplacer ou ajouter la ligne
try:
    lines = open(".env").read().splitlines()
except FileNotFoundError:
    lines = []

found = False
out = []
for line in lines:
    if line.startswith("ANTHROPIC_API_KEY="):
        out.append(f"ANTHROPIC_API_KEY={key}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"ANTHROPIC_API_KEY={key}")

open(".env", "w").write("\n".join(out) + "\n")
print(f"OK cle mise a jour dans .env : {key[:14]}...{key[-4:]}")
print("Tu peux maintenant lancer: python test_claude.py")
