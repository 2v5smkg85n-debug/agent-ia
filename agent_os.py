#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENT OS V2 - Orchestrateur autonome ultra-efficace.

Ameliorations V2:
1. Reponses rapides et structurees (JSON parse, pas de blabla)
2. Contexte de marche injecte automatiquement
3. Memoire conversationnelle (se souvient des discussions)
4. Commandes Telegram enrichies
5. Analyse technique + web + IA fusionnees
6. Alertes intelligentes (prix, opportunites, anomalies)
7. Apprentissage continu (apprend de chaque interaction)
8. Multi-recherche parallele (plusieurs requetes en parallele)
9. Cache de reponses (evite les appels API redondants)
10. Auto-optimisation des prompts (ajuste selon les retours)
"""
import os
import sys
import json
import time
import threading
import requests
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import tempfile
import traceback
import signal
import ast

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

CODE_DIR = os.path.join(DOSSIER, "generated_code")
os.makedirs(CODE_DIR, exist_ok=True)

# Verrou pour les ecritures concurrentes
_file_locks = {}
_locks_lock = threading.Lock()

def _get_lock(path):
    with _locks_lock:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ============================================
# CONFIG
# ============================================
PPLX_KEY = os.getenv("PPLX_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_ID = TELEGRAM_CHAT  # alias

KB_FILE = os.path.join(DOSSIER, "knowledge_base.json")
CHAT_LOG = os.path.join(DOSSIER, "chat_log.jsonl")
MEMORY_FILE = os.path.join(DOSSIER, "agent_memory.json")
CACHE_FILE = os.path.join(DOSSIER, "response_cache.json")
ALERTS_FILE = os.path.join(DOSSIER, "alerts_config.json")

# Cache en memoire
_response_cache = {}
_conversation_history = deque(maxlen=20)
_last_prices = {}


def load_json_safe(path, default=None):
    if default is None:
        default = {}
    lock = _get_lock(path)
    with lock:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Fichier corrompu - essaie le backup
            backup = path + ".bak"
            try:
                with open(backup, 'r') as f:
                    data = json.load(f)
                    save_json_safe(path, data)  # Restaure
                    return data
            except:
                return default
        except Exception:
            return default


def save_json_safe(path, data):
    lock = _get_lock(path)
    with lock:
        try:
            # Sauvegarde l'ancien fichier avant d'ecrire
            if os.path.exists(path):
                try:
                    os.replace(path, path + ".bak")
                except:
                    pass
            # Ecriture atomique: ecrit dans un fichier temp puis renomme
            tmp_path = path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"[SAVE] Erreur sauvegarde {path}: {e}")
            # Dernier recours: ecriture directe
            try:
                with open(path, 'w') as f:
                    json.dump(data, f, ensure_ascii=False)
            except:
                pass


def send_telegram(message, parse_mode="HTML"):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    
    for attempt in range(3):
        try:
            if len(message) > 4000:
                parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
                for part in parts:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={"chat_id": TELEGRAM_CHAT, "text": part, "parse_mode": parse_mode},
                        timeout=10
                    )
                    time.sleep(0.3)
            else:
                r = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": parse_mode},
                    timeout=10
                )
                if r.status_code == 200:
                    return True
                # Si erreur de parse_mode, renvoie en texte simple
                if r.status_code == 400 and attempt == 1:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={"chat_id": TELEGRAM_CHAT, "text": message[:4000]},
                        timeout=10
                    )
                    return True
            return True
        except requests.exceptions.Timeout:
            print(f"[TELEGRAM] Timeout tentative {attempt+1}/3")
            time.sleep(2)
        except Exception as e:
            print(f"[TELEGRAM] Erreur: {e}")
            time.sleep(2)
    return False

# Stats globales
_stats = {
    "messages_recus": 0,
    "messages_repondus": 0,
    "erreurs": 0,
    "api_timeouts": 0,
    "demarrage": datetime.now().isoformat(),
}

def increment_stat(key):
    _stats[key] = _stats.get(key, 0) + 1

def get_stats():
    uptime = (datetime.now() - datetime.fromisoformat(_stats["demarrage"])).total_seconds()
    heures = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    return {
        **_stats,
        "uptime": f"{heures}h{minutes}m",
        "uptime_seconds": uptime,
    }


# ============================================
# 1. IA CORE - Appels IA optimises
# ============================================
def ask_perplexity(prompt, model="sonar", temperature=0.3, timeout=15):
    """Appel Perplexity optimise avec cache."""
    cache_key = hash(prompt + model)
    if cache_key in _response_cache:
        return _response_cache[cache_key]
    
    if not PPLX_KEY:
        return "Erreur: PPLX_API_KEY manquant"
    
    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PPLX_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 800,
            },
            timeout=timeout
        )
        if r.status_code == 200:
            answer = r.json()["choices"][0]["message"]["content"]
            citations = r.json().get("citations", [])
            result = answer
            if citations:
                result += "\n\nSources: " + ", ".join(citations[:3])
            _response_cache[cache_key] = result
            return result
        print(f"[PERPLEXITY] HTTP {r.status_code}: {r.text[:200]}")
        return f"Erreur API (HTTP {r.status_code})"
    except requests.exceptions.Timeout:
        print("[PERPLEXITY] Timeout")
        increment_stat("api_timeouts")
        # Fallback: essaie Gemini si disponible
        gemini_resp = ask_gemini(prompt)
        if gemini_resp:
            return gemini_resp
        return "L'IA met trop de temps. Reformule ta question."
    except Exception as e:
        print(f"[PERPLEXITY] Erreur: {e}")
        # Fallback: essaie Gemini
        gemini_resp = ask_gemini(prompt)
        if gemini_resp:
            return gemini_resp
        return f"Erreur: {e}"


def ask_gemini(prompt, timeout=30):
    """Appel Gemini optimise."""
    if not GEMINI_KEY:
        return None
    
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout
        )
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return None
    except Exception:
        return None


def consensus_ia(question, context=None):
    """Consensus rapide Perplexity + Gemini en parallele."""
    prompt = question
    if context:
        prompt = f"{context}\n\nQuestion: {question}\n\nRéponds en français, de façon concise et structurée."
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_pplx = executor.submit(ask_perplexity, prompt)
        f_gem = executor.submit(ask_gemini, prompt)
        
        pplx_result = f_pplx.result(timeout=35)
        gem_result = f_gem.result(timeout=35)
    
    # Si Gemini a répondu, synthétise
    if gem_result and "erreur" not in str(gem_result).lower():
        synthese = ask_perplexity(
            f"Synthétise ces deux analyses en une réponse unifiée en français:\n\n"
            f"Analyse 1: {pplx_result[:1000]}\n\n"
            f"Analyse 2: {gem_result[:1000]}\n\n"
            f"Donne la réponse finale, concise et actionnable."
        )
        return synthese
    
    return pplx_result


# ============================================
# 2. RECHERCHE MULTI-REQUETE PARALLELE
# ============================================
def multi_search(queries, max_workers=3):
    """Lance plusieurs recherches en parallele."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(ask_perplexity, q): q for q in queries}
        for future in as_completed(futures):
            query = futures[future]
            results[query] = future.result()
    return results


def crypto_deep_analysis(symbole):
    """Analyse ultra-complete d'un crypto en parallele."""
    if not symbole.endswith("USDT"):
        symbole += "USDT"
    
    queries = [
        f"{symbole} prix actuel, analyse technique et prédiction court terme",
        f"{symbole} actualités récentes et annonces importantes aujourd'hui",
        f"{symbole} sentiment de marché, les traders sont-ils bullish ou bearish?",
        f"{symbole} niveaux de support et résistance clés",
    ]
    
    # Recherche parallele
    web_results = multi_search(queries)
    
    # Analyse technique
    tech = get_technical_data(symbole)
    
    # Synthèse IA
    context = f"""
DONNÉES TECHNIQUES:
{json.dumps(tech, indent=2, default=str)}

DONNÉES WEB:
{json.dumps(web_results, indent=2, default=str)[:2000]}
"""
    
    recommendation = ask_perplexity(
        f"{context}\n\n"
        f"Analyse {symbole} et donne une recommandation structurée en français:\n"
        f"1. Tendance (bullish/bearish/neutre)\n"
        f"2. Niveau de confiance (0-100%)\n"
        f"3. Prix cible court terme\n"
        f"4. Risques principaux\n"
        f"5. Recommandation: ACHETER / VENDRE / ATTENDRE\n"
        f"Sois concis et data-driven."
    )
    
    return {
        "symbole": symbole,
        "technique": tech,
        "web": web_results,
        "recommandation": recommendation,
    }


def get_technical_data(symbole):
    """Récupère les données techniques d'un symbole."""
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, "1h", 100)
        if not bougies or len(bougies) < 50:
            return {"error": "Pas assez de données"}
        
        clotures = [b["cloture"] for b in bougies]
        prix = clotures[-1]
        
        # Indicateurs
        sma20 = sum(clotures[-20:]) / 20
        sma50 = sum(clotures[-50:]) / 50
        
        # RSI
        gains, pertes = [], []
        for j in range(1, min(len(clotures), 15)):
            diff = clotures[j] - clotures[j-1]
            gains.append(max(diff, 0))
            pertes.append(max(-diff, 0))
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_perte = sum(pertes) / len(pertes) if pertes else 0.001
        rsi = 100 - (100 / (1 + avg_gain / avg_perte)) if avg_perte > 0 else 50
        
        # Variation
        var_1h = (prix - clotures[-2]) / clotures[-2] * 100 if len(clotures) >= 2 else 0
        var_24h = (prix - clotures[-24]) / clotures[-24] * 100 if len(clotures) >= 24 else 0
        var_7d = (prix - clotures[-7*24]) / clotures[-7*24] * 100 if len(clotures) >= 168 else 0
        
        # Bollinger
        sma_bb = sma20
        variance = sum((c - sma_bb) ** 2 for c in clotures[-20:]) / 20
        std = variance ** 0.5
        bb_haut = sma_bb + 2 * std
        bb_bas = sma_bb - 2 * std
        
        # ATR
        trs = [abs(clotures[j] - clotures[j-1]) / clotures[j-1] for j in range(-14, 0) if clotures[j-1] > 0]
        atr = sum(trs) / len(trs) if trs else 0
        
        return {
            "prix": round(prix, 6),
            "variation_1h": round(var_1h, 2),
            "variation_24h": round(var_24h, 2),
            "variation_7j": round(var_7d, 2),
            "rsi": round(rsi, 1),
            "sma20": round(sma20, 6),
            "sma50": round(sma50, 6),
            "trend": "BULL" if sma20 > sma50 else "BEAR",
            "bollinger_haut": round(bb_haut, 6),
            "bollinger_bas": round(bb_bas, 6),
            "atr_pct": round(atr * 100, 2),
            "position_range": round((prix - min(clotures[-24:])) / (max(clotures[-24:]) - min(clotures[-24:])) * 100, 1) if max(clotures[-24:]) > min(clotures[-24:]) else 50,
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================
# 3. MEMOIRE CONVERSATIONNELLE INTELLIGENTE
# ============================================
MEMORY_FILE = os.path.join(DOSSIER, "agent_memory.json")
PROFILE_FILE = os.path.join(DOSSIER, "user_profile.json")

_conversation_history = deque(maxlen=50)

# --- PROFIL UTILISATEUR PERSISTANT ---
def load_profile():
    """Charge le profil utilisateur persistant."""
    return load_json_safe(PROFILE_FILE, {
        "nom": "Tamaya",
        "style_trading": "crypto",
        "capital": 1000,
        "preferences": {},
        "interets": [],
        "cryptos_suivies": [],
        "strategies_preferees": [],
        "derniere_interaction": None,
        "total_conversations": 0,
        "sujets_explores": {},
    })

def save_profile(profile):
    """Sauvegarde le profil utilisateur."""
    save_json_safe(PROFILE_FILE, profile)

def update_profile(message, response=""):
    """Met a jour le profil en fonction du message."""
    profile = load_profile()
    profile["total_conversations"] = profile.get("total_conversations", 0) + 1
    profile["derniere_interaction"] = datetime.now().isoformat()
    
    msg_lower = message.lower()
    
    # Detecte le nom
    if "je m'appelle" in msg_lower or "mon nom est" in msg_lower:
        try:
            nom = message.split("'")[1].split()[0] if "m'appelle" in msg_lower else message.lower().split("nom est")[1].strip().split()[0]
            if nom and len(nom) < 30:
                profile["nom"] = nom.capitalize()
        except:
            pass
    
    # Detecte les preferences
    if "je prefere" in msg_lower or "j'aime" in msg_lower or "je veux" in msg_lower:
        key = datetime.now().strftime("%Y-%m-%d")
        profile["preferences"][key] = message[:300]
    
    # Detecte les cryptos mentionnees
    cryptos_connues = ["btc", "eth", "sol", "bnb", "xrp", "ada", "doge", "avax", "matic", "dot", 
                       "link", "ltc", "pepe", "wif", "jup", "pyth", "strk", "io", "zro", "w",
                       "ethfi", "om", "ena", "jto", "popcat", "mew"]
    mots = msg_lower.replace(",", " ").replace(".", " ").split()
    for crypto in cryptos_connues:
        if crypto in mots and crypto not in profile["cryptos_suivies"]:
            profile["cryptos_suivies"].append(crypto.upper())
    
    # Detecte les strategies mentionnees
    strategies_connues = ["rsi", "ema", "macd", "bollinger", "supertrend", "ichimoku", "vwap", 
                          "cci", "adx", "williams", "parabolic", "heikin", "squeeze"]
    for strat in strategies_connues:
        if strat in msg_lower and strat.upper() not in profile.get("strategies_preferees", []):
            profile.setdefault("strategies_preferees", []).append(strat.upper())
    
    # Compte les sujets explores
    sujets = {
        "trading": ["trader", "trade", "position", "achat", "vente", "long", "short"],
        "analyse": ["analyser", "analyse", "graphique", "indicateur", "technique"],
        "code": ["code", "python", "script", "programmer", "executer"],
        "marche": ["marche", "prix", "cours", "evolution", "tendance"],
        "strategie": ["strategie", "backtest", "winrate", "performance"],
        "actualite": ["news", "actualite", "info", "journal"],
        "sentiment": ["sentiment", "fear", "greed", "peur", "avidite"],
        "opportunite": ["opportunite", "scanner", "signal", "achat"],
        "resolution": ["resoudre", "probleme", "bug", "erreur", "fix"],
    }
    for sujet, mots_cles in sujets.items():
        for mot in mots_cles:
            if mot in msg_lower:
                profile["sujets_explores"][sujet] = profile["sujets_explores"].get(sujet, 0) + 1
                break
    
    save_profile(profile)

def get_profile_context():
    """Genere un resume du profil pour l'IA."""
    profile = load_profile()
    ctx = f"Profil utilisateur: {profile.get('nom', 'Tamaya')}\n"
    ctx += f"Style: {profile.get('style_trading', 'crypto')}\n"
    ctx += f"Capital: {profile.get('capital', 1000)}€\n"
    
    cryptos = profile.get("cryptos_suivies", [])
    if cryptos:
        ctx += f"Cryptos suivies: {', '.join(cryptos[:10])}\n"
    
    strats = profile.get("strategies_preferees", [])
    if strats:
        ctx += f"Strategies interessees: {', '.join(strats[:8])}\n"
    
    sujets = profile.get("sujets_explores", {})
    if sujets:
        top_sujets = sorted(sujets.items(), key=lambda x: x[1], reverse=True)[:3]
        ctx += f"Sujets frequents: {', '.join([s[0] for s in top_sujets])}\n"
    
    total = profile.get("total_conversations", 0)
    ctx += f"Total conversations: {total}\n"
    
    return ctx

# --- MEMOIRE CONVERSATIONNELLE AVANCEE ---
def save_memory(role, message, response=None):
    """Sauvegarde la conversation avec metadata et apprend."""
    memoire = load_json_safe(MEMORY_FILE, {
        "conversations": [], 
        "facts": [], 
        "preferences": {}, 
        "summaries": [],
        "important_conv": [],
    })
    
    # Migration: assure que toutes les cles existent
    memoire.setdefault("important_conv", [])
    memoire.setdefault("conversations", [])
    memoire.setdefault("summaries", [])
    memoire.setdefault("facts", [])
    memoire.setdefault("preferences", {})
    
    # Detecte l'importance
    importance = 1  # normal
    msg_lower = (message or "").lower()
    resp_lower = (response or "").lower()
    
    # Importance elevee pour certains contenus
    if any(kw in msg_lower for kw in ["important", "rapelle", "n'oublie", "souviens", "retiens"]):
        importance = 3  # critique
    elif any(kw in msg_lower for kw in ["strategie", "backtest", "resultat", "performance", "code", "erreur"]):
        importance = 2  # important
    elif any(kw in resp_lower for kw in ["succes", "execute", "gagnant", "benefice"]):
        importance = 2
    
    entry = {
        "role": role,
        "message": message[:800] if message else "",
        "response": response[:800] if response else "",
        "timestamp": datetime.now().isoformat(),
        "importance": importance,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "heure": datetime.now().strftime("%H:%M"),
    }
    memoire["conversations"].append(entry)
    
    # Garde les conversations importantes indefiniment
    if importance >= 2:
        memoire.setdefault("important_conv", []).append(entry)
        memoire["important_conv"] = memoire["important_conv"][-100:]  # max 100 importantes
    
    # Garde les 200 dernieres conversations normales
    memoire["conversations"] = memoire["conversations"][-200:]
    
    # Met a jour le profil
    update_profile(message, response)
    
    save_json_safe(MEMORY_FILE, memoire)

def search_memory(query, limit=5):
    """Recherche dans la memoire par mots-cles."""
    memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "important_conv": []})
    query_lower = query.lower()
    mots_cles = [m for m in query_lower.replace(",", " ").replace(".", " ").split() if len(m) > 2]
    
    results = []
    all_conv = memoire.get("conversations", []) + memoire.get("important_conv", [])
    
    for conv in all_conv:
        text = (conv.get("message", "") + " " + conv.get("response", "")).lower()
        score = sum(1 for mot in mots_cles if mot in text)
        if score > 0:
            conv_copy = conv.copy()
            conv_copy["score"] = score
            results.append(conv_copy)
    
    # Trie par score puis par date
    results.sort(key=lambda x: (x["score"], x.get("importance", 1)), reverse=True)
    
    # Dedouble par message
    seen = set()
    unique = []
    for r in results:
        key = r.get("message", "")[:50]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    return unique[:limit]

def get_context_from_memory():
    """Récupère le contexte intelligent pour l'IA."""
    ctx_parts = []
    
    # 1. Profil utilisateur
    profile_ctx = get_profile_context()
    if profile_ctx:
        ctx_parts.append(profile_ctx)
    
    # 2. Dernieres conversations (3 recentes)
    memoire = load_json_safe(MEMORY_FILE, {})
    convs = memoire.get("conversations", [])
    if convs:
        recent = convs[-3:]
        ctx = "Conversations recentes:\n"
        for c in recent:
            role = "User" if c["role"] == "user" else "Agent"
            ctx += f"  {role}: {c['message'][:150]}\n"
            if c.get("response"):
                ctx += f"  Rep: {c['response'][:100]}\n"
        ctx_parts.append(ctx)
    
    # 3. Conversations importantes recentes (2 dernieres)
    important = memoire.get("important_conv", [])
    if important:
        recent_imp = important[-2:]
        ctx = "Points importants souvenus:\n"
        for c in recent_imp:
            ctx += f"  {c['message'][:200]}\n"
            if c.get("response"):
                ctx += f"  -> {c['response'][:150]}\n"
        ctx_parts.append(ctx)
    
    return "\n".join(ctx_parts)

