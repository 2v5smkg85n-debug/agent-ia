#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VEILLEUR — supervision des agents IA et automatisations (n8n, Make, chatbots, scripts) pour
plusieurs clients, avec alerte Telegram et rapport quotidien. Détecte les PANNES SILENCIEUSES :
l'agent répond « 200 OK » mais dit n'importe quoi, le workflow ne tourne plus, le fichier n'est
plus mis à jour, le service est tombé.

Contrôles disponibles (clients.json) :
  http       : url, methode (GET/POST), corps (JSON), code attendu, delai_max_s, attendu [mots],
               interdit [mots], question_semantique (jugée par Ollama local : OUI/NON)
  battement  : le workflow du client appelle GET http://VPS:8791/battement/<cle>?token=... à chaque
               exécution ; alerte si plus de battement depuis intervalle_max_min
  fichier    : chemin, age_max_min (fraîcheur d'un export, d'un log, d'une base)
  systemd    : unite (active ou non)
  telegram   : token du bot du client → getMe répond (le bot existe et répond)

Usage :
  python3 revenus/veilleur/veilleur.py             # une passe de contrôle (timer toutes les 5 min)
  python3 revenus/veilleur/veilleur.py test        # une passe, affichage, sans Telegram
  python3 revenus/veilleur/veilleur.py serveur     # reçoit les battements + page /etat/<client>?token=
  python3 revenus/veilleur/veilleur.py rapport     # rapport quotidien par client (disponibilité, incidents)
  python3 revenus/veilleur/veilleur.py init        # crée clients.json à partir de l'exemple

Réglages (.env) : VEILLEUR_TOKEN (battements/état), VEILLEUR_PORT=8791, VEILLEUR_ECHECS=2
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commun  # noqa: E402

ICI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ICI, "clients.json")
EXEMPLE = os.path.join(ICI, "clients.exemple.json")
ETAT = os.path.join(commun.DONNEES, "veilleur_etat.json")
HISTO = os.path.join(commun.DONNEES, "veilleur_histo.jsonl")
BATTEMENTS = os.path.join(commun.DONNEES, "veilleur_battements.json")
JOURNAL = os.path.join(commun.DONNEES, "veilleur.log")


def charger_config():
    cfg = commun.lire_json(CONFIG, None)
    if cfg is None:
        cfg = commun.lire_json(EXEMPLE, {"clients": []})
    return cfg


