#!/usr/bin/env python3
"""Prospection automatisée — les 30 contacts de CONTACTS_30.md, 5 par jour.

Deux modes, choisis par le .env :
  PROSPECTION_AUTO=0 (défaut) : chaque matin le bot envoie sur Telegram les 5 messages du jour,
      déjà remplis (objet, destinataire, texte). Tu copies, tu colles dans Mail, tu envoies.
      Il note l'envoi dans prospection.csv et rappelle les relances dues (J+4).
  PROSPECTION_AUTO=1 : le bot envoie lui-même les mails via TON compte (SMTP Gmail/iCloud avec
      mot de passe d'application : SMTP_HOTE, SMTP_PORT, SMTP_UTILISATEUR, SMTP_MDP,
      SMTP_EXPEDITEUR). Les contacts « formulaire » (pas d'adresse) restent envoyés sur Telegram
      pour que tu les colles toi-même. Jamais plus de PROSPECTION_PAR_JOUR (5) par jour.
      Refus net si PROSPECTION_SIGNATURE n'est pas remplie (on n'envoie pas « [Prénom] »).

Commandes :
  python3 revenus/prospection.py matin          # ce que fait le timer : messages du jour + relances
  python3 revenus/prospection.py jour           # affiche / envoie sur Telegram les 5 du jour (sans SMTP)
  python3 revenus/prospection.py envoyer        # envoi SMTP des 5 du jour (si PROSPECTION_AUTO=1)
  python3 revenus/prospection.py relances       # relances dues
  python3 revenus/prospection.py reponse NOM "texte"   # relance NOM : marque la relance faite
  python3 revenus/prospection.py liste | stats | test | message NOM
"""
import csv
import json
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from commun import DONNEES, env, log, telegram  # noqa: E402

CSV = os.path.join(DONNEES, "prospection.csv")
CAMPAGNE = os.path.join(ICI, "campagne.json")
ENTETE = ["date", "groupe", "contact", "canal", "statut", "reponse", "relance"]
JOURNAL = os.path.join(DONNEES, "prospection.log")

CORPS = {
    "A": (
        "Pas seulement « le serveur répond » : le flux qui tourne mais produit du faux, l'agent IA "
        "qui répond à côté, le webhook muet depuis 3 h. Alerte Telegram en moins de 5 minutes, et un "
        "état écrit chaque mois que vous remettez à votre client.\n\n"
        "Mon propre système (plusieurs agents, 24 h/24) est supervisé comme ça depuis des mois ; "
        "c'est de là que vient l'outil.\n\n"
        "Je vous propose de brancher vos 10 premiers contrôles gratuitement pendant 30 jours, sans "
        "engagement ; ensuite 49 €/mois, résiliable. Vous le revendez à vos clients au prix que vous "
        "voulez.\n\n"
        "15 minutes cette semaine pour vous montrer un vrai rapport ?"
    ),
    "B": (
        "Je mesure ça sans toucher à votre boutique : vous m'envoyez un export anonymisé des commandes "
        "refusées ou « en vérification » des 90 derniers jours (numéro, montant, règle, pays, "
        "résultat), je vous rends une analyse écrite : quelles règles coûtent plus qu'elles ne "
        "protègent, combien, et quels réglages proposer. La première analyse est gratuite.\n\n"
        "Si vous appliquez les réglages, je suis payé uniquement sur le résultat : 20 % des ventes "
        "récupérées nettes, mesurées chaque mois. Rien récupéré, rien facturé.\n\n"
        "Qui s'occupe de la fraude et du paiement chez vous ? Je lui écris directement si vous préférez."
    ),
    "C1": (
        "Je propose un format que je ne vois pas dans vos programmes : « l'IA sans abonnement », une "
        "journée où les participants repartent avec un agent IA installé sur leur propre machine ou "
        "serveur, un flux automatisé (n8n) et la supervision qui prévient quand ça déraille. Pas de "
        "carte bancaire, pas de SaaS, leurs données restent chez eux.\n\n"
        "Je fais tourner mon propre système de cette façon 24 h/24 depuis des mois ; tout ce que je "
        "montre est en production.\n\n"
        "Je vous propose un atelier découverte d'une heure gratuit pour vos membres (sur place ou en "
        "visio). La journée complète est à 900 € HT pour 10 personnes, facturée à l'organisme ou aux "
        "participants.\n\n"
        "Qui monte la programmation chez vous ? Je peux envoyer le déroulé détaillé."
    ),
    "C3": (
        "Ce que je montre est en production, pas en démo ; je peux vous envoyer un rapport de "
        "supervision réel.\n\n"
        "Un créneau de 20 minutes pour voir si ça colle ?"
    ),
    "C2": (
        "Je propose de le faire à vos côtés, en gardant votre place : un webinaire d'une heure co-animé "
        "pour vos clients (gratuit), puis, pour ceux qui le veulent, une journée pratique « IA sans "
        "abonnement » à 900 € HT, ou un agent IA installé et supervisé.\n\n"
        "Pour vous, aucun coût ; si vous préférez une convention d'apport d'affaires, je propose 12 % "
        "des missions issues de vos clients, par écrit.\n\n"
        "Un créneau de 20 minutes pour voir si ça colle ?"
    ),
}

