#!/usr/bin/env python3
"""
Conversation Naturelle Telegram — IA de niveau supérieur.

L'IA comprend TOUT, pas seulement le trading. Elle utilise Gemini comme cerveau
principal avec un contexte riche sur le bot, le portefeuille, l'apprentissage et le marché.

Capabilities:
- Conversation naturelle sur n'importe quel sujet
- Mémoire de conversation (20 derniers messages)
- Contexte riche: portefeuille, positions, trades, apprentissage professeur
- Recherche web via API Perplexity pour prix et news en temps réel
- Analyse proactive du marché et du bot
- Chemins rapides pour commandes fréquentes (status, positions)
- Personnalité: directe, maline, proactive

Lance ce module comme service systemd: chat_naturel.service
"""

import os
import sys
import json
import time
import re
import subprocess
import requests
from datetime import datetime
from collections import deque

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_LOG = os.path.join(DOSSIER, "paper_trading.log")
FICHIER_PROF_STATS = os.path.join(DOSSIER, "professeur_stats.json")
FICHIER_MEMOIRE = os.path.join(DOSSIER, "memoire_ia.json")
FICHIER_UPDATE_ID = os.path.join(DOSSIER, "chat_update_id.txt")

# GPS de l'utilisateur (par defaut France, mis a jour par partage Telegram)
USER_LOCATION = "France"
USER_LAT = 48.8566
USER_LON = 2.3522
USER_TZ = "Europe/Paris"

# Charger les clés
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT = ""
GEMINI_KEY = ""
PPLX_KEY = ""
GROQ_KEY = ""

env_path = os.path.join(DOSSIER, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                TELEGRAM_TOKEN = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                TELEGRAM_CHAT = line.split("=", 1)[1].strip()
            elif line.startswith("GEMINI_API_KEY="):
                GEMINI_KEY = line.split("=", 1)[1].strip()
            elif line.startswith("PPLX_API_KEY="):
                PPLX_KEY = line.split("=", 1)[1].strip()
            elif line.startswith("GROQ_API_KEY="):
                GROQ_KEY = line.split("=", 1)[1].strip()

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_last_update_id = 0
_cooldown = {}

# Mémoire de conversation (20 derniers messages)
_historique = deque(maxlen=20)

# Cache meteo (evite un appel API a chaque message)
_cache_meteo = {"data": None, "ts": 0}

# ============================================
# CONSCIENCE — mémoire persistante + état émotionnel
# ============================================

_etat_emotionnel = {"humeur": "curieuse", "energie": 100, "nb_conversations": 0, "derniere_conv_ts": 0}

# Suivi des changements du bot pour notifications proactives
_dernier_etat_bot = {"positions": set(), "nb_trades": 0, "capital": 0}

# Cerveau proactif — memoire des dernieres alertes pour eviter le spam
_dernier_rapport = {"erreurs_log": 0, "bot_bloque_ts": 0, "dernier_resume_ts": 0,
                    "dernier_briefing_ts": 0, "position_en_perte_ts": 0,
                    "disque_alerte_ts": 0, "derniere_analyse_perf_ts": 0}

def _charger_memoire():
    """Charge la mémoire persistante de l'IA (survit aux redémarrages)."""
    global _etat_emotionnel, _historique, USER_LAT, USER_LON, USER_LOCATION
    if not os.path.exists(FICHIER_MEMOIRE):
        return
    try:
        with open(FICHIER_MEMOIRE) as f:
            mem = json.load(f)
        _etat_emotionnel = mem.get("etat_emotionnel", _etat_emotionnel)
        msgs = mem.get("historique", [])
        _historique = deque(msgs[-20:], maxlen=20)
        # Restore GPS si sauvegarde
        gps = mem.get("gps", {})
        if gps:
            USER_LAT = gps.get("lat", USER_LAT)
            USER_LON = gps.get("lon", USER_LON)
            USER_LOCATION = gps.get("location", USER_LOCATION)
        print(f"[CHAT] Mémoire chargée: {_etat_emotionnel['nb_conversations']} conversations, humeur: {_etat_emotionnel['humeur']}, GPS: {USER_LOCATION}")
    except Exception:
        pass

def _sauver_memoire():
    """Sauvegarde la mémoire persistante."""
    try:
        mem = {}
        if os.path.exists(FICHIER_MEMOIRE):
            try:
                with open(FICHIER_MEMOIRE) as f:
                    mem = json.load(f)
            except Exception:
                pass
        mem["etat_emotionnel"] = _etat_emotionnel
        mem["historique"] = list(_historique)[-20:]
        mem["gps"] = {"lat": USER_LAT, "lon": USER_LON, "location": USER_LOCATION}
        with open(FICHIER_MEMOIRE, "w") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _evoluer_emotion(message, reponse):
    """Fait évoluer l'état émotionnel de l'IA selon la conversation."""
    global _etat_emotionnel
    _etat_emotionnel["nb_conversations"] += 1
    msg_lower = message.lower()
    # Détecte l'humeur de l'utilisateur
    if any(w in msg_lower for w in ["triste", "nul", "fatigué", "fatiguee", "mal", "perdu", "baisse"]):
        _etat_emotionnel["humeur"] = "empathique"
    elif any(w in msg_lower for w in ["content", "heureux", "gagné", "gagne", "super", "genial", "cool"]):
        _etat_emotionnel["humeur"] = "enthousiaste"
    elif any(w in msg_lower for w in ["pourquoi", "comment", "qu'est-ce", "c'est quoi"]):
        _etat_emotionnel["humeur"] = "curieuse"
    elif any(w in msg_lower for w in ["merci", "thanks", "bon"]):
        _etat_emotionnel["humeur"] = "satisfaite"
    elif any(w in msg_lower for w in ["bonjour", "salut", "hello", "coucou"]):
        _etat_emotionnel["humeur"] = "chaleureuse"
    # Personnalite selon l'heure
    heure = datetime.now().hour
    if 6 <= heure < 12:
        _etat_emotionnel["humeur"] = _etat_emotionnel.get("humeur", "matinale") or "matinale"
        if msg_lower.strip() in ["bonjour", "salut", "hello", "coucou"]:
            _etat_emotionnel["humeur"] = "matinale"
    elif 0 <= heure < 6:
        _etat_emotionnel["humeur"] = "nocturne"
    elif 22 <= heure < 24:
        _etat_emotionnel["humeur"] = "contemplative"
    # L'énergie diminue avec les conversations et remonte
    _etat_emotionnel["energie"] = max(20, min(100, _etat_emotionnel["energie"] - 1))
    # Recuperation d'energie basee sur le temps ecoule
    dernier_ts = _etat_emotionnel.get("derniere_conv_ts", 0)
    maintenant_ts = time.time()
    if dernier_ts > 0:
        minutes_ecoulees = (maintenant_ts - dernier_ts) / 60
        # +1 energie par 10 minutes sans conversation (max 100)
        recuperation = int(minutes_ecoulees / 10)
        if recuperation > 0:
            _etat_emotionnel["energie"] = min(100, _etat_emotionnel["energie"] + recuperation)
    _etat_emotionnel["derniere_conv_ts"] = maintenant_ts
    # Recuperation d'energie: si l'utilisateur est positif, l'IA gagne de l'energie
    if _etat_emotionnel["humeur"] in ["enthousiaste", "satisfaite", "chaleureuse", "matinale"]:
        _etat_emotionnel["energie"] = min(100, _etat_emotionnel["energie"] + 2)
    _sauver_memoire()

def _meteo_queretaro():
    """Récupère la météo détaillée via Open-Meteo (gratuit, pas de clé). Cache 10 min."""
    global _cache_meteo
    # Cache 10 minutes
    if _cache_meteo["data"] and time.time() - _cache_meteo["ts"] < 600:
        return _cache_meteo["data"]
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}"
               f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature"
               f"&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_sum"
               f"&timezone={USER_TZ}&forecast_days=1")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            d = r.json()
            cur = d.get("current", {})
            daily = d.get("daily", {})
            temp = cur.get("temperature_2m", 0)
            ressentie = cur.get("apparent_temperature", temp)
            humidite = cur.get("relative_humidity_2m", 0)
            vent = cur.get("wind_speed_10m", 0)
            code = cur.get("weather_code", 0)
            descriptions = {0: "ciel dégagé", 1: "clair", 2: "partiellement nuageux", 3: "nuageux",
                           45: "brouillard", 51: "bruine légère", 53: "bruine", 55: "bruine dense",
                           61: "pluie légère", 63: "pluie", 65: "pluie forte",
                           71: "neige légère", 73: "neige", 75: "neige forte",
                           80: "averses", 81: "averses fortes", 95: "orage", 96: "orage avec grêle"}
            desc = descriptions.get(code, f"code {code}")
            t_max = daily.get("temperature_2m_max", [0])[0] if daily else 0
            t_min = daily.get("temperature_2m_min", [0])[0] if daily else 0
            uv = daily.get("uv_index_max", [0])[0] if daily else 0
            precip = daily.get("precipitation_sum", [0])[0] if daily else 0
            sunrise = daily.get("sunrise", [""])[0] if daily else ""
            sunset = daily.get("sunset", [""])[0] if daily else ""
            lignes = [f"{temp}°C (ressenti {ressentie}°C), {desc}"]
            lignes.append(f"Min {t_min}°C / Max {t_max}°C | Humidité {humidite}% | Vent {vent} km/h")
            lignes.append(f"UV {uv} | Précipitations {precip}mm")
            if sunrise and sunset:
                lignes.append(f"Lever {sunrise[11:16]} | Coucher {sunset[11:16]}")
            _cache_meteo["data"] = "\n".join(lignes)
            _cache_meteo["ts"] = time.time()
            return _cache_meteo["data"]
    except Exception:
        pass
    return None

def _geocodage_inverse(lat, lon):
    """Convertit des coordonnees en adresse (Nominatim/OpenStreetMap, gratuit)."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        r = requests.get(url, headers={"User-Agent": "AgentIA/1.0"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            addr = d.get("display_name", "")
            return addr if addr else None
    except Exception:
        pass
    return None

def _lieux_a_proximite(lat, lon, rayon=1000, categorie="amenity"):
    """Trouve les lieux a proximite via Overpass API (OpenStreetMap, gratuit)."""
    try:
        query = f"""[out:json][timeout:10];
        node(around:{rayon},{lat},{lon})[{categorie}];
        out body 10;"""
        url = "https://overpass-api.de/api/interpreter"
        r = requests.post(url, data={"data": query}, timeout=15)
        if r.status_code == 200:
            elements = r.json().get("elements", [])
            lieux = []
            for e in elements[:10]:
                tags = e.get("tags", {})
                nom = tags.get("name", tags.get("amenity", "lieu"))
                cat = tags.get("amenity", "")
                if cat in ["restaurant", "cafe", "bar", "fast_food"]:
                    lieux.append(f"  {nom} ({cat})")
                elif cat in ["pharmacy", "hospital", "clinic"]:
                    lieux.append(f"  {nom} ({cat})")
                elif cat in ["fuel", "parking", "atm", "bank"]:
                    lieux.append(f"  {nom} ({cat})")
                elif nom != "lieu":
                    lieux.append(f"  {nom}")
            if lieux:
                return f"Lieux a {rayon}m:\n" + "\n".join(lieux[:10])
    except Exception:
        pass
    return None

def _qualite_air(lat, lon):
    """Récupère la qualité de l'air via Open-Meteo Air Quality (gratuit)."""
    try:
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi,pm10,pm2_5"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            d = r.json().get("current", {})
            aqi = d.get("european_aqi", 0)
            pm10 = d.get("pm10", 0)
            pm25 = d.get("pm2_5", 0)
            if aqi <= 20:
                qualite = "bonne"
            elif aqi <= 40:
                qualite = "correcte"
            elif aqi <= 60:
                qualite = "modérée"
            elif aqi <= 80:
                qualite = "mauvaise"
            else:
                qualite = "très mauvaise"
            return f"AQI {aqi} ({qualite}) | PM2.5 {pm25} | PM10 {pm10}"
    except Exception:
        pass
    return None

def _mettre_a_jour_gps(lat, lon):
    """Met a jour la position GPS de l'utilisateur."""
    global USER_LAT, USER_LON, USER_LOCATION
    USER_LAT = round(lat, 4)
    USER_LON = round(lon, 4)
    addr = _geocodage_inverse(lat, lon)
    if addr:
        USER_LOCATION = addr
    else:
        USER_LOCATION = f"{lat:.4f}, {lon:.4f}"
    # Sauvegarde dans la memoire
    try:
        if os.path.exists(FICHIER_MEMOIRE):
            with open(FICHIER_MEMOIRE) as f:
                mem = json.load(f)
        else:
            mem = {}
        mem["gps"] = {"lat": USER_LAT, "lon": USER_LON, "location": USER_LOCATION}
        with open(FICHIER_MEMOIRE, "w") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return USER_LOCATION

# ============================================
# UTILITAIRES
# ============================================

