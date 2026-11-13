#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMUN — utilitaires partagés par les outils de revenus hors trading.

- lecture du .env de ~/agent-ia (même fichier que le bot : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- envoi Telegram sans dépendance (urllib), découpage automatique des longs messages
- journal, JSONL, horodatage Paris
Compatible Python 3.10 (aucune dépendance externe).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)  # ~/agent-ia
DONNEES = os.path.join(ICI, "donnees")
os.makedirs(DONNEES, exist_ok=True)

_ENV = {}


def charger_env(chemin=None):
    """Lit le .env (celui de ~/agent-ia par défaut) sans python-dotenv."""
    global _ENV
    chemin = chemin or os.path.join(RACINE, ".env")
    env = {}
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                cle, val = ligne.split("=", 1)
                env[cle.strip()] = val.strip().strip('"').strip("'")
    _ENV = env
    return env


def env(cle, defaut=None):
    """Variable d'environnement système d'abord, puis .env, puis défaut."""
    if not _ENV:
        charger_env()
    return os.environ.get(cle, _ENV.get(cle, defaut))


def maintenant():
    """Heure de Paris (UTC+1 / UTC+2 selon l'heure d'été, calcul simple)."""
    utc = datetime.now(timezone.utc)
    # heure d'été : dernier dimanche de mars -> dernier dimanche d'octobre
    annee = utc.year
    def dernier_dimanche(mois):
        d = datetime(annee, mois + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    ete = dernier_dimanche(3).replace(hour=1) <= utc < dernier_dimanche(10).replace(hour=1)
    return utc + timedelta(hours=2 if ete else 1)


def horodatage():
    return maintenant().strftime("%Y-%m-%d %H:%M:%S")


def log(msg, fichier=None):
    ligne = f"[{horodatage()}] {msg}"
    print(ligne, flush=True)
    if fichier:
        try:
            with open(fichier, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
        except Exception:
            pass


def lire_jsonl(chemin):
    if not os.path.exists(chemin):
        return []
    out = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                try:
                    out.append(json.loads(ligne))
                except Exception:
                    continue
    return out


def ajouter_jsonl(chemin, obj):
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire_json(chemin, obj):
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, chemin)


def http_get(url, timeout=20, headers=None):
    """GET simple, retourne (code, texte). Jamais d'exception."""
    h = {"User-Agent": "Mozilla/5.0 (compatible; agent-ia-revenus/1.0)"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def http_post_json(url, payload, timeout=30, headers=None):
    h = {"Content-Type": "application/json", "User-Agent": "agent-ia-revenus/1.0"}
    if headers:
        h.update(headers)
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def telegram(texte, chat_id=None, token=None, silencieux=False):
    """Envoie un message Telegram (découpé si > 3 900 caractères). Retourne True/False."""
    token = token or env("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or env("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id or env("REVENUS_TELEGRAM", "1") == "0":
        return False
    ok = True
    morceaux = [texte[i:i + 3900] for i in range(0, len(texte), 3900)] or [""]
    for m in morceaux:
        code, _ = http_post_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": m, "disable_notification": silencieux,
             "disable_web_page_preview": True},
            timeout=15,
        )
        ok = ok and code == 200
    return ok


def ollama(prompt, modele=None, timeout=60, num_predict=300):
    """Demande à Ollama local (si présent). Retourne le texte ou '' si indisponible."""
    if env("REVENUS_OLLAMA", "1") == "0":
        return ""
    modele = modele or env("OLLAMA_MODEL", "qwen2.5:3b")
    code, corps = http_post_json(
        "http://localhost:11434/api/generate",
        {"model": modele, "prompt": prompt, "stream": False,
         "options": {"num_predict": num_predict, "temperature": 0.2}},
        timeout=timeout,
    )
    if code != 200:
        return ""
    try:
        return json.loads(corps).get("response", "").strip()
    except Exception:
        return ""


def euros(x):
    try:
        return f"{x:,.0f} €".replace(",", " ")
    except Exception:
        return str(x)


if __name__ == "__main__":
    charger_env()
    print("Heure Paris :", horodatage())
    print("Telegram configuré :", bool(env("TELEGRAM_BOT_TOKEN")) and bool(env("TELEGRAM_CHAT_ID")))
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Envoi test :", telegram("Test outils revenus — " + horodatage()))


def battement(cle):
    """Signale « je viens de tourner » au veilleur (fichier partagé, pas de réseau)."""
    chemin = os.path.join(DONNEES, "veilleur_battements.json")
    b = lire_json(chemin, {})
    b[cle] = time.time()
    try:
        ecrire_json(chemin, b)
    except Exception:
        pass