RELANCE = (
    "Bonjour,\n\nje me permets de remonter mon message du {date}. Si ce n'est pas le bon moment ou pas "
    "la bonne personne, un simple « non » me suffit et je ne reviendrai pas. Merci.\n\n{signature}"
)


def aujourd_hui():
    return date.today().isoformat()


def lire_csv():
    if not os.path.exists(CSV):
        return []
    with open(CSV, encoding="utf-8", newline="") as f:
        lignes = list(csv.reader(f, delimiter=";"))
    return [dict(zip(ENTETE, l + [""] * (7 - len(l)))) for l in lignes[1:] if l and l[0] != "date"]


def ecrire_csv(lignes):
    os.makedirs(DONNEES, exist_ok=True)
    with open(CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(ENTETE)
        for l in lignes:
            w.writerow([l.get(c, "") for c in ENTETE])


def noter_envoi(groupe, contact, canal, delai=4):
    lignes = lire_csv()
    lignes.append({"date": aujourd_hui(), "groupe": groupe, "contact": contact, "canal": canal,
                   "statut": "envoye", "reponse": "",
                   "relance": (date.today() + timedelta(days=delai)).isoformat()})
    ecrire_csv(lignes)


def deja_contactes():
    return {l["contact"].lower() for l in lire_csv()}


def charger_campagne():
    with open(CAMPAGNE, encoding="utf-8") as f:
        return json.load(f)["contacts"]


def signature():
    return env("PROSPECTION_SIGNATURE", "").strip()


def corps(c):
    sig = signature() or "[Prénom] — [ton mail]"
    return f"{c['salut']}\n\n{c['ouverture']}\n\n{CORPS[c['corps']]}\n\n{sig}"


def message_complet(c):
    dest = c.get("email") or f"formulaire : {c.get('formulaire', 'n.a.')}"
    return (f"[{c['id']}] {c['nom']} — {c.get('personne') or 'n.a.'}\n"
            f"À : {dest}\nObjet : {c['objet']}\n\n{corps(c)}")


def contacts_du_jour(n=None):
    n = n or int(env("PROSPECTION_PAR_JOUR", "5"))
    faits = deja_contactes()
    restants = [c for c in charger_campagne() if c["nom"].lower() not in faits]
    restants.sort(key=lambda c: (c["jour"], c["id"]))
    return restants[:n]


def smtp_pret():
    return all(env(k) for k in ("SMTP_HOTE", "SMTP_UTILISATEUR", "SMTP_MDP", "SMTP_EXPEDITEUR"))


def envoyer_mail(c, test=False):
    nom_exp, adr_exp = parseaddr(env("SMTP_EXPEDITEUR"))
    msg = EmailMessage()
    msg["From"] = formataddr((nom_exp, adr_exp)) if nom_exp else adr_exp
    msg["To"] = c["email"]
    msg["Subject"] = c["objet"]
    msg["Reply-To"] = env("SMTP_REPONDRE_A", adr_exp)
    msg.set_content(corps(c))
    if test:
        return True
    port = int(env("SMTP_PORT", "587"))
    with smtplib.SMTP(env("SMTP_HOTE"), port, timeout=30) as s:
        s.ehlo()
        if port != 465:
            s.starttls()
        s.login(env("SMTP_UTILISATEUR"), env("SMTP_MDP"))
        s.send_message(msg)
    return True


def cmd_jour(afficher=True):
    cibles = contacts_du_jour()
    if not cibles:
        telegram("Prospection : les 30 contacts sont tous envoyés. Reste les relances.")
        print("Campagne terminée.")
        return cibles
    telegram(f"Prospection — {len(cibles)} message(s) à envoyer aujourd'hui. Un message Telegram par "
             f"contact : copie le texte, colle-le dans Mail (ou le formulaire), envoie. Puis : "
             f"bash ~/agent-ia/revenus/prospection.sh ajouter {cibles[0]['groupe']} \"{cibles[0]['nom']}\" mail")
    for c in cibles:
        txt = message_complet(c)
        telegram(txt, silencieux=True)
        if afficher:
            print(txt)
            print("-" * 60)
    return cibles


def cmd_envoyer():
    if env("PROSPECTION_AUTO", "0") != "1":
        print("PROSPECTION_AUTO=0 : envoi manuel. Les messages du jour partent sur Telegram.")
        return cmd_jour(afficher=False)
    if not signature():
        telegram("Prospection : PROSPECTION_SIGNATURE est vide dans .env — je n'envoie rien avec "
                 "« [Prénom] ». Ajoute : PROSPECTION_SIGNATURE=Prénom Nom — mail")
        print("Signature manquante, rien envoyé.")
        return []
    if not smtp_pret():
        telegram("Prospection : SMTP incomplet dans .env (SMTP_HOTE, SMTP_UTILISATEUR, SMTP_MDP, "
                 "SMTP_EXPEDITEUR). Les messages du jour partent sur Telegram à la place.")
        return cmd_jour(afficher=False)
    envoyes, manuels, erreurs = [], [], []
    for c in contacts_du_jour():
        if not c.get("email"):
            telegram(message_complet(c), silencieux=True)
            noter_envoi(c["groupe"], c["nom"], "telegram-a-coller")
            manuels.append(c["nom"])
            continue
        try:
            envoyer_mail(c)
            noter_envoi(c["groupe"], c["nom"], "mail-auto")
            envoyes.append(f"{c['nom']} <{c['email']}>")
            log(f"mail envoyé à {c['nom']} <{c['email']}>", JOURNAL)
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"{c['nom']} : {e}")
            log(f"ERREUR {c['nom']} : {e}", JOURNAL)
    bilan = [f"Prospection auto — {len(envoyes)} mail(s) envoyé(s) depuis ton compte :"]
    bilan += [f"  • {e}" for e in envoyes]
    if manuels:
        bilan.append(f"À coller toi-même (formulaire) : {', '.join(manuels)} — textes ci-dessus.")
    if erreurs:
        bilan.append("Erreurs : " + " | ".join(erreurs))
    telegram("\n".join(bilan))
    print("\n".join(bilan))
    return envoyes