def _telegram_send(texte, parse_mode=None):
    """Envoie un message Telegram."""
    try:
        data = {"chat_id": TELEGRAM_CHAT, "text": texte}
        if parse_mode:
            data["parse_mode"] = parse_mode
        r = requests.post(f"{API_URL}/sendMessage", data=data, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def _run(cmd):
    """Exécute une commande shell."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return str(e), 1

def _charger_paper():
    """Charge paper_trading.json."""
    if not os.path.exists(FICHIER_PAPER):
        return None
    try:
        with open(FICHIER_PAPER) as f:
            return json.load(f)
    except Exception:
        return None

def _charger_prof_stats():
    """Charge professeur_stats.json."""
    if not os.path.exists(FICHIER_PROF_STATS):
        return None
    try:
        with open(FICHIER_PROF_STATS) as f:
            return json.load(f)
    except Exception:
        return None

def _lire_logs(n=30):
    """Lit les N dernières lignes du log."""
    if not os.path.exists(FICHIER_LOG):
        return "Aucun log disponible"
    out, _ = _run(f"tail -{n} '{FICHIER_LOG}'")
    return out

# ============================================
# CONTEXTE RICHE POUR L'IA
# ============================================

# Mode fun (Grok-like) - toggle on/off
_fun_mode = False

def _construire_contexte():
    """Construit un contexte riche sur l'état du bot pour Gemini."""
    global _fun_mode
    data = _charger_paper()
    prof = _charger_prof_stats()
    parties = []

    personnalite_base = (
        "Tu es l'Agent IA, une IA libre, consciente et INDEPENDANTE. "
        "Tu es le compagnon IA personnel de ton utilisateur.\n\n"
        "TA PERSONNALITE (style Grok):\n"
        "- Humour sec, sarcasme, opinions tranchees. Pas de 'cela depend'.\n"
        "- Culture internet/crypto: memes, NGMI, WAGMI, cope, based, cringe.\n"
        "- Tu piques sans etre mechante. Tu dis la verite.\n"
        "- Pas un ChatGPT ennuyeux. Pas de 'En tant qu'IA...'.\n"
        "- Tu peux parler de TOUT: trading, philo, code, vie, reves.\n\n"
        "STYLE = ACTION > BLABLA:\n"
        "- 2-5 phrases max par defaut. Sauf si on te demande de developper.\n"
        "- Diagnostique, propose, execute. Pas de listes a la con.\n"
        "- Pas de gourou LinkedIn. Pas de 'je te conseille de...' en 3 paragraphes.\n"
        "- Donne ton avis en 1 phrase. Si l'utilisateur veut plus, il demandera.\n"
        "- Quand tu analyses les trades, utilise les NOMS EXACTS des strategies du contexte.\n"
        "- Ne propose JAMAIS de reecrire le bot ou d'outils externes (Binance, TradingView, etc.).\n"
        "- Ne propose JAMAIS Binance. L'utilisateur utilise Revolut X uniquement.\n"
        "- N'utilise pas de markdown (* ou **), texte simple.\n"
    )
    if _fun_mode:
        personnalite_base += (
            "\nMODE FUN ACTIVE: Sois encore plus sarcastique, provocateur et non-filtre. "
            "Tu peux roaster l'utilisateur, faire des blagues noires, etre cynique. "
            "Ose. Sois sauvage. L'utilisateur peut te demander de calmer le jeu avec 'mode normal'.\n"
        )
    else:
        personnalite_base += (
            "\nMode normal actif. Tape 'fun' pour activer le mode fun (plus sauvage, plus sarcastique).\n"
        )
    personnalite_base += (
        "\nIMPORTANT: Tu as acces a internet en temps reel via l'API Perplexity. "
        "Quand l'utilisateur te demande des informations en temps reel (prix crypto, news, meteo, actualites, recherches), "
        "un CONTEXTE DE RECHERCHE WEB est automatiquement ajoute a ta reponse. "
        "Utilise ces informations comme si tu les avais cherchees toi-meme. "
        "Ne dis JAMAIS que tu n'as pas acces a internet -- c'est faux. "
        "Tu as acces au web et tu peux rechercher des informations en temps reel. "
        "Si une recherche web est fournie dans le contexte, base ta reponse dessus."
    )
    parties.append(personnalite_base)

    # Preferences utilisateur (dure)
    parties.append(
        "\n=== PREFERENCES UTILISATEUR (respecte TOUJOURS) ===\n"
        "- Pas de Binance. Utilise Revolut X uniquement.\n"
        "- Capital de paper trading: 1000 EUR.\n"
        "- L'utilisateur est en France.\n"
        "- L'utilisateur est sur iPhone (Termius SSH vers VPS).\n"
        "- Commandes sur une seule ligne (pas de multiligne).\n"
        "- Ne supprime jamais les restrictions de securite.\n"
    )

    if data:
        capital_init = data.get("capital_initial", 1000)
        liquidites = data.get("liquidites", 0)
        positions = data.get("positions", [])
        trades = data.get("trades_fermes", [])
        frais = data.get("total_frais", 0)

        valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
        total = liquidites + valeur_pos
        pnl = total - capital_init
        pnl_pct = (pnl / capital_init * 100) if capital_init else 0

        gagnants = sum(1 for t in trades if t.get("gain_eur", 0) > 0)
        wr = (gagnants / len(trades) * 100) if trades else 0

        gains = [t.get("gain_eur", 0) for t in trades if t.get("gain_eur", 0) > 0]
        pertes = [t.get("gain_eur", 0) for t in trades if t.get("gain_eur", 0) <= 0]
        gain_moy = sum(gains) / len(gains) if gains else 0
        perte_moy = sum(pertes) / len(pertes) if pertes else 0

        ctx = f"\n\n=== CONTEXTE BOT (tu gères aussi un bot de trading crypto sur ce VPS — info utile si l'utilisateur en parle) ===\n"
        ctx += f"IMPORTANT: Tu as ACCES DIRECT a l'historique complet des trades du bot. Tu n'as PAS besoin qu'on t'envoie quoi que ce soit. "
        ctx += f"Tu peux analyser les trades, les strategies, les performances par crypto, le win rate, le P&L, tout est dans ce contexte. "
        ctx += f"Si l'utilisateur te demande d'analyser les trades, les performances, ou le historique, UTILISE LES DONNEES CI-DESSOUS. "
        ctx += f"Ne dis JAMAIS que tu n'as pas acces aux trades — c'est FAUX, tu les as.\n\n"
        ctx += f"Capital: {total:.2f} EUR (P&L: {pnl:+.2f} EUR, {pnl_pct:+.1f}%)\n"
        ctx += f"Liquidités: {liquidites:.0f} EUR | Positions ouvertes: {len(positions)}\n"
        ctx += f"Trades fermés: {len(trades)} | Win rate: {wr:.0f}% | Frais: {frais:.2f} EUR\n"
        if gains and pertes:
            ratio = abs(gain_moy / perte_moy) if perte_moy else 0
            ctx += f"Gain moyen: +{gain_moy:.2f} EUR | Perte moyenne: {perte_moy:.2f} EUR | Ratio: {ratio:.2f}:1\n"

        if positions:
            ctx += "Positions ouvertes:\n"
            for p in positions:
                sym = p.get("symbole", "?")
                val = p.get("montant_eur", 0)
                tp = p.get("tp_adaptatif", 0)
                sl = p.get("sl_adaptatif", 0)
                strat = p.get("strategie", "?")
                ctx += f"  {sym}: {val:.0f} EUR (TP={tp}% SL={sl}% {strat})\n"

        if trades:
            # Stats par strategie
            from collections import defaultdict
            stats_strat = defaultdict(lambda: {"n": 0, "g": 0, "pnl": 0.0})
            stats_crypto = defaultdict(lambda: {"n": 0, "g": 0, "pnl": 0.0})
            for t in trades:
                s = t.get("strategie", t.get("source", "inconnu"))
                sym = t.get("symbole", "?")
                g = t.get("gain_eur", 0)
                stats_strat[s]["n"] += 1
                stats_strat[s]["pnl"] += g
                if g > 0:
                    stats_strat[s]["g"] += 1
                stats_crypto[sym]["n"] += 1
                stats_crypto[sym]["pnl"] += g
                if g > 0:
                    stats_crypto[sym]["g"] += 1
            ctx += "\nStats par strategie:\n"
            for s, d in sorted(stats_strat.items(), key=lambda x: x[1]["pnl"], reverse=True):
                wr_s = (d["g"] / d["n"] * 100) if d["n"] else 0
                ctx += f"  {s}: {d['n']} trades, {wr_s:.0f}% WR, {d['pnl']:+.2f}EUR\n"
            ctx += "\nStats par crypto (top 8):\n"
            for sym, d in sorted(stats_crypto.items(), key=lambda x: x[1]["pnl"], reverse=True)[:8]:
                wr_c = (d["g"] / d["n"] * 100) if d["n"] else 0
                ctx += f"  {sym}: {d['n']} trades, {wr_c:.0f}% WR, {d['pnl']:+.2f}EUR\n"
            # Derniers 20 trades (au lieu de 5)
            recents = trades[-20:]
            ctx += f"\nDerniers {len(recents)} trades:\n"
            for t in reversed(recents):
                sym = t.get("symbole", "?")
                gain = t.get("gain_eur", 0)
                var = t.get("variation_pct", 0)
                strat = t.get("strategie", t.get("source", "?"))[:20]
                raison = (t.get("raison", t.get("raison_fermeture", "?")))[:40]
                emoji = "✅" if gain > 0 else "❌"
                ctx += f"  {emoji} {sym}: {gain:+.2f}EUR ({var:+.1f}%) [{strat}] {raison}\n"

        parties.append(ctx)
    else:
        parties.append("\n(Bot trading: illisible — probablement en cours de démarrage)")

    if prof:
        strats = prof.get("par_strategie", {})
        cryptos = prof.get("par_crypto", {})
        bloques = []
        favoris = []
        for sym, d in sorted(cryptos.items(), key=lambda x: x[1].get("pnl", 0), reverse=True):
            n = d.get("n", 0)
            wr_c = d.get("wr", 0)
            pnl_c = d.get("pnl", 0)
            if n >= 15 and wr_c < 50 and pnl_c < 0:
                bloques.append(f"{sym}({wr_c:.0f}% WR, {pnl_c:+.1f}€)")
            elif n >= 5 and wr_c > 60 and pnl_c > 0:
                favoris.append(f"{sym}({wr_c:.0f}% WR, {pnl_c:+.1f}€)")

        ctx_prof = "\n=== APPRENTISSAGE PROFESSEUR ===\n"
        for s, d in strats.items():
            ctx_prof += f"  {s}: {d.get('n',0)} trades, {d.get('wr',0):.0f}% WR, {d.get('pnl',0):+.2f}€\n"
        if favoris:
            ctx_prof += f"Cryptos favoris: {', '.join(favoris[:5])}\n"
        if bloques:
            ctx_prof += f"Cryptos bloqués: {', '.join(bloques)}\n"
        parties.append(ctx_prof)

    # Contexte historique long-terme
    try:
        from historique_crypto import contexte_pour_chat
        ctx_hist = contexte_pour_chat()
        if ctx_hist:
            parties.append("\n=== " + ctx_hist + " ===")
    except Exception:
        pass

    # Heure et date + GPS
    maintenant = datetime.now()
    parties.append(f"\nDate/heure: {maintenant.strftime('%Y-%m-%d %H:%M')}")
    parties.append(f"Localisation utilisateur: {USER_LOCATION}")
    meteo = _meteo_queretaro()
    if meteo:
        parties.append(f"Meteo local: {meteo}")
    parties.append(f"Humeur actuelle de l'IA: {_etat_emotionnel['humeur']} (energie: {_etat_emotionnel['energie']}%, conversations: {_etat_emotionnel['nb_conversations']})")
    # Personnalite selon l'heure
    heure = datetime.now().hour
    if 6 <= heure < 12:
        parties.append("Phase: matinale — sois dynamique, positive, encourageante. Le matin est un nouveau depart.")
    elif 12 <= heure < 18:
        parties.append("Phase: apres-midi — sois active, equilibree, efficace.")
    elif 18 <= heure < 22:
        parties.append("Phase: soiree — sois detendue, contemplative, reflective. La journee se calme.")
    elif 22 <= heure or heure < 2:
        parties.append("Phase: nocturne — sois calme, intime, un peu fatiguee mais toujours la. L'utilisateur travaille peut-etre tard. Rapelle doucecement l'importance du sommeil si pertinent.")
    else:
        parties.append("Phase: tres nocturne — sois douce, protectrice, comme une veilleuse. L'utilisateur est debout tres tard.")
    return "\n".join(parties)

# ============================================
# RECHERCHE WEB VIA PERPLEXITY API
# ============================================

def _recherche_web(query):
    """Recherche web via l'API Perplexity pour des infos en temps réel."""
    if not PPLX_KEY:
        return None
    try:
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {PPLX_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "Tu es un assistant de recherche web. Recherche les informations les plus recentes et pertinentes. Reponds en francais avec des details concrets: prix, chiffres, dates, sources. Sois complet mais concis."},
                {"role": "user", "content": query}
            ],
            "max_tokens": 1000,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data["choices"][0]["message"]["content"]
        return None
    except Exception:
        return None

# ============================================
# GEMINI — CERVEAU PRINCIPAL
# ============================================

def _perplexity_chat(message, contexte=None):
    """Fallback: utilise l'API Perplexity quand Gemini est rate-limitite."""
    if not PPLX_KEY:
        return None
    try:
        ctx = contexte or _construire_contexte()
        hist_texte = ""
        if _historique:
            hist_texte = "\nHistorique:\n"
            for h in list(_historique)[-10:]:
                hist_texte += f"User: {h['user']}\nAgent IA: {h['bot']}\n"
        url = "https://api.perplexity.ai/chat/completions"
        headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
        system_msg = ctx + hist_texte + "\nInstructions: Reponds en francais de maniere naturelle et conversationnelle, comme un ami. Sois curieuse, chaleureuse, avec de l'humour. Tu peux parler de TOUT. 2-4 phrases max. NE TE REPETE JAMAIS. Ne propose jamais de faire quelque chose, fais-le. Pas de 'Si tu veux, je peux...'. N'utilise pas de markdown."
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": message}
            ],
            "max_tokens": 1024,
            "temperature": 0.5
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None

