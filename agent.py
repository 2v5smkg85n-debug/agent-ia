import os
import sys
import json
import time
import re as _re
import threading
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY= os.getenv("PPLX_API_KEY")
IFTTT_WEBHOOK     = os.getenv("IFTTT_WEBHOOK")

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_MEMOIRE = os.path.join(DOSSIER, "memoire.json")
FICHIER_LECONS = os.path.join(DOSSIER, "lecons.json")
FICHIER_HISTORIQUE = os.path.join(DOSSIER, "historique.json")
_HISTORIQUE_MAX = 100  # garde les 100 derniers echanges pour eviter l'inflation

# ============================================
# MEMOIRE LONG TERME
# ============================================
def charger_memoire():
    if os.path.exists(FICHIER_MEMOIRE):
        try:
            with open(FICHIER_MEMOIRE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"profil": [], "interets": [], "objectifs": [], "apprentissages": [], "preferences": []}

def sauver_memoire(memoire):
    with open(FICHIER_MEMOIRE, "w") as f:
        json.dump(memoire, f, ensure_ascii=False, indent=2)

def ajouter(categorie, texte):
    m = charger_memoire()
    texte = texte.strip()
    existants = [a if isinstance(a,str) else a.get("contenu","") for a in m[categorie]]
    if texte not in existants:
        m[categorie].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "contenu": texte})
        sauver_memoire(m)

def instruction_memoire():
    m = charger_memoire()
    parties = []
    def derniers(liste, n=5):
        items = [p["contenu"] if isinstance(p,dict) else p for p in liste[-n:]]
        return [i[:200] for i in items]
    if m["interets"]:
        parties.append("INTERETS: " + " | ".join(derniers(m["interets"])))
    if m["objectifs"]:
        parties.append("OBJECTIFS: " + " | ".join(derniers(m["objectifs"])))
    if m["preferences"]:
        parties.append("PREFERENCES: " + " | ".join(derniers(m["preferences"])))
    if m["profil"]:
        parties.append("PROFIL: " + " | ".join(derniers(m["profil"])))
    if m["apprentissages"][-5:]:
        parties.append("CONTEXTES RECENTS: " + " | ".join(derniers(m["apprentissages"])))
    if not parties:
        return ""
    instr = ("INFORMATIONS IMPORTANTES SUR L'UTILISATEUR (utilise-les pour personnaliser ta reponse):\n"
            + "\n".join(parties) + "\n")
    if len(instr) > 4000:
        instr = instr[:4000] + "...\n"
    return instr

# ============================================
# AUTO-EXTRACTION
# ============================================
MOTS_INTERET = ["je m'interesse", "j'aime ", "je kiffe", "je suis passionne", "j'adore", "je fais du", "j'utilise", "interesse par", "passionne par"]
MOTS_OBJECTIF = ["je veux ", "j'aimerais ", "mon objectif", "je cherche a", "je compte ", "je vise ", "je souhaiterais", "je voudrais"]
MOTS_PREFERENCE = ["je prefere", "j'aime mieux", "je n'aime pas", "je deteste", "toujours en", "jamais de"]
MOTS_PROFIL = ["je m'appelle", "j'habite", "je vis ", "je travaille", "je gagne", "mon age", "j'ai "]

def extraire_et_memoriser(question):
    q = question.lower()
    for mot in MOTS_INTERET:
        if mot in q:
            ajouter("interets", question)
            return True
    for mot in MOTS_OBJECTIF:
        if mot in q:
            ajouter("objectifs", question)
            return True
    for mot in MOTS_PREFERENCE:
        if mot in q:
            ajouter("preferences", question)
            return True
    for mot in MOTS_PROFIL:
        if mot in q:
            if "appelle" in mot and not _re.search(r"appelle\s+\w{2,}", q):
                continue
            ajouter("profil", question)
            return True
    return False

# ============================================
# IA + gestion erreurs
# ============================================
# Rate-limit PAR MODELE (pas global): on n'attend plus entre un appel Claude et un appel Gemini
_VERROUX_APPELS = threading.Lock()
_DERNIER_APPEL = {}  # {modele: timestamp}
_DELAI_MIN_ENTRE_APPELS = 2  # par modele/provider