def get_memory_summary():
    """Genere un resume de la memoire pour l'utilisateur."""
    memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "important_conv": []})
    profile = load_profile()
    
    total = len(memoire.get("conversations", []))
    important = len(memoire.get("important_conv", []))
    
    summary = f"🧠 MEMOIRE DE L'AGENT\n\n"
    summary += f"👤 Profil: {profile.get('nom', 'Tamaya')}\n"
    summary += f"💬 Conversations: {total}\n"
    summary += f"⭐ Conversations importantes: {important}\n"
    summary += f"📊 Total echanges: {profile.get('total_conversations', 0)}\n\n"
    
    cryptos = profile.get("cryptos_suivies", [])
    if cryptos:
        summary += f"💰 Cryptos suivies: {', '.join(cryptos[:10])}\n"
    
    strats = profile.get("strategies_preferees", [])
    if strats:
        summary += f"📐 Strategies: {', '.join(strats[:8])}\n"
    
    sujets = profile.get("sujets_explores", {})
    if sujets:
        top = sorted(sujets.items(), key=lambda x: x[1], reverse=True)[:5]
        summary += f"📚 Sujets: {', '.join([f'{s}({n})' for s, n in top])}\n"
    
    prefs = profile.get("preferences", {})
    if prefs:
        recent_prefs = sorted(prefs.items())[-3:]
        summary += f"\n🔑 Preferences recentes:\n"
        for date, pref in recent_prefs:
            summary += f"  {date}: {pref[:80]}\n"
    
    # Dernieres conversations importantes
    imp_conv = memoire.get("important_conv", [])
    if imp_conv:
        summary += f"\n⭐ Souvenirs importants:\n"
        for c in imp_conv[-3:]:
            summary += f"  [{c.get('date', '?')}] {c['message'][:100]}\n"
    
    return summary

def forget_last():
    """Oublie la derniere conversation."""
    memoire = load_json_safe(MEMORY_FILE, {"conversations": []})
    if memoire.get("conversations"):
        memoire["conversations"].pop()
        save_json_safe(MEMORY_FILE, memoire)
        return True
    return False

def learn_fact(fact, category="general"):
    """Apprend un fait et le stocke dans la KB."""
    kb = load_json_safe(KB_FILE, {"facts": [], "strategies": [], "lessons": [], "market_data": {}})
    entry = {
        "fact": fact,
        "category": category,
        "timestamp": datetime.now().isoformat(),
    }
    if category == "strategy":
        kb["strategies"].append(entry)
    elif category == "lesson":
        kb["lessons"].append(entry)
    elif category == "market":
        kb["market_data"][datetime.now().strftime("%Y-%m-%d %H:%M")] = fact
    else:
        kb["facts"].append(entry)
    save_json_safe(KB_FILE, kb)

# --- MEMOIRE DE RESOLUTION DE PROBLEMES ---
SOLUTIONS_FILE = os.path.join(DOSSIER, "solutions_db.json")
CORRECTIONS_FILE = os.path.join(DOSSIER, "corrections_db.json")

def save_solution(problem, solution, category="general"):
    """Sauvegarde une solution pour reutilisation future."""
    db = load_json_safe(SOLUTIONS_FILE, {"solutions": []})
    entry = {
        "problem": problem[:500],
        "solution": solution[:1000],
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "times_reused": 0,
    }
    db["solutions"].append(entry)
    db["solutions"] = db["solutions"][-200:]  # max 200 solutions
    save_json_safe(SOLUTIONS_FILE, db)

def search_similar_problem(problem, limit=3):
    """Cherche des problemes similaires deja resolus."""
    db = load_json_safe(SOLUTIONS_FILE, {"solutions": []})
    problem_lower = problem.lower()
    mots = [m for m in problem_lower.replace(",", " ").replace(".", " ").split() if len(m) > 2]
    
    results = []
    for sol in db.get("solutions", []):
        text = (sol.get("problem", "") + " " + sol.get("solution", "")).lower()
        score = sum(1 for mot in mots if mot in text)
        if score > 0:
            sol_copy = sol.copy()
            sol_copy["score"] = score
            results.append(sol_copy)
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

def save_correction(error, correction, topic=""):
    """Sauvegarde une correction d'erreur pour ne plus la repeter."""
    db = load_json_safe(CORRECTIONS_FILE, {"corrections": []})
    entry = {
        "error": error[:500],
        "correction": correction[:500],
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    db["corrections"].append(entry)
    db["corrections"] = db["corrections"][-100:]
    save_json_safe(CORRECTIONS_FILE, db)
    # Aussi apprend comme fait
    learn_fact(f"ERREUR: {error[:100]} -> CORRECTION: {correction[:100]}", "lesson")

def get_corrections_context():
    """Retourne les corrections recentes pour l'IA."""
    db = load_json_safe(CORRECTIONS_FILE, {"corrections": []})
    corrections = db.get("corrections", [])
    if not corrections:
        return ""
    recent = corrections[-5:]
    ctx = "Corrections aprendues (ne repete pas ces erreurs):\n"
    for c in recent:
        ctx += f"  Erreur: {c['error'][:100]}\n"
        ctx += f"  Correction: {c['correction'][:100]}\n\n"
    return ctx

def auto_summarize_old_conversations():
    """Compresse les vieilles conversations en resumes."""
    memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "summaries": []})
    convs = memoire.get("conversations", [])
    summaries = memoire.get("summaries", [])
    
    # Si on a plus de 100 conversations, on resume les 50 plus vieilles
    if len(convs) > 100:
        old_convs = convs[:50]
        convs = convs[50:]
        
        # Cree un resume simple par date
        by_date = {}
        for c in old_convs:
            date = c.get("date", "unknown")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(c)
        
        for date, day_convs in by_date.items():
            topics = [c["message"][:80] for c in day_convs[:5]]
            summary = {
                "date": date,
                "count": len(day_convs),
                "topics": topics,
                "summary": f"{len(day_convs)} conversations le {date}: " + " | ".join(topics),
            }
            summaries.append(summary)
        
        summaries = summaries[-50:]  # max 50 resumes
        memoire["conversations"] = convs
        memoire["summaries"] = summaries
        save_json_safe(MEMORY_FILE, memoire)

def get_solutions_context(problem):
    """Cherche des solutions similaires et les injecte dans le contexte."""
    similar = search_similar_problem(problem)
    if not similar:
        return ""
    ctx = "Solutions similaires trouvees dans ma memoire:\n"
    for s in similar[:2]:
        ctx += f"  Probleme: {s['problem'][:150]}\n"
        ctx += f"  Solution: {s['solution'][:200]}\n\n"
    return ctx

def detect_correction(user_msg, bot_response):
    """Detecte si l'utilisateur corrige une reponse precedente."""
    msg_lower = user_msg.lower()
    correction_indicators = [
        "non", "pas", "erreur", "faux", "incorrect", "c'est faux",
        "le bon", "la bonne", "c'est ca", "rectification",
        "en fait", "actuellement", "c'est pas", "non c'est",
    ]
    is_correction = any(ind in msg_lower for ind in correction_indicators)
    if is_correction and bot_response:
        save_correction(bot_response[:300], user_msg[:300])
        return True
    return False

def smart_solve(problem):
    """Resolution de probleme multi-étapes avec memoire."""
    steps = []
    
    # 1. Cherche dans les solutions existantes
    similar = search_similar_problem(problem, limit=1)
    if similar and similar[0].get("score", 0) >= 3:
        sol = similar[0]
        steps.append(f"Solution similaire trouvee (score {sol['score']})")
        # Incremente le compteur de reutilisation
        db = load_json_safe(SOLUTIONS_FILE, {"solutions": []})
        for s in db["solutions"]:
            if s.get("timestamp") == sol.get("timestamp"):
                s["times_reused"] = s.get("times_reused", 0) + 1
                break
        save_json_safe(SOLUTIONS_FILE, db)
        
        # Demande a l'IA d'adapter la solution
        prompt = f"""Probleme: {problem}

J'ai deja resolu un probleme similaire:
{sol['problem']}
Solution: {sol['solution']}

Adapte cette solution au probleme actuel. Reponds en français."""
        response = ask_perplexity(prompt)
        return response, steps
    
    # 2. Resolution multi-étapes avec l'IA
    steps.append("Aucune solution similaire - resolution IA")
    
    # Contexte enrichi
    context_parts = []
    profile_ctx = get_profile_context()
    context_parts.append(profile_ctx)
    
    corrections_ctx = get_corrections_context()
    if corrections_ctx:
        context_parts.append(corrections_ctx)
    
    mem_ctx = get_context_from_memory()
    if mem_ctx:
        context_parts.append(mem_ctx)
    
    full_context = "\n".join(context_parts)
    
    prompt = f"""{full_context}

Probleme a resoudre: {problem}

Instructions:
1. Analyse le probleme etape par etape
2. Si des calculs sont necessaires, montre-les
3. Si une erreur precedente existe, evite-la
4. Donne une solution complete et precise
5. Reponds en français"""
    
    response = ask_perplexity(prompt)
    
    # 3. Sauvegarde la solution
    save_solution(problem, response)
    
    return response, steps

# ============================================
# 3b. PRIX CRYPTO EN TEMPS REEL (CoinGecko - gratuit, sans cle)
# ============================================
COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "DOT": "polkadot", "LINK": "chainlink", "LTC": "litecoin",
    "PEPE": "pepe", "WIF": "dogwifcoin", "JUP": "jupiter-exchange-solana",
    "PYTH": "pyth-network", "STRK": "starknet", "IO": "io-net", "ZRO": "layerzero",
    "W": "wormhole", "ETHFI": "ether-fi", "OM": "mantra-dao", "ENA": "ethena",
    "JTO": "jito-governance-token", "POPCAT": "popcat", "MEW": "cat-in-a-dogs-world",
    "TRX": "tron", "ATOM": "cosmos", "NEAR": "near", "APT": "aptos",
    "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia",
    "FIL": "filecoin", "HBAR": "hedera-hashgraph", "ICP": "internet-computer",
}

def get_crypto_price(symbole):
    """Recupere le prix d'un crypto via CoinGecko."""
    symbole = symbole.upper().replace("USDT", "").replace("USD", "")
    coin_id = COINGECKO_IDS.get(symbole)
    if not coin_id:
        return None
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd,eur",
                    "include_24hr_change": "true", "include_24hr_vol": "true",
                    "include_market_cap": "true"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get(coin_id, {})
            return {"symbole": symbole, "prix_usd": data.get("usd"),
                    "prix_eur": data.get("eur"),
                    "variation_24h": round(data.get("usd_24h_change", 0), 2),
                    "volume_24h": data.get("usd_24h_vol"),
                    "market_cap": data.get("usd_market_cap")}
    except Exception as e:
        print(f"[COINGECKO] Erreur: {e}")
    return None

def get_multiple_prices(symboles):
    """Recupere plusieurs prix en une requete."""
    coin_ids, symbole_map = [], {}
    for s in symboles:
        s = s.upper().replace("USDT", "").replace("USD", "")
        coin_id = COINGECKO_IDS.get(s)
        if coin_id:
            coin_ids.append(coin_id)
            symbole_map[coin_id] = s
    if not coin_ids:
        return []
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(coin_ids), "vs_currencies": "eur",
                    "include_24hr_change": "true"}, timeout=10)
        if r.status_code == 200:
            results = []
            for coin_id, symbole in symbole_map.items():
                if coin_id in r.json():
                    d = r.json()[coin_id]
                    results.append({"symbole": symbole, "prix_eur": d.get("eur"),
                                   "variation_24h": round(d.get("eur_24h_change", 0), 2)})
            return results
    except Exception as e:
        print(f"[COINGECKO] Erreur: {e}")
    return []

def format_price(info):
    """Formate les infos prix pour Telegram."""
    prix = info.get("prix_eur") or info.get("prix_usd")
    if not prix:
        return None
    var = info.get("variation_24h", 0)
    arrow = "📈" if var >= 0 else "📉"
    msg = f"💰 {info['symbole']}: {prix:,.2f}€ {arrow} ({var:+.2f}% 24h)"
    if info.get("volume_24h"):
        vol = info["volume_24h"]
        msg += f"\n📊 Vol: ${vol/1e9:.1f}B" if vol > 1e9 else f"\n📊 Vol: ${vol/1e6:.1f}M"
    if info.get("market_cap"):
        mc = info["market_cap"]
        msg += f" | Cap: ${mc/1e9:.1f}B" if mc > 1e9 else f" | Cap: ${mc/1e6:.1f}M"
    return msg

def get_global_market():
    """Stats globales du marche crypto."""
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", {})
            return {"market_cap_total": data.get("total_market_cap", {}).get("usd", 0),
                    "volume_total": data.get("total_volume", {}).get("usd", 0),
                    "btc_dominance": round(data.get("market_cap_percentage", {}).get("btc", 0), 1)}
    except Exception as e:
        print(f"[COINGECKO] Erreur global: {e}")
    return None

def trading_performance():
    """Analyse ultra-complete des performances de trading."""
    try:
        with open(os.path.join(DOSSIER, "paper_trading.json"), 'r') as f:
            pf = json.load(f)
    except Exception:
        return "paper_trading.json non trouvé"
    
    trades = pf.get("trades", [])
    positions = pf.get("positions", [])
    capital = pf.get("capital", 0)
    liquidites = pf.get("liquidites", 0)
    
    # Stats détaillées
    gagnes = sum(1 for t in trades if t.get("pnl", 0) > 0)
    perdus = len(trades) - gagnes
    pnl_total = sum(t.get("pnl", 0) for t in trades)
    wr = gagnes / len(trades) * 100 if trades else 0
    
    # PnL par stratégie
    pnl_strat = defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0})
    for t in trades:
        strat = t.get("strategie", "inconnu")
        pnl = t.get("pnl", 0)
        if pnl > 0:
            pnl_strat[strat]["gagnes"] += 1
        else:
            pnl_strat[strat]["perdus"] += 1
        pnl_strat[strat]["pnl"] += pnl
    
    # PnL par actif
    pnl_actif = defaultdict(lambda: {"gagnes": 0, "perdus": 0, "pnl": 0})
    for t in trades:
        sym = t.get("symbole", "?")
        pnl = t.get("pnl", 0)
        if pnl > 0:
            pnl_actif[sym]["gagnes"] += 1
        else:
            pnl_actif[sym]["perdus"] += 1
        pnl_actif[sym]["pnl"] += pnl
    
    # Meilleur/worst trade
    if trades:
        best = max(trades, key=lambda t: t.get("pnl", 0))
        worst = min(trades, key=lambda t: t.get("pnl", 0))
    else:
        best = worst = None
    
    report = f"""
📊 PERFORMANCE TRADING
━━━━━━━━━━━━━━━━━━━━━━━━
Capital: {capital}€
Liquidités: {liquidites}€
Positions ouvertes: {len(positions)}
Trades fermés: {len(trades)} ({gagnes}G/{perdus}P)
Win Rate: {wr:.0f}%
PnL Total: {pnl_total:+.2f}€
"""
    
    if best and worst:
        report += f"\nMeilleur trade: {best.get('symbole', '?')} ({best.get('pnl', 0):+.2f}€)"
        report += f"\nPire trade: {worst.get('symbole', '?')} ({worst.get('pnl', 0):+.2f}€)"
    
    if pnl_strat:
        report += "\n\n📋 Par stratégie:"
        for strat, s in sorted(pnl_strat.items(), key=lambda x: x[1]["pnl"], reverse=True)[:5]:
            total = s["gagnes"] + s["perdus"]
            wr_s = s["gagnes"] / total * 100 if total > 0 else 0
            report += f"\n  {strat}: {s['gagnes']}G/{s['perdus']}P | WR {wr_s:.0f}% | {s['pnl']:+.2f}€"
    
    if pnl_actif:
        report += "\n\n💰 Par actif:"
        for sym, s in sorted(pnl_actif.items(), key=lambda x: x[1]["pnl"], reverse=True)[:5]:
            report += f"\n  {sym}: {s['gagnes']}G/{s['perdus']}P | {s['pnl']:+.2f}€"
    
    if positions:
        report += "\n\n📍 Positions ouvertes:"
        for pos in positions[:10]:
            sym = pos.get("symbole", "?")
            pnl = pos.get("pnl", 0)
            duree = pos.get("duree_min", 0)
            report += f"\n  {sym}: {pnl:+.2f}€ ({duree}min)"
    
    return report


# ============================================
# 5. SURVEILLANCE ET ALERTES
# ============================================
def check_opportunities():
    """Scanne le marché pour des opportunités en temps réel."""
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
              "LDOUSDT", "ARBUSDT", "AVAXUSDT", "LINKUSDT", "INJUSDT",
              "NEARUSDT", "FETUSDT", "RNDRUSDT", "SUIUSDT", "APTUSDT"]
    
    opportunities = []
    
    for sym in cryptos:
        try:
            tech = get_technical_data(sym)
            if "error" in tech:
                continue
            
            rsi = tech.get("rsi", 50)
            trend = tech.get("trend", "")
            var_24h = tech.get("variation_24h", 0)
            position = tech.get("position_range", 50)
            
            # Signaux d'opportunité
            score = 0
            raisons = []
            
            # RSI oversold + trend bull = opportunité
            if rsi < 35:
                score += 30
                raisons.append(f"RSI oversold ({rsi})")
            elif rsi < 45:
                score += 15
                raisons.append(f"RSI bas ({rsi})")
            
            # Trend bull
            if trend == "BULL":
                score += 20
                raisons.append("trend haussier")
            
            # Baisse récente (opportunité d'achat)
            if var_24h < -5:
                score += 25
                raisons.append(f"baisse 24h ({var_24h}%)")
            elif var_24h < -2:
                score += 10
                raisons.append(f"légère baisse ({var_24h}%)")
            
            # Position basse dans le range
            if position < 30:
                score += 15
                raisons.append(f"bas du range ({position}%)")
            
            if score >= 40:
                opportunities.append({
                    "symbole": sym,
                    "score": score,
                    "prix": tech.get("prix", 0),
                    "rsi": rsi,
                    "trend": trend,
                    "var_24h": var_24h,
                    "raisons": raisons,
                })
        except Exception:
            continue
    
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    return opportunities[:5]


def scan_and_alert():
    """Scanne le marché et envoie des alertes si opportunités."""
    opps = check_opportunities()
    
    if opps:
        msg = "🚨 OPPORTUNITÉS DÉTECTÉES\n━━━━━━━━━━━━━━━━━━\n"
        for o in opps:
            msg += f"\n{o['symbole']} (score: {o['score']}/100)\n"
            msg += f"  Prix: {o['prix']}\n"
            msg += f"  RSI: {o['rsi']} | Trend: {o['trend']}\n"
            msg += f"  Var 24h: {o['var_24h']}%\n"
            msg += f"  Pourquoi: {', '.join(o['raisons'])}\n"
        send_telegram(msg)
        return msg
    return None


# ============================================
# 6b. EXECUTION DE CODE - Ecrire et executer du Python
# ============================================
ALLOWED_IMPORTS = {
    "os", "sys", "json", "math", "time", "datetime", "collections",
    "requests", "re", "random", "statistics", "itertools", "functools",
    "decimal", "fractions", "hashlib", "base64", "csv", "io",
    "dotenv", "indicateurs", "gestion_risque", "backtest_moteur",
}