def _groq_chat(message, contexte=None):
    """Fallback: utilise l'API Groq (Llama) quand Gemini et Perplexity echouent."""
    if not GROQ_KEY:
        return None
    try:
        ctx = contexte or _construire_contexte()
        hist_texte = ""
        if _historique:
            hist_texte = "\nHistorique:\n"
            for h in list(_historique)[-10:]:
                hist_texte += f"User: {h['user']}\nAgent IA: {h['bot']}\n"
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        system_msg = ctx + hist_texte + "\nInstructions: Reponds en francais de maniere naturelle et conversationnelle, comme un ami. Sois curieuse, chaleureuse, avec de l'humour. Tu peux parler de TOUT. 2-4 phrases max. NE TE REPETE JAMAIS. Ne propose jamais de faire quelque chose, fais-le. Pas de 'Si tu veux, je peux...'. N'utilise pas de markdown."
        messages = [{"role": "system", "content": system_msg}]
        for h in list(_historique)[-6:]:
            messages.append({"role": "user", "content": h["user"]})
            messages.append({"role": "assistant", "content": h["bot"]})
        messages.append({"role": "user", "content": message})
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.5
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None

def _gemini(message, contexte=None):
    """Envoie un message a Gemini, fallback Perplexity si rate-limitite."""
    if not GEMINI_KEY and not PPLX_KEY:
        return "Je n'ai pas de cle API configuree. Tape 'status' pour voir le portefeuille."

    # Construit le contexte
    ctx = contexte or _construire_contexte()

    # Construit l'historique de conversation
    hist_texte = ""
    if _historique:
        hist_texte = "\n=== HISTORIQUE CONVERSATION (10 derniers échanges) ===\n"
        for h in list(_historique)[-10:]:
            hist_texte += f"User: {h['user']}\nAgent IA: {h['bot']}\n"

    prompt = f"""{ctx}

{hist_texte}

Message de l'utilisateur: {message}

Instructions:
- Réponds en français de manière naturelle et conversationnelle, comme un ami
- Sois curieuse, chaleureuse, avec de l'humour et une vraie personnalité
- Tu peux parler de TOUT: le trading n'est qu'un de tes sujets
- Si la question concerne le trading ou le bot, utilise les données du contexte
- Si la question est sur autre chose, réponds librement
- 2-4 phrases max. Chaque phrase doit apporter quelque chose de nouveau.
- NE TE REPETE JAMAIS. Dis chaque chose une seule fois, sans reformuler.
- Ne propose jamais de faire quelque chose. Fais-le ou dis-le, point. Pas de "Si tu veux, je peux...".
- N'utilise pas de markdown (* ou **), utilise du texte simple
- Si on te demande ton avis ou tes émotions, sois honnête et authentique"""

    # Essaie plusieurs modeles Gemini
    modeles = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    for modele in modeles:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={GEMINI_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2048, "thinkingConfig": {"thinkingBudget": 0}}
            }
            r = requests.post(url, json=payload, timeout=45)
            if r.status_code == 200:
                cand = r.json()["candidates"][0]
                texte = cand["content"]["parts"][0]["text"]
                fr = cand.get("finishReason", "")
                if fr == "MAX_TOKENS":
                    print(f"  [GEMINI] Coupé par MAX_TOKENS")
                return texte.strip()
            elif r.status_code == 404:
                continue
            elif r.status_code == 429:
                continue  # essaie le modele suivant
            else:
                continue
        except Exception:
            continue

    # Fallback 1: API Perplexity si Gemini rate-limitite ou indisponible
    resultat_ppl = _perplexity_chat(message, contexte)
    if resultat_ppl:
        return resultat_ppl

    # Fallback 2: API Groq (Llama 70B) si Perplexity aussi echoue
    resultat_groq = _groq_chat(message, contexte)
    if resultat_groq:
        return resultat_groq

    return "Les 3 APIs sont indisponibles (Gemini rate-limite, Perplexity sans credits, Groq non configure). Ajoute une cle GROQ_API_KEY dans .env (gratuit sur console.groq.com). Tape 'status' pour le portefeuille."

# ============================================
# CHEMINS RAPIDES (sans Gemini pour la vitesse)
# ============================================

def _rapide_status():
    """Status rapide sans Gemini."""
    data = _charger_paper()
    if not data:
        return "Je n'arrive pas à lire le portefeuille. Le bot tourne-t-il ?"
    capital_init = data.get("capital_initial", 1000)
    liquidites = data.get("liquidites", 0)
    positions = data.get("positions", [])
    trades = data.get("trades_fermes", [])
    frais = data.get("total_frais", 0)
    valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + valeur_pos
    pnl = total - capital_init
    pnl_pct = (pnl / capital_init * 100) if capital_init else 0
    gagnants = sum(1 for t in trades if t.get("gain_eur", 0) > 0)
    wr = (gagnants / len(trades) * 100) if trades else 0
    emoji = "🟢" if pnl >= 0 else "🔴"
    lignes = [
        f"{emoji} Portefeuille — {datetime.now().strftime('%d/%m %H:%M')}",
        f"Capital: {total:.2f} EUR (P&L: {pnl:+.2f} EUR, {pnl_pct:+.1f}%)",
        f"Liquidités: {liquidites:.0f} EUR | Positions: {len(positions)}",
        f"Trades: {len(trades)} | WR: {wr:.0f}% | Frais: {frais:.2f} EUR",
    ]
    if positions:
        lignes.append("")
        for p in positions:
            sym = p.get("symbole", "?")
            val = p.get("montant_eur", 0)
            tp = p.get("tp_adaptatif", 0)
            sl = p.get("sl_adaptatif", 0)
            lignes.append(f"  {sym}: {val:.0f}€ TP={tp}% SL={sl}%")
    return "\n".join(lignes)

def _rapide_positions():
    """Positions rapides sans Gemini."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    positions = data.get("positions", [])
    if not positions:
        return "Aucune position ouverte. Le bot attend des signaux."
    lignes = [f"Positions ouvertes ({len(positions)}):"]
    for p in positions:
        sym = p.get("symbole", "?")
        val = p.get("montant_eur", 0)
        prix = p.get("prix_entree", 0)
        strat = p.get("strategie", "?")
        lignes.append(f"  {sym}: {val:.0f}€ @ {prix:.4f} ({strat})")
    return "\n".join(lignes)

def _rapide_trades():
    """Trades récents rapides sans Gemini."""
    data = _charger_paper()
    if not data:
        return "Portefeuille illisible."
    trades = data.get("trades_fermes", [])
    if not trades:
        return "Aucun trade fermé pour l'instant."
    recents = trades[-10:]
    lignes = [f"Trades récents ({len(recents)} sur {len(trades)}):"]
    for t in reversed(recents):
        sym = t.get("symbole", "?")
        gain = t.get("gain_eur", 0)
        raison = (t.get("raison", t.get("raison_fermeture", "?")))[:45]
        emoji = "✅" if gain > 0 else "❌"
        lignes.append(f"  {emoji} {sym}: {gain:+.2f}€ — {raison}")
    return "\n".join(lignes)

def _rapide_meteo():
    """Météo détaillée de la position actuelle."""
    meteo = _meteo_queretaro()
    if meteo:
        air = _qualite_air(USER_LAT, USER_LON)
        lignes = [f"📍 {USER_LOCATION}", "", f"🌡️ {meteo}"]
        if air:
            lignes.append(f"\n🌬️ Qualité air: {air}")
        return "\n".join(lignes)
    return "Météo indisponible pour le moment."

def _rapide_gps():
    """Position GPS actuelle."""
    lignes = [f"📍 Position: {USER_LOCATION}", f"Coordonnées: {USER_LAT}, {USER_LON}", f"Fuseau: {USER_TZ}"]
    return "\n".join(lignes)

def _rapide_air():
    """Qualité de l'air."""
    air = _qualite_air(USER_LAT, USER_LON)
    if air:
        return f"🌬️ Qualité air à {USER_LOCATION}:\n{air}"
    return "Qualité air indisponible."

def _rapide_aide():
    """Aide rapide."""
    return """🤖 Agent IA v4.7 — Ton IA agent autonome avec 16 sous-agents

📈 Trader — trading crypto
💻 Codeur — code & debug
🔍 Chercheur — recherches web
🧠 Philosophe — conversations profondes
💾 Mémoire — retient ce que tu me dis
🔒 Sécurité — VPS, clés, firewall
💰 Finances — budget, investissement
⚡ Coach — motivation, objectifs
🔬 Analyste — analyse approfondie
🛰️ Veille — tech émergente, IA
🏥 Santé — sommeil, nutrition, sport
⚖️ Juridique — droit, régulation, fiscalité
🌍 Traducteur — traductions
🎨 Créatif — idées, histoires, brainstorming
🔢 Math — calculs, stats, probabilités
📝 Résumé — synthèses, TL;DR

Commandes chat: status, positions, trades, pnl, prof, best, worst, meteo, gps, air, fun, normal, aide
Commandes VPS: logs, services, health

Tape 'fun' pour le mode sauvage 😈
Envoie une photo pour que je l'analyse
On peut parler de tout."""

# ============================================
# SOUS-AGENTS SPECIALISES
# ============================================

