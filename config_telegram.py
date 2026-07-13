#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFIG TELEGRAM — configure le bot en interactif.
1. Demande le token (depuis @BotFather)
2. Auto-détecte le chat_id (via getUpdates)
3. Écrit dans .env
4. Envoie un message test

Prérequis: avoir envoyé au moins 1 message au bot.
"""
import os
import sys
import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(DOSSIER, ".env")


def lire_env_actuel():
    lignes = {}
    if os.path.exists(ENV):
        with open(ENV, "r") as f:
            for ligne in f:
                if "=" in ligne and not ligne.strip().startswith("#"):
                    k, _, v = ligne.strip().partition("=")
                    lignes[k] = v
    return lignes


def ecrire_env(dico):
    # Lit le .env actuel, remplace/ajoute les clés, garde le reste
    existant = {}
    contenu = ""
    if os.path.exists(ENV):
        with open(ENV, "r") as f:
            contenu = f.read()
    lignes = contenu.splitlines()
    vues = set()
    nouvelles = []
    for ligne in lignes:
        if "=" in ligne and not ligne.strip().startswith("#"):
            k = ligne.split("=", 1)[0].strip()
            if k in dico:
                nouvelles.append(f"{k}={dico[k]}")
                vues.add(k)
            else:
                nouvelles.append(ligne)
        else:
            nouvelles.append(ligne)
    for k, v in dico.items():
        if k not in vues:
            nouvelles.append(f"{k}={v}")
    with open(ENV, "w") as f:
        f.write("\n".join(nouvelles) + "\n")


def main():
    print("=" * 50)
    print("CONFIGURATION TELEGRAM")
    print("=" * 50)
    print()
    token = input("Colle ton TELEGRAM_BOT_TOKEN: ").strip()
    if not token or ":" not in token:
        print("Token invalide. Il doit contenir ':' (format 123456:ABC...)")
        return

    print("\nDétection du chat_id...")
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates", timeout=15
        )
        data = r.json()
    except Exception as e:
        print(f"Erreur réseau: {e}")
        return

    if not data.get("ok"):
        print(f"Erreur API Telegram: {data}")
        return

    chat_id = None
    nom = None
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
        if msg and msg.get("chat"):
            chat_id = msg["chat"]["id"]
            nom = msg["chat"].get("first_name") or msg["chat"].get("title", "")
            break

    if chat_id is None:
        print("Aucun message trouvé.")
        print("Envoie n'importe quel message à ton bot sur Telegram, puis relance ce script.")
        return

    print(f"\n✓ Chat ID détecté: {chat_id}" + (f" ({nom})" if nom else ""))

    # Écrit dans .env
    ecrire_env({
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": str(chat_id),
    })
    print("✓ Configuré dans .env")

    # Test
    print("\nEnvoi du message test...")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": "🤖 Agent IA Trading connecté.\n\nTu recevras: trades ouverts/fermés, alertes service, digest quotidien."},
            timeout=15,
        )
        if r.status_code == 200:
            print("✓ Message test envoyé ! Vérifie Telegram.")
        else:
            print(f"✗ Erreur envoi: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"✗ Erreur: {e}")

    print("\nProchaine étape: bash setup_telegram_service.sh")


if __name__ == "__main__":
    main()