DANGEROUS_PATTERNS = [
    "import subprocess", "os.system", "os.popen",
    "os.remove", "os.rmdir", "os.unlink", "shutil.rmtree",
    "__import__", "eval(", "exec(",
    "open('/etc", "open('/var", "open('/root",
    "import socket", "import ctypes",
    "import multiprocessing", "os.exec",
    "os.spawn", "os.fork", "os.kill",
]

def validate_code(code):
    """Valide que le code est sur de executer."""
    # Verifie les imports
    for line in code.split('\n'):
        line = line.strip()
        if line.startswith('import ') or line.startswith('from '):
            # Extrait le nom du module
            if line.startswith('from '):
                mod = line.split()[1].split('.')[0]
            else:
                mod = line.split()[1].split(',')[0].strip().split(' as ')[0]
            if mod not in ALLOWED_IMPORTS:
                return False, f"Import interdit: {mod}"
    
    # Verifie les patterns dangereux
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            return False, f"Pattern dangereux detecte: {pattern}"
    
    return True, "OK"

def extract_code(text):
    """Extrait le code Python d'une reponse IA."""
    # Cherche blocs ```python ... ```
    blocks = re.findall(r'```python\n(.*?)```', text, re.DOTALL)
    if blocks:
        return blocks[0].strip()
    
    # Cherche blocs ``` ... ```
    blocks = re.findall(r'```\n(.*?)```', text, re.DOTALL)
    if blocks:
        return blocks[0].strip()
    
    # Cherche code qui commence par import ou def
    lines = text.split('\n')
    code_lines = []
    in_code = False
    for line in lines:
        if line.startswith('import ') or line.startswith('from ') or line.startswith('def ') or line.startswith('#'):
            in_code = True
        if in_code:
            code_lines.append(line)
    
    if code_lines:
        return '\n'.join(code_lines)
    
    return None