_MODELE_VERS_PROVIDER = {
    "chatgpt": "openai", "claude": "anthropic", "gemini": "gemini", "perplexity": "perplexity"
}

# Cooldown: quand un provider est rate-limit (429), on l'ignore pendant COOLDOWN_DUREE secondes
# -> evite de re-tenter le meme provider en boucle et bascule immediatement sur une autre IA
_COOLDOWN = {}  # {provider: timestamp de fin de cooldown}
_COOLDOWN_DUREE = 60  # secondes pendant lesquelles un provider rate-limit est ignore


def _provider(modele):
    return _MODELE_VERS_PROVIDER.get(modele, modele)

def _en_cooldown(modele):
    provider = _provider(modele)
    fin = _COOLDOWN.get(provider, 0)
    return time.time() < fin

def _activer_cooldown(modele):
    with _VERROUX_APPELS:
        _COOLDOWN[_provider(modele)] = time.time() + _COOLDOWN_DUREE

def _attendre_rate_limit(modele=None):
    provider = _provider(modele) if modele else "global"
    with _VERROUX_APPELS:
        maintenant = time.time()
        ecoule = maintenant - _DERNIER_APPEL.get(provider, 0)
        attente = _DELAI_MIN_ENTRE_APPELS - ecoule
    if attente > 0:
        time.sleep(attente)
    with _VERROUX_APPELS:
        _DERNIER_APPEL[provider] = time.time()

def _extraire_retry_after(texte_erreur):
    m = _re.search(r"seconds:\s*(\d+)", str(texte_erreur))
    if m:
        return min(int(m.group(1)), 60)
    return 10

def _post(url, headers=None, json_data=None, timeout=60, modele=None):
    _attendre_rate_limit(modele)
    r = None
    for tentative in range(3):
        try:
            r = requests.post(url, headers=headers or {}, json=json_data, timeout=timeout)
            if r.status_code == 429:
                # Rate-limit: on met le provider en cooldown et on ARRETE de reessayer
                # -> l'IA wrapper va raise_for_status -> appeler_ia bascule immediatement sur une autre IA
                _activer_cooldown(modele)
                print(f"[rate-limit {_provider(modele)}, cooldown {_COOLDOWN_DUREE}s]", end="", flush=True)
                return r  # retourne la reponse 429 -> declenche le fallback immediat
            return r
        except Exception:
            if tentative < 2:
                time.sleep(3)
                continue
            raise
    return r

def chatgpt(prompt):
    if not OPENAI_API_KEY: return "[ChatGPT non configure]"
    try:
        r = _post("https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {OPENAI_API_KEY}"},
            {"model":"gpt-4o-mini","messages":[{"role":"user","content":prompt}],"temperature":0.7}, 90, modele="chatgpt")
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erreur ChatGPT: {e}]"

