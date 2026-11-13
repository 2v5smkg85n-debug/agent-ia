#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCANNER DE LEADS — repère les PME françaises qui viennent de dire qu'elles veulent
de l'automatisation / de l'IA, et les classe par intérêt.

Sources (toutes gratuites) :
  - codeur     : flux RSS public des projets Codeur.com (aucune clé) — des PME postent
                 un besoin ET un budget ("Concepteur d'agent IA, 500 à 1 000 €").
  - adzuna     : offres d'emploi France (clé gratuite, optionnelle : ADZUNA_APP_ID / ADZUNA_APP_KEY
                 dans le .env) — une PME qui recrute "chargé d'automatisation" a un besoin.
  - francetravail : API Offres d'emploi (optionnelle : FT_CLIENT_ID / FT_CLIENT_SECRET) —
                 l'accès est suspendu pour les nouveaux demandeurs depuis oct. 2026,
                 le code est prêt si l'accès revient.

Usage (une ligne sur le VPS, depuis ~/agent-ia) :
  python3 revenus/leads/scanner_leads.py            # scanne, mémorise, envoie les nouveaux leads chauds sur Telegram
  python3 revenus/leads/scanner_leads.py test       # idem sans Telegram
  python3 revenus/leads/scanner_leads.py liste 20   # 20 derniers leads les mieux notés
  python3 revenus/leads/scanner_leads.py csv        # exporte donnees/leads.csv (à vendre / à travailler)
  python3 revenus/leads/scanner_leads.py stats      # combien de leads, par source et par niveau