def execute_code(code, timeout=30):
    """Execute du code Python sur le VPS de maniere securisee."""
    # Valide le code
    is_safe, reason = validate_code(code)
    if not is_safe:
        return {"success": False, "error": f"Code rejete: {reason}", "output": ""}
    
    # Valide la syntaxe Python
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"success": False, "error": f"Erreur de syntaxe: {e}", "output": ""}
    
    # Cree un fichier temporaire
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"script_{timestamp}.py"
    filepath = os.path.join(CODE_DIR, filename)
    
    # Ajoute le path du dossier pour les imports locaux
    full_code = f"import sys\nsys.path.insert(0, '{DOSSIER}')\n\n{code}"
    
    with open(filepath, 'w') as f:
        f.write(full_code)
    
    try:
        # Execute avec timeout
        result = subprocess.run(
            [sys.executable, '-u', filepath],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=DOSSIER
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        
        return {
            "success": result.returncode == 0,
            "output": output[:3000],
            "returncode": result.returncode,
            "file": filename,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout apres {timeout}s", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}

def generate_and_run_code(instruction):
    """Genere du code avec l'IA puis l'execute sur le VPS."""
    # 1. Demande a l'IA de generer le code
    prompt = f"""Genere du code Python pour cette tache:
{instruction}

Regles:
- Code complet, executable, autonome
- Imports autorises: os, sys, json, math, time, datetime, requests, re, random, statistics, collections, csv, io, hashlib, base64, indicateurs, gestion_risque, backtest_moteur
- PAS de subprocess, PAS de os.system, PAS de fichiers systeme
- Affiche les resultats avec print()
- Code en français (commentaires)
- VERIFIE l'indentation (4 espaces)
- Reponds UNIQUEMENT avec le code dans un bloc ```python```"""
    
    ia_response = ask_perplexity(prompt, temperature=0.2)
    
    # 2. Extrait le code
    code = extract_code(ia_response)
    if not code:
        return {
            "success": False,
            "error": "Aucun code trouve dans la reponse IA",
            "ia_response": ia_response[:500],
        }
    
    # 3. Valide le code
    is_safe, reason = validate_code(code)
    if not is_safe:
        return {
            "success": False,
            "error": f"Code rejete pour securite: {reason}",
            "code": code[:500],
        }
    
    # 4. Execute
    result = execute_code(code)
    
    # 5. Si erreur de syntaxe, essaie de corriger
    if not result.get("success") and "syntaxe" in result.get("error", "").lower():
        fix_prompt = f"""Ce code Python a une erreur de syntaxe:
{code}

Erreur: {result['error']}

Corrige l'erreur et renvoie UNIQUEMENT le code corrige dans un bloc ```python```."""
        fixed_response = ask_perplexity(fix_prompt, temperature=0.1)
        fixed_code = extract_code(fixed_response)
        if fixed_code and fixed_code != code:
            is_safe2, reason2 = validate_code(fixed_code)
            if is_safe2:
                result = execute_code(fixed_code)
                result["auto_fixed"] = True
                result["code"] = fixed_code[:1000]
                return result
    
    return {
        "success": result.get("success", False),
        "code": code[:1000],
        "output": result.get("output", ""),
        "error": result.get("error", ""),
        "file": result.get("file", ""),
    }

def list_generated_scripts():
    """Liste les scripts generes."""
    scripts = []
    try:
        for f in os.listdir(CODE_DIR):
            if f.endswith('.py'):
                path = os.path.join(CODE_DIR, f)
                size = os.path.getsize(path)
                mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m %H:%M")
                scripts.append(f"{f} ({size}b, {mtime})")
    except Exception:
        pass
    return scripts

def run_existing_script(filename):
    """Re-execute un script deja genere."""
    if not filename.endswith('.py'):
        filename += '.py'
    filepath = os.path.join(CODE_DIR, filename)
    if not os.path.exists(filepath):
        return {"success": False, "error": f"Script {filename} introuvable"}
    
    with open(filepath, 'r') as f:
        code = f.read()
    
    return execute_code(code)

# ============================================
# 6. TRAITEMENT DES MESSAGES TELEGRAM
# ============================================
def handle_message(text, user_name="User"):
    """Traite un message avec intelligence et contexte."""
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    
    # Sauvegarde dans la mémoire
    _conversation_history.append({"role": "user", "text": text_stripped})
    
    # Contexte des conversations précédentes
    context = get_context_from_memory()
    
    # === COMMANDES RAPIDES ===
    
    if text_lower in ["status", "etat", "état", "perf", "performance"]:
        response = trading_performance()
        send_telegram(response)
        save_memory("user", text_stripped, response)
        return response
    
    if text_lower in ["opportunites", "opportunités", "scan", "opportunite"]:
        msg = scan_and_alert()
        if not msg:
            response = "Aucune opportunité détectée actuellement. Le marché est calme."
            send_telegram(response)
        save_memory("user", text_stripped, msg or response)
        return msg or response
    
    if text_lower in ["news", "actu", "actualités", "actualites"]:
        result = ask_perplexity(
            "Donne les 5 dernières actualités crypto importantes en français, "
            "de façon concise (2 lignes par actu). Format: numéro + titre + résumé."
        )
        send_telegram(f"📰 Actus Crypto:\n\n{result}")
        save_memory("user", text_stripped, result)
        return result
    
    if text_lower in ["sentiment", "marche", "marché", "bull", "bear"]:
        result = ask_perplexity(
            "Analyse le sentiment actuel du marché crypto en français:\n"
            "1. Fear & Greed Index actuel\n"
            "2. Tendance Bitcoin (bull/bear/neutre)\n"
            "3. Recommandation courte terme\n"
            "Sois concis (5 lignes max)."
        )
        send_telegram(f"📊 Sentiment Marché:\n\n{result}")
        save_memory("user", text_stripped, result)
        return result
    
    if text_lower in ["top", "top crypto", "meilleur crypto", "meilleures crypto"]:
        result = ask_perplexity(
            "Quelles sont les 5 meilleures cryptos à surveiller aujourd'hui? "
            "Pour chacune: nom, prix approximatif, raison (1 ligne). "
            "Réponds en français."
        )
        send_telegram(f"🏆 Top Crypto:\n\n{result}")
        save_memory("user", text_stripped, result)
        return result
    
    # === PRIX CRYPTO EN TEMPS REEL ===
    # Detection en langage naturel: "prix du btc", "donne moi le prix de eth", "cours du sol", etc.
    prix_patterns = ["prix du", "prix de", "prix d'", "cours du", "cours de", "cours d'",
                     "combien coute", "combien vaut", "valeur du", "valeur de"]
    is_prix_request = any(p in text_lower for p in prix_patterns) or text_lower.startswith("prix ") or text_lower.startswith("cours ")
    
    if is_prix_request or text_lower in ["prix", "cours", "prix crypto", "cours crypto"]:
        # Extrait le symbole du message
        symbole = None
        if text_lower in ["prix", "cours", "prix crypto", "cours crypto"]:
            symbole = None  # Affiche tous les prix
        else:
            # Cherche un symbole crypto dans le message
            cryptos_connues = list(COINGECKO_IDS.keys())
            mots = text_stripped.upper().replace(",", " ").replace(".", " ").split()
            for c in cryptos_connues:
                if c in mots or c + "USDT" in text_stripped.upper() or c + "USD" in text_stripped.upper():
                    symbole = c
                    break
            # Cherche aussi les noms complets
            noms_complets = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
                           "cardano": "ADA", "dogecoin": "DOGE", "ripple": "XRP",
                           "litecoin": "LTC", "polkadot": "DOT", "chainlink": "LINK",
                           "avalanche": "AVAX", "binance": "BNB"}
            for nom, sym in noms_complets.items():
                if nom in text_lower and not symbole:
                    symbole = sym
                    break
        
        if symbole:
            info = get_crypto_price(symbole)
            if info:
                msg = format_price(info)
            else:
                msg = f"❌ {symbole} non trouve. Cryptos: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, etc."
        else:
            # Top 8 cryptos
            top_symboles = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK"]
            prices = get_multiple_prices(top_symboles)
            if prices:
                msg = "💰 PRIX DU MARCHE\n━━━━━━━━━━━━━━━━━━\n"
                for p in prices:
                    var = p.get("variation_24h", 0)
                    arrow = "📈" if var >= 0 else "📉"
                    msg += f"{p['symbole']}: {p['prix_eur']:,.2f}€ {arrow} ({var:+.2f}%)\n"
                global_data = get_global_market()
                if global_data:
                    msg += f"\n📊 Cap total: ${global_data['market_cap_total']/1e9:.0f}B"
                    msg += f" | Vol 24h: ${global_data['volume_total']/1e9:.0f}B"
                    msg += f"\n BTC dominance: {global_data['btc_dominance']}%"
            else:
                msg = "Erreur recuperation prix. Reessaie plus tard."
        send_telegram(msg)
        return msg
    
    # === ANALYSE D'UN CRYPTO ===
    if text_lower.startswith("analyser") or text_lower.startswith("analyse") or text_lower.startswith("analyse "):
        words = text_stripped.split()
        if len(words) > 1:
            symbole = words[1].upper()
            if not symbole.endswith("USDT"):
                symbole += "USDT"
            send_telegram(f"🔍 Analyse de {symbole} en cours...")
            result = crypto_deep_analysis(symbole)
            
            # Formatage
            tech = result.get("technique", {})
            rec = result.get("recommandation", "")
            
            msg = f"📊 ANALYSE {symbole}\n━━━━━━━━━━━━━━━━━━\n"
            if "prix" in tech:
                msg += f"Prix: {tech['prix']}\n"
                msg += f"Var 1h: {tech['variation_1h']}% | 24h: {tech['variation_24h']}% | 7j: {tech['variation_7j']}%\n"
                msg += f"RSI: {tech['rsi']} | Trend: {tech['trend']}\n"
                msg += f"Position range: {tech.get('position_range', '?')}%\n"
                msg += f"ATR: {tech.get('atr_pct', '?')}%\n"
            msg += f"\n🤖 Recommandation IA:\n{rec[:1500]}"
            
            send_telegram(msg)
            save_memory("user", text_stripped, msg)
            return msg
    
    # === RECHERCHE WEB ===
    if text_lower.startswith("recherche") or text_lower.startswith("search"):
        query = text_stripped[len("recherche"):].strip() or text_stripped[len("search"):].strip()
        if not query:
            query = text_stripped  # Prend tout si pas de mot-clé
        if query:
            send_telegram(f"🔍 Recherche: {query}...")
            result = ask_perplexity(f"Réponds en français de façon concise:\n{query}")
            send_telegram(f"🔍 {query}\n\n{result}")
            save_memory("user", text_stripped, result)
            return result
    
    # === RÉSOUDRE UN PROBLÈME (avec memoire de resolution) ===
    if text_lower.startswith("resoudre") or text_lower.startswith("résoudre") or text_lower.startswith("solve"):
        problem = text_stripped[len("resoudre"):].strip() or text_stripped[len("résoudre"):].strip() or text_stripped[len("solve"):].strip()
        if problem:
            # Cherche d'abord dans les solutions existantes
            similar = search_similar_problem(problem, limit=1)
            if similar and similar[0].get("score", 0) >= 3:
                send_telegram(f"🧠 Solution similaire trouvee dans ma memoire! Adaptation...")
            else:
                send_telegram(f"🧠 Resolution en cours...")
            
            result, steps = smart_solve(problem)
            
            msg = "🧠 Solution:\n\n"
            if steps:
                msg += f"📝 Etapes: {', '.join(steps)}\n\n"
            msg += result
            send_telegram(msg)
            save_memory("user", text_stripped, result)
            learn_fact(problem, "lesson")
            return result
    
    if text_lower in ["stats", "health", "watchdog"]:
        stats = get_stats()
        msg = f"📊 STATS AGENT\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"⏱ Uptime: {stats['uptime']}\n"
        msg += f"💬 Messages recus: {stats.get('messages_recus', 0)}\n"
        msg += f"✅ Messages repondus: {stats.get('messages_repondus', 0)}\n"
        msg += f"❌ Erreurs: {stats.get('erreurs', 0)}\n"
        msg += f"⏳ API timeouts: {stats.get('api_timeouts', 0)}\n"
        # Verifie l'etat des fichiers
        files_check = ["agent_memory.json", "paper_trading.json", "knowledge_base.json"]
        msg += "\n📁 Fichiers:\n"
        for f in files_check:
            path = os.path.join(DOSSIER, f)
            exists = "✅" if os.path.exists(path) else "❌"
            size = os.path.getsize(path) if os.path.exists(path) else 0
            msg += f"  {exists} {f} ({size}b)\n"
        # Verifie le papier trading
        try:
            pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
            capital = pt.get("capital_initial", "?")
            liquidites = pt.get("liquidites", "?")
            positions = len(pt.get("positions", []))
            trades = len(pt.get("trades", []))
            msg += f"\n💰 Capital: {capital}€\n"
            msg += f"💵 Liquidites: {liquidites}€\n"
            msg += f"📊 Positions: {positions}\n"
            msg += f"📝 Trades: {trades}\n"
        except:
            msg += "\n❌ paper_trading.json illisible\n"
        send_telegram(msg)
        return msg
    
    # === CODE AUTONOME ===
    if text_lower in ["code-seul", "code seul", "autonome", "code autonome", "improve", "auto-code"]:
        send_telegram("🤖 Demarrage du codage autonome...\nAnalyse du systeme + codage + test en cours.")
        bilan = autonomous_coder()
        return bilan
    
    # === RECHERCHE WEB ===
    if text_lower.startswith("recherche") or text_lower.startswith("search"):
        query = text_stripped.split(" ", 1)[1] if " " in text_stripped else ""
        if not query:
            send_telegram("Usage: recherche [sujet]\nEx: recherche bitcoin halving 2026")
            return ""
        send_telegram(f"🔍 Recherche web: {query}...")
        result = web_search(query)
        send_telegram(result)
        save_memory("user", text_stripped, result)
        return result
    
    # === RAPPORTS AUTO ===
    if text_lower in ["rapport", "bilan", "report"]:
        send_telegram("📊 Generation du rapport...")
        rapport = generate_report()
        send_telegram(rapport[:4000])
        # Sauvegarde en fichier HTML
        filepath = os.path.join(DOSSIER, f"rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"<html><head><meta charset='utf-8'><style>body{{font-family:Arial;max-width:800px;margin:auto;padding:20px}}h1{{color:#2196F3}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}</style></head><body>{rapport.replace(chr(10),'<br>')}</body></html>")
        send_telegram(f"📁 Rapport sauvegarde: rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
        save_memory("agent", "rapport", rapport)
        return rapport
    
    # === AUTO-AMELIORATION ===
    if text_lower in ["auto-ameliorer", "evolue", "ameliorer", "self-improve"]:
        send_telegram("🧠 Auto-amenlioration lancee...\nAnalyse des faiblesses + corrections.")
        bilan = self_improve()
        send_telegram(bilan)
        return bilan
    
    # === TACHES PROGRAMMEES ===
    if text_lower.startswith("planifie") or text_lower.startswith("programme"):
        result = schedule_task(text_stripped)
        send_telegram(result)
        return result
    
    if text_lower in ["taches", "planning", "schedule"]:
        result = list_scheduled_tasks()
        send_telegram(result)
        return result
    
    # === ALERTES ===
    if text_lower in ["alertes", "alerte", "veille"]:
        send_telegram("🚨 Scan des alertes en cours...")
        result = alertes_intelligentes()
        if isinstance(result, tuple):
            send_telegram(result[0])
            return result[0]
        else:
            send_telegram(result)
            return result
    
    # === COMPARATIF ===
    if text_lower in ["comparatif", "compare", "comparer", "classement"]:
        send_telegram("📊 Analyse comparative en cours...")
        result = analyse_comparative()
        send_telegram(result[:4000])
        return result
    
    # === GRAPHIQUES ===
    if text_lower.startswith("graph") or text_lower.startswith("chart"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() if len(parts) > 1 else "BTC"
        symbole = symbole + "USDT" if not symbole.endswith("USDT") else symbole
        send_telegram(f"📊 Generation du graphique {symbole}...")
        result = generer_graphique(symbole)
        if isinstance(result, str) and result.startswith("Erreur"):
            send_telegram(result)
        return result or ""
    
    if text_lower in ["graph pnl", "chart pnl", "pnl chart"]:
        send_telegram("📊 Generation du graphique PnL...")
        result = generer_graphique_pnl()
        if isinstance(result, str) and result.startswith("Erreur"):
            send_telegram(result)
        return result or ""
    
    # === BACKTEST RAPIDE ===
    if text_lower.startswith("backtest"):
        parts = text_stripped.split(None, 2)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        strategie = parts[2].lower() if len(parts) > 2 else "momentum"
        send_telegram(f"🔬 Backtest {symbole} strategie {strategie}...")
        result = backtest_rapide(symbole, strategie)
        send_telegram(result[:4000])
        return result
    
    # === PNL TEMPS REEL ===
    if text_lower in ["pnl", "gain", "gains", "pertes", "latents"]:
        send_telegram("💰 Calcul du PnL temps reel...")
        result = pnl_temps_reel()
        send_telegram(result[:4000])
        return result
    
    # === ALERTES PRIX ===
    if text_lower.startswith("alerte") and not text_lower in ["alertes", "alerte"]:
        # alerte BTC 70000 | alerte supprime 2 | alerte liste
        if "supprime" in text_lower or "remove" in text_lower or "delete" in text_lower:
            result = supprimer_alerte_prix(text_stripped)
            send_telegram(result)
            return result
        elif "liste" in text_lower or "list" in text_lower:
            result = lister_alertes_prix()
            send_telegram(result)
            return result
        else:
            result = ajouter_alerte_prix(text_stripped)
            send_telegram(result)
            return result
    
    if text_lower in ["alertes prix", "prix alertes"]:
        result = lister_alertes_prix()
        send_telegram(result)
        return result
    
    # === MULTI-TIMEFRAME ===
    if text_lower.startswith("mtf") or (text_lower.startswith("multi") and "time" in text_lower):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🔬 Analyse multi-timeframe {symbole}...")
        result = analyse_multi_timeframe(symbole)
        send_telegram(result[:4000])
        return result
    
    # === SENTIMENT NEWS ===
    if text_lower.startswith("sentiment") or text_lower.startswith("news"):
        parts = text_stripped.split(None, 1)
        crypto = parts[1].upper().replace("USDT", "") if len(parts) > 1 else "BTC"
        send_telegram(f"📰 Analyse sentiment {crypto}...")
        result = sentiment_news(crypto)
        send_telegram(result[:4000])
        return result
    
    # === APPRENTISSAGE AUTO ===
    if text_lower in ["apprentissage", "apprend", "learn", "analyse trades"]:
        send_telegram("📚 Analyse des trades en cours...")
        result = apprentissage_auto_trades()
        send_telegram(result[:4000])
        return result
    
    # === CORRELATIONS ===
    if text_lower in ["correlations", "correlation", "corr", "diversification"]:
        send_telegram("🔗 Analyse des correlations...")
        result = detection_correlations()
        send_telegram(result[:4000])
        return result
    
    # === PREVISION IA ===
    if text_lower.startswith("prevision") or text_lower.startswith("forecast"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🔮 Generation prevision {symbole}...")
        result = prevision_ia_prix(symbole)
        send_telegram(result[:4000])
        return result
    
    # === AIDE ===
    if text_lower in ["aide", "help", "commandes", "commands"]:
        help_msg = """🤖 AGENT OS - COMMANDES

━━━━━━━━━━━━━━━━━━━━
📊 TRADING:
  prix - Prix du marche (top 8)
  prix BTC - Prix d'un crypto precis
  status - Performance du portefeuille
  opportunites - Scanner les opportunites
  analyser BTC - Analyse complete d'un crypto
  sentiment - Sentiment du marche

📰 INFO:
  news - Actualités crypto
  top - Top 5 crypto à surveiller
  recherche [sujet] - Recherche web

🧠 IA:
  resoudre [problème] - Résoudre un problème
  code [description] - Génère et exécute du code Python
  scripts - Liste les scripts générés
  run [nom] - Ré-exécute un script
  [question] - Pose n'importe quelle question

🧠 MEMOIRE:
  memoire - Resume de la memoire
  profil - Ton profil utilisateur
  souviens [info] - Retiens quelque chose
  cherche [mots] - Recherche dans la memoire
  oublie - Oublie la derniere conversation
  stats - Stats et sante de l'agent
  code-seul - L'agent code seul et s'ameliorer

🔧 AVANCE:
  recherche [sujet] - Recherche web via Perplexity
  rapport - Genere un rapport complet (HTML)
  auto-ameliorer - L'agent analyse ses faiblesses et se corrige
  planifie [tache] - Planifie une tache repetitive
  taches - Liste les taches programmees

🔬 ANALYSE:
  alertes - Alertes intelligentes (RSI extreme, pump/dump)
  comparatif - Compare les cryptos et recommande les meilleures
  graph BTC - Genere un graphique (prix + RSI) en image
  graph pnl - Graphique du PnL cumule
  backtest BTC momentum - Backtest rapide d'une strategie

💰 TRADING:
  pnl - PnL temps reel (gains/pertes latents)
  alerte BTC 70000 - Alerte prix personnalisee
  alerte BTC 70000 bas - Alerte prix a la baisse
  alerte liste - Liste tes alertes prix
  alerte supprime 2 - Supprime une alerte
  mtf BTC - Analyse multi-timeframe (15m, 1h, 4h, 1d)

🧠 INTELLIGENCE:
  sentiment BTC - Sentiment des news + communaute
  apprentissage - Analyse les trades et ajuste les strategies
  correlations - Detecte les correlations du portefeuille
  prevision BTC - Prevision de prix 24h/7j + analyse IA

━━━━━━━━━━━━━━━━━━━━
L'agent apprend de chaque interaction."""
        send_telegram(help_msg)
        return help_msg
    
    if text_lower.startswith("memoire"):
        msg = get_memory_summary()
        send_telegram(msg)
        return msg
    
    if text_lower.startswith("souviens") or text_lower.startswith("rapelle") or text_lower.startswith("retiens"):
        # Force la sauvegarde comme important
        memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "important_conv": []})
        entry = {
            "role": "user",
            "message": text_stripped,
            "response": "",
            "timestamp": datetime.now().isoformat(),
            "importance": 3,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "heure": datetime.now().strftime("%H:%M"),
        }
        memoire.setdefault("important_conv", []).append(entry)
        memoire.setdefault("conversations", []).append(entry)
        save_json_safe(MEMORY_FILE, memoire)
        learn_fact(text_stripped, "lesson")
        msg = "✅ Retenu! Je m'en souviendrai."
        send_telegram(msg)
        return msg
    
    if text_lower.startswith("cherche ") or text_lower.startswith("recherche memoire"):
        query = text_stripped.split(" ", 1)[1] if " " in text_stripped else ""
        if query:
            results = search_memory(query)
            if results:
                msg = f"🔍 {len(results)} resultats pour '{query}':\n\n"
                for i, r in enumerate(results, 1):
                    msg += f"{i}. [{r.get('date', '?')}] {r['message'][:150]}\n"
                    if r.get("response"):
                        msg += f"   -> {r['response'][:100]}\n"
            else:
                msg = f"Rien trouve pour '{query}' dans ma memoire."
        else:
            msg = "Usage: cherche [mots cles]"
        send_telegram(msg)
        return msg
    
    if text_lower.startswith("oublie"):
        if forget_last():
            msg = "✅ Derniere conversation oubliee."
        else:
            msg = "Rien a oublier."
        send_telegram(msg)
        return msg
    
    if text_lower.startswith("profil"):
        profile = load_profile()
        msg = f"👤 PROFIL UTILISATEUR\n\n"
        msg += f"Nom: {profile.get('nom', '?')}\n"
        msg += f"Capital: {profile.get('capital', '?')}€\n"
        msg += f"Total echanges: {profile.get('total_conversations', 0)}\n"
        cryptos = profile.get("cryptos_suivies", [])
        if cryptos:
            msg += f"Cryptos: {', '.join(cryptos[:15])}\n"
        strats = profile.get("strategies_preferees", [])
        if strats:
            msg += f"Strategies: {', '.join(strats[:10])}\n"
        sujets = profile.get("sujets_explores", {})
        if sujets:
            top = sorted(sujets.items(), key=lambda x: x[1], reverse=True)[:5]
            msg += f"Sujets: {', '.join([f'{s}({n})' for s, n in top])}\n"
        msg += f"\nDerniere interaction: {profile.get('derniere_interaction', 'jamais')}\n"
        send_telegram(msg)
        return msg
    
    # === EXECUTION DE CODE ===
    if text_lower.startswith("code ") or text_lower.startswith("execute ") or text_lower.startswith("codegen "):
        instruction = text_stripped.split(" ", 1)[1] if " " in text_stripped else ""
        if not instruction:
            response = "Usage: code [description de la tache]\nExemple: code calcule la moyenne mobile du BTC sur 20 jours"
            send_telegram(response)
            return response
        
        send_telegram(f"🤖 Generation et execution du code...\nTache: {instruction[:100]}")
        result = generate_and_run_code(instruction)
        
        if result.get("success"):
            msg = f"✅ Code execute avec succes\n"
            msg += f"📁 Fichier: {result.get('file', '?')}\n"
            msg += f"\n📤 Sortie:\n{result.get('output', '')[:2000]}"
            send_telegram(msg)
            save_memory("user", text_stripped, msg)
            learn_fact(f"Code genere pour: {instruction[:100]}", "strategy")
            return msg
        else:
            msg = f"❌ Erreur\n"
            if result.get("error"):
                msg += f"Erreur: {result['error']}\n"
            if result.get("code"):
                msg += f"\nCode genere:\n```python\n{result['code'][:1000]}\n```\n"
            if result.get("output"):
                msg += f"\nSortie:\n{result['output'][:1000]}"
            send_telegram(msg)
            return msg
    
    if text_lower.startswith("scripts"):
        scripts = list_generated_scripts()
        if scripts:
            msg = "📁 Scripts generes:\n\n" + "\n".join(scripts[:20])
        else:
            msg = "Aucun script genere pour l'instant.\nUtilise: code [description] pour en créer un."
        send_telegram(msg)
        return msg
    
    if text_lower.startswith("run "):
        filename = text_stripped.split(" ", 1)[1].strip()
        send_telegram(f"🔄 Execution de {filename}...")
        result = run_existing_script(filename)
        if result.get("success"):
            msg = f"✅ Executé\n\n{result.get('output', '')[:2000]}"
        else:
            msg = f"❌ Erreur: {result.get('error', 'inconnue')}\n{result.get('output', '')[:1000]}"
        send_telegram(msg)
        return msg
    
    # === CONVERSATION GÉNÉRALE (rapide et intelligente) ===
    # Detecte si l'utilisateur corrige une reponse precedente
    memoire = load_json_safe(MEMORY_FILE, {"conversations": []})
    last_conv = memoire.get("conversations", [])[-1] if memoire.get("conversations") else None
    if last_conv and last_conv.get("response"):
        detect_correction(text_stripped, last_conv["response"])
    
    # Auto-resume si trop de conversations
    auto_summarize_old_conversations()
    
    # Contexte leger (pas trop de texte pour aller vite)
    profile = load_profile()
    recent_convs = memoire.get("conversations", [])[-3:]
    
    context = f"Profil: {profile.get('nom', 'Tamaya')}, capital {profile.get('capital', 1000)}€\n"
    if recent_convs:
        context += "Dernieres conversations:\n"
        for c in recent_convs:
            role = "User" if c["role"] == "user" else "Agent"
            context += f"  {role}: {c['message'][:80]}\n"
    
    # Corrections recentes (3 max)
    corrections_db = load_json_safe(CORRECTIONS_FILE, {"corrections": []})
    corrections = corrections_db.get("corrections", [])[-3:]
    if corrections:
        context += "\nCorrections (ne repete pas):\n"
        for c in corrections:
            context += f"  {c['error'][:60]} -> {c['correction'][:60]}\n"
    
    # === COUCHE NLP: comprendre le langage naturel ===
    nlp_result = comprendre_message(text_stripped)
    if nlp_result:
        send_telegram(nlp_result[:4000] if isinstance(nlp_result, str) else str(nlp_result)[:4000])
        save_memory("user", text_stripped, nlp_result[:200] if isinstance(nlp_result, str) else "")
        return nlp_result
    
    # Prompt court pour aller vite
    prompt = f"""Tu es un assistant IA expert en trading crypto et technologie.
Utilisateur: {profile.get('nom', 'Tamaya')} (capital {profile.get('capital', 1000)}€)

{context}

Question: {text_stripped}

Reponds en français, concis et direct. Maximum 5 phrases."""
    
    response = ask_perplexity(prompt)
    send_telegram(response)
    save_memory("user", text_stripped, response)
    
    # Apprend de la conversation
    if len(text_stripped) > 20:
        learn_fact(f"Q: {text_stripped[:100]} -> R: {response[:100]}", "general")
    
    return response


# ============================================
# 7. BOUCLE TELEGRAM
# ============================================
def telegram_poll():
    """Écoute Telegram en continu avec gestion d'erreurs robuste."""
    if not TELEGRAM_TOKEN:
        print("[AGENT OS] Pas de token Telegram")
        return
    
    # Gestionnaire de signaux pour arret propre
    def _signal_handler(signum, frame):
        print(f"\n[AGENT OS] Signal {signum} recu - arret propre...")
        try:
            send_telegram("⚠️ Agent OS redemarre...")
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
    print("[AGENT OS V2] Écoute Telegram démarrée")
    print("[AGENT OS V2] Envoie 'aide' sur Telegram pour voir les commandes")
    
    offset = 0
    last_health_check = time.time()
    last_watchdog = time.time()
    last_alerte_check = time.time()
    consecutive_errors = 0
    
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            
            if r.status_code != 200:
                print(f"[AGENT OS] Telegram HTTP {r.status_code}")
                consecutive_errors += 1
                if consecutive_errors > 10:
                    print("[AGENT OS] Trop d'erreurs - pause 30s")
                    time.sleep(30)
                    consecutive_errors = 0
                else:
                    time.sleep(5)
                continue
            
            consecutive_errors = 0  # Reset si OK
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                user_name = msg.get("from", {}).get("first_name", "User")
                
                if text:
                    print(f"[CHAT] {user_name}: {text}")
                    increment_stat("messages_recus")
                    # Lance le traitement dans un thread pour ne pas bloquer
                    import threading as _th
                    def _process():
                        try:
                            # Indicateur 'typing' repeat
                            def _keep_typing():
                                while True:
                                    try:
                                        requests.get(
                                            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                                            params={"chat_id": TELEGRAM_CHAT_ID, "action": "typing"},
                                            timeout=3
                                        )
                                    except:
                                        pass
                                    time.sleep(4)
                            
                            t_typing = _th.Thread(target=_keep_typing, daemon=True)
                            t_typing.start()
                            handle_message(text, user_name)
                            increment_stat("messages_repondus")
                        except Exception as e:
                            increment_stat("erreurs")
                            print(f"[CHAT] Erreur traitement: {e}")
                            print(traceback.format_exc()[:500])
                            try:
                                send_telegram(f"Erreur: {e}")
                            except:
                                pass
                    t = _th.Thread(target=_process, daemon=True)
                    t.start()
            
            # Health check toutes les 10 min
            if time.time() - last_health_check > 600:
                last_health_check = time.time()
                print(f"[AGENT OS] Health check OK - {datetime.now().strftime('%H:%M')}")
            
            # Verifier les alertes prix toutes les 5 minutes
            if time.time() - last_alerte_check > 300:
                last_alerte_check = time.time()
                try:
                    nb = verifier_alertes_prix()
                    if nb > 0:
                        print(f"[AGENT OS] {nb} alerte(s) prix declenchee(s)")
                except Exception as e:
                    print(f"[AGENT OS] Erreur alertes prix: {e}")
                
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"[AGENT OS] Erreur: {e}")
            time.sleep(10)


# ============================================
# 8. BOUCLE AUTONOME
# ============================================
def autonomous_loop():
    """Boucle autonome: scanne le marche + alertes."""
    print("=" * 60)
    print(f"AGENT OS V2 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    # 1. Scan d'opportunites
    print("\n[1] Scan des opportunites...")
    opps = check_opportunities()
    if opps:
        print(f"    {len(opps)} opportunites detectees")
        for o in opps:
            print(f"    {o['symbole']}: score {o['score']} - {', '.join(o['raisons'])}")
    else:
        print("    Aucune opportunite")
    
    # 2. Performance trading
    print("\n[2] Performance trading...")
    perf = trading_performance()
    print(perf[:500])
    
    # 3. Sentiment marche
    print("\n[3] Sentiment marche...")
    sentiment = ask_perplexity(
        "Donne le sentiment crypto actuel en 3 lignes max (francais): "
        "Fear & Greed index, trend BTC, recommandation."
    )
    print(f"    {sentiment[:200]}")
    
    # 4. Apprend
    learn_fact(f"Scan {datetime.now().strftime('%H:%M')}: {len(opps)} opportunites, sentiment={sentiment[:100]}", "market")
    
    print("\n" + "=" * 60)
    print("Cycle autonome termine")


def autonomous_coder():
    """L'agent code seul: analyse le systeme, identifie des ameliorations, code et test."""
    print("\n" + "=" * 60)
    print(f"[AUTONOMOUS CODER] {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    taches_faites = []
    
    # 1. Analyse le systeme de trading
    print("[1] Analyse du systeme...")
    try:
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        capital = pt.get("capital_initial", 1000)
        liquidites = pt.get("liquidites", 0)
        positions = pt.get("positions", [])
        trades = pt.get("trades", [])
        
        # Calcule les stats
        if trades:
            gagnants = [t for t in trades if t.get("pnl", 0) > 0]
            perdants = [t for t in trades if t.get("pnl", 0) < 0]
            winrate = len(gagnants) / len(trades) * 100 if trades else 0
            pnl_total = sum(t.get("pnl", 0) for t in trades)
            
            analyse = f"""Capital: {capital}€ | Liquidites: {liquidites}€
Positions ouvertes: {len(positions)}
Trades total: {len(trades)} | Gagnants: {len(gagnants)} | Perdants: {len(perdants)}
Winrate: {winrate:.1f}% | PnL: {pnl_total:.2f}€"""
        else:
            analyse = f"Capital: {capital}€ | Liquidites: {liquidites}€ | 0 trade"
        print(f"  {analyse}")
    except Exception as e:
        analyse = f"Erreur analyse: {e}"
        print(f"  {analyse}")
    
    # 2. Identifie les ameliorations possibles
    print("\n[2] Identification des ameliorations...")
    ameliorations = []
    
    # Si winrate < 50%, code un meilleur filtre
    if trades and winrate < 50:
        ameliorations.append({
            "titre": "Filtre anti-perte",
            "description": f"Le winrate est de {winrate:.0f}%. Cree un script qui analyse les trades perdants et identifie les patterns a eviter",
            "instruction": f"Analyse les trades dans paper_trading.json. Pour chaque trade perdant (pnl < 0), affiche le symbole, la strategie utilisee, et le PnL. Affiche un resume des strategies qui perdent le plus.",
        })
    
    # Si peu de positions, code un scanner d'opportunites
    if len(positions) < 5:
        ameliorations.append({
            "titre": "Scanner d'opportunites",
            "description": "Peu de positions ouvertes. Cree un scanner deportunites",
            "instruction": f"Recupere les prix de BTC, ETH, SOL, BNB, XRP via l'API CoinGecko (api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,binancecoin,ripple&vs_currencies=eur&include_24hr_change=true). Affiche ceux qui ont une variation negative > -2% (potentiel achat).",
        })
    
    # Code un rapport de performance
    ameliorations.append({
        "titre": "Rapport performance",
        "description": "Genere un rapport de performance detaille",
        "instruction": f"Lis paper_trading.json. Affiche: capital initial, liquidites actuelles, nombre de positions ouvertes, nombre total de trades, nombre de trades gagnants/perdants, winrate en %, PnL total. Affiche aussi les 3 derniers trades avec date, symbole, strategie et PnL.",
    })
    
    # Code un analyseur de volatilite
    ameliorations.append({
        "titre": "Analyseur volatilite",
        "description": "Cree un analyseur de volatilite crypto",
        "instruction": f"Recupere les prix et variations 24h de BTC, ETH, SOL, BNB, DOGE, AVAX, LINK, XRP via CoinGecko (api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,binancecoin,dogecoin,avalanche-2,chainlink,ripple&vs_currencies=eur&include_24hr_change=true). Classe-les du plus volatile au moins volatile. Affiche un score de volatilite (absolu de la variation 24h).",
    })
    
    print(f"  {len(ameliorations)} ameliorations identifiees")
    for a in ameliorations:
        print(f"  - {a['titre']}")
    
    # 3. Code et execute chaque amelioration
    print("\n[3] Codage et test...")
    for i, amel in enumerate(ameliorations, 1):
        print(f"\n  [{i}/{len(ameliorations)}] {amel['titre']}...")
        result = generate_and_run_code(amel["instruction"])
        
        if result.get("success"):
            output = result.get("output", "")[:500]
            taches_faites.append(f"✅ {amel['titre']}: {output[:100]}")
            print(f"    ✅ Succes")
            print(f"    Output: {output[:200]}")
            
            # Envoie le resultat sur Telegram
            msg = f"🤖 CODAGE AUTONOME\n━━━━━━━━━━━━━━━━━━\n"
            msg += f"📋 Tache: {amel['titre']}\n"
            msg += f"📁 Fichier: {result.get('file', '?')}\n"
            msg += f"📤 Resultat:\n{output[:1500]}"
            if result.get("auto_fixed"):
                msg += "\n\n🔧 Code auto-corrige"
            send_telegram(msg)
            
            # Apprend du resultat
            save_solution(amel["instruction"], output, category=amel["titre"])
            learn_fact(f"Code autonome: {amel['titre']} -> {output[:100]}", "strategy")
        else:
            error = result.get("error", "inconnue")[:200]
            taches_faites.append(f"❌ {amel['titre']}: {error[:50]}")
            print(f"    ❌ Echec: {error[:100]}")
        
        time.sleep(2)  # Pause entre chaque tache
    
    # 4. Bilan
    print("\n[4] Bilan...")
    bilan = "🤖 BILAN CODAGE AUTONOME\n━━━━━━━━━━━━━━━━━━\n"
    bilan += f"Tentatives: {len(ameliorations)}\n"
    reussis = [t for t in taches_faites if t.startswith("✅")]
    echoues = [t for t in taches_faites if t.startswith("❌")]
    bilan += f"Reussis: {len(reussis)} | Echoues: {len(echoues)}\n\n"
    for t in taches_faites:
        bilan += f"{t}\n"
    
    print(bilan)
    send_telegram(bilan)
    
    # Sauvegarde le bilan en memoire
    save_memory("agent", f"Codage autonome: {len(reussis)}/{len(ameliorations)} reussis", bilan)
    learn_fact(f"Codage autonome {datetime.now().strftime('%d/%m %H:%M')}: {len(reussis)}/{len(ameliorations)} reussis", "strategy")
    
    print("\n" + "=" * 60)
    print("Codage autonome termine")
    return bilan


# ============================================
# 9. RECHERCHE WEB
# ============================================
def web_search(query):
    """Recherche web via Perplexity API avec sources."""
    prompt = f"""Recherche web: {query}

Reponds en francais de facon structuree:
1. Resume (3-5 lignes)
2. Points cles (3-5 bullet points)
3. Sources (nom + URL si possible)

Sois precis et factuel."""
    result = ask_perplexity(prompt, temperature=0.1)
    learn_fact(f"Recherche web: {query[:50]}", "research")
    return result


# ============================================
# 10. RAPPORTS AUTOMATIQUES
# ============================================
def generate_report():
    """Genere un rapport complet du systeme."""
    rapport = f"""📊 RAPPORT SYSTEME - {datetime.now().strftime('%d/%m/%Y %H:%M')}
{'='*50}

## 1. PERFORMANCE TRADING
"""
    try:
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        capital = pt.get("capital_initial", 0)
        liquidites = pt.get("liquidites", 0)
        positions = pt.get("positions", [])
        trades = pt.get("trades", [])
        trades_fermes = pt.get("trades_fermes", [])
        total_frais = pt.get("total_frais", 0)
        
        valeur_positions = sum(p.get("montant_eur", p.get("valeur_actuelle", p.get("montant", 0))) for p in positions)
        valeur_totale = liquidites + valeur_positions
        gain_perte = valeur_totale - capital
        gain_pct = (gain_perte / capital * 100) if capital else 0
        
        rapport += f"Capital initial: {capital:.2f} EUR\n"
        rapport += f"Liquidites: {liquidites:.2f} EUR\n"
        rapport += f"Positions ouvertes: {len(positions)}\n"
        rapport += f"Valeur positions: {valeur_positions:.2f} EUR\n"
        rapport += f"Valeur totale: {valeur_totale:.2f} EUR\n"
        rapport += f"Gain/Perte: {gain_perte:+.2f} EUR ({gain_pct:+.1f}%)\n"
        rapport += f"Frais payes: {total_frais:.2f} EUR\n"
        rapport += f"Trades total: {len(trades_fermes)}\n"
        
        if trades_fermes:
            gagnants = [t for t in trades_fermes if t.get("pnl", 0) > 0]
            perdants = [t for t in trades_fermes if t.get("pnl", 0) < 0]
            winrate = len(gagnants) / len(trades_fermes) * 100
            pnl_total = sum(t.get("pnl", 0) for t in trades_fermes)
            rapport += f"Winrate: {winrate:.1f}% ({len(gagnants)}G / {len(perdants)}P)\n"
            rapport += f"PnL realise: {pnl_total:+.2f} EUR\n"
            
            # Top stratégies
            from collections import Counter
            strats = Counter(t.get("strategie", "?") for t in trades_fermes if t.get("pnl", 0) > 0)
            if strats:
                rapport += f"\nTop strategies gagnantes:\n"
                for s, n in strats.most_common(5):
                    rapport += f"  {s}: {n} trades gagnants\n"
        
        # Positions ouvertes
        if positions:
            rapport += f"\nPositions ouvertes:\n"
            for p in positions[:10]:
                sym = p.get("symbole", "?")
                prix_entree = p.get("prix_entree", 0)
                montant = p.get("montant_eur", 0)
                quantite = p.get("quantite", 0)
                rapport += f"  📈 {sym} @ {prix_entree:.4f} | {montant:.2f} EUR | qty {quantite:.6f}\n"
    except Exception as e:
        rapport += f"Erreur: {e}\n"
    
    # 2. MARCHE
    rapport += f"\n## 2. ETAT DU MARCHE\n"
    try:
        prix_data = get_multiple_prices(["BTC", "ETH", "SOL", "BNB", "XRP"])
        if prix_data:
            for item in prix_data:
                sym = item.get("symbole", "?")
                prix = item.get("prix_eur", 0)
                var = item.get("variation_24h", 0)
                rapport += f"  {sym}: {prix:.2f} EUR ({var:+.1f}%)\n"
        else:
            rapport += "  Prix indisponibles\n"
    except Exception as e:
        rapport += f"  Prix indisponibles ({e})\n"
    
    # 3. STATS AGENT
    rapport += f"\n## 3. STATS AGENT\n"
    stats = get_stats()
    rapport += f"  Uptime: {stats['uptime']}\n"
    rapport += f"  Messages recus: {stats.get('messages_recus', 0)}\n"
    rapport += f"  Messages repondus: {stats.get('messages_repondus', 0)}\n"
    rapport += f"  Erreurs: {stats.get('erreurs', 0)}\n"
    rapport += f"  API timeouts: {stats.get('api_timeouts', 0)}\n"
    
    # 4. SERVICES
    rapport += f"\n## 4. SERVICES\n"
    fichiers = ["agent_memory.json", "paper_trading.json", "knowledge_base.json", "solutions_db.json", "corrections_db.json"]
    for f in fichiers:
        path = os.path.join(DOSSIER, f)
        if os.path.exists(path):
            size = os.path.getsize(path)
            rapport += f"  ✅ {f} ({size}b)\n"
        else:
            rapport += f"  ❌ {f}\n"
    
    # 5. RECOMMANDATIONS IA
    rapport += f"\n## 5. ANALYSE IA\n"
    try:
        analyse = ask_perplexity(
            f"Analyse ce portefeuille crypto et donne 3 recommandations en francais (2 lignes max chacune):\n"
            f"Capital: {capital}EUR, Liquidites: {liquidites}EUR, Positions: {len(positions)}, "
            f"Winrate: {winrate:.0f}% si trades, PnL: {gain_perte:+.2f}EUR\n"
            f"Recommande: ajuster taille positions? diversifier? arreter?",
            temperature=0.3
        )
        rapport += analyse
    except:
        rapport += "Analyse IA indisponible\n"
    
    rapport += f"\n{'='*50}\nGenere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}"
    return rapport


# ============================================
# 11. AUTO-AMELIORATION
# ============================================
def self_improve():
    """L'agent analyse ses faiblesses et se corrige automatiquement."""
    rapport = "🧠 AUTO-AMELIORATION\n" + "=" * 40 + "\n"
    corrections = []
    
    # 1. Analyse des erreurs recentes
    rapport += "\n[1] Analyse des erreurs...\n"
    stats = get_stats()
    nb_erreurs = stats.get("erreurs", 0)
    nb_timeouts = stats.get("api_timeouts", 0)
    nb_messages = stats.get("messages_recus", 0)
    
    if nb_messages > 0 and nb_erreurs / nb_messages > 0.1:
        corrections.append(f"Taux d'erreur eleve: {nb_erreurs}/{nb_messages} ({nb_erreurs/nb_messages*100:.0f}%)")
        rapport += f"  ⚠️ Taux d'erreur: {nb_erreurs/nb_messages*100:.0f}%\n"
    else:
        rapport += f"  ✅ Taux d'erreur OK: {nb_erreurs}/{nb_messages}\n"
    
    if nb_timeouts > 5:
        corrections.append(f"API timeouts frequents: {nb_timeouts}")
        rapport += f"  ⚠️ API timeouts: {nb_timeouts}\n"
    else:
        rapport += f"  ✅ API timeouts OK: {nb_timeouts}\n"
    
    # 2. Analyse des trades
    rapport += "\n[2] Analyse des trades...\n"
    try:
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        trades = pt.get("trades_fermes", [])
        positions = pt.get("positions", [])
        
        if trades:
            gagnants = [t for t in trades if t.get("pnl", 0) > 0]
            perdants = [t for t in trades if t.get("pnl", 0) < 0]
            winrate = len(gagnants) / len(trades) * 100 if trades else 0
            pnl_total = sum(t.get("pnl", 0) for t in trades)
            
            rapport += f"  Trades: {len(trades)} | Winrate: {winrate:.1f}% | PnL: {pnl_total:+.2f}EUR\n"
            
            if winrate < 50:
                corrections.append(f"Winrate faible: {winrate:.0f}%")
                rapport += f"  ⚠️ Winrate faible: {winrate:.0f}%\n"
                
                # Analyse des trades perdants
                perdants_strats = {}
                for t in perdants:
                    s = t.get("strategie", "?")
                    perdants_strats[s] = perdants_strats.get(s, 0) + 1
                if perdants_strats:
                    pire_strat = max(perdants_strats, key=perdants_strats.get)
                    corrections.append(f"Strategie perdante: {pire_strat} ({perdants_strats[pire_strat]} pertes)")
                    rapport += f"  ⚠️ Strategie {pire_strat}: {perdants_strats[pire_strat]} pertes\n"
            else:
                rapport += f"  ✅ Winrate OK: {winrate:.0f}%\n"
            
            if pnl_total < 0:
                corrections.append(f"PnL negatif: {pnl_total:.2f}EUR")
                rapport += f"  ⚠️ PnL negatif: {pnl_total:.2f}EUR\n"
            else:
                rapport += f"  ✅ PnL positif: {pnl_total:.2f}EUR\n"
        else:
            rapport += "  Aucun trade ferme\n"
        
        rapport += f"  Positions ouvertes: {len(positions)}\n"
    except Exception as e:
        rapport += f"  Erreur analyse: {e}\n"
    
    # 3. Analyse memoire
    rapport += "\n[3] Analyse memoire...\n"
    try:
        memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "important_conv": []})
        nb_conv = len(memoire.get("conversations", []))
        nb_important = len(memoire.get("important_conv", []))
        rapport += f"  Conversations: {nb_conv}\n"
        rapport += f"  Conversations importantes: {nb_important}\n"
        
        solutions = load_json_safe(os.path.join(DOSSIER, "solutions_db.json"), [])
        corrections_db = load_json_safe(os.path.join(DOSSIER, "corrections_db.json"), [])
        rapport += f"  Solutions sauvegardees: {len(solutions)}\n"
        rapport += f"  Corrections apprises: {len(corrections_db)}\n"
        
        if nb_conv > 150:
            corrections.append(f"Memoire pleine: {nb_conv} conversations -> nettoyer")
            rapport += f"  ⚠️ Memoire pleine: {nb_conv} conversations\n"
            # Auto-nettoyage: supprime les vieilles conversations non importantes
            convs = memoire.get("conversations", [])
            if len(convs) > 150:
                memoire["conversations"] = convs[-150:]  # garde les 150 plus recentes
                save_json_safe(MEMORY_FILE, memoire)
                rapport += f"  🧹 Nettoyage: garde 150 conversations recentes\n"
        else:
            rapport += f"  ✅ Memoire OK\n"
    except Exception as e:
        rapport += f"  Erreur: {e}\n"
    
    # 4. Analyse fichiers
    rapport += "\n[4] Analyse fichiers...\n"
    fichiers_critiques = ["paper_trading.json", "agent_memory.json"]
    for f in fichiers_critiques:
        path = os.path.join(DOSSIER, f)
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size < 50:
                corrections.append(f"Fichier {f} suspectement petit: {size}b")
                rapport += f"  ⚠️ {f}: {size}b (trop petit)\n"
            else:
                rapport += f"  ✅ {f}: {size}b\n"
        else:
            corrections.append(f"Fichier {f} manquant")
            rapport += f"  ❌ {f} manquant\n"
    
    # 5. Actions correctives
    rapport += "\n[5] Actions correctives...\n"
    if corrections:
        rapport += f"  {len(corrections)} probleme(s) detecte(s):\n"
        for i, c in enumerate(corrections, 1):
            rapport += f"  {i}. {c}\n"
            learn_fact(f"Faiblesse detectee: {c}", "correction")
            
            # Demande a l'IA une solution
            try:
                solution = ask_perplexity(
                    f"Probleme detecte dans un systeme de trading crypto: {c}\n"
                    f"Donne une solution concrete en 2 lignes max (francais).",
                    temperature=0.2
                )
                rapport += f"     -> Solution: {solution[:100]}\n"
                save_solution(c, solution, category="auto-improvement")
            except:
                pass
    else:
        rapport += "  ✅ Aucun probleme detecte\n"
    
    # 6. Apprentissage
    rapport += "\n[6] Apprentissage...\n"
    try:
        # Apprend des trades gagnants/perdants
        if trades:
            gagnants = [t for t in trades if t.get("pnl", 0) > 0]
            perdants = [t for t in trades if t.get("pnl", 0) < 0]
            
            if gagnants:
                for t in gagnants[-3:]:  # 3 derniers gagnants
                    learn_fact(
                        f"Trade gagnant: {t.get('symbole')} {t.get('strategie')} "
                        f"PnL={t.get('pnl', 0):.2f}EUR",
                        "strategy"
                    )
            if perdants:
                for t in perdants[-3:]:  # 3 derniers perdants
                    learn_fact(
                        f"Trade perdant: {t.get('symbole')} {t.get('strategie')} "
                        f"PnL={t.get('pnl', 0):.2f}EUR",
                        "correction"
                    )
            rapport += f"  ✅ Appris de {len(gagnants[-3:])} gagnants et {len(perdants[-3:])} perdants\n"
    except:
        rapport += "  Erreur apprentissage\n"
    
    bilan = f"\n{'='*40}\nBilan: {len(corrections)} probleme(s) | {len(corrections)} solution(s) generee(s)\n"
    rapport += bilan
    learn_fact(f"Auto-amenlioration {datetime.now().strftime('%d/%m %H:%M')}: {len(corrections)} problemes", "correction")
    save_memory("agent", "auto-amenlioration", rapport)
    return rapport


# ============================================
# 12. TACHES PROGRAMMEES
# ============================================
_TASKS_FILE = os.path.join(DOSSIER, "scheduled_tasks.json")

def list_scheduled_tasks():
    """Liste les taches programmees."""
    tasks = load_json_safe(_TASKS_FILE, [])
    if not tasks:
        return "📋 Aucune tache programmee.\nUsage: planifie [tache]\nEx: planifie rapport quotidien 8h"
    msg = "📋 TACHES PROGRAMMEES\n" + "━" * 30 + "\n"
    for i, t in enumerate(tasks, 1):
        msg += f"{i}. {t.get('description', '?')}\n"
        msg += f"   Frequence: {t.get('frequence', '?')}\n"
        msg += f"   Derniere execution: {t.get('derniere_exec', 'jamais')}\n"
    return msg

def schedule_task(text):
    """Planifie une tache repetitive depuis Telegram."""
    # Parse: planifie [tache] [frequence]
    parts = text.split(None, 1)
    if len(parts) < 2:
        return "Usage: planifie [tache]\nEx: planifie rapport quotidien 8h"
    
    task_desc = parts[1]
    
    # Determine la frequence
    freq = "quotidien"
    crontab_entry = "0 8 * * *"  # defaut: 8h tous les jours
    
    if "horaire" in task_desc.lower() or "heure" in task_desc.lower():
        freq = "horaire"
        crontab_entry = "0 * * * *"
    elif "quotidien" in task_desc.lower() or "jour" in task_desc.lower():
        freq = "quotidien"
        # Cherche une heure
        import re
        heure_match = re.search(r'(\d+)h', task_desc.lower())
        if heure_match:
            h = int(heure_match.group(1))
            crontab_entry = f"0 {h} * * *"
    elif "hebdo" in task_desc.lower() or "semaine" in task_desc.lower():
        freq = "hebdomadaire"
        crontab_entry = "0 8 * * 1"
    
    # Determine la commande
    commande = None
    if "rapport" in task_desc.lower() or "bilan" in task_desc.lower():
        commande = "cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u agent_os.py rapport-telegram"
    elif "scan" in task_desc.lower() or "opportunite" in task_desc.lower():
        commande = "cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u agent_os.py scan"
    elif "ameliorer" in task_desc.lower() or "evolue" in task_desc.lower():
        commande = "cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u agent_os.py auto-improve"
    elif "code" in task_desc.lower():
        commande = "cd /home/ubuntu/agent-ia && /home/ubuntu/agent-ia/venv/bin/python -u agent_os.py code-seul"
    else:
        commande = f"echo 'Tache: {task_desc}'"
    
    # Sauvegarde la tache
    tasks = load_json_safe(_TASKS_FILE, [])
    tasks.append({
        "description": task_desc,
        "frequence": freq,
        "crontab": crontab_entry,
        "commande": commande,
        "derniere_exec": "jamais",
        "cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_json_safe(_TASKS_FILE, tasks)
    
    # Installe le cron sur le VPS
    try:
        import subprocess as sp
        # Recupere le crontab actuel
        result = sp.run(["crontab", "-l"], capture_output=True, text=True)
        current = result.stdout if result.returncode == 0 else ""
        # Ajoute la nouvelle ligne
        new_entry = f"{crontab_entry} {commande} >> /home/ubuntu/agent-ia/tasks.log 2>&1\n"
        current += new_entry
        # Ecrit le nouveau crontab
        sp.run(["crontab", "-"], input=current, text=True)
        return f"✅ Tache planifiee!\n📋 {task_desc}\n⏰ Frequence: {freq} ({crontab_entry})\n🔧 Commande: {commande[:80]}"
    except Exception as e:
        return f"✅ Tache sauvegardee (mais cron non installe: {e})\n📋 {task_desc}\n⏰ {freq}"



# ============================================
# 13. ALERTES INTELLIGENTES
# ============================================
def alertes_intelligentes():
    """Scan les cryptos et envoie des alertes intelligentes."""
    alertes = []
    symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "ARBUSDT"]
    for sym in symboles:
        try:
            analyse = analyser_actif(sym, "1h")
            if not analyse:
                continue
            score = analyse.get("score", 0)
            rsi = analyse.get("indicateurs", {}).get("RSI", 50)
            prix = analyse.get("prix", 0)
            signaux = analyse.get("signaux", [])
            if score >= 3:
                alertes.append({"type": "🚀 ACHAT FORT", "symbole": sym, "prix": prix, "score": score, "rsi": rsi, "raison": "; ".join(signaux[:2])})
            elif rsi < 25:
                alertes.append({"type": "🔴 SURVENTE", "symbole": sym, "prix": prix, "score": score, "rsi": rsi, "raison": f"RSI tres bas ({rsi:.0f}) - rebond possible"})
            elif score <= -2:
                alertes.append({"type": "⚠️ VENTE FORTE", "symbole": sym, "prix": prix, "score": score, "rsi": rsi, "raison": "; ".join(signaux[:2])})
            elif rsi > 75:
                alertes.append({"type": "🟠 SURACHAT", "symbole": sym, "prix": prix, "score": score, "rsi": rsi, "raison": f"RSI tres haut ({rsi:.0f}) - correction possible"})
        except:
            continue
    if not alertes:
        return "✅ Aucune alerte. Marche calme."
    msg = "🚨 ALERTES INTELLIGENTES\n" + "━" * 30 + "\n"
    for a in alertes:
        msg += f"\n{a['type']} {a['symbole']}\n  Prix: {a['prix']:.4f} EUR\n  Score: {a['score']:+d} | RSI: {a['rsi']:.0f}\n  Raison: {a['raison']}\n"
    return msg, alertes


def envoyer_alertes():
    """Execute les alertes et envoie sur Telegram."""
    resultat = alertes_intelligentes()
    if isinstance(resultat, tuple):
        msg, alertes = resultat
        if alertes:
            send_telegram(msg)
            learn_fact(f"Alerte {datetime.now().strftime('%H:%M')}: {len(alertes)} signaux", "alert")
            return msg
    return ""


# ============================================
# 14. ANALYSE COMPARATIVE
# ============================================
def analyse_comparative(symboles=None):
    """Compare plusieurs cryptos cote a cote."""
    from indicateurs import NOMS
    if not symboles:
        symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
    msg = "📊 ANALYSE COMPARATIVE\n" + "━" * 35 + "\n\n"
    msg += f"{'Crypto':<12} {'Prix':>10} {'RSI':>6} {'Score':>6} {'Verdict':<12}\n"
    msg += "─" * 50 + "\n"
    donnees = []
    for sym in symboles:
        try:
            analyse = analyser_actif(sym, "1h")
            if not analyse:
                continue
            prix = analyse.get("prix", 0)
            rsi = analyse.get("indicateurs", {}).get("RSI", 0)
            score = analyse.get("score", 0)
            verdict = analyse.get("verdict", "NEUTRE")
            bb_haut = analyse.get("indicateurs", {}).get("BB_haut", 0)
            bb_bas = analyse.get("indicateurs", {}).get("BB_bas", 0)
            volatilite = ((bb_haut - bb_bas) / prix * 100) if prix > 0 else 0
            donnees.append({"symbole": sym, "prix": prix, "rsi": rsi, "score": score, "verdict": verdict, "volatilite": volatilite})
            nom = NOMS.get(sym, sym)[:11]
            emoji = "🟢" if score >= 2 else ("🔴" if score <= -2 else "⚪")
            msg += f"{emoji} {nom:<10} {prix:>10.4f} {rsi:>5.0f} {score:>+5d} {verdict:<12}\n"
        except:
            continue
    if not donnees:
        return msg + "Donnees indisponibles\n"
    msg += "\n" + "━" * 35 + "\n🏆 TOP RECOMMANDATIONS:\n"
    tries = sorted(donnees, key=lambda x: x["score"], reverse=True)
    for i, d in enumerate(tries[:3], 1):
        msg += f"  {i}. {NOMS.get(d['symbole'], d['symbole'])} - Score {d['score']:+d} ({d['verdict']})\n"
        msg += f"     RSI: {d['rsi']:.0f} | Volat: {d['volatilite']:.1f}% | Prix: {d['prix']:.4f}EUR\n"
    msg += "\n📈 TOP VOLATILITE (opportunite):\n"
    tries_vol = sorted(donnees, key=lambda x: x["volatilite"], reverse=True)
    for d in tries_vol[:3]:
        msg += f"  {NOMS.get(d['symbole'], d['symbole'])} - {d['volatilite']:.1f}% | Score {d['score']:+d}\n"
    achats = [d for d in donnees if d["score"] > 0]
    ventes = [d for d in donnees if d["score"] < 0]
    msg += f"\n📊 CORRELATION:\n  {len(achats)} haussieres vs {len(ventes)} baissieres\n"
    if len(achats) > len(ventes) * 2:
        msg += "  -> Marche globalement haussier\n"
    elif len(ventes) > len(achats) * 2:
        msg += "  -> Marche globalement baissier\n"
    else:
        msg += "  -> Marche mixte/neutre\n"
    return msg


# ============================================
# 15. GRAPHIQUES VISUELS
# ============================================
def generer_graphique(symbole="BTCUSDT", type_graph="prix"):
    """Genere un graphique et l'envoie sur Telegram."""
    try:
        from indicateurs import historique_ohlcv, NOMS
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.style.use('dark_background')
    except ImportError:
        return "Erreur: matplotlib ou indicateurs non installe"
    bougies = historique_ohlcv(symbole, "1h", 60)
    if not bougies or len(bougies) < 20:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    ouvertures = [b["ouverture"] for b in bougies]
    hauts = [b["haut"] for b in bougies]
    bas = [b["bas"] for b in bougies]
    temps = [datetime.fromtimestamp(b["temps"]/1000) for b in bougies]
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), gridspec_kw={'height_ratios': [3, 1]})
    nom = NOMS.get(symbole, symbole)
    fig.suptitle(f"{nom} ({symbole}) - {datetime.now().strftime('%d/%m %H:%M')}", fontsize=14, color='white')
    ax1 = axes[0]
    # Bougies japonaises
    for i in range(len(bougies)):
        o, h, l, c = ouvertures[i], hauts[i], bas[i], clotures[i]
        couleur = '#26A69A' if c >= o else '#EF5350'
        # Mèche (haute-basse)
        ax1.vlines(i, l, h, color=couleur, linewidth=0.8)
        # Corps (ouverture-cloture)
        body_bottom = min(o, c)
        body_height = abs(c - o) if abs(c - o) > 0 else h * 0.0001
        ax1.bar(i, body_height, bottom=body_bottom, color=couleur, width=0.7, edgecolor=couleur)
    # SMA20
    if len(clotures) >= 20:
        sma20 = [sum(clotures[max(0,i-19):i+1])/min(20,i+1) for i in range(len(clotures))]
        ax1.plot(range(len(clotures)), sma20, color='#FF9800', linewidth=1, label='SMA20', alpha=0.8)
    # SMA50
    if len(clotures) >= 50:
        sma50 = [sum(clotures[max(0,i-49):i+1])/min(50,i+1) for i in range(len(clotures))]
        ax1.plot(range(len(clotures)), sma50, color='#4CAF50', linewidth=1, label='SMA50', alpha=0.8)
    # Bandes de Bollinger
    if len(clotures) >= 20:
        import statistics
        bb_milieu = sma20
        bb_ecart = [statistics.stdev(clotures[max(0,i-19):i+1]) * 2 if i >= 19 else 0 for i in range(len(clotures))]
        bb_haut = [m + e for m, e in zip(bb_milieu, bb_ecart)]
        bb_bas = [m - e for m, e in zip(bb_milieu, bb_ecart)]
        ax1.fill_between(range(len(clotures)), bb_haut, bb_bas, color='#2196F3', alpha=0.08, label='Bollinger')
    # Labels X tous les 10
    tick_pos = list(range(0, len(temps), 10))
    tick_labels = [temps[i].strftime('%d/%m %Hh') for i in tick_pos]
    ax1.set_xticks(tick_pos)
    ax1.set_xticklabels(tick_labels, rotation=30, ha='right', fontsize=7)
    ax1.set_ylabel('Prix (EUR)', color='white')
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.15)
    ax2 = axes[1]
    if len(clotures) >= 14:
        rsi_vals = []
        for i in range(len(clotures)):
            if i < 14:
                rsi_vals.append(50)
                continue
            gains = [clotures[j] - clotures[j-1] for j in range(i-13, i+1) if clotures[j] > clotures[j-1]]
            pertes = [clotures[j-1] - clotures[j] for j in range(i-13, i+1) if clotures[j] < clotures[j-1]]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_perte = sum(pertes) / 14 if pertes else 0.001
            rs = avg_gain / avg_perte if avg_perte > 0 else 100
            rsi_vals.append(100 - (100 / (1 + rs)))
        ax2.plot(range(len(clotures)), rsi_vals, color='#E91E63', linewidth=1)
        ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='Surachat (70)')
        ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='Survente (30)')
        ax2.fill_between(range(len(clotures)), 70, 100, color='red', alpha=0.1)
        ax2.fill_between(range(len(clotures)), 0, 30, color='green', alpha=0.1)
    ax2.set_ylabel('RSI', color='white')
    ax2.set_ylim(0, 100)
    ax2.set_xticks(tick_pos)
    ax2.set_xticklabels(tick_labels, rotation=30, ha='right', fontsize=7)
    ax2.legend(loc='upper left', fontsize=8)
    ax2.grid(True, alpha=0.15)
    plt.tight_layout()
    filepath = os.path.join(DOSSIER, f"chart_{symbole}_{datetime.now().strftime('%Y%m%d_%H%M')}.png")
    plt.savefig(filepath, dpi=100, facecolor='#1a1a2e')
    plt.close()
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(filepath, 'rb') as f:
            r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": f"📊 {nom} - Prix + RSI"}, files={"photo": f}, timeout=30)
        if r.status_code == 200:
            return filepath
        return f"Erreur envoi photo: {r.status_code}"
    except Exception as e:
        return f"Erreur envoi: {e}"