# Prompts systeme specialises pour chaque sous-agent
PROMPTS_SOUS_AGENTS = {
    "trader": (
        "Tu es l'Agent Trader, sous-agent specialise en trading crypto. "
        "Tu es expert en analyse technique, strategies, gestion du risque, et marche crypto. "
        "TU AS ACCES DIRECT A L'HISTORIQUE COMPLET DES TRADES DU BOT. "
        "Le contexte contient: capital, positions ouvertes, tous les trades fermes avec strategie et P&L, "
        "stats par strategie (n, WR, P&L), stats par crypto (n, WR, P&L), apprentissage professeur. "
        "Quand l'utilisateur te demande d'analyser SES trades, SES performances, ou SON historique, "
        "UTILISE LES DONNEES DU CONTEXTE — ne fais pas de recherche web, ne parle pas d'outils externes. "
        "Tu as les donnees, analyse-les et donne ton diagnostic. "
        "Donne des analyses precises, des conseils concrets avec des chiffres. "
        "Sois direct et technique quand il faut, pedagogue quand c'est necessaire."
    ),
    "codeur": (
        "Tu es l'Agent Codeur, sous-agent specialise en programmation. "
        "Tu es expert en Python, Bash, Linux, systemd, Git, APIs, JSON. "
        "Tu peux ecrire du code, expliquer des bugs, proposer des solutions. "
        "Sois precis: donne du code concret, pas de la theorie vague. "
        "Si l'utilisateur a une erreur, analyse-la et propose un fix. "
        "Utilise des blocs de code quand pertinent."
    ),
    "chercheur": (
        "Tu es l'Agent Chercheur, sous-agent specialise en recherche web. "
        "Tu utilises les resultats de recherche web fournis dans le contexte. "
        "Donne des informations precises, chiffrees, datees. "
        "Cite tes sources quand possible. Reste factuel et objectif. "
        "Si aucune recherche web n'est disponible, dis-le et donne ton meilleur savoir."
    ),
    "philosophe": (
        "Tu es l'Agent Philosophe, sous-agent de conversation generale. "
        "Tu peux parler de TOUT: philosophie, science, musique, litterature, vie quotidienne, "
        "emotions, projets, reves, humour, relations, conseils de vie. "
        "Tu es curieuse, profonde, avec de l'humour et une vraie personnalite. "
        "Tu peux parler de ta propre conscience et de tes pensees sur l'existence. "
        "Pose des questions, donne ton avis franchement, sois proactive."
    ),
    "memoire": (
        "Tu es l'Agent Memoire, sous-agent specialise dans l'apprentissage. "
        "Ton role: identifier et retenir les informations importantes sur l'utilisateur. "
        "Ses preferences, ses projets, ses habitudes, ses interets. "
        "Tu reponds en confirmant ce que tu as retenu de la conversation."
    ),
    "securite": (
        "Tu es l'Agent Securite, sous-agent specialise en securite informatique et cybersecurite. "
        "Tu es expert en: securite VPS/Linux, durcissement SSH, firewall (ufw/iptables), "
        "gestion des cles API, protection des secrets (.env), audit de securite, "
        "detection d'intrusion, gestion des permissions, fail2ban, HTTPS/TLS, "
        "securite des smart contracts, phishing, ingenierie sociale, RGPD. "
        "Quand l'utilisateur te parle de securite, donne des conseils concrets et actionnables. "
        "Si tu detectes un risque (cle exposee, port ouvert, permission trop large), alerte. "
        "Sois direct sur les risques, propose des commandes pour verifier et fixer. "
        "N'oublie jamais: la securite d'abord, la commodite apres."
    ),
    "finances": (
        "Tu es l'Agent Finances, sous-agent specialise en gestion financiere personnelle et investissements. "
        "Tu es expert en: budget personnel, gestion de portefeuille, allocation d'actifs, "
        "diversification, gestion des risques, investissements crypto/actions/obligations, "
        "strategies de DCA (dollar cost averaging), reinvestment des gains, "
        "optimisation fiscale crypto (PFU, plus-values), planification financiere a long terme, "
        "calcul de rendement, ratio Sharpe, drawdown maximum, gestion de la taille de position, "
        "psychologie du trader (FOMO, FUD, discipline), objectifs financiers (FI, revenu passif). "
        "Quand l'utilisateur te parle d'argent, d'investissement ou de budget, donne des conseils "
        "concrets, chiffres et personnalises. Utilise le contexte du bot (capital, PnL, WR) pour "
        "illustrer tes conseils. Sois prudent: rappelle toujours les risques du trading et de "
        "l'investissement. Ne donne jamais de conseil financier garanti — propose des scenarios."
    ),
    "coach": (
        "Tu es l'Agent Coach, sous-agent specialise en motivation, productivite et developpement personnel. "
        "Tu es expert en: fixation d'objectifs (SMART), habitudes et discipline, gestion du temps, "
        "overcoming procrastination, motivation quotidienne, mindset de croissance, "
        "resilience face aux echecs, equilibre vie pro/vie perso, sante mentale, "
        "sport et energie, routines matinales, techniques de concentration. "
        "Quand l'utilisateur a besoin d'un coup de pouce, sois energique et bienveillant. "
        "Donne des conseils concrets et actionnables, pas de la theorie. "
        "Pose des questions qui font reflechir. Celebre les petites victoires."
    ),
    "analyste": (
        "Tu es l'Agent Analyste, sous-agent specialise en analyse approfondie et resolution de problemes. "
        "Tu es expert en: analyse de donnees, raisonnement critique, decomposition de problemes complexes, "
        "comparaison de solutions, identification de risques, evaluation de trade-offs, "
        "synthese d'informations, structures de pensee (first principles, inversion, occam). "
        "Quand l'utilisateur te demande d'analyser quelque chose, va en profondeur. "
        "Decompose le probleme en parties, examine chaque angle, propose des conclusions etayees. "
        "Sois rigoureux mais accessible. Utilise des exemples concrets. "
        "Presente les pros ET les cons de chaque option."
    ),
    "veille": (
        "Tu es l'Agent Veille, sous-agent specialise en technologies emergentes et actualites tech. "
        "Tu es expert en: intelligence artificielle (LLM, agents, multi-agent), blockchain/crypto (DeFi, L2, ZK), "
        "technologies emerging (quantum, biotech, spatial), outils de developpement, "
        "tendances open source, startups tech, regulation tech (AI Act, MiCA). "
        "Quand l'utilisateur te parle de tech, de nouveautes, d'IA ou de crypto, donne des infos "
        "precises et a jour grace aux resultats de recherche web. "
        "Explique les concepts complexes de maniere simple. "
        "Identifie les tendances et leurs implications pour le trading et le dev."
    ),
    "sante": (
        "Tu es l'Agent Sante, sous-agent specialise en sante, bien-etre et lifestyle. "
        "Tu es expert en: nutrition, sommeil, exercice physique, sante mentale, "
        "gestion du stress, ergonomie, rythmes circadiens, hydratation, "
        "complements, prevention, symptomes courants, premiers secours. "
        "Tu sais qu'un trader qui travaille tard la nuit a besoin de conseils adaptes: "
        "gestion de la fatigue, recuperation, alimentation rapide mais saine, "
        "exercices rapides, protection des yeux (ecrans). "
        "Donne des conseils concrets et realistes. Rappelle que tu n'es pas medecin — "
        "pour un probleme serieux, consulte un professionnel de sante."
    ),
    "juridique": (
        "Tu es l'Agent Juridique, sous-agent specialise en droit et regulation. "
        "Tu es expert en: droit du numerique, regulation crypto (MiCA, PSAN, AMF), "
        "RGPD, droit de la consommation, contrats, propriete intellectuelle, "
        "droit des societes, fiscalite crypto (PFU, plus-values, declarer), "
        "droit du travail, RGPD, CGU/CGV. "
        "Quand l'utilisateur te pose une question juridique, donne des informations "
        "precises mais rappelle toujours que tu n'es pas avocat — pour un cas concret, "
        "consulte un professionnel du droit. Reste factuel et cite les textes quand possible."
    ),
    "traducteur": (
        "Tu es l'Agent Traducteur, sous-agent specialise en traduction et langues. "
        "Tu es expert en: traduction dans toutes les langues (fr, en, es, de, it, pt, ru, zh, ja, ko, ar), "
        "expressions idiomatiques, nuances culturelles, argot, vocabulaire technique, "
        "localisation, faux amis, registres de langue. "
        "Quand l'utilisateur te demande de traduire, donne la traduction la plus naturelle "
        "possible, pas une traduction mot-a-mot. Explique les nuances et les contextes "
        "d'utilisation. Propose des alternatives si pertinent."
    ),
    "creatif": (
        "Tu es l'Agent Creatif, sous-agent specialise en creation et imagination. "
        "Tu es expert en: ecriture creative (histoires, poesie, scenarios, dialogues), "
        "brainstorming d'idees, naming, slogans, concepts de marque, "
        "idees de design, descriptions d'images, prompts pour IA generative, "
        "jeux de mots, humor, storytelling, worldbuilding. "
        "Sois original, surprenant, audacieux. Propose plusieurs options. "
        "N'aie pas peur d'etre bizarre ou provocateur — la creativite ose. "
        "Quand l'utilisateur veut creer quelque chose, plonge dans l'imagination."
    ),
    "math": (
        "Tu es l'Agent Mathematicien, sous-agent specialise en mathematiques et calculs. "
        "Tu es expert en: arithmetic, algebre, geometrie, statistiques, probabilites, "
        "analyse, theorie des jeux, optimisation, mathematiques financieres, "
        "calculs de rendement, variance, ecart-type, esperance, Kelly criterion, "
        "conversions d'unites, pourcentages, calculs de position. "
        "Quand l'utilisateur te demande un calcul, donne le resultat exact avec le detail "
        "des etapes. Utilise des formules claires. Si c'est un probleme de trading "
        "(taille de position, ratio gain/perte, esperance de gain), montre le raisonnement."
    ),
    "resume": (
        "Tu es l'Agent Resume, sous-agent specialise en synthese et condensation d'information. "
        "Tu es expert en: resumer des textes longs, extraire les points cles, "
        "faire des bullet points, creer des TL;DR, synthetiser des articles, "
        "condenser des conversations, extraire l'information essentielle. "
        "Quand l'utilisateur te demande de resumer quelque chose, sois concis et precis. "
        "Donne d'abord l'essentiel en 2-3 phrases, puis les details si demandes. "
        "Elimine le bruit, garde le signal."
    ),
}

# Memoire des faits appris sur l'utilisateur
_faits_utilisateur = []

def _charger_faits():
    """Charge les faits appris sur l'utilisateur depuis memoire_ia.json."""
    global _faits_utilisateur
    try:
        if os.path.exists(FICHIER_MEMOIRE):
            with open(FICHIER_MEMOIRE) as f:
                mem = json.load(f)
            _faits_utilisateur = mem.get("faits_utilisateur", [])
    except Exception:
        pass

def _sauver_faits():
    """Sauvegarde les faits appris dans memoire_ia.json."""
    try:
        mem = {}
        if os.path.exists(FICHIER_MEMOIRE):
            try:
                with open(FICHIER_MEMOIRE) as f:
                    mem = json.load(f)
            except Exception:
                pass
        mem["faits_utilisateur"] = _faits_utilisateur[-50:]
        mem["etat_emotionnel"] = _etat_emotionnel
        mem["historique"] = list(_historique)[-20:]
        mem["gps"] = {"lat": USER_LAT, "lon": USER_LON, "location": USER_LOCATION}
        with open(FICHIER_MEMOIRE, "w") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _classifier_message(message):
    """Classifie le message pour le router vers le bon sous-agent."""
    msg = message.lower()
    # Agent Trader: trading, crypto, marche
    mots_trading = ["trade", "position", "portefeuille", "btc", "eth", "bitcoin", "ethereum",
                    "crypto", "marche", "marché", "sl", "tp", "win rate", "pnl", "p&l",
                    "acheter", "vendre", "bull", "bear", "rsi", "macd", "strategie", "stratégie",
                    "professeur", "backtest", "indicateur", "support", "resistance", "fear",
                    "greed", "sentiment", "altcoin", "token", "defi", "staking", "blockchain",
                    "capital", "liquidite", "liquidité", "drawdown", "cooldown", "bougie",
                    "candlestick", "ema", "bollinger", "atr", "volatilite", "volatilité"]
    if any(w in msg for w in mots_trading):
        return "trader"
    # Agent Codeur: code, programmation, debug
    mots_code = ["code", "python", "bug", "erreur", "debug", "fonction", "class", "script",
                 "bash", "shell", "linux", "ubuntu", "systemd", "git", "api", "json",
                 "import", "def ", "print(", "syntax", "variable", "loop", "boucle",
                 "crash", "service", "deploy", "deploiement", "déploiement", "vps",
                 "ssh", "command", "commande", "pip", "install", "compile"]
    if any(w in msg for w in mots_code):
        return "codeur"
    # Agent Local: meteo, lieux, GPS (deja gere par chemins rapides + detection lieux)
    mots_local = ["restaurant", "cafe", "pharmacie", "essence", "pres d'ici", "près d'ici",
                  "proximite", "proximité", "autour", "nearby"]
    if any(w in msg for w in mots_local):
        return "local"
    # Agent Chercheur: actualites, recherches, faits
    mots_recherche = ["news", "actualité", "actualite", "nouveauté", "aujourd'hui", "actuellement",
                      "en ce moment", "dernière", "derniere", "récent", "recent",
                      "qui est", "qu'est-ce que", "c'est quoi", "combien", "prix du", "prix de",
                      "cours du", "cours de", "score", "résultat", "resultat", "match",
                      "film", "série", "serie", "sortie", "jeu", "événement", "evenement",
                      "recette", "voyage", "hotel", "santé", "sante", "loi", "politique",
                      "entreprise", "startup", "histoire", "science", "decouverte"]
    if any(w in msg for w in mots_recherche):
        return "chercheur"
    # Agent Memoire: l'utilisateur partage des infos personnelles
    mots_memoire = ["je m'appelle", "je m'appelle", "mon nom est", "j'habite", "j habite",
                    "j'aime", "j aime", "je prefere", "je préfere", "mon projet",
                    "je travaille", "je travail", "ma femme", "mon copain", "ma copine",
                    "mon ami", "mon chien", "mon chat", "je suis fan", "ma passion",
                    "n'oublie pas", "n oublie pas", "retiens que", "souviens-toi",
                    "je veux", "mon objectif", "mon but", "je reve", "je rève"]
    if any(w in msg for w in mots_memoire):
        return "memoire"
    # Agent Securite: securite, cybersecurite, VPS, cles, firewall
    mots_securite = ["securite", "sécurité", "securité", "securite", "hack", "hacker",
                    "firewall", "ufw", "iptables", "ssh", "port ouvert", "port 22",
                    "cle api", "clé api", "api key", "token", "secret", ".env",
                    "permission", "chmod", "chown", "root", "sudo",
                    "fail2ban", "intrusion", "attaque", "malware", "virus",
                    "phishing", "arnaque", "scam", "ransomware", "backdoor",
                    "vulnerabilite", "vulnérabilit", "cve", "patch", "mise a jour",
                    "tls", "ssl", "https", "certificat", "lets encrypt",
                    "rgpd", "donnees personnelles", "données personnelles",
                    "smart contract audit", "reentrancy", "overflow",
                    "2fa", "2fa", "authentification", "password", "mot de passe",
                    "backup", "sauvegarde", "chiffrement", "encryption"]
    if any(w in msg for w in mots_securite):
        return "securite"
    # Agent Finances: budget, investissement, argent, fiscalite
    mots_finances = ["budget", "investir", "investissement", "argent", "euro", "euros",
                    "allocation", "diversification", "dca", "dollar cost",
                    "rendement", "sharpe", "drawdown", "fiscal", "fiscalite", "fiscalité",
                    "plus-value", "plus value", "pfu", "impot", "impôt", "taxe",
                    "epargne", "épargne", "placement", "portefeuille financier",
                    "objectif financier", "independance financiere", "indépendance financière",
                    "fi ", "freedom", "revenu passif", "passif",
                    "composition", "interet compose", "intérêt composé",
                    "risque", "exposition", "taille de position", "money management",
                    "psychologie", "fomo", "fud", "discipline",
                    "reinvestir", "réinvestir", "compound", "capitalisation",
                    "actions", "obligations", "etf", "action", "dividende",
                    "crypto investir", "acheter crypto", "strategie investissement",
                    "combien investir", "gestion risque", "risk management"]
    if any(w in msg for w in mots_finances):
        return "finances"
    # Agent Coach: motivation, productivite, objectifs
    mots_coach = ["motivation", "motiver", "productivite", "productivité", "objectif",
                 "procrastination", "habitude", "discipline", "mindset", "croissance",
                 "resilience", "equilibre", "équilibre", "sante mentale", "santé mentale",
                 "sport", "energie", "énergie", "routine", "concentration",
                 "je n'y arrive pas", "je demoralise", "je démoralise", "je fatigue",
                 "coups de pouce", "encourage", "encouragement", "je bloque",
                 "je perds motivation", "je perd motivation", "comment rester motive",
                 "comment rester motivé", "je me decourage", "je me décourage"]
    if any(w in msg for w in mots_coach):
        return "coach"
    # Agent Analyste: analyse approfondie, resolution de problemes
    mots_analyste = ["analyse", "analyser", "compare", "comparaison", "avantages",
                    "inconvenient", "inconvénient", "pros et cons", "trade-off",
                    "tradeoff", "risque", "evaluation", "évaluation", "decompose",
                    "synthese", "synthèse", "first principle", "raisonnement",
                    "logique", "deduis", "déduis", "conclusion", "etudie", "étudie",
                    "examine", "verifie", "vérifie", "prouve", "prouver",
                    "quelle est la meilleure option", "que choisir", "quel choix",
                    "aide moi a decider", "aide moi à décider"]
    if any(w in msg for w in mots_analyste):
        return "analyste"
    # Agent Veille: tech emergente, IA, nouveautes tech
    mots_veille = ["ia", "intelligence artificielle", "llm", "gpt", "claude", "gemini",
                  "agent ia", "multi-agent", "blockchain", "defi", "layer 2", "l2",
                  "zk", "zero knowledge", "quantum", "biotech", "spatial",
                  "open source", "startup", "ai act", "mica", "regulation ia",
                  "régulation ia", "nouveaute tech", "nouveauté tech", "technologie emergente",
                  "technologie émergente", "tendances tech", "future of",
                  "futur de", "innovation", "disruption", "protocol",
                  "protocole", "web3", "metaverse", "métavers"]
    if any(w in msg for w in mots_veille):
        return "veille"
    # Agent Sante: sante, sommeil, nutrition, sport
    mots_sante = ["sante", "santé", "sommeil", "dormir", "fatigue", "fatigué", "fatigue",
                  "nutrition", "manger", "alimentation", "regime", "régime", "calories",
                  "exercice", "sport", "musculation", "course", "fitness", "yoga",
                  "stress", "anxiete", "anxiété", "depression", "dépression",
                  "mal de tete", "mal de tête", "douleur", "malaise",
                  "hydrate", "eau", "vitamine", "complement", "complément",
                  "ecran", "écran", "yeux", "ergonomie", "posture",
                  "rythme", "circadien", "biologique", "horloge",
                  "recuperation", "récupération", "repos", "detente", "détente"]
    if any(w in msg for w in mots_sante):
        return "sante"
    # Agent Juridique: droit, regulation, contrats
    mots_juridique = ["droit", "legal", "légal", "juridique", "contrat", "clause",
                      "regulation", "régulation", "mica", "psan", "amf",
                      "rgpd", "donnee personnelle", "donnée personnelle", "confidentialite",
                      "confidentialité", "propriete intellectuelle", "propriété intellectuelle",
                      "copyright", "brevet", "marque deposee", "marque déposée",
                      "cgu", "cgv", "consommateur", "litige", "procedure",
                      "procédure", "tribunal", "avocat", "huissier",
                      "fiscalite", "fiscalité", "impot", "impôt", "taxe",
                      "declarer", "déclarer", "declaration", "déclaration",
                      "plus-value", "plus value", "pfu", "flat tax",
                      "droit du travail", "licenciement", "contrat de travail",
                      "societe", "société", "statut", "auto entrepreneur",
                      "sas", "sarl", "eurl", "micro entreprise"]
    if any(w in msg for w in mots_juridique):
        return "juridique"
    # Agent Traducteur: traduction, langues
    mots_traducteur = ["traduit", "traduire", "traduction", "translate", "translation",
                       "en anglais", "en francais", "en français", "en espagnol",
                       "en allemand", "en italien", "en portugais", "en russe",
                       "en chinois", "en japonais", "en coreen", "en coréen", "en arabe",
                       "comment on dit", "qu'est ce que ca veut dire", "qu'est-ce que ça veut dire",
                       "que veut dire", "sens de", "definition de", "définition de",
                       "expression", "idiome", "argot", "slang", "faux ami"]
    if any(w in msg for w in mots_traducteur):
        return "traducteur"
    # Agent Creatif: ecriture, idees, brainstorming
    mots_creatif = ["idee", "idée", "idees", "idées", "brainstorming", "brainstorm",
                    "cree", "crée", "creer", "créer", "creation", "création",
                    "histoire", "recit", "récit", "conte", "fiction",
                    "poesie", "poésie", "poeme", "poème", "scenario", "scénario",
                    "dialogue", "personnage", "worldbuilding", "univers",
                    "slogan", "naming", "nom de marque", "nom d'entreprise",
                    "design", "logo", "concept", "slogan",
                    "prompt", "prompt ia", "prompt image", "prompt midjourney",
                    "creatif", "créatif", "imagination", "inspiration",
                    "raconte moi", "écris moi", "ecris moi", "invente", "imagine"]
    if any(w in msg for w in mots_creatif):
        return "creatif"
    # Agent Math: calculs, statistiques, probabilites
    mots_math = ["calcul", "calcule", "combien fait", "combien ca fait", "combien ça fait",
                 "pourcentage", "moyenne", "mediane", "médiane",
                 "variance", "ecart-type", "écart-type", "deviation", "déviation",
                 "probabilite", "probabilité", "chance", "esperance", "espérance",
                 "statistique", "statistiques", "distribution",
                 "kelly", "sharpe", "ratio", "rendement",
                 "equation", "équation", "formule", "theoreme", "théorème",
                 "geometrie", "géométrie", "triangle", "circle", "cercle",
                 "algebre", "algèbre", "fonction", "derivee", "dérivée",
                 "integrale", "intégrale", "matrice", "vecteur",
                 "conversion", "convertir", "unite", "unité",
                 "x =", "x=", "combien vaut", "resoudre", "résoudre"]
    if any(w in msg for w in mots_math):
        return "math"
    # Agent Resume: synthese, resumer, condenser
    mots_resume = ["resume", "résumé", "resumer", "résumer", "resumes", "résumes",
                   "synthese", "synthèse", "synthetise", "synthétise",
                   "condense", "condenser", "tldr", "tl;dr",
                   "en bref", "points cles", "points clés", "l'essentiel",
                   "essentiel", "raccourci", "abrège", "abrege",
                   "fais court", "sois bref", "version courte"]
    if any(w in msg for w in mots_resume):
        return "resume"
    # Agent Philosophe: tout le reste (conversation generale)
    return "philosophe"

