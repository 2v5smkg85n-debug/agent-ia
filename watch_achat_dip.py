#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watch_achat_dip.py — Surveille paper_trading.log et Telegram a chaque ACHAT avec dip.

Démarrage: envoie un message de confirmation.
Boucle: every 45s, lit les nouvelles lignes du log. Si une ligne contient
'ACHAT' ET 'dip', envoie une alerte Telegram (anti-doublon par hash).
Survit en arrière-plan via nohup.
"""
import os, time, hashlib, sys
from dotenv import load_dotenv
import requests

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
LOG = "paper_trading.log"

if not TOKEN or not CHAT:
    print("ERREUR: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
    sys.exit(1)


def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"telegram err: {e}")
        return False


def h(line):
    return hashlib.md5(line.encode()).hexdigest()


# Demarre a la fin du log (alerte seulement sur les NOUVEAUX ACHAT+dip)
pos = os.path.getsize(LOG) if os.path.exists(LOG) else 0
sent = set()

print("watcher ACHAT+dip demarre", flush=True)
send("🤖 Watcher ACHAT+dip démarré.\nJe te préviendrai dès qu'un ACHAT avec dip "
     "apparaît dans paper_trading.log.\n(le gate dip-buying est actif)")

while True:
    try:
        size = os.path.getsize(LOG)
        if size < pos:
            pos = 0  # log rotate
        with open(LOG, encoding="utf-8", errors="ignore") as f:
            f.seek(pos)
            new = f.read()
            pos = f.tell()
        for line in new.splitlines():
            if "ACHAT" in line and "dip" in line:
                hh = h(line)
                if hh in sent:
                    continue
                sent.add(hh)
                # garde seulement les 50 derniers hash pour pas exploser la memoire
                if len(sent) > 50:
                    sent = set(list(sent)[-50:])
                msg = f"📈 <b>ACHAT avec dip détecté</b>\n\n<code>{line}</code>"
                send(msg)
                print(f"ALERTE: {line}", flush=True)
    except Exception as e:
        print(f"err: {e}", flush=True)
    time.sleep(45)
