#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT CONTREFACTUEL DES RÈGLES — « combien de ventes vos règles anti-fraude vous coûtent ? »

Même méthode que l'entonnoir du bot de trading : chaque règle qui a bloqué une commande
est jugée a posteriori. On estime, règle par règle, la part des commandes refusées qui
étaient en réalité légitimes, et l'argent perdu.

Entrée : un export CSV des commandes du marchand (Shopify, PrestaShop, WooCommerce, Stripe
Radar, module anti-fraude...). Les colonnes sont reconnues par synonymes :
  id        : id, order_id, commande, numero, reference
  date      : date, created_at, date_commande
  montant   : montant, amount, total, total_paid, prix
  decision  : decision, statut_fraude, fraud_status, risk_decision  (accepte|refuse|revue)
  regles    : regles, rules, rules_triggered, motif, raison, risk_reasons  (séparées par | ; ou ,)
  resultat  : resultat, outcome, chargeback, litige, dispute, rembourse  (ok|chargeback|rembourse|inconnu)
  client_connu : client_connu, returning, repeat_customer, nb_commandes_precedentes (0/1 ou nombre)
  pays, email : facultatifs

Usage :
  python3 revenus/audit_regles/audit_regles.py commandes.csv            # rapport Markdown dans donnees/
  python3 revenus/audit_regles/audit_regles.py commandes.csv --cb 25    # coût fixe d'un chargeback (€), défaut 20
  python3 revenus/audit_regles/audit_regles.py demo                      # jeu de données synthétique + rapport