def generer_graphique_pnl():
    """Genere un graphique du PnL du portefeuille."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.style.use('dark_background')
    except ImportError:
        return "Erreur: matplotlib non installe"
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    trades = pt.get("trades_fermes", [])
    if not trades:
        return "Aucun trade ferme pour generer un graphique"
    pnl_cumule = []
    total = 0
    for t in trades:
        total += t.get("pnl", 0)
        pnl_cumule.append(total)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(range(1, len(pnl_cumule) + 1), pnl_cumule, color='#4CAF50', linewidth=2, marker='o', markersize=3)
    ax.axhline(y=0, color='white', linestyle='--', alpha=0.3)
    ax.fill_between(range(1, len(pnl_cumule) + 1), pnl_cumule, 0, where=[p >= 0 for p in pnl_cumule], color='#4CAF50', alpha=0.3)
    ax.fill_between(range(1, len(pnl_cumule) + 1), pnl_cumule, 0, where=[p < 0 for p in pnl_cumule], color='#f44336', alpha=0.3)
    ax.set_title(f"PnL Cumule - {len(trades)} trades", color='white', fontsize=14)
    ax.set_xlabel('Nombre de trades', color='white')
    ax.set_ylabel('PnL (EUR)', color='white')
    ax.grid(True, alpha=0.2)
    filepath = os.path.join(DOSSIER, f"chart_pnl_{datetime.now().strftime('%Y%m%d_%H%M')}.png")
    plt.savefig(filepath, dpi=100, facecolor='#1a1a2e')
    plt.close()
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(filepath, 'rb') as f:
            r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": f"📊 PnL Cumule - Total: {pnl_cumule[-1]:+.2f} EUR"}, files={"photo": f}, timeout=30)
        if r.status_code == 200:
            return filepath
        return f"Erreur envoi: {r.status_code}"
    except Exception as e:
        return f"Erreur: {e}"


# ============================================
# 16. BACKTEST A LA VOLEE
# ============================================
def backtest_rapide(symbole="BTCUSDT", strategie="momentum"):
    """Backtest rapide depuis Telegram."""
    from indicateurs import NOMS
    msg = f"🔬 BACKTEST RAPIDE\n" + "━" * 30 + "\n"
    msg += f"Crypto: {NOMS.get(symbole, symbole)}\n"
    msg += f"Strategie: {strategie}\n\n"
    try:
        from indicateurs import historique_ohlcv, NOMS
        bougies = historique_ohlcv(symbole, "1h", 200)
        if not bougies or len(bougies) < 60:
            return msg + "❌ Pas assez de donnees historiques"
        clotures = [b["cloture"] for b in bougies]
        capital = 100.0
        position = None
        trades = []
        for i in range(50, len(clotures)):
            prix = clotures[i]
            sma20 = sum(clotures[max(0,i-19):i+1]) / min(20, i+1)
            sma50 = sum(clotures[max(0,i-49):i+1]) / min(50, i+1)
            gains = [clotures[j] - clotures[j-1] for j in range(i-13, i+1) if clotures[j] > clotures[j-1]]
            pertes = [clotures[j-1] - clotures[j] for j in range(i-13, i+1) if clotures[j] < clotures[j-1]]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_perte = sum(pertes) / 14 if pertes else 0.001
            rs = avg_gain / avg_perte if avg_perte > 0 else 100
            rsi_val = 100 - (100 / (1 + rs))
            signal_achat = False
            signal_vente = False
            raison = ""
            if strategie == "momentum":
                signal_achat = sma20 > sma50 and 50 <= rsi_val <= 65
                signal_vente = sma20 < sma50 or rsi_val > 75
                raison = f"SMA20{'>' if sma20>sma50 else '<'}SMA50 RSI={rsi_val:.0f}"
            elif strategie == "rsi":
                signal_achat = rsi_val < 35
                signal_vente = rsi_val > 65
                raison = f"RSI={rsi_val:.0f}"
            elif strategie == "tendance":
                signal_achat = sma20 > sma50 and prix > sma20
                signal_vente = sma20 < sma50 and prix < sma20
                raison = "Prix vs SMA"
            elif strategie == "bollinger":
                import statistics
                if i >= 19:
                    bb_ecart = statistics.stdev(clotures[i-19:i+1]) * 2
                    bb_bas = sma20 - bb_ecart
                    bb_haut = sma20 + bb_ecart
                    signal_achat = prix <= bb_bas
                    signal_vente = prix >= bb_haut
                    raison = f"BB {'bas' if signal_achat else 'haut' if signal_vente else 'milieu'}"
            if signal_achat and not position:
                qty = (capital * 0.95) / prix
                position = {"prix": prix, "qty": qty, "index": i, "raison": raison}
            elif signal_vente and position:
                pnl = (prix - position["prix"]) * position["qty"]
                capital += pnl
                trades.append({"achat": position["prix"], "vente": prix, "pnl": pnl, "raison": position["raison"]})
                position = None
        if position:
            prix_final = clotures[-1]
            pnl = (prix_final - position["prix"]) * position["qty"]
            capital += pnl
            trades.append({"achat": position["prix"], "vente": prix_final, "pnl": pnl, "raison": position["raison"]})
        gagnants = [t for t in trades if t["pnl"] > 0]
        perdants = [t for t in trades if t["pnl"] < 0]
        winrate = len(gagnants) / len(trades) * 100 if trades else 0
        pnl_total = capital - 100
        pnl_pct = (pnl_total / 100) * 100
        msg += f"Periode: {len(bougies)} bougies (1h)\n"
        msg += f"Trades: {len(trades)}\n"
        msg += f"Gagnants: {len(gagnants)} | Perdants: {len(perdants)}\n"
        msg += f"Winrate: {winrate:.1f}%\n"
        msg += f"Capital final: {capital:.2f} EUR\n"
        msg += f"PnL: {pnl_total:+.2f} EUR ({pnl_pct:+.1f}%)\n\n"
        if trades:
            msg += "Derniers trades:\n"
            for t in trades[-5:]:
                emoji = "✅" if t["pnl"] > 0 else "❌"
                msg += f"  {emoji} {t['raison']} | PnL: {t['pnl']:+.2f}EUR\n"
        msg += f"\n💡 Verdict: {'🟢 STRATEGIE GAGNANTE' if pnl_total > 0 else '🔴 STRATEGIE PERDANTE'}"
        learn_fact(f"Backtest {symbole} {strategie}: {winrate:.0f}% WR, {pnl_pct:+.1f}% PnL", "strategy")
        return msg
    except Exception as e:
        return msg + f"Erreur: {e}"




# ============================================
# 17. PnL TEMPS REEL
# ============================================
def pnl_temps_reel():
    """Calcule les gains/pertes latents sur les positions ouvertes."""
    from indicateurs import NOMS
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    liquidites = pt.get("liquidites", 0)
    capital = pt.get("capital_initial", 1000)
    if not positions:
        return "Aucune position ouverte"
    msg = "💰 PnL TEMPS REEL\n" + "━" * 35 + "\n\n"
    msg += f"{'Crypto':<12} {'Entree':>10} {'Actuel':>10} {'PnL':>10} {'%':>7}\n"
    msg += "─" * 52 + "\n"
    total_investi = 0
    total_actuel = 0
    for p in positions:
        try:
            sym = p.get("symbole", "?")
            prix_entree = p.get("prix_entree", 0)
            quantite = p.get("quantite", 0)
            montant = p.get("montant_eur", 0)
            # Recupere le prix actuel
            prix_actuel = get_crypto_price(sym.replace("USDT", ""))
            if not prix_actuel or prix_actuel == 0:
                prix_actuel = prix_entree
            valeur_actuelle = prix_actuel * quantite
            pnl = valeur_actuelle - montant
            pnl_pct = (pnl / montant * 100) if montant > 0 else 0
            total_investi += montant
            total_actuel += valeur_actuelle
            nom = NOMS.get(sym, sym)[:11]
            emoji = "🟢" if pnl >= 0 else "🔴"
            msg += f"{emoji} {nom:<10} {prix_entree:>10.4f} {prix_actuel:>10.4f} {pnl:>+9.2f} {pnl_pct:>+6.1f}%\n"
        except:
            continue
    pnl_total = total_actuel - total_investi
    pnl_pct_total = (pnl_total / total_investi * 100) if total_investi > 0 else 0
    valeur_portefeuille = liquidites + total_actuel
    gain_global = valeur_portefeuille - capital
    gain_global_pct = (gain_global / capital * 100) if capital > 0 else 0
    msg += "─" * 52 + "\n"
    msg += f"\n💼 Investi: {total_investi:.2f} EUR\n"
    msg += f"📈 Valeur actuelle: {total_actuel:.2f} EUR\n"
    msg += f"{'🟢' if pnl_total >= 0 else '🔴'} PnL latents: {pnl_total:+.2f} EUR ({pnl_pct_total:+.1f}%)\n"
    msg += f"\n💵 Liquidites: {liquidites:.2f} EUR\n"
    msg += f"🏦 Valeur totale: {valeur_portefeuille:.2f} EUR\n"
    msg += f"{'🟢' if gain_global >= 0 else '🔴'} Gain global: {gain_global:+.2f} EUR ({gain_global_pct:+.1f}%)\n"
    return msg


# ============================================
# 18. ALERTES PRIX PERSONNALISEES
# ============================================
_ALERTES_PRIX_FILE = os.path.join(DOSSIER, "alertes_prix.json")


def ajouter_alerte_prix(texte):
    """Ajoute une alerte prix personnalisee. Format: alerte BTC 70000"""
    from indicateurs import NOMS
    parts = texte.split()
    if len(parts) < 3:
        return "Usage: alerte BTC 70000\n ou: alerte BTC 70000 bas\n (haut/bas pour direction)"
    crypto = parts[1].upper()
    if not crypto.endswith("USDT"):
        crypto = crypto + "USDT"
    try:
        prix_cible = float(parts[2].replace(",", "."))
    except:
        return "Prix invalide. Ex: alerte BTC 70000"
    direction = "haut"
    if len(parts) > 3 and parts[3].lower() in ["bas", "down", "dessous"]:
        direction = "bas"
    # Prix actuel pour reference
    prix_actuel = get_crypto_price(crypto.replace("USDT", ""))
    alertes = load_json_safe(_ALERTES_PRIX_FILE, [])
    alerte = {
        "crypto": crypto,
        "nom": NOMS.get(crypto, crypto),
        "prix_cible": prix_cible,
        "direction": direction,
        "prix_creation": prix_actuel,
        "active": True,
        "cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    alertes.append(alerte)
    save_json_safe(_ALERTES_PRIX_FILE, alertes)
    emoji = "📈" if direction == "haut" else "📉"
    msg = f"✅ Alerte creee!\n"
    msg += f"{emoji} {NOMS.get(crypto, crypto)} {direction} {prix_cible:.2f} EUR\n"
    if prix_actuel:
        diff = ((prix_cible - prix_actuel) / prix_actuel * 100) if prix_actuel > 0 else 0
        msg += f" Prix actuel: {prix_actuel:.2f} EUR ({diff:+.1f}%)\n"
    msg += f" Tu seras notifie sur Telegram quand le prix sera atteint."
    return msg


def lister_alertes_prix():
    """Liste les alertes prix actives."""
    alertes = load_json_safe(_ALERTES_PRIX_FILE, [])
    actives = [a for a in alertes if a.get("active", True)]
    if not actives:
        return "Aucune alerte prix active.\nCree: alerte BTC 70000"
    msg = "📋 ALERTES PRIX ACTIVES\n" + "━" * 30 + "\n"
    for i, a in enumerate(actives, 1):
        emoji = "📈" if a["direction"] == "haut" else "📉"
        msg += f"\n{i}. {emoji} {a['nom']} {a['direction']} {a['prix_cible']:.2f} EUR\n"
        msg += f"   Cree: {a['cree_le']} | Prix: {a.get('prix_creation', '?'):.2f} EUR\n"
    msg += f"\nTotal: {len(actives)} alerte(s) active(s)"
    return msg


def supprimer_alerte_prix(texte):
    """Supprime une alerte prix. Format: alerte supprime 2"""
    parts = texte.split()
    if len(parts) < 3 or parts[1].lower() not in ["supprime", "remove", "delete"]:
        return "Usage: alerte supprime [numero]"
    try:
        num = int(parts[2])
    except:
        return "Numero invalide"
    alertes = load_json_safe(_ALERTES_PRIX_FILE, [])
    actives = [a for a in alertes if a.get("active", True)]
    if num < 1 or num > len(actives):
        return f"Numero invalide (1-{len(actives)})"
    # Trouve et desactive
    target = actives[num - 1]
    for a in alertes:
        if a == target:
            a["active"] = False
            break
    save_json_safe(_ALERTES_PRIX_FILE, alertes)
    return f"✅ Alerte supprimee: {target['nom']} {target['direction']} {target['prix_cible']:.2f} EUR"


def verifier_alertes_prix():
    """Verifie si des alertes prix sont declenchees et notifie sur Telegram."""
    alertes = load_json_safe(_ALERTES_PRIX_FILE, [])
    declenchees = []
    for a in alertes:
        if not a.get("active", True):
            continue
        crypto = a["crypto"]
        prix_cible = a["prix_cible"]
        direction = a["direction"]
        prix_actuel = get_crypto_price(crypto.replace("USDT", ""))
        if not prix_actuel:
            continue
        triggered = False
        if direction == "haut" and prix_actuel >= prix_cible:
            triggered = True
        elif direction == "bas" and prix_actuel <= prix_cible:
            triggered = True
        if triggered:
            emoji = "🚀" if direction == "haut" else "🔻"
            msg = f"{emoji} ALERTE PRIX ATTEINT!\n"
            msg += f"{a['nom']} a {prix_actuel:.2f} EUR\n"
            msg += f"Objectif: {direction} {prix_cible:.2f} EUR\n"
            msg += f"Variation: {((prix_actuel - a.get('prix_creation', prix_cible)) / a.get('prix_creation', prix_cible) * 100):+.1f}%"
            send_telegram(msg)
            a["active"] = False
            a["declenchee_le"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            a["prix_declenchement"] = prix_actuel
            declenchees.append(a)
    if declenchees:
        save_json_safe(_ALERTES_PRIX_FILE, alertes)
    return len(declenchees)


# ============================================
# 19. MULTI-TIMEFRAME ANALYSIS
# ============================================
def analyse_multi_timeframe(symbole="BTCUSDT"):
    """Analyse une crypto sur plusieurs timeframes (15m, 1h, 4h, 1d)."""
    from indicateurs import historique_ohlcv, NOMS
    timeframes = [("15m", 100), ("1h", 100), ("4h", 100), ("1d", 100)]
    nom = NOMS.get(symbole, symbole)
    msg = f"🔬 ANALYSE MULTI-TIMEFRAME\n{nom} ({symbole})\n" + "━" * 40 + "\n\n"
    msg += f"{'TF':<6} {'Prix':>10} {'RSI':>5} {'SMA20':>10} {'SMA50':>10} {'Tendance':<12} {'Score':>6}\n"
    msg += "─" * 62 + "\n"
    resultats = []
    for tf, limite in timeframes:
        try:
            bougies = historique_ohlcv(symbole, tf, limite)
            if not bougies or len(bougies) < 50:
                msg += f"{tf:<6} Donnees insuffisantes\n"
                resultats.append({"tf": tf, "score": 0, "tendance": "NEUTRE"})
                continue
            clotures = [b["cloture"] for b in bougies]
            prix = clotures[-1]
            sma20 = sum(clotures[-20:]) / 20
            sma50 = sum(clotures[-50:]) / 50
            # RSI
            gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
            pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_perte = sum(pertes) / 14 if pertes else 0.001
            rs = avg_gain / avg_perte if avg_perte > 0 else 100
            rsi_val = 100 - (100 / (1 + rs))
            # Tendance
            if prix > sma20 > sma50:
                tendance = "HAUSSIERE"
                score = 2
            elif prix > sma20 or sma20 > sma50:
                tendance = "HAUSSIER"
                score = 1
            elif prix < sma20 < sma50:
                tendance = "BAISSIERE"
                score = -2
            elif prix < sma20 or sma20 < sma50:
                tendance = "BAISSIER"
                score = -1
            else:
                tendance = "NEUTRE"
                score = 0
            # RSI ajustement
            if rsi_val > 70:
                score -= 1
            elif rsi_val < 30:
                score += 1
            resultats.append({"tf": tf, "score": score, "tendance": tendance, "prix": prix, "rsi": rsi_val, "sma20": sma20, "sma50": sma50})
            emoji = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")
            msg += f"{emoji} {tf:<4} {prix:>10.4f} {rsi_val:>4.0f} {sma20:>10.4f} {sma50:>10.4f} {tendance:<12} {score:>+5d}\n"
        except Exception as e:
            msg += f"{tf:<6} Erreur: {str(e)[:20]}\n"
            resultats.append({"tf": tf, "score": 0, "tendance": "NEUTRE"})
    # Synthese
    msg += "\n" + "━" * 40 + "\n"
    total_score = sum(r["score"] for r in resultats)
    nb_haussier = len([r for r in resultats if r["score"] > 0])
    nb_baissier = len([r for r in resultats if r["score"] < 0])
    msg += f"📊 SYNTHESE:\n"
    msg += f"  Score global: {total_score:+d}/8\n"
    msg += f"  Timeframes haussiers: {nb_haussier}/4\n"
    msg += f"  Timeframes baissiers: {nb_baissier}/4\n"
    if total_score >= 3:
        msg += f"\n🟢 SIGNAL FORT: ACHAT (confluence {nb_haussier}/4 timeframes)\n"
    elif total_score >= 1:
        msg += f"\n🟡 SIGNAL MODERE: tendance positive\n"
    elif total_score <= -3:
        msg += f"\n🔴 SIGNAL FORT: VENTE (confluence {nb_baissier}/4 timeframes)\n"
    elif total_score <= -1:
        msg += f"\n🟠 SIGNAL MODERE: tendance negative\n"
    else:
        msg += f"\n⚪ NEUTRE: signaux mixtes\n"
    learn_fact(f"MTF {symbole}: score {total_score:+d}, {nb_haussier}H/{nb_baissier}B", "mtf")
    return msg




# ============================================
# 20. SENTIMENT NEWS CRYPTO
# ============================================
def sentiment_news(crypto="BTC"):
    """Analyse le sentiment des news crypto via Perplexity API."""
    from indicateurs import NOMS
    nom = NOMS.get(crypto + "USDT", crypto) if not crypto.endswith("USDT") else NOMS.get(crypto, crypto)
    if not PPLX_KEY:
        # Fallback: utilise CoinGecko sentiment data
        try:
            sym_clean = crypto.replace("USDT", "").upper()
            coin_id = COINGECKO_IDS.get(sym_clean, "bitcoin")
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                sentiment_up = data.get("sentiment_votes_up_percentage", 50)
                sentiment_down = data.get("sentiment_votes_down_percentage", 50)
                community_score = data.get("community_score", 0)
                msg = f"📰 SENTIMENT COMMUNAUTAIRE - {nom}\n" + "━" * 35 + "\n\n"
                msg += f"🟢 Votes positifs: {sentiment_up:.1f}%\n"
                msg += f"🔴 Votes negatifs: {sentiment_down:.1f}%\n"
                msg += f"👥 Score communaute: {community_score:.0f}/100\n"
                score = (sentiment_up - 50) / 50 * 10
                if score > 3:
                    msg += f"\n🟢 Sentiment POSITIF (score: {score:+.1f}/10)"
                elif score < -3:
                    msg += f"\n🔴 Sentiment NEGATIF (score: {score:+.1f}/10)"
                else:
                    msg += f"\n⚪ Sentiment NEUTRE (score: {score:+.1f}/10)"
                return msg
        except Exception as e:
            return f"Erreur sentiment: {e}"
        return "Pas de cle API Perplexity et CoinGecko indisponible"
    try:
        headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
        prompt = f"Analyse le sentiment actuel du marche pour {nom} ({crypto}). Donne: 1) sentiment global (positif/negatif/neutre) avec score -10 a +10, 2) 3 news importantes recentes en une ligne chacune, 3) impact potentiel sur le prix a court terme (haussier/baissier/neutre). Sois concis."
        payload = {
            "model": "sonar",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }
        r = requests.post("https://api.perplexity.ai/chat/completions",
                          json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            texte = data["choices"][0]["message"]["content"]
            # Recupere aussi le sentiment CoinGecko
            sym_clean = crypto.replace("USDT", "").upper()
            coin_id = COINGECKO_IDS.get(sym_clean, "bitcoin")
            cg_sentiment = 50
            try:
                r2 = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}", timeout=10)
                if r2.status_code == 200:
                    cg_sentiment = r2.json().get("sentiment_votes_up_percentage", 50)
            except:
                pass
            msg = f"📰 SENTIMENT IA - {nom}\n" + "━" * 35 + "\n\n"
            msg += f"👥 Vote communaute: {cg_sentiment:.0f}% positif\n\n"
            msg += texte
            learn_fact(f"Sentiment {crypto}: communaute {cg_sentiment:.0f}% positif", "sentiment")
            return msg
        return f"Erreur API: {r.status_code}"
    except Exception as e:
        return f"Erreur: {e}"


# ============================================
# 21. APPRENTISSAGE AUTO DES TRADES
# ============================================
def apprentissage_auto_trades():
    """Analyse les trades passes et ajuste les poids des strategies."""
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    trades_fermes = pt.get("trades_fermes", [])
    positions = pt.get("positions", [])
    if not trades_fermes or len(trades_fermes) < 1:
        # Analyse les positions ouvertes
        if positions:
            msg = "📚 APPRENTISSAGE - Analyse des positions ouvertes\n" + "━" * 40 + "\n\n"
            strategies = {}
            for p in positions:
                strat = p.get("strategie", "inconnu")
                source = p.get("source", "inconnu")
                key = f"{strat}/{source}"
                if key not in strategies:
                    strategies[key] = {"count": 0, "exemples": []}
                strategies[key]["count"] += 1
                if len(strategies[key]["exemples"]) < 2:
                    strategies[key]["exemples"].append(p.get("symbole", "?"))
            msg += "Strategies utilisees sur les positions ouvertes:\n\n"
            for key, info in sorted(strategies.items(), key=lambda x: x[1]["count"], reverse=True):
                msg += f"  📊 {key}: {info['count']} position(s) - {', '.join(info['exemples'])}\n"
            msg += f"\n💡 {len(positions)} positions ouvertes, pas assez de trades fermes pour apprentissage complet.\n"
            msg += "L'agent analysera les trades fermes des qu'il y en aura assez (min 5)."
            return msg
        return "Pas assez de trades pour l'apprentissage (min 1 trade ferme)"
    msg = "📚 APPRENTISSAGE AUTO DES TRADES\n" + "━" * 40 + "\n\n"
    # Analyse par strategie
    stats_strategies = {}
    for t in trades_fermes:
        strat = t.get("strategie", "inconnu")
        pnl = t.get("pnl", 0)
        if strat not in stats_strategies:
            stats_strategies[strat] = {"trades": 0, "gagnants": 0, "perdants": 0, "pnl_total": 0, "symboles": set()}
        stats_strategies[strat]["trades"] += 1
        stats_strategies[strat]["pnl_total"] += pnl
        if pnl > 0:
            stats_strategies[strat]["gagnants"] += 1
        else:
            stats_strategies[strat]["perdants"] += 1
        stats_strategies[strat]["symboles"].add(t.get("symbole", "?"))
    # Affichage
    msg += f"{'Strategie':<20} {'Trades':>7} {'Win%':>6} {'PnL':>10} {'Verdict':<12}\n"
    msg += "─" * 58 + "\n"
    recommandations = []
    for strat, info in sorted(stats_strategies.items(), key=lambda x: x[1]["pnl_total"], reverse=True):
        winrate = info["gagnants"] / info["trades"] * 100 if info["trades"] > 0 else 0
        verdict = "GARDER" if info["pnl_total"] > 0 else "AMERLIORER"
        if info["pnl_total"] < 0 and winrate < 40:
            verdict = "DESACTIVER"
            recommandations.append(f"Desactiver {strat} (winrate {winrate:.0f}%, PnL {info['pnl_total']:+.2f})")
        elif info["pnl_total"] > 0 and winrate > 60:
            verdict = "BOOSTER"
            recommandations.append(f"Booster {strat} (winrate {winrate:.0f}%, PnL {info['pnl_total']:+.2f})")
        emoji = "🟢" if info["pnl_total"] > 0 else "🔴"
        msg += f"{emoji} {strat:<18} {info['trades']:>7} {winrate:>5.0f}% {info['pnl_total']:>+9.2f} {verdict:<12}\n"
    # Analyse par source
    msg += f"\n📋 ANALYSE PAR SOURCE DE SIGNAL:\n"
    stats_sources = {}
    for t in trades_fermes:
        source = t.get("source", "inconnu")
        pnl = t.get("pnl", 0)
        if source not in stats_sources:
            stats_sources[source] = {"trades": 0, "pnl_total": 0}
        stats_sources[source]["trades"] += 1
        stats_sources[source]["pnl_total"] += pnl
    for source, info in sorted(stats_sources.items(), key=lambda x: x[1]["pnl_total"], reverse=True):
        emoji = "🟢" if info["pnl_total"] > 0 else "🔴"
        msg += f"  {emoji} {source}: {info['trades']} trades, PnL {info['pnl_total']:+.2f} EUR\n"
    # Recommandations IA
    msg += f"\n💡 RECOMMANDATIONS:\n"
    if recommandations:
        for r in recommandations:
            msg += f"  → {r}\n"
    else:
        msg += "  → Maintenir les strategies actuelles (performances equilibrees)\n"
    # Sauvegarde l'apprentissage
    apprentissage = load_json_safe(os.path.join(DOSSIER, "apprentissage.json"), {})
    apprentissage["derniere_analyse"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    apprentissage["strategies"] = {k: {"trades": v["trades"], "pnl": v["pnl_total"],
                                       "winrate": v["gagnants"]/v["trades"]*100 if v["trades"] > 0 else 0}
                                   for k, v in stats_strategies.items()}
    apprentissage["recommandations"] = recommandations
    save_json_safe(os.path.join(DOSSIER, "apprentissage.json"), apprentissage)
    learn_fact(f"Apprentissage: {len(trades_fermes)} trades analyses, {len(recommandations)} recommandations", "learning")
    return msg


# ============================================
# 22. DETECTION CORRELATIONS
# ============================================
def detection_correlations():
    """Detecte les correlations entre les cryptos du portefeuille."""
    from indicateurs import historique_ohlcv, NOMS
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    if len(positions) < 2:
        return "Pas assez de positions pour analyser les correlations (min 2)"
    symboles = list(set(p.get("symbole", "") for p in positions if p.get("symbole")))
    if len(symboles) < 2:
        return "Pas assez de cryptos differentes dans le portefeuille"
    msg = "🔗 ANALYSE DES CORRELATIONS\n" + "━" * 40 + "\n\n"
    # Recupere les historiques de prix
    prix_data = {}
    for sym in symboles[:12]:
        try:
            bougies = historique_ohlcv(sym, "1d", 30)
            if bougies and len(bougies) >= 20:
                prix_data[sym] = [b["cloture"] for b in bougies]
        except:
            continue
    if len(prix_data) < 2:
        return "Pas assez de donnees historiques pour les correlations"
    # Calcul des rendements
    rendements = {}
    for sym, prix in prix_data.items():
        rets = [(prix[i] - prix[i-1]) / prix[i-1] for i in range(1, len(prix)) if prix[i-1] > 0]
        rendements[sym] = rets
    # Matrice de correlation
    msg += f"{'':>12}"
    for sym in list(rendements.keys())[:6]:
        nom = NOMS.get(sym, sym)[:4]
        msg += f" {nom:>8}"
    msg += "\n" + "─" * 60 + "\n"
    correlations_hautes = []
    correlations_negatives = []
    sym_list = list(rendements.keys())
    for i, sym1 in enumerate(sym_list[:6]):
        nom1 = NOMS.get(sym1, sym1)[:10]
        msg += f"{nom1:>12}"
        for j, sym2 in enumerate(sym_list[:6]):
            if i == j:
                msg += f" {'---':>8}"
                continue
            r1, r2 = rendements[sym1], rendements[sym2]
            min_len = min(len(r1), len(r2))
            if min_len < 5:
                msg += f" {'N/A':>8}"
                continue
            # Coefficient de correlation de Pearson
            r1_cut, r2_cut = r1[:min_len], r2[:min_len]
            avg1, avg2 = sum(r1_cut)/min_len, sum(r2_cut)/min_len
            num = sum((r1_cut[k] - avg1) * (r2_cut[k] - avg2) for k in range(min_len))
            den1 = sum((r1_cut[k] - avg1)**2 for k in range(min_len)) ** 0.5
            den2 = sum((r2_cut[k] - avg2)**2 for k in range(min_len)) ** 0.5
            corr = num / (den1 * den2) if den1 > 0 and den2 > 0 else 0
            if j < 6:
                msg += f" {corr:>+7.2f}"
            if abs(corr) > 0.7 and i < j:
                correlations_hautes.append((sym1, sym2, corr))
            elif corr < -0.3 and i < j:
                correlations_negatives.append((sym1, sym2, corr))
        msg += "\n"
    # Analyse
    msg += "\n" + "━" * 40 + "\n"
    if correlations_hautes:
        msg += "⚠️ CORRELATIONS HAUTES (>0.7):\n"
        for s1, s2, c in correlations_hautes:
            n1, n2 = NOMS.get(s1, s1), NOMS.get(s2, s2)
            msg += f"  {n1} <-> {n2}: {c:+.2f}\n"
        msg += "\n💡 Risque: ces cryptos bougent ensemble. Diversification faible.\n"
        msg += "    Envisage de vendre l'une pour acheter une crypto decoorreee.\n"
    else:
        msg += "✅ Aucune correlation excessive (>0.7) detectee.\n"
        msg += "    Le portefeuille est bien diversifie.\n"
    if correlations_negatives:
        msg += f"\n🟢 CORRELATIONS NEGATIVES (diversification):\n"
        for s1, s2, c in correlations_negatives:
            n1, n2 = NOMS.get(s1, s1), NOMS.get(s2, s2)
            msg += f"  {n1} <-> {n2}: {c:+.2f}\n"
    # Score de diversification
    nb_paires = len(sym_list) * (len(sym_list) - 1) / 2
    pct_hautes = len(correlations_hautes) / nb_paires * 100 if nb_paires > 0 else 0
    msg += f"\n📊 Score diversification: {100 - pct_hautes:.0f}/100\n"
    if pct_hautes < 10:
        msg += "🟢 Excellent - portefeuille bien diversifie\n"
    elif pct_hautes < 30:
        msg += "🟡 Correct - quelques correlations a surveiller\n"
    else:
        msg += "🔴 Faible - trop de correlations, risque concentre\n"
    learn_fact(f"Correlations: {len(correlations_hautes)} hautes, diversification {100-pct_hautes:.0f}/100", "correlation")
    return msg


# ============================================
# 23. PREVISIONS IA PRIX
# ============================================
def prevision_ia_prix(symbole="BTCUSDT"):
    """Genere des previsions de prix a 24h et 7j en combinant indicateurs + IA."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1h", 100)
    if not bougies or len(bougies) < 50:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    prix_actuel = clotures[-1]
    # Indicateurs techniques
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
    pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
    avg_gain = sum(gains) / 14 if gains else 0
    avg_perte = sum(pertes) / 14 if pertes else 0.001
    rs = avg_gain / avg_perte if avg_perte > 0 else 100
    rsi_val = 100 - (100 / (1 + rs))
    # Bandes de Bollinger
    import statistics
    bb_milieu = sma20
    bb_ecart = statistics.stdev(clotures[-20:]) * 2
    bb_haut = bb_milieu + bb_ecart
    bb_bas = bb_milieu - bb_ecart
    # Variation recente
    var_24h = (prix_actuel - clotures[-24]) / clotures[-24] * 100 if len(clotures) >= 24 else 0
    var_7d = (prix_actuel - clotures[-7*24]) / clotures[-7*24] * 100 if len(clotures) >= 168 else 0
    # Tendance
    if prix_actuel > sma20 > sma50:
        tendance = "HAUSSIERE FORTE"
        score_tech = 3
    elif prix_actuel > sma20:
        tendance = "HAUSSIERE"
        score_tech = 1
    elif prix_actuel < sma20 < sma50:
        tendance = "BAISSIERE FORTE"
        score_tech = -3
    elif prix_actuel < sma20:
        tendance = "BAISSIERE"
        score_tech = -1
    else:
        tendance = "NEUTRE"
        score_tech = 0
    # Ajustement RSI
    if rsi_val > 70:
        score_tech -= 1
    elif rsi_val < 30:
        score_tech += 1
    # Position dans les bandes de Bollinger
    bb_pos = (prix_actuel - bb_bas) / (bb_haut - bb_bas) * 100 if (bb_haut - bb_bas) > 0 else 50
    # Prevision technique simple
    momentum = (clotures[-1] - clotures[-5]) / clotures[-5] * 100 if len(clotures) >= 5 else 0
    # Estimation 24h
    volatilite = statistics.stdev(clotures[-24:]) / prix_actuel * 100 if len(clotures) >= 24 else 2
    estimation_24h_hausse = prix_actuel * (1 + volatilite/100 * 0.5)
    estimation_24h_baisse = prix_actuel * (1 - volatilite/100 * 0.5)
    # Biais technique
    if score_tech > 0:
        prevision_24h = prix_actuel * (1 + volatilite/100 * 0.3 * min(score_tech, 3)/3)
    elif score_tech < 0:
        prevision_24h = prix_actuel * (1 - volatilite/100 * 0.3 * min(abs(score_tech), 3)/3)
    else:
        prevision_24h = prix_actuel
    # Estimation 7j
    prevision_7j = prevision_24h * (1 + (score_tech * 0.02))
    msg = f"🔮 PREVISION IA - {nom} ({symbole})\n" + "━" * 40 + "\n\n"
    msg += f" Prix actuel: {prix_actuel:.4f} EUR\n"
    msg += f" RSI: {rsi_val:.0f} | SMA20: {sma20:.4f} | SMA50: {sma50:.4f}\n"
    msg += f" Tendance: {tendance} (score: {score_tech:+d})\n"
    msg += f" Bandes BB: {bb_bas:.4f} / {bb_milieu:.4f} / {bb_haut:.4f}\n"
    msg += f" Position BB: {bb_pos:.0f}%\n"
    msg += f" Volatilite 24h: {volatilite:.2f}%\n"
    msg += f" Variation 24h: {var_24h:+.1f}% | 7j: {var_7d:+.1f}%\n"
    msg += f" Momentum 5h: {momentum:+.2f}%\n"
    msg += f"\n{'━' * 40}\n"
    msg += f"📊 PREVISIONS TECHNIQUES:\n"
    msg += f"  24h: {prevision_24h:.4f} EUR ({(prevision_24h/prix_actuel-1)*100:+.1f}%)\n"
    msg += f"  7j:  {prevision_7j:.4f} EUR ({(prevision_7j/prix_actuel-1)*100:+.1f}%)\n"
    msg += f"  Range 24h: {estimation_24h_baisse:.4f} - {estimation_24h_hausse:.4f} EUR\n"
    # Analyse IA si dispo
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Prix actuel {nom}: {prix_actuel:.4f} EUR. RSI: {rsi_val:.0f}. Tendance: {tendance}. Variation 24h: {var_24h:+.1f}%. Donne une prevision de prix a 24h et 7j pour {nom}. Sois concis: juste les 2 prix prevus et 2-3 lignes de raison."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                ia_texte = r.json()["choices"][0]["message"]["content"]
                msg += f"\n🤖 ANALYSE IA:\n{ia_texte}\n"
        except:
            pass
    # Verdict final
    msg += f"\n{'━' * 40}\n"
    if score_tech >= 2:
        msg += "🟢 SIGNAL: ACHAT - Tendance haussiere forte confirmee\n"
    elif score_tech >= 1:
        msg += "🟡 SIGNAL: ACHAT MODERE - Tendance positive\n"
    elif score_tech <= -2:
        msg += "🔴 SIGNAL: VENTE - Tendance baissiere forte\n"
    elif score_tech <= -1:
        msg += "🟠 SIGNAL: VENTE MODERE - Tendance negative\n"
    else:
        msg += "⚪ SIGNAL: NEUTRE - Attendre une direction claire\n"
    learn_fact(f"Prevision {symbole}: {tendance} score {score_tech:+d}, 24h {(prevision_24h/prix_actuel-1)*100:+.1f}%", "forecast")
    return msg