def claude(prompt):
    if not ANTHROPIC_API_KEY: return "[Claude non configure]"
    try:
        r = _post("https://api.anthropic.com/v1/messages",
            {"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            {"model":"claude-sonnet-5","max_tokens":4096,"messages":[{"role":"user","content":prompt}]}, 120, modele="claude")
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except Exception as e:
        return f"[Erreur Claude: {e}]"

def gemini(prompt):
    if not GEMINI_API_KEY: return "[Gemini non configure]"
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
        r = _post(url, None, {"contents":[{"parts":[{"text":prompt}]}]}, 120, modele="gemini")
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[Erreur Gemini: {e}]"

def perplexity(prompt):
    if not PERPLEXITY_API_KEY: return "[Perplexity non configure]"
    try:
        r = _post("https://api.perplexity.ai/v1/sonar",
            {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
            {"model":"sonar","messages":[{"role":"user","content":prompt}]}, 180, modele="perplexity")
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erreur Perplexity: {e}]"

MODELS = {"chatgpt":chatgpt,"claude":claude,"gemini":gemini,"perplexity":perplexity}

# ============================================
# PRIX CRYPTO TEMPS REEL (Binance, sans IA)
# ============================================
# Evite les hallucinations de Perplexity/Claude sur les prix.
# Source unique fiable: Binance, gratuitement, instantane.

# Mots-cles -> symbole Binance
_SYMBOLUMS_CRYPTO = {
    "bitcoin": "BTCUSDT", "btc": "BTCUSDT",
    "ethereum": "ETHUSDT", "eth": "ETHUSDT", "ether": "ETHUSDT",
    "solana": "SOLUSDT", "sol": "SOLUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT", "ripple": "XRPUSDT",
    "cardano": "ADAUSDT", "ada": "ADAUSDT",
    "dogecoin": "DOGEUSDT", "doge": "DOGEUSDT",
}

# Symbole Binance -> id CoinGecko (fallback si Binance bloque la localisation)
_COINGECKO_ID = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin",
}

_MOTS_PRIX = ["prix", "prix de", "combien coute", "cote combien", "vaut combien", "cours", "cours actuel", "cours du"]

def _prix_binance_api(symbole):
    """Recupere le prix temps reel via l'API publique Binance (peut etre bloque: 451)."""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbole}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "symbole": symbole,
            "prix": float(d["lastPrice"]),
            "variation": float(d["priceChangePercent"]),
            "haut": float(d["highPrice"]),
            "bas": float(d["lowPrice"]),
            "volume": float(d["quoteVolume"]),
        }
    except Exception:
        return None

def _prix_coingecko_api(symbole):
    """Fallback CoinGecko (accessible partout, prix temps reel aussi)."""
    try:
        cg_id = _COINGECKO_ID.get(symbole)
        if not cg_id:
            return None
        url = (f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}"
               f"&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true")
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json().get(cg_id, {})
        if not d:
            return None
        return {
            "symbole": symbole,
            "prix": float(d.get("usd", 0)),
            "variation": float(d.get("usd_24h_change", 0)),
            "haut": 0.0,  # CoinGecko simple/price ne donne pas high/low directement
            "bas": 0.0,
            "volume": float(d.get("usd_24h_vol", 0)),
        }
    except Exception:
        return None

def prix_binance(symbole):
    """Recupere le prix temps reel: Binance d'abord, CoinGecko en fallback."""
    data = _prix_binance_api(symbole)
    if data:
        return data
    return _prix_coingecko_api(symbole)

def detecter_question_prix(question):
    """Si la question porte sur le prix d'un crypto connu, retourne le symbole Binance.
    Sinon retourne None (la question est traitee normalement par l'IA)."""
    q = question.lower()
    # Il faut qu'il y ait un mot de prix ET un crypto reconnu
    if not any(m in q for m in _MOTS_PRIX):
        return None
    for nom, symbole in _SYMBOLUMS_CRYPTO.items():
        # match sur mot entier pour eviter "ada" dans "adaptation"
        import re as _re2
        if _re2.search(rf"\b{_re2.escape(nom)}\b", q):
            return symbole
    return None

def reponse_prix(question, symbole):
    """Genere une reponse formatee avec le prix temps reel Binance."""
    data = prix_binance(symbole)
    if not data:
        return None  # echec -> laisser l'IA repondre
    prix = data["prix"]
    var = data["variation"]
    fleche = "📈" if var >= 0 else "📉"
    # Conversion EUR approx (USDT ~ USD, ~0.92 EUR)
    prix_eur = prix * 0.92
    sens = "hausse" if var >= 0 else "baisse"
    nom = symbole.replace("USDT", "")
    lignes = [
        f"{fleche} **Prix {nom} (temps reel)**\n\n",
        f"• Prix actuel : **{prix:,.2f} $** (~{prix_eur:,.2f} €)\n",
        f"• Variation 24h : **{var:+.2f}%** ({sens})\n",
    ]
    if data["haut"] > 0:
        lignes.append(f"• Haut 24h : {data['haut']:,.2f} $\n")
    if data["bas"] > 0:
        lignes.append(f"• Bas 24h : {data['bas']:,.2f} $\n")
    if data["volume"] > 0:
        lignes.append(f"• Volume 24h : {data['volume']:,.0f} $\n")
    lignes.append("\n_Source: API publique temps reel (sans IA)._")
    return "".join(lignes)