Réglages (.env) : LEADS_SEUIL_TELEGRAM=60  LEADS_IA=0|1 (résumé Ollama sur les leads chauds)
"""
import csv
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commun  # noqa: E402

FICHIER_LEADS = os.path.join(commun.DONNEES, "leads.jsonl")
FICHIER_CSV = os.path.join(commun.DONNEES, "leads.csv")
JOURNAL = os.path.join(commun.DONNEES, "leads.log")

# Mots-clés -> points. Ce qu'on sait livrer vaut plus.
MOTS_CLES = {
    # coeur de métier : agents / automatisation
    r"agent[s]? ia|agent[s]? d.ia|ai agent|agentique": 40,
    r"\bn8n\b|\bmake\.com\b|\bmake\b.*automati|zapier|activepieces": 35,
    r"automatis|automation|workflow": 30,
    r"chatbot|chat bot|assistant virtuel|assistant ia|bot telegram|bot whatsapp|bot discord": 30,
    r"\bia\b|intelligence artificielle|\bai\b|gpt|chatgpt|openai|claude|mistral|ollama|llm|rag\b": 25,
    r"scrap|extraction de donn|collecte de donn|veille automati": 20,
    r"\bpython\b|\bapi\b|script": 15,
    r"\bcrm\b|hubspot|notion|airtable|google sheets|prise de rendez|relance": 15,
    r"g[ée]n[ée]ration (de )?(contenu|vid[ée]o|image)|vid[ée]os? ia|contenus? ia|images? ia|avatar|voix off|tiktok|faceless": 20,
    # second coeur : e-commerce / fraude (audit des règles)
    r"e-?commerce|shopify|prestashop|woocommerce|boutique en ligne": 15,
    r"fraude|anti-?fraude|paiement refus|chargeback|impay": 25,
    # supervision / VPS
    r"\bvps\b|serveur|monitoring|supervision|maintenance|panne|bug": 12,
    r"trading|bot de trading|crypto|mql": 10,
}
# Ce qu'on ne fait pas : pénalité (évite le bruit)
NEGATIFS = {
    r"wordpress|wix|webflow|site vitrine|logo|flyer|graphiste|powerpoint": -15,
    r"t[ée]l[ée]prospect|closer|commercial freelance|community manager": -20,
    r"unity|godot|jeu mobile|3d": -25,
    r"r[ée]dacteur|r[ée]daction|traduction|th[èe]se": -20,
}


def points_budget(texte):
    """Lit le budget max annoncé (« 1 000 € à 10 000 € », « plus de 10 000 € ») -> points."""
    m = re.search(r"budget\s*:\s*([^-]+?)(?:\s*-|$)", texte, re.I)
    if not m:
        return 0, None
    brut = m.group(1)
    nombres = [int(n.replace(" ", "").replace("\u202f", "")) for n in re.findall(r"\d[\d \u202f]*", brut)]
    if not nombres:
        return 0, None
    maxi = max(nombres)
    if "moins de" in brut.lower():
        return 3, maxi
    if maxi >= 10000:
        return 25, maxi
    if maxi >= 5000:
        return 22, maxi
    if maxi >= 2000:
        return 18, maxi
    if maxi >= 1000:
        return 14, maxi
    return 10, maxi


def _net(t):
    t = html.unescape(t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def noter(titre, texte):
    """Score 0-100 + raisons. Déterministe, lisible, modifiable."""
    corps = f"{titre} {texte}".lower()
    score, raisons = 0, []
    for motif, pts in MOTS_CLES.items():
        if re.search(motif, corps):
            score += pts
            raisons.append(motif.split("|")[0].replace("\\b", "").replace("\\", ""))
    for motif, pts in NEGATIFS.items():
        if re.search(motif, titre.lower()):  # la pénalité ne joue que sur le titre
            score += pts
    pts, maxi = points_budget(corps)
    if pts:
        score += pts
        raisons.append(f"budget {maxi} €")
    # le titre qui dit le besoin vaut un bonus
    if re.search(r"ia|agent|automati|n8n|chatbot|bot", titre.lower()):
        score += 10
    return max(0, min(100, score)), raisons[:6]


def niveau(score):
    if score >= 75:
        return "CHAUD"
    if score >= 50:
        return "TIEDE"
    return "FROID"


# ---------------------------------------------------------------- sources
def source_codeur():
    """Codeur.com — 35 derniers projets, sans clé."""
    code, xml_txt = commun.http_get("https://www.codeur.com/projects?format=rss")
    if code != 200 or not xml_txt:
        commun.log(f"codeur indisponible (HTTP {code})", JOURNAL)
        return []
    out = []
    try:
        racine = ET.fromstring(xml_txt.encode("utf-8"))
    except ET.ParseError as e:
        commun.log(f"codeur RSS illisible : {e}", JOURNAL)
        return []
    for item in racine.iter("item"):
        titre = _net(item.findtext("title"))
        lien = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or lien).strip()
        desc = _net(item.findtext("description"))
        try:
            date = parsedate_to_datetime(item.findtext("pubDate")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            date = commun.horodatage()[:16]
        budget = ""
        m = re.search(r"Budget\s*:\s*([^-]+?)\s*-\s*Cat", desc)
        if m:
            budget = m.group(1).strip()
        cats = ""
        m = re.search(r"Cat[ée]gories\s*:\s*(.+?)(?:\s{2,}|$|Voir ce projet)", desc)
        if m:
            cats = m.group(1).strip()
        out.append({
            "id": f"codeur:{guid}", "source": "codeur", "date": date, "titre": titre,
            "texte": desc[:700], "budget": budget, "categories": cats, "lien": lien,
            "entreprise": "", "lieu": "France",
        })
    return out


def source_adzuna():
    """Adzuna France — offres d'emploi, clé gratuite (developer.adzuna.com)."""
    app_id = commun.env("ADZUNA_APP_ID", "")
    app_key = commun.env("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        return []
    out = []
    import json
    import urllib.parse
    for mots in ("n8n", "automatisation IA", "agent IA", "chatbot", "intelligence artificielle PME"):
        q = urllib.parse.urlencode({
            "app_id": app_id, "app_key": app_key, "what": mots, "results_per_page": 20,
            "max_days_old": 3, "sort_by": "date", "content-type": "application/json",
        })
        code, corps = commun.http_get(f"https://api.adzuna.com/v1/api/jobs/fr/search/1?{q}")
        if code != 200:
            commun.log(f"adzuna HTTP {code} pour « {mots} »", JOURNAL)
            continue
        try:
            res = json.loads(corps).get("results", [])
        except Exception:
            continue
        for r in res:
            out.append({
                "id": f"adzuna:{r.get('id')}", "source": "adzuna",
                "date": (r.get("created") or "")[:16].replace("T", " "),
                "titre": _net(r.get("title")), "texte": _net(r.get("description"))[:700],
                "budget": (f"{r.get('salary_min', '')}-{r.get('salary_max', '')} €/an"
                           if r.get("salary_min") else ""),
                "categories": (r.get("category") or {}).get("label", ""),
                "lien": r.get("redirect_url", ""),
                "entreprise": (r.get("company") or {}).get("display_name", ""),
                "lieu": (r.get("location") or {}).get("display_name", ""),
            })
    return out


def source_francetravail():
    """API Offres d'emploi France Travail — prête, mais l'accès est suspendu pour les nouveaux."""
    cid = commun.env("FT_CLIENT_ID", "")
    sec = commun.env("FT_CLIENT_SECRET", "")
    if not cid or not sec:
        return []
    import json
    import urllib.parse
    import urllib.request
    try:
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials", "client_id": cid, "client_secret": sec,
            "scope": "api_offresdemploiv2 o2dsoffre",
        }).encode()
        req = urllib.request.Request(
            "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire",
            data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=20) as r:
            token = json.loads(r.read().decode()).get("access_token")
    except Exception as e:
        commun.log(f"francetravail token impossible : {e}", JOURNAL)
        return []
    out = []
    for mots in ("automatisation", "intelligence artificielle", "n8n", "chatbot"):
        q = urllib.parse.urlencode({"motsCles": mots, "publieeDepuis": 3, "range": "0-49", "sort": 1})
        code, corps = commun.http_get(
            f"https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search?{q}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if code not in (200, 206):
            continue
        try:
            res = json.loads(corps).get("resultats", [])
        except Exception:
            continue
        for r in res:
            out.append({
                "id": f"ft:{r.get('id')}", "source": "francetravail",
                "date": (r.get("dateCreation") or "")[:16].replace("T", " "),
                "titre": _net(r.get("intitule")), "texte": _net(r.get("description"))[:700],
                "budget": _net((r.get("salaire") or {}).get("libelle", "")),
                "categories": r.get("romeLibelle", ""),
                "lien": (r.get("origineOffre") or {}).get("urlOrigine", ""),
                "entreprise": (r.get("entreprise") or {}).get("nom", ""),
                "lieu": (r.get("lieuTravail") or {}).get("libelle", ""),
            })
    return out


SOURCES = [source_codeur, source_adzuna, source_francetravail]


# ---------------------------------------------------------------- moteur
def scanner(envoyer=True, ia=None):
    connus = {l["id"] for l in commun.lire_jsonl(FICHIER_LEADS)}
    seuil = int(commun.env("LEADS_SEUIL_TELEGRAM", "60"))
    ia = (commun.env("LEADS_IA", "0") == "1") if ia is None else ia
    nouveaux = []
    for src in SOURCES:
        try:
            trouves = src()
        except Exception as e:
            commun.log(f"{src.__name__} erreur : {e}", JOURNAL)
            continue
        for lead in trouves:
            if lead["id"] in connus:
                continue
            lead["score"], lead["raisons"] = noter(lead["titre"], lead["texte"] + " " + lead["budget"])
            lead["niveau"] = niveau(lead["score"])
            lead["vu_le"] = commun.horodatage()
            lead["statut"] = "nouveau"
            if ia and lead["score"] >= seuil:
                avis = commun.ollama(
                    "Tu es un commercial d'une agence d'automatisation IA française. En UNE phrase, "
                    "dis ce qu'on peut vendre à ce prospect et à quel prix (en euros). Projet : "
                    f"{lead['titre']}. Détail : {lead['texte'][:500]}", num_predict=80)
                if avis:
                    lead["avis_ia"] = avis[:300]
            commun.ajouter_jsonl(FICHIER_LEADS, lead)
            connus.add(lead["id"])
            nouveaux.append(lead)
    chauds = sorted([l for l in nouveaux if l["score"] >= seuil], key=lambda l: -l["score"])
    commun.log(f"scan : {len(nouveaux)} nouveaux, {len(chauds)} au-dessus de {seuil}", JOURNAL)
    commun.battement("leads")
    if chauds and envoyer:
        commun.telegram(formater(chauds, titre=f"🎯 {len(chauds)} lead(s) chaud(s)"))
    return nouveaux, chauds


def formater(leads, titre="Leads"):
    lignes = [titre]
    for l in leads[:12]:
        bud = f" | {l['budget']}" if l.get("budget") else ""
        ent = f" | {l['entreprise']}" if l.get("entreprise") else ""
        lignes.append(f"\n[{l['score']}] {l['titre']}{bud}{ent}\n{l['source']} · {l['date']}\n{l['lien']}")
        if l.get("avis_ia"):
            lignes.append("→ " + l["avis_ia"])
    return "\n".join(lignes)


def exporter_csv():
    leads = commun.lire_jsonl(FICHIER_LEADS)
    champs = ["vu_le", "date", "source", "niveau", "score", "titre", "budget", "entreprise",
              "lieu", "categories", "lien", "statut", "raisons", "avis_ia"]
    with open(FICHIER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore", delimiter=";")
        w.writeheader()
        for l in sorted(leads, key=lambda x: (-x.get("score", 0), x.get("date", ""))):
            l = dict(l)
            l["raisons"] = ", ".join(l.get("raisons", []))
            w.writerow(l)
    return FICHIER_CSV, len(leads)


def stats():
    leads = commun.lire_jsonl(FICHIER_LEADS)
    par_src, par_niv = {}, {}
    for l in leads:
        par_src[l["source"]] = par_src.get(l["source"], 0) + 1
        par_niv[l["niveau"]] = par_niv.get(l["niveau"], 0) + 1
    print(f"{len(leads)} leads mémorisés")
    print("par source :", par_src)
    print("par niveau :", par_niv)
    chauds = [l for l in leads if l["niveau"] == "CHAUD"]
    if chauds:
        print(f"\n{len(chauds)} CHAUDS, derniers :")
        for l in sorted(chauds, key=lambda x: x["date"], reverse=True)[:5]:
            print(f"  [{l['score']}] {l['date']} {l['titre']} ({l['budget'] or 'budget ?'})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        n, c = scanner(envoyer=True)
        print(f"{len(n)} nouveaux, {len(c)} chauds envoyés")
    elif cmd == "test":
        n, c = scanner(envoyer=False)
        print(formater(sorted(n, key=lambda l: -l["score"]), titre=f"{len(n)} nouveaux (test, sans Telegram)"))
    elif cmd == "liste":
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        leads = sorted(commun.lire_jsonl(FICHIER_LEADS), key=lambda l: (-l["score"], l["date"]))
        print(formater(leads[:k], titre=f"{k} meilleurs leads"))
    elif cmd == "csv":
        chemin, n = exporter_csv()
        print(f"{n} leads -> {chemin}")
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