def cmd_relances(envoyer_telegram=True):
    auj = aujourd_hui()
    dues = [l for l in lire_csv() if l["statut"] == "envoye" and l["relance"] and l["relance"] <= auj]
    if not dues:
        print("Aucune relance due.")
        return []
    par_nom = {c["nom"].lower(): c for c in charger_campagne()}
    sig = signature() or "[Prénom] — [ton mail]"
    for l in dues:
        c = par_nom.get(l["contact"].lower(), {})
        dest = c.get("email") or f"formulaire : {c.get('formulaire', 'n.a.')}"
        texte = (f"RELANCE [{l['groupe']}] {l['contact']} — envoyé le {l['date']} ({l['canal']})\n"
                 f"À : {dest}\nObjet : Re: {c.get('objet', '')}\n\n"
                 + RELANCE.format(date=l["date"], signature=sig))
        print(texte)
        print("-" * 60)
        if envoyer_telegram:
            telegram(texte, silencieux=True)
    if envoyer_telegram:
        telegram(f"{len(dues)} relance(s) à envoyer aujourd'hui (textes ci-dessus). Après envoi : "
                 f"bash ~/agent-ia/revenus/prospection.sh relance \"NOM\"")
    return dues


def cmd_relance(nom):
    lignes = lire_csv()
    n = 0
    for l in lignes:
        if l["contact"].lower() == nom.lower() and l["statut"] == "envoye":
            l["statut"], l["relance"] = "relance", ""
            n += 1
    ecrire_csv(lignes)
    print(f"{n} ligne(s) marquée(s) relancée(s)")