def _expandre(obj):
    """Remplace ${NOM} par la valeur du .env (ex. ${DASHBOARD_TOKEN}) dans toute la config."""
    import re
    if isinstance(obj, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: commun.env(m.group(1), ""), obj)
    if isinstance(obj, list):
        return [_expandre(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expandre(v) for k, v in obj.items()}
    return obj


# ------------------------------------------------------------------ contrôles
def ctrl_http(c):
    debut = time.time()
    if (c.get("methode", "GET")).upper() == "POST":
        code, corps = commun.http_post_json(c["url"], c.get("corps", {}), timeout=c.get("delai_max_s", 15) + 5,
                                            headers=c.get("entetes"))
    else:
        code, corps = commun.http_get(c["url"], timeout=c.get("delai_max_s", 15) + 5, headers=c.get("entetes"))
    duree = time.time() - debut
    if code != c.get("code", 200):
        return False, f"HTTP {code or 'injoignable'}"
    if duree > c.get("delai_max_s", 15):
        return False, f"trop lent : {duree:.1f}s"
    bas = corps.lower()
    for m in c.get("attendu", []):
        if m.lower() not in bas:
            return False, f"« {m} » absent de la réponse (panne silencieuse ?)"
    for m in c.get("interdit", []):
        if m.lower() in bas:
            return False, f"« {m} » présent dans la réponse"
    q = c.get("question_semantique")
    if q:
        avis = commun.ollama(
            f"Réponds uniquement par OUI ou NON.\nQuestion : {q}\nRéponse de l'agent à évaluer :\n{corps[:1500]}\nRéponse (OUI/NON) :",
            num_predict=5, timeout=90)
        if avis and avis.strip().upper().startswith("NON"):
            return False, f"jugement sémantique : NON à « {q} »"
    return True, f"OK en {duree:.1f}s"


def ctrl_battement(c):
    b = commun.lire_json(BATTEMENTS, {})
    t = b.get(c["cle"])
    if not t:
        return False, "aucun battement reçu encore"
    age = (time.time() - t) / 60
    if age > c.get("intervalle_max_min", 1440):
        return False, f"dernier battement il y a {age:.0f} min (max {c.get('intervalle_max_min', 1440)})"
    return True, f"dernier battement il y a {age:.0f} min"


def ctrl_fichier(c):
    if not os.path.exists(c["chemin"]):
        return False, "fichier absent"
    age = (time.time() - os.path.getmtime(c["chemin"])) / 60
    if age > c.get("age_max_min", 60):
        return False, f"pas mis à jour depuis {age:.0f} min"
    return True, f"mis à jour il y a {age:.0f} min"


def ctrl_systemd(c):
    try:
        r = subprocess.run(["systemctl", "is-active", c["unite"]], capture_output=True, text=True, timeout=10)
        etat = r.stdout.strip()
    except Exception as e:
        return False, str(e)
    return etat == "active", etat


def ctrl_telegram(c):
    code, corps = commun.http_get(f"https://api.telegram.org/bot{c['token']}/getMe", timeout=15)
    if code != 200:
        return False, f"getMe HTTP {code}"
    return True, "bot joignable"


CONTROLES = {"http": ctrl_http, "battement": ctrl_battement, "fichier": ctrl_fichier,
             "systemd": ctrl_systemd, "telegram": ctrl_telegram}


# ------------------------------------------------------------------ moteur
def passe(envoyer=True):
    cfg = charger_config()
    etat = commun.lire_json(ETAT, {})
    seuil = int(commun.env("VEILLEUR_ECHECS", "2"))
    resume = []
    for client in cfg.get("clients", []):
        chat = client.get("telegram_chat_id") or None
        for c in client.get("controles", []):
            cle = f"{client['nom']}::{c['nom']}"
            fn = CONTROLES.get(c.get("type"))
            if not fn:
                continue
            try:
                ok, detail = fn(_expandre(c))
            except Exception as e:
                ok, detail = False, f"erreur contrôle : {e}"
            e = etat.get(cle, {"echecs": 0, "statut": "OK", "depuis": commun.horodatage()})
            commun.ajouter_jsonl(HISTO, {"t": int(time.time()), "client": client["nom"], "controle": c["nom"],
                                         "ok": ok, "detail": detail})
            if ok:
                if e["statut"] == "PANNE":
                    duree = (time.time() - e.get("panne_t", time.time())) / 60
                    msg = f"✅ {client['nom']} — {c['nom']} rétabli ({detail}) après {duree:.0f} min"
                    commun.log(msg, JOURNAL)
                    if envoyer:
                        commun.telegram(msg)
                        if chat:
                            commun.telegram(msg, chat_id=chat)
                e = {"echecs": 0, "statut": "OK", "depuis": commun.horodatage(), "detail": detail}
            else:
                e["echecs"] = e.get("echecs", 0) + 1
                e["detail"] = detail
                if e["echecs"] >= seuil and e["statut"] != "PANNE":
                    e["statut"], e["panne_t"] = "PANNE", time.time()
                    msg = f"🚨 {client['nom']} — {c['nom']} EN PANNE : {detail}"
                    commun.log(msg, JOURNAL)
                    if envoyer:
                        commun.telegram(msg)
                        if chat:
                            commun.telegram(msg, chat_id=chat)
            etat[cle] = e
            resume.append((client["nom"], c["nom"], "OK" if ok else "KO", detail))
    commun.ecrire_json(ETAT, etat)
    return resume


def rapport(envoyer=True, heures=24):
    cfg = charger_config()
    depuis = time.time() - heures * 3600
    histo = [h for h in commun.lire_jsonl(HISTO) if h["t"] >= depuis]
    textes = []
    for client in cfg.get("clients", []):
        lignes = [f"📋 Rapport {heures} h — {client['nom']} ({commun.maintenant().strftime('%d/%m %H:%M')})"]
        for c in client.get("controles", []):
            h = [x for x in histo if x["client"] == client["nom"] and x["controle"] == c["nom"]]
            if not h:
                lignes.append(f"• {c['nom']} : aucune mesure")
                continue
            dispo = 100 * sum(1 for x in h if x["ok"]) / len(h)
            incidents = sum(1 for i in range(1, len(h)) if h[i - 1]["ok"] and not h[i]["ok"])
            lignes.append(f"• {c['nom']} : {dispo:.1f} % disponible, {incidents} incident(s), {len(h)} contrôles")
        texte = "\n".join(lignes)
        textes.append(texte)
        if envoyer:
            commun.telegram(texte, silencieux=True)
            if client.get("telegram_chat_id"):
                commun.telegram(texte, chat_id=client["telegram_chat_id"], silencieux=True)
    return "\n\n".join(textes)


def serveur(port=None):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs
    port = port or int(commun.env("VEILLEUR_PORT", "8791"))
    token = commun.env("VEILLEUR_TOKEN", "")

    class H(BaseHTTPRequestHandler):
        def _rep(self, code, obj):
            corps = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if token and q.get("token", [""])[0] != token:
                return self._rep(401, {"erreur": "token"})
            parts = u.path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "battement":
                b = commun.lire_json(BATTEMENTS, {})
                b[parts[1]] = time.time()
                commun.ecrire_json(BATTEMENTS, b)
                return self._rep(200, {"ok": True, "cle": parts[1]})
            if len(parts) == 2 and parts[0] == "etat":
                etat = commun.lire_json(ETAT, {})
                return self._rep(200, {k.split("::", 1)[1]: v for k, v in etat.items() if k.startswith(parts[1] + "::")})
            self._rep(404, {"erreur": "route"})

        do_POST = do_GET

        def log_message(self, *a):
            pass

    commun.log(f"veilleur serveur sur {port} (token {'actif' if token else 'ABSENT : mettre VEILLEUR_TOKEN dans .env'})", JOURNAL)
    HTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "passe"
    if cmd == "passe":
        r = passe(envoyer=True)
        print(f"{sum(1 for x in r if x[2] == 'OK')}/{len(r)} contrôles OK")
    elif cmd == "test":
        for cl, c, s, d in passe(envoyer=False):
            print(f"{s}  {cl} — {c} : {d}")
    elif cmd == "rapport":
        print(rapport(envoyer="test" not in sys.argv))
    elif cmd == "serveur":
        serveur(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "init":
        if os.path.exists(CONFIG):
            print("clients.json existe déjà")
        else:
            shutil.copy(EXEMPLE, CONFIG)
            print(f"créé : {CONFIG} — édite-le avec nano")
    else:
        print(__doc__)