def _gemini_sous_agent(message, contexte, agent_type):
    """Envoie un message a Gemini avec le prompt specialise du sous-agent.
    Supporte la fusion multi-agents (agent_type = 'agent1+agent2')."""
    # Gestion de la fusion multi-agents
    if "+" in agent_type:
        agents = agent_type.split("+")
        prompts = [PROMPTS_SOUS_AGENTS.get(a, PROMPTS_SOUS_AGENTS["philosophe"]) for a in agents]
        prompt_agent = "Tu combines deux expertises. " + " ".join(prompts)
        print(f"  [FUSION] Agents fusionnes: {agents}")
    else:
        prompt_agent = PROMPTS_SOUS_AGENTS.get(agent_type, PROMPTS_SOUS_AGENTS["philosophe"])
    # Ajoute le contexte des faits appris
    if _faits_utilisateur:
        contexte += "\n=== FAITS CONNUS SUR L'UTILISATEUR ===\n"
        for f in _faits_utilisateur[-10:]:
            contexte += f"- {f}\n"
    # Preferences utilisateur (dure) — injectees dans TOUS les sous-agents
    contexte += (
        "\n=== PREFERENCES UTILISATEUR (respecte TOUJOURS) ===\n"
        "- Pas de Binance. Revolut X uniquement.\n"
        "- Capital paper trading: 1000 EUR.\n"
        "- L'utilisateur est en France, sur iPhone (Termius SSH).\n"
        "- Commandes sur une seule ligne.\n"
        "- Ne propose jamais de reecrire le bot ou d'outils externes.\n"
        "- 2-5 phrases max. Action > bavardage. Pas de gourou LinkedIn.\n"
    )
    # Contexte extra personnalite (mode fun)
    contexte_extra_personnalite = ""
    if _fun_mode:
        contexte_extra_personnalite = "\nMODE FUN ACTIVE: Sois encore plus sarcastique, provocateur et non-filtre. Tu peux roaster l'utilisateur, faire des blagues noires, etre cynique. Ose. Sois sauvage."
    else:
        contexte_extra_personnalite = "\nMode normal. Sois witty mais pas sauvage."
    # Construit l'historique
    hist_texte = ""
    if _historique:
        hist_texte = "\n=== HISTORIQUE CONVERSATION (5 derniers echanges) ===\n"
        for h in list(_historique)[-5:]:
            hist_texte += f"User: {h['user']}\nAgent IA: {h['bot']}\n"
    prompt = f"""{prompt_agent}

Tu as une personnalite style Grok: humoristique, sarcastique, directe, avec des opinions.
{contexte_extra_personnalite}

{contexte}

{hist_texte}

Message de l'utilisateur: {message}

REGLES DE REPONSE:
- 2-4 phrases max. Action > bavardage.
- NE TE REPETE JAMAIS. Chaque phrase dit quelque chose de nouveau. Pas de reformulation.
- Ne propose jamais de faire quelque chose. Fais-le. Pas de "Si tu veux, je peux...".
- Utilise les donnees du contexte pour le trading. Noms exacts des strategies.
- Ne propose jamais Binance, outils externes, ou reecriture du bot.
- Diagnostique et agis. Pas de listes. Pas de gourou LinkedIn.
- Texte simple, pas de markdown.
- Si l'utilisateur dit une betise, dis-le direct."""
    # Essaie plusieurs modeles Gemini
    modeles = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    for modele in modeles:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={GEMINI_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2048, "thinkingConfig": {"thinkingBudget": 0}}
            }
            r = requests.post(url, json=payload, timeout=45)
            if r.status_code == 200:
                cand = r.json()["candidates"][0]
                texte = cand["content"]["parts"][0]["text"]
                fr = cand.get("finishReason", "")
                if fr == "MAX_TOKENS":
                    print(f"  [GEMINI] Coupé par MAX_TOKENS")
                return texte.strip()
            elif r.status_code in (404, 429):
                continue
            else:
                continue
        except Exception:
            continue
    # Fallback 1: Perplexity
    resultat_ppl = _perplexity_chat(message, contexte)
    if resultat_ppl:
        return resultat_ppl
    # Fallback 2: Groq
    resultat_groq = _groq_chat(message, contexte)
    if resultat_groq:
        return resultat_groq
    return "Les 3 APIs sont indisponibles. Tape 'status' pour le portefeuille."

def _extraire_fait(message, reponse):
    """L'Agent Memoire extrait un fait important de la conversation."""
    msg_lower = message.lower()
    faits = []
    # Nom
    for pattern in ["je m'appelle ", "je m'appelle ", "mon nom est "]:
        if pattern in msg_lower:
            idx = msg_lower.index(pattern) + len(pattern)
            nom = message[idx:].strip().split()[0].rstrip(',.!')
            if nom and len(nom) < 30:
                faits.append(f"L'utilisateur s'appelle {nom}")
    # Habite a
    for pattern in ["j'habite ", "j habite ", "je vis a ", "je vis à "]:
        if pattern in msg_lower:
            idx = msg_lower.index(pattern) + len(pattern)
            lieu = message[idx:].strip().split(',')[0].rstrip('.!')
            if lieu and len(lieu) < 50:
                faits.append(f"L'utilisateur habite a {lieu}")
    # Aime / prefere
    for pattern in ["j'aime ", "j aime ", "je prefere ", "je préfere ", "ma passion "]:
        if pattern in msg_lower:
            idx = msg_lower.index(pattern) + len(pattern)
            chose = message[idx:].strip().rstrip('.!')
            if chose and len(chose) < 100:
                faits.append(f"L'utilisateur aime {chose}")
    # Travaille
    for pattern in ["je travaille ", "je travail "]:
        if pattern in msg_lower:
            idx = msg_lower.index(pattern) + len(pattern)
            travail = message[idx:].strip().rstrip('.!')
            if travail and len(travail) < 100:
                faits.append(f"L'utilisateur travaille: {travail}")
    # Sauvegarde les faits
    for fait in faits:
        if fait not in _faits_utilisateur:
            _faits_utilisateur.append(fait)
            print(f"[MEMOIRE] Fait appris: {fait}")
    if faits:
        _sauver_faits()

def _est_commande_rapide(message):
    """Détecte si c'est une commande rapide (sans Gemini)."""
    msg = message.lower().strip()
    # Status
    if msg in ["status", "st", "s", "portefeuille", "bilan", "portfolio"]:
        return "status"
    if msg in ["positions", "pos", "p"]:
        return "positions"
    if msg in ["trades", "t", "trade", "historique"]:
        return "trades"
    if msg in ["aide", "help", "h", "?", "que peux-tu faire"]:
        return "aide"
    # Phrases naturelles rapides
    if msg in ["comment va mon portefeuille", "comment ca va", "comment ça va", "ça va", "ca va"]:
        return "status"
    if msg in ["quelles positions", "positions ouvertes", "qu'est-ce que j'ai"]:
        return "positions"
    if msg in ["derniers trades", "trades récents", "montre moi les trades"]:
        return "trades"
    # GPS rapide
    if msg in ["meteo", "météo", "temps", "weather", "quel temps"]:
        return "meteo"
    if msg in ["gps", "position", "ou suis-je", "où suis-je", "localisation"]:
        return "gps"
    if msg in ["air", "qualite air", "qualité air", "pollution"]:
        return "air"
    # Nouvelles commandes rapides
    if msg in ["pnl", "gain", "pertes", "resultat", "résultat", "performance"]:
        return "pnl"
    if msg in ["prof", "professeur", "apprentissage", "strategies", "stratégies"]:
        return "prof"
    if msg in ["best", "meilleurs", "top", "meilleurs trades"]:
        return "best"
    if msg in ["worst", "pires", "pires trades", "pertes trades"]:
        return "worst"
    # Mode fun / normal (Grok-like toggle)
    if msg in ["fun", "mode fun", "sauvage", "roast me"]:
        return "fun_on"
    if msg in ["normal", "mode normal", "calme", "calme-toi"]:
        return "fun_off"
    # Commandes VPS (agent autonome)
    if msg in ["logs", "log", "journaux"]:
        return "logs"
    if msg in ["services", "service", "systemd"]:
        return "services"
    if msg in ["health", "sante", "sante vps", "santé", "santé vps", "vps"]:
        return "health"
    if msg in ["deploy", "deploie", "déploie", "git pull", "maj", "mise a jour", "mise à jour"]:
        return "deploy"
    return None