def disponible(modele):
    cles = {"chatgpt":OPENAI_API_KEY,"claude":ANTHROPIC_API_KEY,"gemini":GEMINI_API_KEY,"perplexity":PERPLEXITY_API_KEY}
    if not cles.get(modele):
        return False
    # Un provider en cooldown est considere comme non disponible -> routeur/critiqueur/fallback l'evitent
    if _en_cooldown(modele):
        return False
    return True

def meilleur_defaut():
    # Ordre prefere: perplexity (fiable, sonar) > gemini > claude > chatgpt
    for m in ["perplexity","gemini","claude","chatgpt"]:
        if disponible(m):
            return m
    return "gemini"

# ============================================
# ROUTAGE
# ============================================
def router(question):
    q = question.lower()
    if any(w in q for w in ["actualite","prix","aujourd","news","recent","cours","meteo","tendance","market","bitcoin","btc","ethereum","solana"]):
        return "perplexity" if disponible("perplexity") else meilleur_defaut()
    # Claude UNIQUEMENT pour les questions vraiment techniques (code, bug, optimisation)
    # -> appele moins souvent, donc moins de rate-limits tier 1
    if any(w in q for w in ["bug","erreur python","fonction","optimise","optimise mon code","debogage","traceback","syntaxerror"]):
        return "claude" if disponible("claude") else meilleur_defaut()
    if any(w in q for w in ["ecris","redige","idee","cree","traduis","tweet","post","article"]):
        return "chatgpt" if disponible("chatgpt") else meilleur_defaut()
    return "gemini" if disponible("gemini") else meilleur_defaut()

# ============================================
# RAISONNEMENT EN 2 TEMPS (planification pour questions complexes)
# ============================================
MOTS_COMPLEXES = ["explique", "compare", "analyse", "strategie", "comment", "pourquoi",
                  "etapes", "plan", "optimise", "construis", "detailler", "difference",
                  "avantages", "inconvenients", "guide", "marche par marche", "ameliorer"]

def est_complexe(question):
    if len(question) > 80:
        return True
    q = question.lower()
    if any(w in q for w in MOTS_COMPLEXES):
        return True
    if question.count("?") > 1:
        return True
    return False

def planifier(question):
    """Etape 1: planifie la reponse (que couvrir, quelles infos necessaires)."""
    memoire = instruction_memoire()
    lecons = lecons_recentes()
    prompt = (
        f"Un utilisateur va poser cette question a une IA:\n{question}\n\n"
        f"{memoire}{lecons}"
        f"Produis un PLAN concis pour y repondre parfaitement. Liste:\n"
        f"- Les points cles a couvrir\n"
        f"- Les informations necessaires (donnees, exemples, etapes)\n"
        f"- Les pieges a eviter\n"
        f"Sois bref (max 120 mots). Pas de bla-bla, juste le plan."
    )
    plan_modele = choisir_critiqueur("perplexity")
    try:
        plan = MODELS[plan_modele](prompt)
        if plan.startswith("[Erreur") or plan.startswith("["):
            return "", plan_modele
        return plan, plan_modele
    except:
        return "", plan_modele