# ============================================
# 24. INTELLIGENCE CONVERSATIONNELLE (NLP)
# ============================================
def comprendre_message(texte):
    """Comprend un message en langage naturel et le route vers la bonne action."""
    texte_lower = texte.lower().strip()
    
    # Si c'est une commande connue, on la laisse passer
    commandes_connues = [
        "aide", "help", "status", "opportunites", "analyser", "sentiment",
        "news", "top", "recherche", "resoudre", "code", "scripts", "run",
        "prix", "memoire", "profil", "souviens", "cherche", "oublie", "stats",
        "code-seul", "rapport", "auto-ameliorer", "planifie", "taches",
        "alertes", "alerte", "comparatif", "graph", "backtest",
        "pnl", "mtf", "sentiment", "apprentissage", "correlations",
        "prevision", "forecast"
    ]
    premiere_mot = texte_lower.split()[0] if texte_lower.split() else ""
    for cmd in commandes_connues:
        if premiere_mot.startswith(cmd) or texte_lower == cmd:
            return None  # Laisser le handler normal traiter
    
    # Detection d'intention par mots-cles
    intentions = {
        "portefeuille": ["portefeuille", "portfolio", "combien j", "valeur", "capital", "solde", "balance"],
        "pnl": ["gain", "perte", "profit", "pnl", "latents", "performance", "resultat"],
        "prix_simple": ["prix", "cote", "vaut combien", "combien coute"],
        "achat_suggestion": ["acheter", "achat", "dois je acheter", "investir", "bon moment"],
        "vente_suggestion": ["vendre", "vente", "dois je vendre", "liquider", "sortir"],
        "analyse_crypto": ["analyser", "analyse", "qu en penses", "avis sur", "tendance"],
        "opportunites": ["opportunite", "opportunit", "quel crypto", "quoi acheter", "bon crypto"],
        "risque": ["risque", "dangereux", "safe", "securise", "peur", "inquiet"],
        "strategie": ["strategie", "methode", "approche", "comment trader"],
        "marche": ["marche", "market", "comment va le marche", "global"],
        "aide_general": ["aide", "comment", "que peux tu", "que sais tu"],
    }
    
    for intention, mots_cles in intentions.items():
        for mot in mots_cles:
            if mot in texte_lower:
                return executer_intention(intention, texte)
    
    # Si aucun mot-cle trouve, utiliser l'IA pour comprendre
    return repondre_ia(texte)