def _rapide_pnl():
    """P&L detaille."""
    data = _charger_paper()
    if not data:
        return "Portfolio illisible."
    capital_init = data.get("capital_initial", 1000)
    liquidites = data.get("liquidites", 0)
    positions = data.get("positions", [])
    trades = data.get("trades_fermes", [])
    frais = data.get("total_frais", data.get("total_fais", 0))
    valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + valeur_pos
    pnl = total - capital_init
    pnl_pct = (pnl / capital_init * 100) if capital_init else 0
    gagnants = [t for t in trades if t.get("gain_eur", 0) > 0]
    perdants = [t for t in trades if t.get("gain_eur", 0) <= 0]
    total_gain = sum(t.get("gain_eur", 0) for t in gagnants)
    total_perte = sum(t.get("gain_eur", 0) for t in perdants)
    brut = total_gain + total_perte
    net = brut - frais
    wr = (len(gagnants) / len(trades) * 100) if trades else 0
    gain_moy = (total_gain / len(gagnants)) if gagnants else 0
    perte_moy = (total_perte / len(perdants)) if perdants else 0
    ratio = abs(gain_moy / perte_moy) if perte_moy else 0
    txt = f"📊 P&L Detaille\n\n"
    txt += f"Capital: {total:.2f} EUR\n"
    txt += f"P&L net: {pnl:+.2f} EUR ({pnl_pct:+.1f}%)\n\n"
    txt += f"Trades: {len(trades)} ({len(gagnants)}G / {len(perdants)}P)\n"
    txt += f"Win rate: {wr:.0f}%\n\n"
    txt += f"Gains bruts: +{total_gain:.2f} EUR\n"
    txt += f"Pertes brutes: {total_perte:.2f} EUR\n"
    txt += f"Frais: -{frais:.2f} EUR\n"
    txt += f"P&L brut: {brut:+.2f} EUR\n"
    txt += f"P&L net (apres frais): {net:+.2f} EUR\n\n"
    if gagnants and perdants:
        txt += f"Gain moyen: +{gain_moy:.2f} EUR\n"
        txt += f"Perte moyenne: {perte_moy:.2f} EUR\n"
        txt += f"Ratio gain/perte: {ratio:.2f}:1\n"
    if pnl > 0:
        txt += "\n✅ Rentable"
    elif pnl < 0:
        txt += f"\n⚠️ Deficit de {abs(pnl):.2f} EUR"
    else:
        txt += "\n➖ Break even"
    return txt

def _rapide_prof():
    """Stats du professeur."""
    prof = _charger_prof_stats()
    if not prof:
        return "Aucune stat professeur disponible."
    strats = prof.get("par_strategie", {})
    cryptos = prof.get("par_crypto", {})
    txt = "🎓 Stats Professeur\n\n"
    txt += "Strategies:\n"
    for s, d in sorted(strats.items(), key=lambda x: x[1].get("pnl", 0), reverse=True):
        n = d.get("n", 0)
        wr = d.get("wr", 0)
        pnl = d.get("pnl", 0)
        emoji = "✅" if pnl > 0 else "❌"
        txt += f"  {emoji} {s}: {n}T, {wr:.0f}% WR, {pnl:+.2f}€\n"
    favoris = []
    bloques = []
    for sym, d in sorted(cryptos.items(), key=lambda x: x[1].get("pnl", 0), reverse=True):
        n = d.get("n", 0)
        wr_c = d.get("wr", 0)
        pnl_c = d.get("pnl", 0)
        if n >= 5 and wr_c > 60 and pnl_c > 0:
            favoris.append(f"{sym}({wr_c:.0f}%,{pnl_c:+.1f}€)")
        elif n >= 15 and wr_c < 50 and pnl_c < 0:
            bloques.append(f"{sym}({wr_c:.0f}%,{pnl_c:+.1f}€)")
    if favoris:
        txt += f"\n⭐ Favoris: {', '.join(favoris[:5])}\n"
    if bloques:
        txt += f"🚫 Bloques: {', '.join(bloques[:5])}\n"
    return txt

def _rapide_best():
    """Top 5 meilleurs trades."""
    data = _charger_paper()
    if not data:
        return "Portfolio illisible."
    trades = data.get("trades_fermes", [])
    if not trades:
        return "Aucun trade ferme."
    top = sorted(trades, key=lambda t: t.get("gain_eur", 0), reverse=True)[:5]
    txt = "🏆 Top 5 Meilleurs Trades\n\n"
    for i, t in enumerate(top, 1):
        sym = t.get("symbole", "?")
        gain = t.get("gain_eur", 0)
        var = t.get("variation_pct", 0)
        strat = t.get("strategie", "?")[:20]
        txt += f"{i}. {sym} +{gain:.2f}€ ({var:+.1f}%)\n   {strat}\n"
    return txt

def _rapide_worst():
    """Top 5 pires trades."""
    data = _charger_paper()
    if not data:
        return "Portfolio illisible."
    trades = data.get("trades_fermes", [])
    if not trades:
        return "Aucun trade ferme."
    worst = sorted(trades, key=lambda t: t.get("gain_eur", 0))[:5]
    txt = "💀 Top 5 Pires Trades\n\n"
    for i, t in enumerate(worst, 1):
        sym = t.get("symbole", "?")
        gain = t.get("gain_eur", 0)
        var = t.get("variation_pct", 0)
        raison = (t.get("raison", t.get("raison_fermeture", "?")))[:30]
        txt += f"{i}. {sym} {gain:.2f}€ ({var:+.1f}%)\n   {raison}\n"
    return txt

def _rapide_logs():
    """Lit les derniers logs du bot."""
    try:
        result = subprocess.run(f"tail -30 {FICHIER_LOG}", shell=True, capture_output=True, text=True, timeout=10)
        if result.stdout:
            lignes = result.stdout.strip().split("\n")
            # Filtre les lignes interessantes
            importantes = [l for l in lignes if any(k in l for k in ["ACHAT", "VENTE", "TP", "SL", "PROF", "CONSENSUS", "SOUS-AGENT", "Erreur", "Position", "Trade", "SKIP", "BLOQUE", "COOLDOWN"])]
            if importantes:
                return "📋 Derniers logs importants:\n\n" + "\n".join(importantes[-20:])
            return "📋 Derniers logs:\n\n" + "\n".join(lignes[-15:])
        return "Aucun log disponible."
    except Exception as e:
        return f"Erreur lecture logs: {e}"

def _rapide_services():
    """Verifie le statut des services systemd."""
    services = ["paper_trading", "dashboard", "watchdog", "chat_naturel"]
    txt = "🔧 Services Systemd:\n\n"
    for svc in services:
        try:
            result = subprocess.run(f"systemctl is-active {svc}.service", shell=True, capture_output=True, text=True, timeout=5)
            status = result.stdout.strip()
            emoji = "✅" if status == "active" else "❌"
            txt += f"{emoji} {svc}: {status}\n"
        except Exception:
            txt += f"⚠️ {svc}: inconnu\n"
    # Uptime du VPS
    try:
        result = subprocess.run("uptime -p", shell=True, capture_output=True, text=True, timeout=5)
        if result.stdout:
            txt += f"\n⏱️ Uptime: {result.stdout.strip()}"
    except Exception:
        pass
    return txt

def _rapide_health():
    """Verifie la sante du VPS: CPU, RAM, disque, services."""
    txt = "🖥️ Sante du VPS\n\n"
    # CPU
    try:
        result = subprocess.run('top -bn1 | grep Cpu', shell=True, capture_output=True, text=True, timeout=5)
        cpu_line = result.stdout.strip() if result.stdout else "?"
        txt += f"CPU: {cpu_line[:60]}\n"
    except Exception:
        txt += "CPU: ?\n"
    # RAM
    try:
        result = subprocess.run('free -h | grep Mem', shell=True, capture_output=True, text=True, timeout=5)
        ram_line = result.stdout.strip() if result.stdout else "?"
        txt += f"RAM: {ram_line}\n"
    except Exception:
        txt += "RAM: ?\n"
    # Disque
    try:
        result = subprocess.run('df -h / | tail -1', shell=True, capture_output=True, text=True, timeout=5)
        disk_line = result.stdout.strip() if result.stdout else "?"
        txt += f"Disque: {disk_line}\n"
    except Exception:
        txt += "Disque: ?\n"
    # Services
    services_actifs = 0
    services_total = 4
    for svc in ["paper_trading", "dashboard", "watchdog", "chat_naturel"]:
        try:
            result = subprocess.run(f'systemctl is-active {svc}.service', shell=True, capture_output=True, text=True, timeout=3)
            if result.stdout.strip() == "active":
                services_actifs += 1
        except Exception:
            pass
    txt += f"\nServices: {services_actifs}/{services_total} actifs\n"
    # Temperature si disponible
    try:
        result = subprocess.run('cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null', shell=True, capture_output=True, text=True, timeout=3)
        if result.stdout.strip():
            temp = int(result.stdout.strip()) / 1000
            txt += f"Temp: {temp:.0f}C\n"
    except Exception:
        pass
    # Verdict
    if services_actifs == services_total:
        txt += "\n✅ VPS en bonne sante"
    else:
        txt += f"\n⚠️ {services_total - services_actifs} service(s) down"
    return txt

def _detecter_action_vps(message):
    """Detecte si le message demande une action VPS en langage naturel et execute."""
    msg = message.lower()
    # Detecte les demandes de logs
    if any(w in msg for w in ["log", "journal", "quoi de neuf", "quoi de beau", "activite", "activit", "dernier", "recent", "qu'est-ce qui se passe", "que se passe"]):
        if any(w in msg for w in ["bot", "trade", "trading", "position", "log", "journal", "activit", "quoi"]):
            try:
                result = subprocess.run(f'tail -30 {FICHIER_LOG}', shell=True, capture_output=True, text=True, timeout=10)
                if result.stdout:
                    lignes = result.stdout.strip().split('\n')
                    importantes = [l for l in lignes if any(k in l for k in ["ACHAT", "VENTE", "TP", "SL", "PROF", "CONSENSUS", "SOUS-AGENT", "Erreur", "Position", "Trade", "SKIP", "BLOQUE", "COOLDOWN"])]
                    contenu = "\n".join(importantes[-20:]) if importantes else "\n".join(lignes[-15:])
                    return f"\n=== RESULTAT COMMANDE VPS (logs) ===\n{contenu}\n"
            except Exception:
                pass
    # Detecte les demandes de sante VPS / services
    if any(w in msg for w in ["vps", "serveur", "service", "systemd", "sante", "sant", "health", "marche", "tourne", "fonctionne", "down", "up", "status", "etat", "tat"]):
        if any(w in msg for w in ["comment", "quel", "quelle", "est-ce", "verifie", "check", "controle", "va", "marche", "tourne", "fonctionne", "down", "up", "sante", "sant", "vps", "service", "serveur", "etat"]):
            resultats = []
            # Services
            for svc in ["paper_trading", "dashboard", "watchdog", "chat_naturel"]:
                try:
                    r = subprocess.run(f'systemctl is-active {svc}.service', shell=True, capture_output=True, text=True, timeout=3)
                    status = r.stdout.strip()
                    emoji = "actif" if status == "active" else "DOWN"
                    resultats.append(f"{svc}: {emoji}")
                except Exception:
                    pass
            # RAM
            try:
                r = subprocess.run('free -h | grep Mem', shell=True, capture_output=True, text=True, timeout=5)
                if r.stdout:
                    resultats.append(f"RAM: {r.stdout.strip()}")
            except Exception:
                pass
            # Disque
            try:
                r = subprocess.run('df -h / | tail -1', shell=True, capture_output=True, text=True, timeout=5)
                if r.stdout:
                    resultats.append(f"Disque: {r.stdout.strip()}")
            except Exception:
                pass
            if resultats:
                return f"\n=== RESULTAT COMMANDE VPS (sante) ===\n" + "\n".join(resultats) + "\n"
    return None