# ============================================
# AUTO-CRITIQUE (le coeur de l'intelligence)
# ============================================
def charger_lecons():
    if os.path.exists(FICHIER_LECONS):
        try:
            with open(FICHIER_LECONS, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def sauver_lecons(lecons):
    with open(FICHIER_LECONS, "w") as f:
        json.dump(lecons, f, ensure_ascii=False, indent=2)

def lecons_recentes():
    """Retourne les 5 dernieres lecons apprises pour eviter de repeter les memes erreurs."""
    lecons = charger_lecons()
    if not lecons:
        return ""
    recentes = lecons[-5:]
    texte = " | ".join(l["contenu"][:150] for l in recentes)
    return f"LECONS APPRISES (evite ces erreurs): {texte}\n"

def choisir_critiqueur(modele_reponse):
    """Choisit une IA differente pour critiquer (croise les modeles).
    Claude en DERNIER recours pour le critique -> evite de saturer son quota tier 1."""
    ordre = ["perplexity","gemini","chatgpt","claude"]
    for m in ordre:
        if m != modele_reponse and disponible(m):
            return m
    return modele_reponse

def critiquer(question, reponse, modele_reponse):
    """Etape 1: une IA differente critique la reponse (erreurs, manques, vagueutes)."""
    lecons = lecons_recentes()
    prompt = (
        f"Tu es un critique rigoureux. Analyse cette reponse de facon critique et honnete.\n\n"
        f"QUESTION POSEE: {question}\n\n"
        f"REPONSE A ANALYSER: {reponse}\n\n"
        f"{lecons}"
        f"Identifie de facon concise et directe:\n"
        f"1. Les erreurs factuelles ou approximations (chiffres, dates, noms)\n"
        f"2. Les informations importantes manquantes\n"
        f"3. Les passages vagues, non verifies ou trop generaux\n"
        f"4. Les conseils potentiellement mauvais ou risques\n\n"
        f"Reponds en liste numerotee. Si la reponse est solide, dis-le et liste seulement les ameliorations mineures. "
        f"Sois bref (max 150 mots)."
    )
    critiqueur = choisir_critiqueur(modele_reponse)
    try:
        c = MODELS[critiqueur](prompt)
        if c.startswith("[Erreur") or c.startswith("["):
            return "", critiqueur
        return c, critiqueur
    except:
        return "", critiqueur

def ameliorer(question, reponse, critique, modele_reponse, critiqueur):
    """Etape 2: on reecrit la reponse en corrigeant chaque probleme identifie."""
    prompt = (
        f"QUESTION INITIALE: {question}\n\n"
        f"REPONSE INITIALE: {reponse}\n\n"
        f"CRITIQUE RECUE (de {critiqueur}):\n{critique}\n\n"
        f"Tache: Produis une reponse finale MEILLEURE et plus complete.\n"
        f"- Corrige chaque probleme souligne dans la critique.\n"
        f"- Garde les bonnes informations de la reponse initiale.\n"
        f"- Ajoute les informations manquantes importantes.\n"
        f"- Sois precis, concret et utile.\n"
        f"- Reponds directement au utilisateur, sans parler de la critique.\n"
        f"REPONSE FINALE:"
    )
    # On utilise une IA differente du critiqueur pour la reecriture (3e oeil si possible)
    ordre = [modele_reponse, "gemini", "claude", "perplexity", "chatgpt"]
    modele_reecriture = None
    for m in ordre:
        if m != critiqueur and disponible(m):
            modele_reecriture = m
            break
    if not modele_reecriture:
        modele_reecriture = critiqueur
    try:
        r = MODELS[modele_reecriture](prompt)
        if r.startswith("[Erreur") or r.startswith("["):
            return reponse, modele_reecriture
        return r, modele_reecriture
    except:
        return reponse, modele_reecriture

def extraire_lecon(question, critique):
    """Etape 3: si la critique revele un probleme recurrent, on l'apprend pour l'avenir."""
    if not critique or len(critique) < 20:
        return
    prompt = (
        f"Voici une critique faite a une IA:\n{critique}\n\n"
        f"Contexte de la question: {question[:150]}\n\n"
        f"Extrai UNE seule lecon generale et actionnable que l'IA devrait retenir pour s'ameliorer "
        f"(max 120 caracteres). Si la critique ne revele rien de generalisable, reponds 'RIEN'."
    )
    try:
        lecon = gemini(prompt)
        if lecon and not lecon.startswith("[") and "RIEN" not in lecon[:10]:
            lecon = lecon.strip().replace("\n"," ")[:150]
            lecons = charger_lecons()
            existants = [l.get("contenu","") for l in lecons]
            if lecon not in existants and len(lecons) < 50:
                lecons.append({"date": datetime.now().strftime("%Y-%m-%d"), "contenu": lecon})
                sauver_lecons(lecons)
    except:
        pass

# ============================================
# AGENT PRINCIPAL
# ============================================
HISTORIQUE = []

def charger_historique():
    """Charge l'historique de conversation persiste (survit aux redemarrages)."""
    if os.path.exists(FICHIER_HISTORIQUE):
        try:
            with open(FICHIER_HISTORIQUE, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def sauver_historique(historique):
    """Sauvegarde l'historique (tronque aux _HISTORIQUE_MAX derniers echanges)."""
    try:
        with open(FICHIER_HISTORIQUE, "w") as f:
            json.dump(historique[-_HISTORIQUE_MAX:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [sauvegarde historique impossible: {e}]", end="", flush=True)

def _critique_positive(critique):
    """Detecte si la critique est globalement positive (reponse solide, rien a corriger de grave)."""
    if not critique:
        return True
    c = critique.lower()
    positifs = ["solide", "aucune erreur", "rien a signaler", "tres bien", "excellente",
                "pas d'erreur", "aucun probleme", "correcte", "reponse est bonne",
                "ameliorations mineures", "rien a redire", "bonne reponse"]
    return any(p in c for p in positifs)

# Charge l'historique persiste au demarrage
HISTORIQUE = charger_historique()

def appeler_ia(modele, prompt, tentative=1):
    reponse = MODELS[modele](prompt)
    if reponse.startswith("[Erreur") and tentative < 2 and disponible(modele):
        # On ne retry que si le modele est toujours disponible (pas en cooldown apres un 429)
        print(f"  -> {modele} a echoue, retry...", end="", flush=True)
        return appeler_ia(modele, prompt, tentative+1)
    if reponse.startswith("[Erreur"):
        alternatives = [m for m in ["perplexity","gemini","claude","chatgpt"] if m != modele and disponible(m)]
        for alt in alternatives:
            print(f"  -> bascule sur {alt}...", end="", flush=True)
            reponse = MODELS[alt](prompt)
            if not reponse.startswith("[Erreur"):
                return reponse, alt
    return reponse, modele

def agent(question, reflechir=True):
    # === Court-circuit prix crypto: pas besoin d'IA, Binance direct ===
    # -> reponse instantanee, 100% temps reel, 0 hallucination
    symbole_prix = detecter_question_prix(question)
    if symbole_prix:
        print(f"  -> Prix {symbole_prix} via Binance...", end="", flush=True)
        rep_prix = reponse_prix(question, symbole_prix)
        if rep_prix:
            print(f" (temps reel)")
            HISTORIQUE.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "q": question, "r": rep_prix})
            sauver_historique(HISTORIQUE)
            return {"final": rep_prix, "mode": "binance-live", "modele": "binance", "extrait": False, "critique": ""}
        print(f" (echec -> IA)")

    print(f"  -> Routage...", end="", flush=True)
    modele = router(question)
    print(f" {modele}")

    extrait = extraire_et_memoriser(question)

    # Raisonnement en 2 temps: planification pour les questions complexes
    plan = ""
    plan_modele = ""
    if est_complexe(question):
        print(f"  -> Planification...", end="", flush=True)
        plan, plan_modele = planifier(question)
        if plan:
            print(f" ({plan_modele})", end="", flush=True)

    instruction = instruction_memoire()
    historique_text = "\n".join(f"Q: {h['q']}\nR: {h['r'][:150]}" for h in HISTORIQUE[-3:])
    parts = []
    if instruction:
        parts.append(instruction)
    if historique_text:
        parts.append("CONVERSATION RECENTE:\n" + historique_text)
    if plan:
        parts.append("PLAN A SUIVRE POUR REPONDRE (respecte cette structure):\n" + plan)
    parts.append("QUESTION ACTUELLE: " + question)
    prompt_final = "\n".join(parts)

    reponse, modele_utilise = appeler_ia(modele, prompt_final)

    critique = ""
    critiqueur = ""
    ameliore = False
    if reflechir and len(reponse) > 80 and not reponse.startswith("[Erreur"):
        print(f"  -> Critique...", end="", flush=True)
        critique, critiqueur = critiquer(question, reponse, modele_utilise)
        if critique:
            print(f" ({critiqueur})", end="", flush=True)
            # Skip l'etape d'amelioration si la critique est positive (reponse deja solide)
            # -> economise un appel IA et accelere fortement la reponse
            if _critique_positive(critique):
                print(f"  -> reponse solide, amelioration skip", end="", flush=True)
            else:
                print(f"  -> Amelioration...", end="", flush=True)
                # Lance l'amelioration ET l'extraction de lecon EN PARALLELE
                # (les deux ne dependent que de la critique, pas l'une de l'autre)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futur_reecr = pool.submit(ameliorer, question, reponse, critique, modele_utilise, critiqueur)
                    pool.submit(extraire_lecon, question, critique)  # fire-and-forget
                    nouvelle, modele_reecr = futur_reecr.result()
                reponse = nouvelle
                ameliore = True
                print(f" ({modele_reecr})", end="", flush=True)
        else:
            # Pas de critique recue: on extrait quand meme la lecon en arriere-plan
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(extraire_lecon, question, critique)

    HISTORIQUE.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "q": question, "r": reponse})
    sauver_historique(HISTORIQUE)  # persistance: l'historique survit aux redemarrages
    mode_str = modele_utilise
    if reflechir and critique:
        mode_str += f" + critique({critiqueur})"
        if ameliore:
            mode_str += " + amelioration"
    return {"final": reponse, "mode": mode_str, "modele": modele_utilise, "extrait": extrait, "critique": critique}