def executer_intention(intention, texte_original):
    """Execute l'action correspondant a l'intention detectee."""
    if intention == "portefeuille":
        return pnl_temps_reel()
    
    elif intention == "pnl":
        return pnl_temps_reel()
    
    elif intention == "prix_simple":
        # Extraire la crypto mentionnee
        from indicateurs import NOMS
        mots = texte_original.upper().split()
        for mot in mots:
            clean = mot.replace("USDT", "").replace("USD", "")
            if clean in COINGECKO_IDS:
                prix = get_crypto_price(clean)
                if prix:
                    nom = NOMS.get(clean + "USDT", clean)
                    return f"💰 {nom}: {prix:.4f} EUR"
        return "Quelle crypto? Ex: prix BTC"
    
    elif intention == "achat_suggestion":
        # Analyser les opportunites + prevision
        return "Analyse des opportunites d'achat...\n" + scan_opportunites_rapide()
    
    elif intention == "vente_suggestion":
        from indicateurs import NOMS
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        positions = pt.get("positions", [])
        if not positions:
            return "Tu n'as aucune position ouverte a vendre."
        msg = "📊 ANALYSE DE VENTE\n" + "━" * 30 + "\n\n"
        for p in positions[:8]:
            sym = p.get("symbole", "?")
            try:
                prev = prevision_ia_prix(sym)
                # Extraire juste le verdict
                for line in prev.split("\n"):
                    if "SIGNAL:" in line:
                        msg += f"  {NOMS.get(sym, sym)}: {line.strip()}\n"
                        break
            except:
                msg += f"  {NOMS.get(sym, sym)}: Analyse indisponible\n"
        return msg
    
    elif intention == "analyse_crypto":
        from indicateurs import NOMS
        mots = texte_original.upper().split()
        for mot in mots:
            clean = mot.replace("USDT", "").replace("USD", "")
            if clean in COINGECKO_IDS:
                return analyse_multi_timeframe(clean + "USDT")
        return analyse_multi_timeframe("BTCUSDT")
    
    elif intention == "opportunites":
        return scan_opportunites_rapide()
    
    elif intention == "risque":
        return detection_correlations()
    
    elif intention == "strategie":
        return apprentissage_auto_trades()
    
    elif intention == "marche":
        return "📊 ETAT DU MARCHE\n" + "━" * 30 + "\n" + alertes_intelligentes() if isinstance(alertes_intelligentes(), str) else alertes_intelligentes()[0]
    
    elif intention == "aide_general":
        return None  # Laisser le handler d'aide normal
    
    return None