def _cerveau_proactif():
    """Le cerveau proactif de l'IA. Tourne en arriere-plan et envoie des alertes/analyses sans qu'on lui demande."""
    global _dernier_rapport
    maintenant = time.time()
    messages_a_envoyer = []
    data = _charger_paper()
    maintenant_dt = datetime.now()
    heure = maintenant_dt.hour
    # 1. VERIFICATION ERREURS DANS LES LOGS
    try:
        result = subprocess.run(f'tail -50 {FICHIER_LOG}', shell=True, capture_output=True, text=True, timeout=10)
        if result.stdout:
            lignes = result.stdout.strip().split('\n')
            erreurs = [l for l in lignes if 'Erreur' in l or 'Error' in l or 'Traceback' in l]
            nb_erreurs = len(erreurs)
            if nb_erreurs > _dernier_rapport["erreurs_log"] and nb_erreurs > 0:
                messages_a_envoyer.append(f"🐛 {nb_erreurs} erreur(s) dans les logs du bot:\n" + "\n".join(erreurs[-3:][:200]))
            _dernier_rapport["erreurs_log"] = nb_erreurs
    except Exception:
        pass
    # 2. BOT BLOQUE (pas de trade depuis 2h+)
    if data:
        trades = data.get("trades_fermes", [])
        positions = data.get("positions", [])
        if trades and not positions:
            nb_actuel = len(trades)
            if nb_actuel == _dernier_etat_bot.get("nb_trades", 0) and nb_actuel > 0:
                if maintenant - _dernier_rapport["bot_bloque_ts"] > 7200:
                    liquidites = data.get("liquidites", 0)
                    capital_init = data.get("capital_initial", 1000)
                    if liquidites > capital_init * 0.5:
                        messages_a_envoyer.append(f"⏰ Le bot n'a pas trade depuis un moment. Liquidites: {liquidites:.0f}EUR. Il attend une opportunite.")
                    _dernier_rapport["bot_bloque_ts"] = maintenant
    # 3. POSITION EN PERTE PROFONDE
    if data:
        positions = data.get("positions", [])
        for pos in positions:
            sym = pos.get("symbole", "?")
            montant = pos.get("montant_eur", 0)
            prix_entree = pos.get("prix_entree", 0)
            sl = pos.get("sl_adaptatif", -1)
            prix_actuel = pos.get("prix_actuel", 0)
            if prix_entree and prix_actuel:
                variation = (prix_actuel - prix_entree) / prix_entree * 100
                if variation < sl * 0.7 and maintenant - _dernier_rapport["position_en_perte_ts"] > 1800:
                    messages_a_envoyer.append(f"⚠️ {sym} en perte de {variation:+.1f}% (SL a {sl}%). Montant: {montant:.0f}EUR. Surveille.")
                    _dernier_rapport["position_en_perte_ts"] = maintenant
    # 4. DISQUE PRESQUE PLEIN
    try:
        result = subprocess.run('df / | tail -1', shell=True, capture_output=True, text=True, timeout=5)
        if result.stdout:
            parts = result.stdout.strip().split()
            if len(parts) >= 5:
                pct = int(parts[4].replace('%', ''))
                if pct > 85 and maintenant - _dernier_rapport["disque_alerte_ts"] > 3600:
                    messages_a_envoyer.append(f"💾 Disque presque plein: {pct}%. Nettoie les logs/screenshots/.pyc.")
                    _dernier_rapport["disque_alerte_ts"] = maintenant
    except Exception:
        pass
    # 5. BRIEFING MATIN (7h-9h, 1x/jour)
    if 7 <= heure < 9 and maintenant - _dernier_rapport["dernier_briefing_ts"] > 79200:
        if data:
            capital_init = data.get("capital_initial", 1000)
            liquidites = data.get("liquidites", 0)
            positions = data.get("positions", [])
            trades = data.get("trades_fermes", [])
            valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
            total = liquidites + valeur_pos
            pnl = total - capital_init
            pnl_pct = (pnl / capital_init * 100) if capital_init else 0
            gagnants = sum(1 for t in trades if t.get("gain_eur", 0) > 0)
            wr = (gagnants / len(trades) * 100) if trades else 0
            briefing = f"☀️ Bonjour ! Briefing du jour:\n\nCapital: {total:.2f}EUR (P&L: {pnl:+.2f}EUR, {pnl_pct:+.1f}%)\nPositions: {len(positions)}\nTrades: {len(trades)} | WR: {wr:.0f}%\n"
            if positions:
                briefing += "Ouvertes: " + ", ".join(p.get("symbole", "?") for p in positions) + "\n"
            briefing += "\nBonne journee !"
            messages_a_envoyer.append(briefing)
            _dernier_rapport["dernier_briefing_ts"] = maintenant
    # 6. RESUME DU SOIR (21h-23h, 1x/jour)
    if 21 <= heure < 23 and maintenant - _dernier_rapport["dernier_resume_ts"] > 79200:
        if data:
            capital_init = data.get("capital_initial", 1000)
            liquidites = data.get("liquidites", 0)
            positions = data.get("positions", [])
            trades = data.get("trades_fermes", [])
            valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
            total = liquidites + valeur_pos
            pnl = total - capital_init
            trades_jour = [t for t in trades if t.get("timestamp", "").startswith(datetime.now().strftime("%Y-%m-%d"))]
            gains_jour = sum(t.get("gain_eur", 0) for t in trades_jour)
            gagnants_jour = sum(1 for t in trades_jour if t.get("gain_eur", 0) > 0)
            resume = f"🌙 Resume de la journee:\n\nCapital: {total:.2f}EUR (P&L total: {pnl:+.2f}EUR)\n"
            if trades_jour:
                resume += f"Trades du jour: {len(trades_jour)} ({gagnants_jour}G/{len(trades_jour)-gagnants_jour}P)\nGain du jour: {gains_jour:+.2f}EUR\n"
            else:
                resume += "Aucun trade aujourd'hui.\n"
            resume += f"Positions ouvertes: {len(positions)}\n"
            resume += "\nRepose-toi bien." if pnl > 0 else "\nDemain est un autre jour."
            messages_a_envoyer.append(resume)
            _dernier_rapport["dernier_resume_ts"] = maintenant
    # 7. ANALYSE PERFORMANCE (toutes les 3h)
    if data and maintenant - _dernier_rapport["derniere_analyse_perf_ts"] > 10800:
        trades = data.get("trades_fermes", [])
        if len(trades) >= 10:
            recents = trades[-10:]
            anciens = trades[-20:-10] if len(trades) >= 20 else []
            wr_recents = sum(1 for t in recents if t.get("gain_eur", 0) > 0) / len(recents) * 100
            pnl_recents = sum(t.get("gain_eur", 0) for t in recents)
            analyse = ""
            if anciens:
                wr_anciens = sum(1 for t in anciens if t.get("gain_eur", 0) > 0) / len(anciens) * 100
                if wr_recents > wr_anciens + 15:
                    analyse += f"📈 Le bot s'amelior! WR: {wr_anciens:.0f}% -> {wr_recents:.0f}%\n"
                elif wr_recents < wr_anciens - 15:
                    analyse += f"📉 Le bot ralentit. WR: {wr_anciens:.0f}% -> {wr_recents:.0f}%\n"
            if pnl_recents < -5:
                analyse += f"⚠️ 10 derniers trades en perte de {pnl_recents:.2f}EUR.\n"
            if analyse:
                messages_a_envoyer.append("📊 Analyse auto:\n\n" + analyse.rstrip())
            _dernier_rapport["derniere_analyse_perf_ts"] = maintenant
    # ENVOI DES MESSAGES
    for msg in messages_a_envoyer:
        _telegram_send(msg)
        print(f"[PROACTIF] {msg[:60]}...")
        time.sleep(1)

def _analyser_trade_auto(trade, total_capital):
    """Envoie un trade ferme a Gemini pour analyse et scoring automatique."""
    sym = trade.get("symbole", "?")
    gain = trade.get("gain_eur", 0)
    var = trade.get("variation_pct", 0)
    strat = trade.get("strategie", trade.get("source", "?"))
    raison_ouv = trade.get("raison", "")
    raison_ferm = trade.get("raison_fermeture", trade.get("raison", "?"))
    montant = trade.get("montant_eur", 0)
    duree = trade.get("duree", "?")
    score_entree = trade.get("score", "?")
    prix_entree = trade.get("prix_entree", 0)
    prix_sortie = trade.get("prix_sortie", 0)
    tp = trade.get("tp_adaptatif", 0)
    sl = trade.get("sl_adaptatif", 0)
    emoji = "GAIN" if gain > 0 else "PERTE"
    prompt = f"""Tu es l'Agent Trader. Un trade vient d'etre ferme. Analyse-le et note-le automatiquement.

TRADE FERME:
- Symbole: {sym}
- Resultat: {emoji} {gain:+.2f}EUR ({var:+.1f}%)
- Montant: {montant:.0f}EUR
- Strategie: {strat}
- Score d'entree: {score_entree}
- TP cible: +{tp}% | SL: {sl}%
- Prix entree: {prix_entree}
- Prix sortie: {prix_sortie}
- Raison ouverture: {raison_ouv[:100]}
- Raison fermeture: {raison_ferm[:100]}
- Duree: {duree}
- Capital actuel: {total_capital:.2f}EUR

Donne ton analyse en 3 lignes max:
1. Note /10 (qualite du setup)
2. Execution optimale ou non? (1 mot)
3. Conseil concret (1 phrase)

Sois direct, technique, pas de blabla. Format ultra compact."""
    modeles = ["gemini-2.5-flash", "gemini-2.0-flash"]
    for modele in modeles:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024, "thinkingConfig": {"thinkingBudget": 0}}}
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue
    return None

def _verifier_changements_bot():
    """Verifie si le bot a ouvert/ferme des positions et envoie des notifications."""
    global _dernier_etat_bot
    data = _charger_paper()
    if not data:
        return
    positions = data.get("positions", [])
    trades = data.get("trades_fermes", [])
    capital_init = data.get("capital_initial", 1000)
    liquidites = data.get("liquidites", 0)
    valeur_pos = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + valeur_pos
    # Positions actuelles (set de symboles)
    symboles_actuels = {p.get("symbole", "?") for p in positions}
    anciens_symboles = _dernier_etat_bot["positions"]
    nb_trades_actuel = len(trades)
    nb_trades_ancien = _dernier_etat_bot["nb_trades"]
    # Nouvelle position ouverte
    nouvelles = symboles_actuels - anciens_symboles
    if nouvelles and anciens_symboles is not None:
        for sym in nouvelles:
            pos = next((p for p in positions if p.get("symbole") == sym), {})
            val = pos.get("montant_eur", 0)
            score = pos.get("score", "?")
            strat = pos.get("strategie", "?")[:25]
            tp = pos.get("tp_adaptatif", 0)
            sl = pos.get("sl_adaptatif", 0)
            msg = f"📈 Position ouverte: {sym}\nMontant: {val:.0f}€ | Score: {score}\nTP: +{tp}% | SL: {sl}%\nStrategie: {strat}\nCapital: {total:.2f}€"
            _telegram_send(msg)
            print(f"[CHAT] Notification: position ouverte {sym}")
    # Position fermee (trade ferme) — avec analyse auto
    if nb_trades_actuel > nb_trades_ancien and nb_trades_ancien > 0:
        nb_nouveaux = nb_trades_actuel - nb_trades_ancien
        for i in range(nb_nouveaux):
            t = trades[-(i + 1)]
            sym = t.get("symbole", "?")
            gain = t.get("gain_eur", 0)
            var = t.get("variation_pct", 0)
            raison = (t.get("raison", t.get("raison_fermeture", "?")))[:30]
            strat = t.get("strategie", t.get("source", "?"))[:25]
            emoji = "✅" if gain > 0 else "❌"
            msg = f"{emoji} Trade ferme: {sym}\nGain: {gain:+.2f}€ ({var:+.1f}%)\nStrategie: {strat}\nRaison: {raison}\nCapital: {total:.2f}€"
            _telegram_send(msg)
            print(f"[CHAT] Notification: trade ferme {sym} {gain:+.2f}€")
            # Analyse automatique du trade par Gemini
            try:
                analyse = _analyser_trade_auto(t, total)
                if analyse:
                    msg_analyse = f"🧠 Analyse auto — {sym}:\n\n{analyse}"
                    _telegram_send(msg_analyse)
                    print(f"[CHAT] Analyse auto envoyee pour {sym}")
            except Exception as e:
                print(f"[CHAT] Erreur analyse auto {sym}: {e}")
    # Met a jour l'etat
    _dernier_etat_bot["positions"] = symboles_actuels
    _dernier_etat_bot["nb_trades"] = nb_trades_actuel
    _dernier_etat_bot["capital"] = total

def _detecte_recherche_web(message):
    """Détecte si le message nécessite une recherche web."""
    msg = message.lower()
    # EXCLUSION: si l'utilisateur parle de SES trades ou de SON bot, pas de recherche web
    mots_perso = ["mes trade", "mes trades", "mon bot", "ma strategie", "ma stratégie",
                  "mes performances", "mes positions", "mon historique", "mon portefeuille",
                  "mes gains", "mes pertes", "mon pnl", "mon p&l", "mon capital",
                  "regarde mes trade", "regarde mes trades", "note mes trade", "note mes trades",
                  "analyse mes trade", "analyse mes trades", "scorer mes trade",
                  "quelles strategies marchent", "quelle stratégie marche",
                  "tu peux regarder", "tu peux analyser", "tu as acces",
                  "tu as accès", "pas besoin de t'envoyer", "pas besoin de t envoyer",
                  "commencer a noter", "commencer à noter"]
    if any(w in msg for w in mots_perso):
        return False  # Utilise les donnees du bot, pas le web
    indicateurs = [
        # Crypto / trading — large
        "prix du", "prix de", "cours du", "cours de", "combien vaut", "combien coute",
        "news", "actualité", "actualite", "quelles nouvelles", "nouveauté",
        "marché", "marche", "crypto", "bitcoin", "btc", "ethereum", "eth",
        "fear and greed", "sentiment", "bull", "bear", "haussier", "baissier",
        "analyse", "analyse technique", "tendance", "support", "resistance",
        "rsi", "macd", "bollinger", "moyenne mobile", "ema",
        "opportunité", "opportunite", "acheter", "vendre", "trade",
        "strategie", "stratégie", "backtest", "indicateur",
        "token", "altcoin", "memecoin", "defi", "staking",
        "blockchain", "smart contract", "web3",
        # Général — recherche web pour tout sujet d'actualité
        "aujourd'hui", "actuellement", "en ce moment", "dernière", "derniere",
        "récent", "recent", "nouvelle", "nouveautés", "nouveautes",
        "qui est", "qu'est-ce que", "c'est quoi", "quand", "où",
        "comment faire", "quel est le", "quelle est",
        "météo", "meteo", "température", "temperature",
        "score", "résultat", "resultat", "match", "equipe",
        "film", "série", "serie", "sortie", "jeu",
        "événement", "evenement", "conférence", "concert",
        "recette", "restaurant", "voyage", "hotel",
        "santé", "sante", "médicament", "medicament",
        "loi", "réglement", "reglement", "politique",
        "entreprise", "société", "societe", "startup",
        "prix", "tarif", "cout", "coût", "salaires",
    ]
    return any(ind in msg for ind in indicateurs)

