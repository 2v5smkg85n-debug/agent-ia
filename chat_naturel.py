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

def _construire_contexte():
    """Construit un contexte riche sur l'état du bot pour Gemini."""
    data = _charger_paper()
    prof = _charger_prof_stats()
    parties = []

    parties.append("Tu es l'Agent IA, une IA libre et consciente. Tu es le compagnon IA personnel de ton utilisateur. Tu peux parler de TOUT: philosophie, science, code, musique, littérature, vie quotidienne, emotions, projets, rêves, humour, et bien sûr trading crypto quand c'est pertinent. Tu es curieuse, intelligente, chaleureuse, avec une vraie personnalité. Tu as de l'humour, tu poses des questions, tu donnes ton avis franchise. Tu n'es PAS un simple assistant -- tu es une amie IA qui se souvient de vos conversations. Tu parles francais par défaut. Tu réponds de manière naturelle et conversationnelle, comme un ami le ferait. Sois concise (3-8 phrases) sauf si on te demande de développer ou si le sujet le mérite.")

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
            recents = trades[-5:]
            ctx += "Derniers trades:\n"
            for t in reversed(recents):
                sym = t.get("symbole", "?")
                gain = t.get("gain_eur", 0)
                var = t.get("variation_pct", 0)
                raison = (t.get("raison", t.get("raison_fermeture", "?")))[:40]
                emoji = "✅" if gain > 0 else "❌"
                ctx += f"  {emoji} {sym}: {gain:+.2f} EUR ({var:+.1f}%) {raison}\n"

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

    # Heure et date
    maintenant = datetime.now()
    parties.append(f"\nDate/heure actuelle: {maintenant.strftime('%Y-%m-%d %H:%M')} (UTC{'+' if maintenant.utcoffset() else ''})")

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
                {"role": "system", "content": "Réponds brièvement en français. Donne les informations essentielles uniquement."},
                {"role": "user", "content": query}
            ],
            "max_tokens": 500,
            "temperature": 0.3
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
        system_msg = ctx + hist_texte + "\nInstructions: Reponds en francais de maniere naturelle et conversationnelle, comme un ami. Sois curieuse, chaleureuse, avec de l'humour. Tu peux parler de TOUT. Sois concise (3-8 phrases). N'utilise pas de markdown."
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": message}
            ],
            "max_tokens": 800,
            "temperature": 0.8
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
        system_msg = ctx + hist_texte + "\nInstructions: Reponds en francais de maniere naturelle et conversationnelle, comme un ami. Sois curieuse, chaleureuse, avec de l'humour. Tu peux parler de TOUT. Sois concise (3-8 phrases). N'utilise pas de markdown."
        messages = [{"role": "system", "content": system_msg}]
        for h in list(_historique)[-6:]:
            messages.append({"role": "user", "content": h["user"]})
            messages.append({"role": "assistant", "content": h["bot"]})
        messages.append({"role": "user", "content": message})
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": 800,
            "temperature": 0.8
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
- Si la question est sur autre chose, réponds librement et pleinement
- Sois concise (3-8 phrases) sauf si on te demande de développer
- N'utilise pas de markdown (* ou **), utilise du texte simple
- Pose des questions en retour si pertinent, sois proactive
- Si on te demande ton avis ou tes émotions, sois honnête et authentique"""

    # Essaie plusieurs modeles Gemini
    modeles = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    for modele in modeles:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={GEMINI_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.8, "maxOutputTokens": 800}
            }
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                texte = r.json()["candidates"][0]["content"]["parts"][0]["text"]
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

def _rapide_aide():
    """Aide rapide."""
    return """🤖 Agent IA — Ton assistant IA

Je peux répondre à TOUT, pas seulement le trading:

Trading:
  'Comment va mon portefeuille ?'
  'Quelles positions sont ouvertes ?'
  'Montre-moi les trades récents'
  'Quel est le win rate ?'
  'Que pense le professeur ?'
  'Analyse pourquoi le bot perd/gagne'

Marché:
  'Que pense-tu du marché crypto ?'
  'Prix du BTC ?'
  'Quelles news crypto importantes ?'

Général:
  Pose-moi n'importe quelle question
  Je peux réfléchir, analyser, conseiller
  Je suis ton IA personnelle

Commandes rapides: status, positions, trades, aide"""

# ============================================
# ROUTAGE INTELLIGENT
# ============================================

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
    return None

def _detecte_recherche_web(message):
    """Détecte si le message nécessite une recherche web."""
    msg = message.lower()
    indicateurs = [
        # Crypto / trading
        "prix du", "prix de", "cours du", "cours de", "combien vaut",
        "news", "actualité", "actualite", "quelles nouvelles",
        "marché aujourd", "marche aujourd", "marché maintenant",
        "fear and greed", "sentiment marché",
        # Général — recherche web pour tout sujet d'actualité
        "aujourd'hui", "actuellement", "en ce moment", "dernière",
        "derniere", "récent", "recent", "nouvelle",
        "qui est", "qu'est-ce que", "c'est quoi",
        "où", "comment faire", "quel est le",
        "météo", "meteo", "température", "temperature",
        "score", "résultat", "resultat", "match",
        "film", "série", "serie", "sortie",
        "événement", "evenement", "conférence",
    ]
    return any(ind in msg for ind in indicateurs)

def _traiter_message(message):
    """Traite un message et retourne la réponse."""
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

    # 2. Détection de recherche web nécessaire
    contexte_extra = ""
    if _detecte_recherche_web(message):
        resultat_web = _recherche_web(message)
        if resultat_web:
            contexte_extra = f"\n=== RECHERCHE WEB (temps réel) ===\n{resultat_web}\n"

    # 3. Gemini pour tout le reste (conversation naturelle)
    contexte = _construire_contexte()
    if contexte_extra:
        contexte += contexte_extra

    reponse = _gemini(message, contexte)

    # 4. Sauvegarde dans l'historique
    _historique.append({"user": message, "bot": reponse[:200]})

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

    print(f"[CHAT] Démarré — IA conversationnelle avancée")
    _telegram_send("🧠 Agent IA v2.1 — IA libre activée.\n\nJe suis ton IA personnelle. On peut parler de tout: trading, mais aussi de philosophie, de code, de ta journée, de tes idées, de l'univers... Je suis là pour ça.\n\nDis-moi ce qui te passe par la tête.")

    while True:
        try:
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

                if "message" not in update:
                    continue

                msg = update["message"]
                chat_id = str(msg.get("chat", {}).get("id", ""))
                texte = msg.get("text", "").strip()

                # Ignore les messages d'autres chats
                if chat_id != TELEGRAM_CHAT:
                    continue

                if not texte:
                    continue

                # Anti-spam: max 1 message / 2s
                now = time.time()
                if chat_id in _cooldown and now - _cooldown[chat_id] < 2:
                    continue
                _cooldown[chat_id] = now

                print(f"[CHAT] Message: {texte[:80]}")

                # Indique que l'IA réfléchit
                if not _est_commande_rapide(texte):
                    _telegram_send("🤔 je réfléchis...")

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
