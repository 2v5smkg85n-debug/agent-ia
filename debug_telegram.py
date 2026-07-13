#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug Telegram getUpdates — affiche la réponse brute de l'API."""
import requests

t = input("Token: ").strip()
print(f"\nToken reçu: {t[:12]}...{t[-4:]} (longueur {len(t)})")
print(f"Contient ':' ? {':' in t}")
print()

try:
    r = requests.get(f"https://api.telegram.org/bot{t}/getUpdates", timeout=15)
    print(f"STATUS: {r.status_code}")
    print(f"RÉPONSE: {r.text[:2000]}")
except Exception as e:
    print(f"Erreur réseau: {e}")
