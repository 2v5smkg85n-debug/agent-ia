#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODE OMBRE — faire tourner les règles anti-fraude d'un marchand « à blanc » et les juger.

Principe (le même que l'entonnoir du bot) : une règle en mode « ombre » dit ce qu'elle AURAIT
fait sans bloquer la commande. Quand on connaît le sort réel de la commande (livrée sans litige,
ou chargeback), on juge la règle. Au bout de quelques semaines, on sait, chiffres à l'appui,
quelles règles protègent et lesquelles coûtent des ventes.

Deux façons de l'utiliser :

1) En bibliothèque Python chez le marchand ou dans un script :
    from regles_ombre import Ombre
    o = Ombre("boutique_x")
    o.regle("montant_sup_300", lambda c: c.get("montant", 0) > 300, mode="ombre")
    o.regle("email_jetable", lambda c: c.get("email", "").split("@")[-1] in {"yopmail.com"}, mode="actif")
    verdict = o.evaluer({"id": "C1", "montant": 420, "email": "a@b.fr", "client_connu": 1})
    # verdict = {"bloquer": False, "actives": [], "ombre": ["montant_sup_300"]}
    ... 60 jours plus tard :
    o.juger("C1", "ok")        # ou "fraude"
    print(o.rapport_texte())

2) En serveur webhook sur le VPS (le marchand branche un webhook « commande créée » et
   « litige/chargeback » depuis Shopify / PrestaShop / WooCommerce / Stripe) :
    python3 revenus/audit_regles/regles_ombre.py serveur 8790
    POST /evaluer/<client>   {"id": "...", "montant": 420, ..., "regles": {"montant_sup_300": true, ...}}
    POST /juger/<client>     {"id": "...", "resultat": "ok"|"fraude"}
    GET  /rapport/<client>
   En-tête : X-Token: <OMBRE_TOKEN du .env>. Si le marchand envoie déjà ses règles déclenchées
   (champ "regles"), aucune règle Python n'est nécessaire : on journalise et on juge.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commun  # noqa: E402


class Ombre:
    def __init__(self, client, dossier=None):
        self.client = "".join(ch for ch in client if ch.isalnum() or ch in "-_") or "client"
        self.dossier = dossier or commun.DONNEES
        self.journal = os.path.join(self.dossier, f"ombre_{self.client}.jsonl")
        self.regles = {}  # nom -> (fonction, mode)

    def regle(self, nom, fonction, mode="ombre"):
        self.regles[nom] = (fonction, mode)

    def evaluer(self, commande, regles_declenchees=None):
        """Évalue une commande. Retourne {"bloquer", "actives", "ombre"} et journalise."""
        actives, ombre = [], []
        for nom, (fn, mode) in self.regles.items():
            try:
                touche = bool(fn(commande))
            except Exception:
                touche = False
            if touche:
                (actives if mode == "actif" else ombre).append(nom)
        # règles déjà calculées côté marchand : {"nom": true/false} ou liste de noms
        if regles_declenchees:
            noms = (regles_declenchees if isinstance(regles_declenchees, list)
                    else [k for k, v in regles_declenchees.items() if v])
            for n in noms:
                if n not in actives and n not in ombre:
                    (actives if commande.get("decision") in ("refuse", "refused", "declined")
                     else ombre).append(n)
        verdict = {"bloquer": bool(actives), "actives": actives, "ombre": ombre}
        commun.ajouter_jsonl(self.journal, {
            "type": "eval", "id": str(commande.get("id", "")), "date": commun.horodatage(),
            "montant": float(commande.get("montant", 0) or 0),
            "client_connu": bool(commande.get("client_connu", False)),
            "actives": actives, "ombre": ombre,
        })
        return verdict

    def juger(self, id_commande, resultat):
        """resultat : 'ok' (livrée, pas de litige) ou 'fraude' (chargeback / impayé)."""
        resultat = "fraude" if str(resultat).lower() in ("fraude", "fraud", "chargeback", "litige", "1", "true") else "ok"
        commun.ajouter_jsonl(self.journal, {"type": "juge", "id": str(id_commande),
                                            "date": commun.horodatage(), "resultat": resultat})
        return resultat

    def rapport(self, cout_chargeback=20.0):
        evals, juges = {}, {}
        for e in commun.lire_jsonl(self.journal):
            if e.get("type") == "eval":
                evals[e["id"]] = e
            elif e.get("type") == "juge":
                juges[e["id"]] = e["resultat"]
        stats = defaultdict(lambda: {"declenchee": 0, "jugees": 0, "fraude": 0, "montant_legit": 0.0,
                                     "montant_fraude": 0.0, "en_attente": 0, "mode": "ombre"})
        for i, e in evals.items():
            for nom in e["ombre"] + e["actives"]:
                s = stats[nom]
                s["mode"] = "actif" if nom in e["actives"] else "ombre"
                s["declenchee"] += 1
                if i in juges:
                    s["jugees"] += 1
                    if juges[i] == "fraude":
                        s["fraude"] += 1
                        s["montant_fraude"] += e["montant"]
                    else:
                        s["montant_legit"] += e["montant"]
                else:
                    s["en_attente"] += 1
        lignes = []
        for nom, s in stats.items():
            precision = s["fraude"] / s["jugees"] if s["jugees"] else None
            cout_si_bloque = s["montant_legit"]                      # ventes qu'on aurait perdues
            gain_si_bloque = s["montant_fraude"] + cout_chargeback * s["fraude"]
            if s["jugees"] < 20:
                reco = f"ATTENDRE ({s['jugees']}/20 jugements)"
            elif cout_si_bloque > gain_si_bloque * 1.5:
                reco = "NE PAS BLOQUER — coûte plus qu'elle ne protège" if s["mode"] == "ombre" else "DÉSACTIVER — coûte plus qu'elle ne protège"
            elif gain_si_bloque > cout_si_bloque * 1.5:
                reco = "ACTIVER — protège nettement" if s["mode"] == "ombre" else "GARDER"
            else:
                reco = "NEUTRE — remplacer par une revue manuelle"
            lignes.append({"regle": nom, "mode": s["mode"], "declenchee": s["declenchee"], "jugees": s["jugees"],
                           "en_attente": s["en_attente"],
                           "precision": None if precision is None else round(precision, 3),
                           "ventes_si_bloquee": round(cout_si_bloque, 2),
                           "fraude_si_bloquee": round(gain_si_bloque, 2), "recommandation": reco})
        lignes.sort(key=lambda x: -(x["ventes_si_bloquee"] - x["fraude_si_bloquee"]))
        return {"client": self.client, "commandes": len(evals), "jugees": len(juges), "regles": lignes}

    def rapport_texte(self):
        r = self.rapport()
        l = [f"Mode ombre — {r['client']} : {r['commandes']} commandes, {r['jugees']} jugées"]
        for x in r["regles"]:
            p = "?" if x["precision"] is None else f"{x['precision']*100:.0f} %"
            l.append(f"- {x['regle']} [{x['mode']}] déclenchée {x['declenchee']}×, jugée {x['jugees']}×, précision {p}, "
                     f"ventes {commun.euros(x['ventes_si_bloquee'])} vs fraude {commun.euros(x['fraude_si_bloquee'])} → {x['recommandation']}")
        return "\n".join(l)