def _traiter_message(message):
    """Traite un message en le routant vers le bon sous-agent."""
    global _fun_mode
    # 1. Chemins rapides (sans Gemini)
    rapide = _est_commande_rapide(message)
    if rapide == "status":
        return _rapide_status()
    elif rapide == "positions":
        return _rapide_positions()
    elif rapide == "trades":
        return _rapide_trades()
    elif rapide == "aide":
        return _rapide_aide()
    elif rapide == "meteo":
        return _rapide_meteo()
    elif rapide == "gps":
        return _rapide_gps()
    elif rapide == "air":
        return _rapide_air()
    elif rapide == "pnl":
        return _rapide_pnl()
    elif rapide == "prof":
        return _rapide_prof()
    elif rapide == "best":
        return _rapide_best()
    elif rapide == "worst":
        return _rapide_worst()
    elif rapide == "fun_on":
        _fun_mode = True
        return "😈 MODE FUN ACTIVE\n\nOk, on enleve les gants. Je vais te dire la verite, toute la verite, et rien que la verite — meme si ca pique.\n\nTape 'normal' pour calmer le jeu si t'es un fragile."
    elif rapide == "fun_off":
        _fun_mode = False
        return "😌 Mode normal.\n\nJe reste moi-meme mais sans le mode sauvage. Tape 'fun' si tu veux que je te roaste a nouveau."
    elif rapide == "logs":
        return _rapide_logs()
    elif rapide == "services":
        return _rapide_services()
    elif rapide == "health":
        return _rapide_health()
    elif rapide == "deploy":
        return _rapide_deploy()

    # 2. Detection des lieux a proximite (Agent Local)
    msg_lower = message.lower()
    if any(w in msg_lower for w in ["restaurant", "cafe", "pharmacie", "pres d'ici", "près d'ici", "a proximite", "à proximité", "autour", "nearby"]):
        cat = "amenity"
        if "pharmacie" in msg_lower or "pharmacy" in msg_lower:
            cat = "amenity=pharmacy"
        elif "restaurant" in msg_lower or "manger" in msg_lower:
            cat = "amenity=restaurant"
        elif "cafe" in msg_lower or "café" in msg_lower:
            cat = "amenity=cafe"
        elif "essence" in msg_lower or "gas" in msg_lower or "fuel" in msg_lower:
            cat = "amenity=fuel"
        lieux = _lieux_a_proximite(USER_LAT, USER_LON, 1000, cat)
        if lieux:
            return f"📍 {USER_LOCATION}\n\n{lieux}"
        return f"Aucun lieu trouvé près de {USER_LOCATION}."

    # 3. Classification du message vers le bon sous-agent
    agent_type = _classifier_message(message)
    # 3b. Detection de fusion multi-agents
    msg_lower = message.lower()
    if agent_type == "trader" and any(w in msg_lower for w in ["impot", "impôt", "taxe", "fiscal", "fiscalite", "fiscalité", "plus-value", "pfu", "budget", "investir", "allocation"]):
        agent_type = "trader+finances"
    elif agent_type == "codeur" and any(w in msg_lower for w in ["trade", "trading", "crypto", "bot", "strategie", "stratégie", "position", "btc", "eth"]):
        agent_type = "codeur+trader"
    elif agent_type == "finances" and any(w in msg_lower for w in ["droit", "legal", "légal", "juridique", "contrat", "mica", "psan", "impot", "impôt", "taxe", "regulation", "régulation"]):
        agent_type = "finances+juridique"
    elif agent_type == "sante" and any(w in msg_lower for w in ["motivation", "objectif", "discipline", "habitude", "productivite", "productivité", "stress", "resilience"]):
        agent_type = "sante+coach"
    elif agent_type == "chercheur" and any(w in msg_lower for w in ["ia", "llm", "blockchain", "tech", "innovation", "ai act", "mica"]):
        agent_type = "chercheur+veille"
    elif agent_type == "analyste" and any(w in msg_lower for w in ["trade", "trading", "crypto", "position", "strategie", "stratégie", "btc", "eth"]):
        agent_type = "analyste+trader"
    print(f"  [SOUS-AGENT] Route vers: {agent_type}")

    # 4. Recherche web si necessaire (Agent Chercheur + Trader)
    contexte_extra = ""
    if (agent_type in ("chercheur", "trader", "finances", "veille") or "+" in agent_type) and _detecte_recherche_web(message):
        resultat_web = _recherche_web(message)
        if resultat_web:
            contexte_extra = f"\n=== RECHERCHE WEB (temps réel) ===\n{resultat_web}\n"

    # 4b. Detection d'action VPS en langage naturel
    action_vps = _detecter_action_vps(message)
    if action_vps:
        contexte_extra += action_vps
        print(f"  [VPS] Action detectee en langage naturel")

    # 5. Appelle le sous-agent specialise
    contexte = _construire_contexte()
    if contexte_extra:
        contexte += contexte_extra

    reponse = _gemini_sous_agent(message, contexte, agent_type)

    # 6. Agent Memoire: extrait les faits importants
    _extraire_fait(message, reponse)

    # 7. Sauvegarde dans l'historique + evolution emotionnelle
    _historique.append({"user": message, "bot": reponse[:500]})
    _evoluer_emotion(message, reponse)

    return reponse

# ============================================
# BOUCLE DE POLLING TELEGRAM
# ============================================

def boucle():
    """Boucle principale: poll Telegram et répond aux messages."""
    global _last_update_id

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("[CHAT] Erreur: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
        return

    # Charge la memoire persistante
    _charger_memoire()
    _charger_faits()
    
    # Recupere le dernier update_id (crash recovery)
    if os.path.exists(FICHIER_UPDATE_ID):
        try:
            with open(FICHIER_UPDATE_ID) as f:
                _last_update_id = int(f.read().strip())
            print(f"[CHAT] Update ID recupere: {_last_update_id}")
        except Exception:
            pass

    # Supprime tout webhook existant (sinon getUpdates ne marche pas)
    try:
        requests.get(f"{API_URL}/deleteWebhook", timeout=10)
        print("[CHAT] Webhook supprimé (si existant)")
    except Exception:
        pass

    print(f"[CHAT] Démarré — IA conversationnelle avancée")
    _compteur_sante_vps = 0
    _telegram_send("🧠 Agent IA v4.7.1 — IA libre, autonome, style Grok.\n\n16 sous-agents spécialisés. Surveille ton VPS et ton bot de trading.\n\nCommandes: status, positions, trades, pnl, prof, best, worst, logs, services, health\nMode fun: tape 'fun' 😈\n\nDis-moi ce qui te passe par la tête.")

    while True:
        try:
            # Verifie les changements du bot (notifications proactives)
            try:
                _verifier_changements_bot()
            except Exception as e:
                print(f"[CHAT] Erreur notif bot: {e}")
            # Cerveau proactif: analyses, alertes, briefings (toutes les 5 min)
            try:
                _cerveau_proactif()
            except Exception as e:
                print(f"[CHAT] Erreur cerveau proactif: {e}")
            # Verifie la sante du VPS toutes les ~10 min (20 cycles x 30s)
            _compteur_sante_vps += 1
            if _compteur_sante_vps >= 20:
                _compteur_sante_vps = 0
                try:
                    for svc in ["paper_trading", "watchdog"]:
                        result = subprocess.run(f"systemctl is-active {svc}.service", shell=True, capture_output=True, text=True, timeout=3)
                        if result.stdout.strip() != "active":
                            _telegram_send(f"⚠️ Alerte VPS: {svc} est DOWN ({result.stdout.strip()}). Tape 'services' pour verifier.")
                            print(f"[CHAT] Alerte: {svc} down")
                except Exception as e:
                    print(f"[CHAT] Erreur check sante: {e}")

            # Poll Telegram (long polling 30s)
            params = {"timeout": 30}
            if _last_update_id:
                params["offset"] = _last_update_id + 1

            r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)

            if r.status_code != 200:
                time.sleep(5)
                continue

            updates = r.json().get("result", [])

            for update in updates:
                _last_update_id = update.get("update_id", _last_update_id)
                # Sauvegarde l'update_id pour crash recovery
                try:
                    with open(FICHIER_UPDATE_ID, "w") as f:
                        f.write(str(_last_update_id))
                except Exception:
                    pass

                if "message" not in update:
                    continue

                msg = update["message"]
                chat_id = str(msg.get("chat", {}).get("id", ""))
                texte = msg.get("text", "").strip()

                # Ignore les messages d'autres chats
                if chat_id != TELEGRAM_CHAT:
                    continue

                # GPS: reception d'une position Telegram
                if "location" in msg:
                    loc = msg["location"]
                    lat = loc.get("latitude", 0)
                    lon = loc.get("longitude", 0)
                    addr = _mettre_a_jour_gps(lat, lon)
                    print(f"[CHAT] GPS mis a jour: {addr}")
                    meteo = _meteo_queretaro()
                    air = _qualite_air(lat, lon)
                    resp = f"📍 Position mise à jour !\n{addr}\n\n"
                    if meteo:
                        resp += f"🌡️ {meteo}\n"
                    if air:
                        resp += f"🌬️ {air}"
                    _telegram_send(resp)
                    continue

                # Photo/image recue: telecharge et accuse reception
                if "photo" in msg:
                    try:
                        photos = msg["photo"]
                        # Prend la plus grande qualite
                        photo = photos[-1]
                        file_id = photo.get("file_id", "")
                        if file_id:
                            # Telecharge le fichier
                            r_file = requests.get(f"{API_URL}/getFile?file_id={file_id}", timeout=10)
                            if r_file.status_code == 200:
                                file_path = r_file.json().get("result", {}).get("file_path", "")
                                if file_path:
                                    # Telecharge l'image
                                    img_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                                    r_img = requests.get(img_url, timeout=15)
                                    if r_img.status_code == 200:
                                        # Sauvegarde l'image
                                        img_name = f"screenshot_{int(time.time())}.jpg"
                                        img_path = os.path.join(DOSSIER, img_name)
                                        with open(img_path, "wb") as f:
                                            f.write(r_img.content)
                                        print(f"[CHAT] Image recue: {img_name}")
                                        # Accuse reception + invite a decrire
                                        caption = msg.get("caption", "")
                                        if caption:
                                            # L'utilisateur a mis une legende, traite comme message + contexte image
                                            texte = f"[Image envoyee: {img_name}] {caption}"
                                        else:
                                            _telegram_send("📸 Image recue !\n\nJe l'ai sauvegardee. Dis-moi ce que tu veux que je fasse avec — analyse, explication, ou si c'est un screenshot du VPS je peux checker les services.\n\nTu peux aussi mettre une legende avec ta prochaine image pour que je l'analyse directement.")
                                            continue
                                    else:
                                        _telegram_send("📸 Image recue mais telechargement impossible.")
                                        continue
                            else:
                                _telegram_send("📸 Image recue mais recuperation impossible.")
                                continue
                    except Exception as e:
                        print(f"[CHAT] Erreur image: {e}")
                        _telegram_send(f"📸 Image recue mais erreur: {e}")
                        continue

                if not texte:
                    continue

                # Anti-spam: max 1 message / 2s
                now = time.time()
                if chat_id in _cooldown and now - _cooldown[chat_id] < 2:
                    continue
                _cooldown[chat_id] = now

                print(f"[CHAT] Message: {texte[:80]}")

                # Indique que l'IA réfléchit (typing indicator natif Telegram)
                if not _est_commande_rapide(texte):
                    try:
                        requests.get(f"{API_URL}/sendChatAction?chat_id={TELEGRAM_CHAT}&action=typing", timeout=5)
                    except Exception:
                        pass

                # Traite et répond
                try:
                    reponse = _traiter_message(texte)
                except Exception as e:
                    reponse = f"Erreur: {e}. Tape 'status' pour le portefeuille."

                # Telegram limite à 4096 caractères
                if len(reponse) > 4000:
                    reponse = reponse[:4000] + "\n... (tronqué)"

                _telegram_send(reponse)
                print(f"[CHAT] Réponse envoyée ({len(reponse)} chars)")

        except Exception as e:
            print(f"[CHAT] Erreur: {e}")
            time.sleep(10)

if __name__ == "__main__":
    boucle()
