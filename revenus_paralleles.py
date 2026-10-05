"""
Revenus Paralleles — Chaque sous-agent developpe un produit/service crypto en parallele du trading.
Genere du contenu monetisable avec le cerveau Ollama de chaque sous-agent.
"""
import os
import json
import time
import requests
from datetime import datetime

FICHIER_REVENUS = os.path.expanduser("~/agent-ia/revenus_paralleles.json")
DOSSIER_CONTENU = os.path.expanduser("~/agent-ia/revenus/")
os.makedirs(DOSSIER_CONTENU, exist_ok=True)

# === TELEGRAM POUR AUTO-PUBLICATION ===
DOSSIER_PROJET = os.path.expanduser("~/agent-ia")
TELEGRAM_TOKEN = ""
env_path = os.path.join(DOSSIER_PROJET, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                TELEGRAM_TOKEN = line.split("=", 1)[1].strip()

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""

# === DEFINITION DES PROJETS PAR SOUS-AGENT ===
PROJETS = {
    "scalpeur": {
        "nom": "Signaux Scalp Express",
        "description": "Signaux de trading scalp quotidiens avec points d'entree/sortie precis",
        "cerveau": "phi4-mini",
        "frequence": "quotidien",
        "format": "signal",
        "prix_mensuel": 10,
        "objectif_abonnes": 50,
        "sujet_prompt": (
            "Genere un signal de trading scalp pour aujourd'hui. "
            "Format: CRYPTO, DIRECTION (LONG/SHORT), POINT D'ENTREE (prix approximatif), "
            "STOP LOSS (-%), TAKE PROFIT (+%), RAISON TECHNIQUE (RSI, momentum, bougies). "
            "Sois precis et concret. 1 signal par jour maximum. "
            "Si le marche ne presente pas d'opportunite scalp claire, explique pourquoi et "
            "donne le niveau a surveiller pour la prochaine opportunite."
        ),
    },
    "swing": {
        "nom": "Academie Swing Trading",
        "description": "Modules educatifs sur le swing trading crypto (patterns, strategies, gestion du risque)",
        "cerveau": "qwen2.5:7b",
        "frequence": "hebdomadaire",
        "format": "guide",
        "prix_mensuel": 25,
        "objectif_abonnes": 30,
        "sujet_prompt": (
            "Cree un module educatif sur le swing trading crypto. "
            "Choisis UN sujet parmi: patterns de bougies japonaises, gestion du risque, "
            "tendances et EMA, RSI et divergences, support/resistance, Fibonacci, "
            "psychologie du trader, plan de trading, backtesting, gestion de position. "
            "Format: Titre, Introduction, Theorie, Exemple concret sur un graphique crypto, "
            "Erreurs courantes a eviter, Resume actionnable. "
            "Sois pedagogique et pratique. Le lecteur doit pouvoir appliquer immediatement."
        ),
    },
    "contrarien": {
        "nom": "Lettre Contrarienne",
        "description": "Analyse de marche hebdomadaire avec perspective contrarienne (peur/euphorie)",
        "cerveau": "deepseek-r1:7b",
        "frequence": "hebdomadaire",
        "format": "newsletter",
        "prix_mensuel": 15,
        "objectif_abonnes": 40,
        "sujet_prompt": (
            "Redige une lettre contrarienne d'analyse du marche crypto. "
            "Identifie ce que la majorite fait (peur ou euphorie) et pourquoi le contraire est plus rentable. "
            "Format: 1) Etat du marche (Fear & Greed, sentiment general), "
            "2) Ce que tout le monde fait (le troupeau), 3) L'opportunite contrarienne (le pari inverse), "
            "4) Risque du pari contrarien, 5) Conclusion actionnable. "
            "Sois provocateur mais rigoureux. Base toi sur des principes de trading contrarien."
        ),
    },
    "momentum": {
        "nom": "Alertes Momentum Crypto",
        "description": "Alertes sur les mouvements de momentum fort en temps reel",
        "cerveau": "qwen2.5:7b",
        "frequence": "quotidien",
        "format": "alerte",
        "prix_mensuel": 20,
        "objectif_abonnes": 35,
        "sujet_prompt": (
            "Genere une alerte momentum pour le marche crypto actuel. "
            "Identifie les cryptos avec le momentum le plus fort (MACD haussier, volume croissant, "
            "cassure de resistance). Format: TOP 3 cryptos momentum, force du momentum (1-10), "
            "point d'entree, cible, stop loss, fenetre de temps. "
            "Si aucun momentum fort, explique quels niveaux surveiller pour le prochain breakout."
        ),
    },
}


def _charger_revenus():
    """Charge l'etat des revenus paralleles."""
    if os.path.exists(FICHIER_REVENUS):
        try:
            with open(FICHIER_REVENUS, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "date_depart": datetime.now().strftime("%Y-%m-%d"),
        "contenus_generes": 0,
        "projets": {},
        "abonnes_estimes": 0,
        "revenu_estime_mensuel": 0,
        "canal_gratuit_id": "",
        "canal_premium_id": "",
    }


def _sauver_revenus(data):
    """Sauvegarde l'etat des revenus."""
    try:
        with open(FICHIER_REVENUS, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  [REVENUS] Erreur sauvegarde: {e}")


def _envoyer_canal_telegram(channel_id, texte):
    """Envoie un message a un canal Telegram."""
    if not TELEGRAM_API or not channel_id:
        return False
    try:
        # Telegram limite a 4096 caracteres par message
        if len(texte) > 4000:
            texte = texte[:4000] + "\n... (suite dans le canal premium)"
        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": channel_id,
            "text": texte,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print(f"  [REVENUS] ✓ Publie sur canal Telegram ({channel_id})")
            return True
        else:
            print(f"  [REVENUS] Erreur Telegram {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  [REVENUS] Erreur envoi canal: {e}")
    return False


def _formater_post_gratuit(sous_agent, projet, contenu):
    """Formate un extrait gratuit pour le canal public (teaser + CTA)."""
    # Extrait: premieres lignes seulement (teaser)
    lignes = contenu.split("\n")
    extrait = "\n".join(lignes[:15])
    if len(extrait) > 800:
        extrait = extrait[:800] + "..."
    post = (
        f"*{projet['nom']}*\n"
        f"_Par le sous-agent {sous_agent} ({projet['cerveau']})_\n"
        f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"{extrait}\n\n"
        f"... \n\n"
        f"*Pour le signal complet avec SL/TP precis, rejoignez le canal Premium.*\n"
        f"_Crypto Signals IA — Genere par IA_"
    )
    return post


def _formater_post_premium(sous_agent, projet, contenu):
    """Formate le contenu complet pour le canal premium (payant)."""
    post = (
        f"*🔒 PREMIUM — {projet['nom']}*\n"
        f"_Par le sous-agent {sous_agent} ({projet['cerveau']})_\n"
        f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"{contenu}\n\n"
        f"_Crypto Signals IA Premium_"
    )
    return post


def _generer_contenu_ollama(ceveau, prompt):
    """Genere du contenu avec un cerveau Ollama."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": ceveau,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 600},
    }
    try:
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code == 200:
            texte = r.json()["message"]["content"].strip()
            # Filtre les balises de raisonnement deepseek-r1
            import re
            texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip()
            return texte
    except Exception as e:
        print(f"  [REVENUS] Erreur Ollama ({ceveau}): {e}")
    return None


def _sauver_contenu(sous_agent, projet, contenu):
    """Sauvegarde le contenu genere dans un fichier."""
    dossier = os.path.join(DOSSIER_CONTENU, sous_agent)
    os.makedirs(dossier, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    nom_fichier = f"{date_str}_{projet['format']}.md"
    chemin = os.path.join(dossier, nom_fichier)
    entete = (
        f"# {projet['nom']}\n"
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"**Sous-agent:** {sous_agent} ({projet['cerveau']})\n"
        f"**Frequence:** {projet['frequence']}\n"
        f"**Prix mensuel:** {projet['prix_mensuel']}EUR | Objectif: {projet['objectif_abonnes']} abonnes\n"
        f"---\n\n"
    )
    try:
        with open(chemin, "w") as f:
            f.write(entete + contenu)
        return chemin
    except Exception as e:
        print(f"  [REVENUS] Erreur sauvegarde contenu: {e}")
    return None


def _doit_generer(projet, etat_projet):
    """Verifie si un projet doit generer du contenu selon sa frequence."""
    derniere_gen = etat_projet.get("derniere_generation", "")
    maintenant = datetime.now().strftime("%Y-%m-%d")
    if projet["frequence"] == "quotidien":
        return derniere_gen != maintenant
    elif projet["frequence"] == "hebdomadaire":
        # Genere le lundi (jour 0)
        if datetime.now().weekday() != 0:
            return False
        semaine_actuelle = datetime.now().strftime("%Y-W%W")
        return etat_projet.get("derniere_semaine", "") != semaine_actuelle
    return False


def generer_revenus_paralleles(force=False):
    """Genere du contenu pour chaque sous-agent dont c'est le moment."""
    data = _charger_revenus()
    contenus_genere_aujourdhui = []

    for nom_sa, projet in PROJETS.items():
        etat = data["projets"].get(nom_sa, {
            "derniere_generation": "",
            "nb_contenus": 0,
            "abonnes_estimes": 0,
        })

        if not force and not _doit_generer(projet, etat):
            continue

        print(f"  [REVENUS] Generation {projet['nom']} ({projet['cerveau']})...")

        # Prompt enrichi avec contexte de marche si disponible
        prompt = (
            f"{projet['sujet_prompt']}\n\n"
            f"Contexte: Tu es un sous-agent specialise en {nom_sa}. "
            f"Ton produit s'appelle '{projet['nom']}' et cible des traders crypto debutants a intermediaires. "
            f"Reponds en francais, format markdown, sois professionnel et actionnable."
        )

        contenu = _generer_contenu_ollama(projet["cerveau"], prompt)

        if contenu and len(contenu) > 50:
            chemin = _sauver_contenu(nom_sa, projet, contenu)
            if chemin:
                etat["derniere_generation"] = datetime.now().strftime("%Y-%m-%d")
                etat["nb_contenus"] = etat.get("nb_contenus", 0) + 1
                if projet["frequence"] == "hebdomadaire":
                    etat["derniere_semaine"] = datetime.now().strftime("%Y-W%W")
                data["projets"][nom_sa] = etat
                data["contenus_generes"] = data.get("contenus_generes", 0) + 1
                contenus_genere_aujourdhui.append({
                    "sous_agent": nom_sa,
                    "projet": projet["nom"],
                    "chemin": chemin,
                    "extrait": contenu[:200],
                })
                print(f"  [REVENUS] ✓ {projet['nom']}: contenu genere ({len(contenu)} chars)")
                # === AUTO-PUBLICATION SUR TELEGRAM ===
                canal_gratuit = data.get("canal_gratuit_id", "")
                canal_premium = data.get("canal_premium_id", "")
                if canal_gratuit:
                    post_gratuit = _formater_post_gratuit(nom_sa, projet, contenu)
                    _envoyer_canal_telegram(canal_gratuit, post_gratuit)
                if canal_premium:
                    post_premium = _formater_post_premium(nom_sa, projet, contenu)
                    _envoyer_canal_telegram(canal_premium, post_premium)
                if not canal_gratuit and not canal_premium:
                    print(f"  [REVENUS] (Aucun canal Telegram configure — contenu sauve seulement)")
            else:
                print(f"  [REVENUS] ✗ {projet['nom']}: echec sauvegarde")
        else:
            print(f"  [REVENUS] ✗ {projet['nom']}: contenu vide ou trop court")

        # Pause entre les generations (CPU limite, Ollama lock)
        time.sleep(2)

    # Met a jour les estimations de revenu
    total_abonnes = sum(
        data["projets"].get(sa, {}).get("abonnes_estimes", 0)
        for sa in PROJETS
    )
    revenu_mensuel = sum(
        data["projets"].get(sa, {}).get("abonnes_estimes", 0) * PROJETS[sa]["prix_mensuel"]
        for sa in PROJETS
    )
    data["abonnes_estimes"] = total_abonnes
    data["revenu_estime_mensuel"] = revenu_mensuel
    _sauver_revenus(data)

    return contenus_genere_aujourdhui


def statut_revenus():
    """Retourne un resume des revenus paralleles pour Telegram."""
    data = _charger_revenus()
    lignes = ["🧬 REVENUS PARALLELES DES SOUS-AGENTS\n"]
    for nom_sa, projet in PROJETS.items():
        etat = data["projets"].get(nom_sa, {})
        nb_contenus = etat.get("nb_contenus", 0)
        abonnes = etat.get("abonnes_estimes", 0)
        derniere = etat.get("derniere_generation", "jamais")
        revenu = abonnes * projet["prix_mensuel"]
        lignes.append(
            f"  {projet['nom']} ({nom_sa}, {projet['cerveau']})\n"
            f"    Format: {projet['format']} | Freq: {projet['frequence']} | Prix: {projet['prix_mensuel']}EUR/mois\n"
            f"    Contenus generes: {nb_contenus} | Dernier: {derniere}\n"
            f"    Abonnes: {abonnes}/{projet['objectif_abonnes']} | Revenu: {revenu}EUR/mois"
        )
    total_revenu = data.get("revenu_estime_mensuel", 0)
    total_contenus = data.get("contenus_generes", 0)
    lignes.append(f"\n  TOTAL: {total_contenus} contenus generes | {total_revenu}EUR/mois de revenu potentiel")
    lignes.append(f"  Dossier contenus: {DOSSIER_CONTENU}")
    return "\n".join(lignes)


def dernier_contenu(sous_agent):
    """Retourne le dernier contenu genere par un sous-agent."""
    dossier = os.path.join(DOSSIER_CONTENU, sous_agent)
    if not os.path.exists(dossier):
        return None
    fichiers = sorted(os.listdir(dossier), reverse=True)
    if not fichiers:
        return None
    chemin = os.path.join(dossier, fichiers[0])
    try:
        with open(chemin, "r") as f:
            return f.read()
    except Exception:
        return None


def projets_pour_contexte():
    """Genere un resume court des projets de revenus pour le contexte de l'IA."""
    data = _charger_revenus()
    lignes = ["\nREVENUS PARALLELES (tes sous-agents developpent des revenus en parallele):"]
    for nom_sa, projet in PROJETS.items():
        etat = data["projets"].get(nom_sa, {})
        nb = etat.get("nb_contenus", 0)
        lignes.append(f"  - {projet['nom']} ({nom_sa}): {nb} contenus generes, {projet['prix_mensuel']}EUR/mois par abonne")
    total = data.get("revenu_estime_mensuel", 0)
    lignes.append(f"  Revenu potentiel total: {total}EUR/mois si tous les objectifs d'abonnes sont atteints")
    return "\n".join(lignes)