# ------------------------------------------------------------------ serveur webhook
def serveur(port=8790):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    token = commun.env("OMBRE_TOKEN", "")

    class H(BaseHTTPRequestHandler):
        def _rep(self, code, obj):
            corps = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def _auth(self):
            if token and self.headers.get("X-Token", "") != token:
                self._rep(401, {"erreur": "token"})
                return False
            return True

        def do_GET(self):
            if not self._auth():
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "rapport":
                return self._rep(200, Ombre(parts[1]).rapport())
            self._rep(404, {"erreur": "route"})

        def do_POST(self):
            if not self._auth():
                return
            parts = self.path.strip("/").split("/")
            n = int(self.headers.get("Content-Length", "0") or 0)
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:
                return self._rep(400, {"erreur": "json"})
            if len(parts) != 2:
                return self._rep(404, {"erreur": "route"})
            o = Ombre(parts[1])
            if parts[0] == "evaluer":
                return self._rep(200, o.evaluer(data, data.get("regles")))
            if parts[0] == "juger":
                return self._rep(200, {"resultat": o.juger(data.get("id"), data.get("resultat", "ok"))})
            self._rep(404, {"erreur": "route"})

        def log_message(self, *a):
            commun.log(f"ombre {self.address_string()} {a[0] % a[1:] if len(a) > 1 else a[0]}",
                       os.path.join(commun.DONNEES, "ombre.log"))

    commun.log(f"serveur mode ombre sur le port {port} (token {'actif' if token else 'ABSENT : mettre OMBRE_TOKEN dans .env'})")
    HTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "serveur":
        serveur(int(sys.argv[2]) if len(sys.argv) > 2 else 8790)
    elif cmd == "rapport" and len(sys.argv) > 2:
        print(Ombre(sys.argv[2]).rapport_texte())
    elif cmd == "juger" and len(sys.argv) > 4:
        print(Ombre(sys.argv[2]).juger(sys.argv[3], sys.argv[4]))
    elif cmd == "demo":
        import random
        rnd = random.Random(3)
        o = Ombre("demo")
        if os.path.exists(o.journal):
            os.remove(o.journal)
        o.regle("montant_sup_300", lambda c: c["montant"] > 300, mode="ombre")
        o.regle("email_jetable", lambda c: c["email"].endswith("@yopmail.com"), mode="ombre")
        for i in range(300):
            c = {"id": f"D{i}", "montant": round(rnd.lognormvariate(4.5, 0.8), 2),
                 "email": ("x@yopmail.com" if rnd.random() < 0.05 else "x@gmail.com"), "client_connu": rnd.random() < 0.3}
            o.evaluer(c)
            fraude = rnd.random() < (0.7 if c["email"].endswith("yopmail.com") else 0.02)
            o.juger(c["id"], "fraude" if fraude else "ok")
        print(o.rapport_texte())
    else:
        print(__doc__)