def cmd_reponse(nom, texte):
    lignes = lire_csv()
    n = 0
    for l in lignes:
        if l["contact"].lower() == nom.lower():
            l["statut"], l["reponse"], l["relance"] = "repondu", texte, ""
            n += 1
    ecrire_csv(lignes)
    print(f"{n} ligne(s) mise(s) à jour")


def cmd_stats():
    lignes = lire_csv()
    total = len(charger_campagne())
    env_ = sum(1 for l in lignes if l["statut"] in ("envoye", "relance", "repondu"))
    rep = sum(1 for l in lignes if l["statut"] == "repondu")
    txt = (f"Prospection : {env_}/{total} contacts envoyés, {rep} réponse(s), "
           f"{sum(1 for l in lignes if l['statut'] == 'envoye')} en attente.")
    print(txt)
    return txt


def cmd_test():
    camp = charger_campagne()
    assert len(camp) == 30, len(camp)
    ids = {c["id"] for c in camp}
    assert len(ids) == 30
    for c in camp:
        assert c["corps"] in CORPS, c["id"]
        assert c.get("email") or c.get("formulaire"), c["id"]
        assert "[" not in c["ouverture"], c["id"]
        txt = corps(c)
        assert len(txt) < 2500, (c["id"], len(txt))
    print(f"OK : {len(camp)} contacts, 6 jours de {int(env('PROSPECTION_PAR_JOUR', '5'))}, "
          f"mode {'AUTO (SMTP)' if env('PROSPECTION_AUTO', '0') == '1' else 'manuel (Telegram)'}, "
          f"signature {'présente' if signature() else 'ABSENTE'}, SMTP {'prêt' if smtp_pret() else 'absent'}.")
    if env("PROSPECTION_AUTO", "0") == "1" and smtp_pret():
        port = int(env("SMTP_PORT", "587"))
        with smtplib.SMTP(env("SMTP_HOTE"), port, timeout=20) as s:
            s.ehlo()
            if port != 465:
                s.starttls()
            s.login(env("SMTP_UTILISATEUR"), env("SMTP_MDP"))
        print("Connexion SMTP : OK (identifiants acceptés).")


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "matin").strip().lower()
    cmd = "".join(ch for ch in cmd if ch.isalpha())  # espace insécable du clavier iPhone
    if cmd == "matin":
        cmd_envoyer()
        cmd_relances()
    elif cmd == "jour":
        cmd_jour()
    elif cmd == "envoyer":
        cmd_envoyer()
    elif cmd == "relances":
        cmd_relances(envoyer_telegram=False)
    elif cmd == "relance" and len(argv) >= 3:
        cmd_relance(argv[2])
    elif cmd == "reponse" and len(argv) >= 3:
        cmd_reponse(argv[2], argv[3] if len(argv) > 3 else "")
    elif cmd == "message" and len(argv) >= 3:
        for c in charger_campagne():
            if argv[2].lower() in c["nom"].lower():
                print(message_complet(c))
    elif cmd == "liste":
        for l in lire_csv():
            print(";".join(l[c] for c in ENTETE))
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "test":
        cmd_test()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