def notify_ifft(title, message):
    if not IFTTT_WEBHOOK:
        return
    try:
        requests.post(IFTTT_WEBHOOK, json={"value1":title,"value2":message[:1500]}, timeout=15)
    except:
        pass

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    if "--reset-memoire" in sys.argv:
        sauver_memoire({"profil": [], "interets": [], "objectifs": [], "apprentissages": [], "preferences": []})
        print("Memoire reinitialisee.")
        sys.exit(0)
    if "--reset-lecons" in sys.argv:
        sauver_lecons([])
        print("Lecons reinitialisees.")
        sys.exit(0)
    reflechir = "--sans-reflexion" not in sys.argv  # reflexion activee par defaut
    print("="*50)
    print("AGENT IA v7.3 - prix crypto temps reel Binance + cooldown")
    print("="*50)
    m = charger_memoire()
    total = sum(len(m[k]) for k in m)
    lecons = charger_lecons()
    print(f"Memoire: {total} elements | Lecons apprises: {len(lecons)} | Historique: {len(HISTORIQUE)} echanges")
    ias = [name for name in ["perplexity","gemini","claude","chatgpt"] if disponible(name)]
    print(f"IA configurees: {', '.join(ias) if ias else 'AUCUNE'}")
    if lecons:
        print(f"Derniere lecon: {lecons[-1]['contenu']}")
    print("")

    questions = [
        "Je m'appelle et je suis interesse par le trading crypto et les bots Python",
        "Quel est le prix du Bitcoin aujourd'hui ?",
        "Donne-moi une strategie simple adaptee a mon profil et mes interets"
    ]
    for q in questions:
        print(f"\n? {q}")
        res = agent(q, reflechir=reflechir)  # reflexion ON par defaut
        if res["extrait"]:
            print(f"  (memoire mise a jour automatiquement)")
        print(f"[{res['mode']}]")
        print(res["final"][:900])
        if res["critique"]:
            print(f"  >> critique: {res['critique'][:200]}")
        notify_ifft("Agent IA", res["final"])

    print("\n" + "="*50)
    m2 = charger_memoire()
    lecons2 = charger_lecons()
    print(f"Memoire finale: {sum(len(m2[k]) for k in m2)} elements | Lecons: {len(lecons2)}")