"""
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commun  # noqa: E402

SYNONYMES = {
    "id": ["id", "order_id", "commande", "numero", "reference", "order", "name"],
    "date": ["date", "created_at", "date_commande", "created", "order_date"],
    "montant": ["montant", "amount", "total", "total_paid", "prix", "total_price", "montant_ttc"],
    "decision": ["decision", "statut_fraude", "fraud_status", "risk_decision", "risk", "statut", "status"],
    "regles": ["regles", "rules", "rules_triggered", "motif", "raison", "risk_reasons", "reasons", "flags"],
    "resultat": ["resultat", "outcome", "chargeback", "litige", "dispute", "rembourse", "refund"],
    "client_connu": ["client_connu", "returning", "repeat_customer", "nb_commandes_precedentes",
                     "orders_count", "customer_orders", "fidele"],
    "pays": ["pays", "country", "billing_country", "shipping_country"],
}
ACCEPTE = {"accepte", "accepté", "accepted", "approved", "ok", "valide", "validée", "paid", "payee", "payée", "approve"}
REFUSE = {"refuse", "refusé", "declined", "refused", "rejected", "blocked", "bloque", "bloqué", "cancelled_fraud", "decline"}
REVUE = {"revue", "review", "manual_review", "pending", "en attente", "a verifier", "à vérifier", "hold"}
FRAUDE = {"chargeback", "fraude", "fraud", "litige", "dispute", "rembourse_fraude", "impaye", "impayé", "1", "true", "oui", "yes"}


def _colonne(entetes, cle):
    bas = {e.lower().strip(): e for e in entetes}
    for syn in SYNONYMES[cle]:
        if syn in bas:
            return bas[syn]
    for syn in SYNONYMES[cle]:
        for e in bas:
            if syn in e:
                return bas[e]
    return None


def _nombre(x):
    if x is None:
        return 0.0
    x = str(x).replace("€", "").replace(" ", "").replace("\u202f", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", x)
    return float(m.group(0)) if m else 0.0


def charger(chemin):
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        extrait = f.read(4096)
        f.seek(0)
        try:
            dialecte = csv.Sniffer().sniff(extrait, delimiters=";,\t")
        except csv.Error:
            dialecte = csv.excel
        lecteur = csv.DictReader(f, dialect=dialecte)
        entetes = lecteur.fieldnames or []
        cols = {k: _colonne(entetes, k) for k in SYNONYMES}
        manquantes = [k for k in ("montant", "decision") if not cols[k]]
        if manquantes:
            raise SystemExit(f"Colonnes introuvables : {manquantes}. Colonnes vues : {entetes}")
        commandes = []
        for i, ligne in enumerate(lecteur):
            d = (ligne.get(cols["decision"]) or "").strip().lower()
            decision = "accepte" if d in ACCEPTE else "refuse" if d in REFUSE else "revue" if d in REVUE else "autre"
            r = (ligne.get(cols["resultat"]) or "").strip().lower() if cols["resultat"] else ""
            resultat = "fraude" if r in FRAUDE else "ok" if r in {"ok", "0", "false", "non", "no", "none", "livre", "livré", "delivered"} else "inconnu"
            regles_brut = (ligne.get(cols["regles"]) or "") if cols["regles"] else ""
            regles = [x.strip() for x in re.split(r"[|;,/]+", regles_brut) if x.strip()]
            cc = _nombre(ligne.get(cols["client_connu"])) if cols["client_connu"] else 0
            commandes.append({
                "id": ligne.get(cols["id"]) if cols["id"] else str(i + 1),
                "date": ligne.get(cols["date"], "") if cols["date"] else "",
                "montant": _nombre(ligne.get(cols["montant"])),
                "decision": decision, "regles": regles, "resultat": resultat,
                "client_connu": cc > 0,
                "pays": (ligne.get(cols["pays"]) or "").strip() if cols["pays"] else "",
            })
    return commandes, cols


def analyser(commandes, cout_chargeback=20.0, prior_precision=0.5):
    """Estime, par règle, la précision (part des blocages réellement frauduleux) et l'argent perdu."""
    acceptees = [c for c in commandes if c["decision"] == "accepte"]
    refusees = [c for c in commandes if c["decision"] == "refuse"]
    revues = [c for c in commandes if c["decision"] == "revue"]
    nb_fraude_acc = sum(1 for c in acceptees if c["resultat"] == "fraude")
    taux_fraude_acc = nb_fraude_acc / len(acceptees) if acceptees else 0.0
    ca_accepte = sum(c["montant"] for c in acceptees)
    ca_refuse = sum(c["montant"] for c in refusees)

    # Précision observée d'une règle = parmi les commandes ACCEPTÉES où elle s'est déclenchée
    # (passées en revue, seuil, etc.), part finie en fraude. C'est la seule mesure réelle disponible.
    par_regle = defaultdict(lambda: {"bloquees": 0, "montant_bloque": 0.0, "acc_declenchee": 0,
                                     "acc_fraude": 0, "bloquees_client_connu": 0, "montant_client_connu": 0.0})
    for c in commandes:
        for r in c["regles"] or (["(sans motif)"] if c["decision"] == "refuse" else []):
            s = par_regle[r]
            if c["decision"] == "refuse":
                s["bloquees"] += 1
                s["montant_bloque"] += c["montant"]
                if c["client_connu"]:
                    s["bloquees_client_connu"] += 1
                    s["montant_client_connu"] += c["montant"]
            elif c["decision"] == "accepte" and c["resultat"] != "inconnu":
                s["acc_declenchee"] += 1
                if c["resultat"] == "fraude":
                    s["acc_fraude"] += 1

    lignes = []
    for r, s in par_regle.items():
        if s["acc_declenchee"] >= 5:
            precision = s["acc_fraude"] / s["acc_declenchee"]
            source = f"mesurée sur {s['acc_declenchee']} commandes acceptées malgré la règle"
            confiance = "haute" if s["acc_declenchee"] >= 30 else "moyenne"
        else:
            # Bayésien léger : prior + les quelques observations
            precision = (prior_precision * 5 + s["acc_fraude"]) / (5 + s["acc_declenchee"])
            source = "estimée (règle jamais observée à l'acceptation : à mesurer en mode ombre)"
            confiance = "basse"
        # Clients connus bloqués : quasi certainement légitimes (on les compte à part, à 90 %)
        legit_connu = 0.9 * s["montant_client_connu"]
        reste = s["montant_bloque"] - s["montant_client_connu"]
        ventes_perdues = legit_connu + reste * (1 - precision)
        fraude_evitee = reste * precision + 0.1 * s["montant_client_connu"]
        cout_fraude_si_ouvert = fraude_evitee + cout_chargeback * (s["bloquees"] * precision)
        net = ventes_perdues - cout_fraude_si_ouvert  # > 0 : la règle coûte plus qu'elle ne protège
        if net > 0 and confiance != "basse":
            reco = "ASSOUPLIR ou RETIRER — coûte plus qu'elle ne protège"
        elif net > 0:
            reco = "PASSER EN MODE OMBRE — probablement coûteuse, à mesurer avant de toucher"
        elif s["bloquees_client_connu"] > 0:
            reco = "GARDER mais EXEMPTER les clients connus"
        else:
            reco = "GARDER — protège plus qu'elle ne coûte"
        lignes.append({
            "regle": r, "bloquees": s["bloquees"], "montant_bloque": round(s["montant_bloque"], 2),
            "clients_connus_bloques": s["bloquees_client_connu"],
            "precision_estimee": round(precision, 3), "confiance": confiance, "source_precision": source,
            "ventes_perdues_estimees": round(ventes_perdues, 2),
            "fraude_evitee_estimee": round(cout_fraude_si_ouvert, 2),
            "perte_nette": round(net, 2), "recommandation": reco,
        })
    lignes.sort(key=lambda x: -x["perte_nette"])
    total_perdu = sum(max(0.0, l["perte_nette"]) for l in lignes)
    return {
        "nb_commandes": len(commandes), "nb_acceptees": len(acceptees), "nb_refusees": len(refusees),
        "nb_revues": len(revues), "taux_refus": round(len(refusees) / len(commandes), 4) if commandes else 0,
        "taux_fraude_acceptees": round(taux_fraude_acc, 4), "ca_accepte": round(ca_accepte, 2),
        "ca_refuse": round(ca_refuse, 2),
        "clients_connus_refuses": sum(1 for c in refusees if c["client_connu"]),
        "ca_clients_connus_refuses": round(sum(c["montant"] for c in refusees if c["client_connu"]), 2),
        "perte_nette_totale_estimee": round(total_perdu, 2),
        "cout_chargeback": cout_chargeback, "regles": lignes,
    }


