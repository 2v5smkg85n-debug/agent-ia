#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM ALERTES — module d'envoi de messages push vers iPhone.
Lit TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID depuis .env.

Usage:
    from telegram_alerte import envoyer, tester
    envoyer("Trade ouvert: BTC ACHAT 1000€")
    tester()  # message test
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not TOKEN:
    print("ATTENTION: TELEGRAM_BOT_TOKEN absent du .env")
if not CHAT_ID:
    print("ATTENTION: TELEGRAM_CHAT_ID absent du .env")

URL = f"https://api.telegram.org/bot{TOKEN}"


def envoyer(texte, parse_mode=None):
    """Envoie un message Telegram. Retourne True si succès."""
    if not TOKEN or not CHAT_ID:
        return False
    try:
        r = requests.post(
            f"{URL}/sendMessage",
            data={"chat_id": CHAT_ID, "text": texte, "parse_mode": parse_mode},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"Telegram erreur: {e}")
        return False


def tester():
    """Envoie un message test pour vérifier la configuration."""
    if not TOKEN or not CHAT_ID:
        print("ERREUR: configure TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans .env")
        print("  1. @BotFather sur Telegram -> /newbot -> copie le token")
        print("  2. Envoie un message au bot")
        print("  3. Récupère ton chat_id: curl https://api.telegram.org/bot<TOKEN>/getUpdates")
        return False
    ok = envoyer("🤖 Bot Telegram agent-ia connecté.\n\nTu recevras les alertes:\n- Trade ouvert\n- Trade fermé (+/- gain)\n- Service down/recover\n- Capital quotidien")
    if ok:
        print("OK: message test envoyé à Telegram.")
    else:
        print("ERREUR d'envoi. Vérifie le token et le chat_id.")
    return ok


if __name__ == "__main__":
    tester()