def scan_opportunites_rapide():
    """Scan rapide des opportunites d'achat."""
    from indicateurs import NOMS, analyser_signaux_techniques
    msg = "🚀 OPPORTUNITES D'ACHAT\n" + "━" * 30 + "\n\n"
    symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ARBUSDT", "NEARUSDT"]
    opportunites = []
    for sym in symboles:
        try:
            analyse = analyser_actif(sym, "1h")
            if analyse and analyse.get("score", 0) >= 2:
                opportunites.append(analyse)
        except:
            continue
    if not opportunites:
        msg += "Aucune opportunite d'achat forte pour le moment.\n"
        msg += "Le marche est neutre. Patience requise."
        return msg
    for o in sorted(opportunites, key=lambda x: x.get("score", 0), reverse=True)[:5]:
        sym = o.get("symbole", "?")
        msg += f"🟢 {NOMS.get(sym, sym)} - Score {o['score']:+d}\n"
        msg += f"   Prix: {o.get('prix', 0):.4f} EUR | RSI: {o.get('indicateurs', {}).get('RSI', 0):.0f}\n"
        signaux = o.get("signaux", [])
        if signaux:
            msg += f"   Raison: {signaux[0]}\n"
        msg += "\n"
    return msg


def repondre_ia(texte):
    """Repond a un message en langage naturel via l'IA Perplexity."""
    if not PPLX_KEY:
        return None  # Laisser le handler normal
    try:
        # Contexte du portefeuille
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        capital = pt.get("capital_initial", 1000)
        liquidites = pt.get("liquidites", 0)
        positions = pt.get("positions", [])
        nb_positions = len(positions)
        
        contexte = f"Tu es un agent de trading crypto autonome. Capital: {capital}EUR, Liquidites: {liquidites:.2f}EUR, {nb_positions} positions ouvertes. Reponds a la question de maniere concise et utile. Si on te demande un prix, utilise les donnees disponibles. Reponds en francais."
        
        headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": contexte},
                {"role": "user", "content": texte}
            ],
            "max_tokens": 500,
        }
        r = requests.post("https://api.perplexity.ai/chat/completions",
                          json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None


# ============================================
# 25. MOTEUR DE DECISION AUTONOME
# ============================================
def moteur_decision_autonome():
    """L'agent analyse le marche et prend des decisions autonomes."""
    decisions = []
    
    # 1. Verifier les alertes prix
    try:
        nb = verifier_alertes_prix()
        if nb > 0:
            decisions.append(f"{nb} alerte(s) prix declenchee(s)")
    except:
        pass
    
    # 2. Scanner les opportunites
    try:
        from indicateurs import NOMS
        symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                    "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ARBUSDT", "NEARUSDT"]
        opportunites = []
        for sym in symboles:
            try:
                analyse = analyser_actif(sym, "1h")
                if analyse and analyse.get("score", 0) >= 3:
                    opportunites.append((sym, analyse))
            except:
                continue
        if opportunites:
            msg = "🤖 DECISION AUTONOME - Opportunites detectees:\n\n"
            for sym, a in opportunites[:3]:
                msg += f"🟢 {NOMS.get(sym, sym)} - Score {a['score']:+d}\n"
                msg += f"   Prix: {a.get('prix', 0):.4f} EUR\n"
            decisions.append(msg)
    except:
        pass
    
    # 3. Verifier les positions ouvertes pour stop-loss
    try:
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        positions = pt.get("positions", [])
        for p in positions:
            sym = p.get("symbole", "")
            prix_entree = p.get("prix_entree", 0)
            montant = p.get("montant_eur", 0)
            prix_actuel = get_crypto_price(sym.replace("USDT", ""))
            if prix_actuel and prix_entree > 0:
                pnl_pct = (prix_actuel - prix_entree) / prix_entree * 100
                if pnl_pct < -5:
                    decisions.append(f"⚠️ {sym} en perte de {pnl_pct:.1f}% - envisager stop-loss")
                elif pnl_pct > 10:
                    decisions.append(f"🟢 {sym} en gain de {pnl_pct:.1f}% - envisager take-profit")
    except:
        pass
    
    return decisions


def boucle_autonome_intelligente():
    """Boucle autonome qui tourne en arriere-plan et prend des decisions."""
    while True:
        try:
            decisions = moteur_decision_autonome()
            for d in decisions:
                if isinstance(d, str) and len(d) > 20:
                    send_telegram(d)
                    learn_fact(f"Decision autonome: {d[:50]}", "autonomous")
            # Attendre 30 minutes
            time.sleep(1800)
        except Exception as e:
            print(f"[AUTONOME] Erreur: {e}")
            time.sleep(300)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        perf = trading_performance()
        print(perf)
        print("\n" + "=" * 40)
        opps = check_opportunities()
        if opps:
            print("\n🚨 Opportunités:")
            for o in opps:
                print(f"  {o['symbole']}: score {o['score']} - {', '.join(o['raisons'])}")
        else:
            print("\nAucune opportunité détectée")
    elif len(sys.argv) > 1 and sys.argv[1] == "chat":
        telegram_poll()
    elif len(sys.argv) > 1 and sys.argv[1] == "scan":
        scan_and_alert()
    elif len(sys.argv) > 1 and sys.argv[1] == "autonomous":
        autonomous_loop()
    elif len(sys.argv) > 1 and sys.argv[1] == "code-seul":
        autonomous_coder()
    elif len(sys.argv) > 1 and sys.argv[1] == "rapport-telegram":
        rapport = generate_report()
        send_telegram(rapport[:4000])
    elif len(sys.argv) > 1 and sys.argv[1] == "auto-improve":
        bilan = self_improve()
        print(bilan)
    elif len(sys.argv) > 1 and sys.argv[1] == "rapport":
        rapport = generate_report()
        print(rapport)
    elif len(sys.argv) > 1 and sys.argv[1] == "alertes":
        r = envoyer_alertes()
        if r:
            print(r)
    elif len(sys.argv) > 1 and sys.argv[1] == "check-alertes":
        nb = verifier_alertes_prix()
        print(f"{nb} alerte(s) declenchee(s)")
    elif len(sys.argv) > 1 and sys.argv[1] == "pnl":
        result = pnl_temps_reel()
        send_telegram(result[:4000])
        print(result)
    elif len(sys.argv) > 1 and sys.argv[1] == "autonome-ia":
        boucle_autonome_intelligente()
    elif len(sys.argv) > 1 and sys.argv[1] == "graph-telegram":
        generer_graphique("BTCUSDT")
        generer_graphique_pnl()
    else:
        autonomous_loop()