def rapport_markdown(res, nom_client="le marchand", periode=""):
    E = commun.euros
    l = [f"# Audit des règles anti-fraude — {nom_client}", ""]
    l.append(f"Généré le {commun.horodatage()}{(' · période ' + periode) if periode else ''}. "
             "Méthode : chaque règle est jugée sur ce qu'elle a bloqué et sur ce qui s'est passé quand "
             "elle s'est déclenchée sans bloquer. Les chiffres sont des estimations, la colonne confiance dit lesquelles sont solides.")
    l += ["", "## En une phrase", ""]
    l.append(f"Vos règles ont refusé **{res['nb_refusees']} commandes** ({res['taux_refus']*100:.1f} % du flux, "
             f"{E(res['ca_refuse'])}) ; nous estimons que **{E(res['perte_nette_totale_estimee'])} de ventes nettes** "
             f"(après déduction de la fraude évitée) pouvaient être récupérés sur la période.")
    l += ["", "## Les chiffres de base", "",
          "| Indicateur | Valeur |", "|---|---|",
          f"| Commandes analysées | {res['nb_commandes']} |",
          f"| Acceptées / refusées / en revue | {res['nb_acceptees']} / {res['nb_refusees']} / {res['nb_revues']} |",
          f"| Taux de refus | {res['taux_refus']*100:.1f} % |",
          f"| Taux de fraude réel sur les acceptées | {res['taux_fraude_acceptees']*100:.2f} % |",
          f"| CA accepté / CA refusé | {E(res['ca_accepte'])} / {E(res['ca_refuse'])} |",
          f"| Clients déjà connus pourtant refusés | {res['clients_connus_refuses']} ({E(res['ca_clients_connus_refuses'])}) |",
          f"| Coût fixe d'un chargeback retenu | {E(res['cout_chargeback'])} |"]
    l += ["", "## Règle par règle (de la plus coûteuse à la plus utile)", "",
          "| Règle | Bloquées | Montant bloqué | Précision estimée | Confiance | Ventes perdues | Fraude évitée | Perte nette | Recommandation |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in res["regles"]:
        l.append(f"| {r['regle']} | {r['bloquees']} | {E(r['montant_bloque'])} | {r['precision_estimee']*100:.0f} % | "
                 f"{r['confiance']} | {E(r['ventes_perdues_estimees'])} | {E(r['fraude_evitee_estimee'])} | "
                 f"{E(r['perte_nette'])} | {r['recommandation']} |")
    l += ["", "## Ce que nous proposons", ""]
    a_ombre = [r["regle"] for r in res["regles"] if "OMBRE" in r["recommandation"]]
    a_retirer = [r["regle"] for r in res["regles"] if "RETIRER" in r["recommandation"]]
    a_exempter = [r["regle"] for r in res["regles"] if "EXEMPTER" in r["recommandation"]]
    etapes = []
    if a_retirer:
        etapes.append(f"Assouplir immédiatement : {', '.join(a_retirer)} (mesure solide : elles coûtent plus qu'elles ne protègent).")
    if a_exempter or res["clients_connus_refuses"]:
        etapes.append(f"Exempter les clients ayant déjà une commande livrée sans litige"
                      f"{(' pour ' + ', '.join(a_exempter)) if a_exempter else ''} : "
                      f"{res['clients_connus_refuses']} refus et {E(res['ca_clients_connus_refuses'])} concernés.")
    if a_ombre:
        etapes.append(f"Passer en mode ombre (la règle journalise mais ne bloque plus, on juge chaque commande 60 jours après) : {', '.join(a_ombre)}.")
    etapes.append("Suivi : nous mesurons chaque semaine les ventes effectivement récupérées et la fraude effectivement subie ; "
                  "notre rémunération est un pourcentage des ventes récupérées nettes, zéro si rien n'est récupéré.")
    for i, e in enumerate(etapes, 1):
        l.append(f"{i}. {e}")
    l += ["", "## Précision de la méthode", "",
          "- La précision « mesurée » vient des commandes où la règle s'est déclenchée mais qui ont quand même été acceptées (revue manuelle, seuil) : on connaît leur sort réel.",
          "- Quand une règle n'a jamais laissé passer de commande, on ne sait pas ce qu'elle bloque vraiment : la précision est une estimation prudente, d'où le mode ombre avant toute décision.",
          "- Un client connu (déjà livré sans litige) refusé est compté légitime à 90 %.",
          "- Les clients refusés qui ne reviennent jamais (41 % selon les études sectorielles) ne sont pas comptés : la perte réelle est supérieure à l'estimation."]
    return "\n".join(l)


def demo(n=1200, graine=7):
    """Jeu de données synthétique mais réaliste pour tester et pour la démo commerciale."""
    rnd = random.Random(graine)
    regles_def = {
        # nom : (part des commandes où elle se déclenche, probabilité de fraude réelle quand déclenchée)
        "pays_livraison_different": (0.08, 0.12),
        "montant_sup_300": (0.10, 0.08),
        "email_jetable": (0.03, 0.70),
        "adresse_ip_etrangere": (0.06, 0.15),
        "trois_tentatives_cb": (0.02, 0.80),
        "nouveau_client_nuit": (0.07, 0.05),
    }
    lignes = []
    for i in range(n):
        montant = round(rnd.lognormvariate(4.3, 0.7), 2)
        connu = rnd.random() < 0.35
        declenchees, p_fraude = [], 0.004
        for nom, (part, pf) in regles_def.items():
            if rnd.random() < part * (0.5 if connu else 1.0):
                declenchees.append(nom)
                p_fraude = max(p_fraude, pf)
        fraude = rnd.random() < p_fraude
        if declenchees:
            # le marchand bloque 85 % des déclenchements, met 15 % en revue puis accepte
            decision = "refuse" if rnd.random() < 0.85 else "accepte"
        else:
            decision = "accepte"
        resultat = ("chargeback" if fraude else "ok") if decision == "accepte" else ""
        lignes.append({
            "order_id": 10000 + i, "date": f"2026-{rnd.randint(8, 10):02d}-{rnd.randint(1, 28):02d}",
            "total": str(montant).replace(".", ","), "fraud_status": decision,
            "rules_triggered": "|".join(declenchees), "outcome": resultat,
            "orders_count": rnd.randint(1, 9) if connu else 0, "country": "FR" if rnd.random() < 0.9 else "BE",
        })
    chemin = os.path.join(commun.DONNEES, "demo_commandes.csv")
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    return chemin


def executer(chemin, cout_cb=20.0, nom_client=None):
    commandes, cols = charger(chemin)
    res = analyser(commandes, cout_chargeback=cout_cb)
    nom = nom_client or os.path.splitext(os.path.basename(chemin))[0]
    md = rapport_markdown(res, nom_client=nom)
    import unicodedata
    nom_ascii = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    base = os.path.join(commun.DONNEES, f"audit_{re.sub(r'[^a-zA-Z0-9_-]+', '_', nom_ascii).strip('_')}")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    commun.ecrire_json(base + ".json", res)
    return res, md, base


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cout = 20.0
    if "--cb" in sys.argv:
        cout = float(sys.argv[sys.argv.index("--cb") + 1])
        args = [a for a in args if a != str(cout) and a != sys.argv[sys.argv.index("--cb") + 1]]
    if not args:
        print(__doc__)
        sys.exit(0)
    chemin = demo() if args[0] == "demo" else args[0]
    nom = args[1] if len(args) > 1 else ("Boutique démo" if args[0] == "demo" else None)
    res, md, base = executer(chemin, cout, nom)
    print(md)
    print(f"\n→ rapport : {base}.md  (données : {base}.json)")
