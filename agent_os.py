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
import urllib.request
import urllib.error

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

# Charger .env depuis le dossier de l'agent (DOSSIER deja defini plus haut)
_env_path = os.path.join(DOSSIER, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_env_path)
except Exception:
    # Fallback: parser .env manuellement
    try:
        if os.path.exists(_env_path):
            with open(_env_path) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and "=" in _line and not _line.startswith("#"):
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip('"').strip("'")
                        if _k and _k not in os.environ:
                            os.environ[_k] = _v
    except:
        pass

# ============================================
# CONFIG
# ============================================
PPLX_KEY = os.getenv("PPLX_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
CLAUDE_KEY = os.getenv("CLAUDE_API_KEY", "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GROK_KEY = os.getenv("XAI_API_KEY", "")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "")
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
                    payload = {"chat_id": TELEGRAM_CHAT, "text": part}
                    if parse_mode:
                        payload["parse_mode"] = parse_mode
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json=payload,
                        timeout=10
                    )
                    time.sleep(0.3)
            else:
                payload = {"chat_id": TELEGRAM_CHAT, "text": message}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                r = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json=payload,
                    timeout=10
                )
                if r.status_code == 200:
                    return True
                # Si erreur de parse_mode, renvoie en texte simple
                if r.status_code == 400 and parse_mode:
                    r2 = requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={"chat_id": TELEGRAM_CHAT, "text": message[:4000]},
                        timeout=10
                    )
                    return r2.status_code == 200
                print(f"[TELEGRAM] HTTP {r.status_code}: {r.text[:200]}")
                if attempt < 2:
                    time.sleep(2)
                    continue
                return False
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
    
    # === BACKTEST AVANCE (doit etre avant le backtest rapide) ===
    if text_lower.startswith("backtest avance") or text_lower.startswith("bt avance"):
        parts = text_stripped.split()
        symbole = parts[2].upper() + "USDT" if len(parts) > 2 and not parts[2].upper().endswith("USDT") else (parts[2].upper() if len(parts) > 2 else "BTCUSDT")
        strategie = parts[3] if len(parts) > 3 else "momentum"
        jours = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 90
        send_telegram(f"🔬 Backtest avance {symbole} {strategie} {jours}j...")
        result = backtest_avance(symbole, strategie, jours)
        send_telegram(result[:4000])
        return result
    
    # === AUTO-AJUSTEMENT STRATEGIES ===
    if text_lower in ["ajuster", "auto-ajuster", "ajuste", "ajustement", "poids strategies"]:
        send_telegram("🧠 Auto-ajustement des strategies...")
        result = auto_ajuster_strategies()
        print(f"[AUTO-AJUSTER] Resultat: {len(result)} chars")
        ok = send_telegram(result, parse_mode=None)
        print(f"[AUTO-AJUSTER] Telegram envoye: {ok}")
        return result
    
    # === CONSEIL MULTI-IA ===
    if text_lower.startswith("conseil") or text_lower.startswith("avis "):
        parts = text_stripped.split(None, 1)
        symbole = parts[1] if len(parts) > 1 else "BTC"
        symbole = symbole.upper() + "USDT" if not symbole.upper().endswith("USDT") else symbole.upper()
        send_telegram(f"🎯 Conseil multi-IA pour {symbole}...")
        result = conseil_multi_ia(symbole)
        send_telegram(result, parse_mode=None)
        return result
    
    # === OPTIMISATION PARAMETRES ===
    if text_lower in ["optimiser", "optimise", "optimisation", "params"]:
        send_telegram("⚙️ Optimisation des parametres...")
        result = optimiser_parametres()
        send_telegram(result, parse_mode=None)
        return result
    
    # === PREDICTION ML ===
    if text_lower.startswith("prediction") or text_lower.startswith("predire") or text_lower.startswith("ml "):
        parts = text_stripped.split(None, 1)
        symbole = parts[1] if len(parts) > 1 else "BTC"
        symbole = symbole.upper() + "USDT" if not symbole.upper().endswith("USDT") else symbole.upper()
        send_telegram(f"🤖 Prediction ML pour {symbole}...")
        result = predire_ml(symbole)
        send_telegram(result, parse_mode=None)
        return result
    
    # === META-APPRENTISSAGE ===
    if text_lower in ["meta", "meta-apprentissage", "apprentissage"]:
        send_telegram("🧠 Meta-apprentissage...")
        result = meta_apprentissage()
        send_telegram(result, parse_mode=None)
        return result
    
    # === AUTO-GENERATION STRATEGIES ===
    if text_lower in ["generer", "genere", "strategies_generees", "nouvelles strategies"]:
        send_telegram("🧬 Generation de nouvelles strategies...")
        result = auto_generer_strategies()
        send_telegram(result, parse_mode=None)
        return result
    
    # === APPRENTISSAGE TRADER ===
    if text_lower in ["learning", "apprentissage", "apprendre", "analyse trades"]:
        send_telegram("🧠 Analyse des trades pour apprentissage...")
        try:
            import apprentissage_trader as ap
            d = os.path.join(DOSSIER, "paper_trading.json")
            pf = json.load(open(d))
            trades = pf.get("trades_fermes", [])
            if trades:
                ap.analyser_trades(trades)
                rapport = ap.rapport_learning()
                send_telegram(rapport[:4000], parse_mode=None)
            else:
                send_telegram("Aucun trade ferme a analyser encore.")
        except Exception as e:
            send_telegram(f"Erreur apprentissage: {e}")
        return "", ""
    
    # === TRADER PRO ===
    if text_lower in ["traderpro", "trader pro", "pro", "score pro"]:
        send_telegram("🎯 Analyse trader pro en cours...")
        try:
            import trader_pro as tp_mod
            rapport = tp_mod.rapport_trader_pro()
            # Score sur top 5 cryptos
            cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
            lignes = [rapport, "\n=== SCORES LIVE ==="]
            for sym in cryptos:
                try:
                    score, details, reco, params = tp_mod.score_opportunite(sym, 0)
                    emoji = "🟢" if reco in ["ACHAT", "ACHAT_FORT"] else ("🔴" if "VENTE" in reco else "🟡")
                    lignes.append(f"{emoji} {sym}: {reco} (score {score:+.1f}) TP={params.get('tp',0):.1f}% SL={params.get('sl',0):.1f}%")
                except Exception:
                    pass
                time.sleep(2)
            send_telegram("\n".join(lignes)[:4000], parse_mode=None)
        except Exception as e:
            send_telegram(f"Erreur trader pro: {e}")
        return "", ""
    
    # === DIVERGENCES + PATTERNS ===
    if text_lower.startswith("divergence") or text_lower.startswith("pattern") or text_lower.startswith("technique "):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🔍 Analyse technique {symbole}...")
        result = detecter_divergences(symbole)
        send_telegram(result[:4000])
        return result
    
    # === SENTIMENT TEMPS REEL ===
    if text_lower.startswith("sentiment"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"📰 Sentiment temps reel {symbole}...")
        result = sentiment_temps_reel(symbole)
        send_telegram(result[:4000])
        return result
    
    # === SIMULATEUR SCENARIOS ===
    if text_lower.startswith("scenario") or text_lower.startswith("simule") or text_lower.startswith("simulation"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🔮 Simulation scenarios {symbole}...")
        result = simulateur_scenarios(symbole)
        send_telegram(result[:4000])
        return result
    
    # === AUTO-DIAGNOSTIC ===
    if text_lower in ["diagnostic", "diag", "scanne", "auto-repare", "repare", "sante", "health"]:
        send_telegram("🔧 Auto-diagnostic en cours...")
        result = auto_diagnostic()
        send_telegram(result[:4000])
        return result
    
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
    
    # === STRATEGIES AVANCEES ===
    if text_lower.startswith("strategies") or text_lower.startswith("avance"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🧪 Strategies avancees {symbole}...")
        result = analyser_strategies_avancees(symbole)
        send_telegram(result[:4000])
        return result
    
    # === BRIEFING MATIN ===
    if text_lower in ["briefing", "matin", "bonjour", "salut", "morning"]:
        send_telegram("🌅 Generation du briefing...")
        result = briefing_matin()
        return result
    
    # === GESTION AUTO (stop-loss/take-profit manuel) ===
    if text_lower in ["gestion", "stop-loss", "stop loss", "take profit", "verifier positions"]:
        send_telegram("🛡️ Verification des positions...")
        result = gerer_stop_loss_take_profit()
        if result:
            send_telegram(result[:4000])
        else:
            send_telegram("Aucune position a fermer. Tout va bien.")
        return result or "OK"
    
    # === DOUBLE IA ===
    if text_lower.startswith("double") or text_lower.startswith("croise"):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"🧠 Double IA croisee {symbole}...")
        result = analyse_double_ia(symbole)
        send_telegram(result[:4000])
        return result
    
    # === REGIME MARCHE ===
    if text_lower in ["regime", "marche", "market regime"]:
        send_telegram("🌐 Analyse du regime global...")
        result = analyser_regime_global()
        send_telegram(result[:4000])
        return result
    
    # === MEMOIRE D'ERREURS ===
    if text_lower in ["erreurs", "memoire erreurs", "lecons", "lessons"]:
        result = consulter_memoire_erreurs()
        send_telegram(result[:4000])
        return result
    
    # === AUTO-EVOLUTION ===
    if text_lower in ["evolution", "evolue", "auto-evolution", "evolution code"]:
        send_telegram("🧬 Auto-evolution en cours...")
        result = auto_evolution_code()
        send_telegram(result[:4000])
        return result
    
    # === DEBAT IA ===
    if text_lower.startswith("debat") or text_lower.startswith("versus") or text_lower.startswith("vs "):
        parts = text_stripped.split(None, 1)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        send_telegram(f"⚔️ Debat IA sur {symbole}...")
        result = debat_ia(symbole)
        send_telegram(result[:4000])
        return result
    
    # === OPTIMISATION PORTEFEUILLE ===
    if text_lower in ["optimise", "optimiser", "reequilibrage", "equilibrage", "rebalance"]:
        send_telegram("⚖️ Optimisation du portefeuille...")
        result = optimiser_portefeuille()
        send_telegram(result[:4000])
        return result
    
    # === ANALYSE WHALES ===
    if text_lower in ["whales", "baleines", "whale", "gros volume"]:
        send_telegram("🐋 Analyse des mouvements de baleines...")
        result = analyser_whales()
        send_telegram(result[:4000])
        return result
    
    # === COPILOT TRADING ===
    if text_lower.startswith("copilot") or text_lower.startswith("conseil"):
        question = text_stripped.split(None, 1)[1] if len(text_stripped.split(None, 1)) > 1 else "analyse generale"
        send_telegram(f"🤖 Copilot analyse: {question[:40]}...")
        result = copilot_trading(question)
        send_telegram(result[:4000])
        return result
    
    # === RAPPORT DOCUMENT ===
    if text_lower in ["rapport pdf", "document", "genere rapport", "rapport complet"]:
        send_telegram("📄 Generation du rapport...")
        result = generer_rapport_pdf("complet")
        send_telegram(result[:4000])
        return result
    
    # === VISUALISATIONS ===
    if text_lower.startswith("viz") or text_lower.startswith("visualise"):
        type_viz = text_stripped.split(None, 1)[1] if len(text_stripped.split(None, 1)) > 1 else "correlations"
        send_telegram(f"📊 Visualisation: {type_viz}...")
        result = visualisation_avancee(type_viz)
        if isinstance(result, str) and not result.endswith(".svg"):
            send_telegram(result[:4000])
        return result
    
    # === SOUS-AGENTS PARALLELES ===
    if text_lower.startswith("scan") or text_lower.startswith("sous-agents") or text_lower.startswith("parallele"):
        critere = text_stripped.split(None, 1)[1] if len(text_stripped.split(None, 1)) > 1 else "toutes"
        send_telegram(f"🤖 Scan parallele de {critere}...")
        result = sous_agents_scan(critere)
        send_telegram(result[:4000])
        return result
    
    # === CONNECTEURS EXTERNES ===
    if text_lower.startswith("connecteur"):
        parts = text_stripped.split(None, 3)
        service = parts[1] if len(parts) > 1 else "liste"
        action = parts[2] if len(parts) > 2 else "status"
        params = parts[3] if len(parts) > 3 else ""
        result = connecteur_externe(service, action, params)
        send_telegram(result[:4000])
        return result
    
    # === MEMOIRE SEMANTIQUE ===
    if text_lower.startswith("memoire"):
        parts = text_stripped.split(None, 2)
        action = parts[1] if len(parts) > 1 else "stats"
        requete = parts[2] if len(parts) > 2 else ""
        result = memoire_semantique_commande(action, requete)
        send_telegram(result[:4000])
        return result
    
    # === MULTI-MODELES ===
    if text_lower.startswith("multi") or text_lower.startswith("consensus"):
        parts = text_stripped.split(None, 2)
        symbole = parts[1].upper() + "USDT" if len(parts) > 1 and not parts[1].upper().endswith("USDT") else (parts[1].upper() if len(parts) > 1 else "BTCUSDT")
        question = parts[2] if len(parts) > 2 else ""
        send_telegram(f"🌐 Multi-modeles sur {symbole}...")
        result = multi_modeles_analyse(symbole, question)
        send_telegram(result[:4000])
        return result
    
    # === RECHERCHE ACADEMIQUE ===
    if text_lower.startswith("paper") or text_lower.startswith("academique") or text_lower.startswith("recherche paper"):
        sujet = text_stripped.split(None, 1)[1] if len(text_stripped.split(None, 1)) > 1 else "cryptocurrency trading"
        send_telegram(f"📚 Recherche academique: {sujet}...")
        result = recherche_academique(sujet, 5)
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

🛡️ RISQUE:
  gestion - Verifie stop-loss (-5%) et take-profit (+10%) auto
  strategies BTC - Ichimoku + VWAP + Elliott Wave
  briefing - Briefing matinal complet (PnL + alertes + opportunit)

🧬 SUPER INTELLIGENCE:
  double BTC - Double IA croisee (Perplexity + Gemini)
  regime - Regime global du marche (bull/bear/range)
  erreurs - Memoire des erreurs passees
  evolution - Auto-evolution: analyse faiblesses + genere code
  debat BTC - Debat IA bull vs bear avec juge impartial
  optimise - Reequilibrage optimal du portefeuille
  whales - Detecte les mouvements de baleines (gros volumes)
  copilot BTC - Assistant IA qui croise toutes les analyses

📄 DOCUMENTS & VISUALISATIONS:
  rapport pdf - Genere un rapport HTML complet (camembert + barres + stats)
  viz correlations - Heatmap des correlations entre cryptos
  viz camembert - Repartition du portefeuille en camembert
  viz courbe - Evolution du capital en graphique

🤖 SOUS-AGENTS & CONNECTEURS:
  scan - Scan parallele de 10 cryptos (score + RSI + signaux)
  scan BTC - Scan d'une crypto specifique
  connecteur liste - Voir les connecteurs externes disponibles
  connecteur email config <smtp> <email> <password> - Configurer email
  connecteur email send <dest> <sujet> <msg> - Envoyer email
  connecteur slack config <webhook_url> - Configurer Slack
  connecteur slack send <message> - Envoyer message Slack

🧠 INTELLIGENCE AVANCEE:
  memoire cherche <mots> - Recherche semantique dans ta memoire
  memoire ajoute <texte> - Enregistre un souvenir
  memoire stats - Statistiques de ta memoire
  multi BTC - Consulte Perplexity + Gemini + GPT + Claude en parallele
  paper cryptocurrency trading - Recherche de papers academiques
  academique machine learning finance - Alias pour recherche papers

🔬 BACKTESTING AVANCE:
  backtest avance BTC momentum 90 - Walk-forward + stats pro
  backtest avance ETH mean_reversion 180 - 6 mois
  bt avance SOL breakout 90 - Version courte
  Strategies: momentum, mean_reversion, breakout, rsi_extreme, macd

🧠 INTELLIGENCE SUPERIEURE:
  ajuster - Auto-ajuste les poids des strategies selon les backtests
  divergence BTC - Detecte divergences + patterns chartistes
  sentiment BTC - Sentiment temps reel (news + social + communaute)
  scenario BTC - Simulateur de scenarios futurs avec probabilites

⚙️ AUTO-OPTIMISATION:
  conseil BTC - Interroge 6 IA (Perplexity/Gemini/Claude/DeepSeek/Grok/Mistral)
  optimiser - Trouve les meilleurs parametres RSI/SMA par crypto
  prediction BTC - Machine learning (regression + decision tree)
  meta - Apprend quelles strategies marchent par regime (bull/bear/sideways)
  generer - Genere et teste de nouvelles strategies (Ichimoku, VWAP, Bollinger...)

🔧 AUTO-REPARATION:
  diagnostic - Scanne l'agent et repare les problemes automatiquement
  sante - Alias pour diagnostic
  (Auto-diagnostic toutes les 30min en arriere-plan)

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
                    # Stop-loss / take-profit auto
                    gerer_stop_loss_take_profit()
                except Exception as e:
                    print(f"[AGENT OS] Erreur alertes/gestion: {e}")
                
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
        "pnl", "mtf", "apprentissage", "correlations",
        "prevision", "forecast",
        "ajuster", "divergence", "pattern", "scenario", "simule",
        "diagnostic", "diag", "sante", "repare",
        "optimiser", "optimise", "prediction", "predire", "ml",
        "meta", "apprentissage", "generer", "genere", "strategies_generees",
        "conseil", "avis", "traderpro", "pro"
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




# ============================================
# 26. STOP-LOSS / TAKE-PROFIT AUTOMATIQUE
# ============================================
def gerer_stop_loss_take_profit():
    """Verifie toutes les positions et ferme celles qui hitent stop-loss ou take-profit."""
    from indicateurs import NOMS
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    trades_fermes = pt.get("trades_fermes", [])
    liquidites = pt.get("liquidites", 0)
    if not positions:
        return "Aucune position ouverte"
    fermees = []
    for p in list(positions):
        sym = p.get("symbole", "")
        prix_entree = p.get("prix_entree", 0)
        quantite = p.get("quantite", 0)
        montant = p.get("montant_eur", 0)
        strategie = p.get("strategie", "inconnu")
        date_ouv = p.get("date_ouverture", "")
        # Prix actuel
        prix_actuel = get_crypto_price(sym.replace("USDT", ""))
        if not prix_actuel or prix_actuel == 0:
            continue
        pnl_pct = (prix_actuel - prix_entree) / prix_entree * 100 if prix_entree > 0 else 0
        pnl_eur = (prix_actuel - prix_entree) * quantite
        # Stop-loss a -5%
        if pnl_pct <= -5:
            raison = f"Stop-loss declenche ({pnl_pct:+.1f}%)"
            liquidites += montant + pnl_eur - montant * 0.001  # frais 0.1%
            trades_fermes.append({
                "symbole": sym, "nom": NOMS.get(sym, sym),
                "prix_entree": prix_entree, "prix_sortie": prix_actuel,
                "quantite": quantite, "pnl": pnl_eur,
                "raison": raison, "strategie": strategie,
                "date_ouverture": date_ouv,
                "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "type_sortie": "stop_loss"
            })
            positions.remove(p)
            fermees.append((sym, "STOP-LOSS", pnl_pct, pnl_eur))
        # Take-profit a +10%
        elif pnl_pct >= 10:
            raison = f"Take-profit declenche ({pnl_pct:+.1f}%)"
            liquidites += montant + pnl_eur - montant * 0.001
            trades_fermes.append({
                "symbole": sym, "nom": NOMS.get(sym, sym),
                "prix_entree": prix_entree, "prix_sortie": prix_actuel,
                "quantite": quantite, "pnl": pnl_eur,
                "raison": raison, "strategie": strategie,
                "date_ouverture": date_ouv,
                "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "type_sortie": "take_profit"
            })
            positions.remove(p)
            fermees.append((sym, "TAKE-PROFIT", pnl_pct, pnl_eur))
    # Sauvegarde
    if fermees:
        pt["positions"] = positions
        pt["trades_fermes"] = trades_fermes
        pt["liquidites"] = liquidites
        save_json_safe(os.path.join(DOSSIER, "paper_trading.json"), pt)
        # Notification Telegram
        msg = "🛡️ GESTION AUTOMATIQUE DES POSITIONS\n" + "━" * 35 + "\n"
        for sym, type_s, pct, eur in fermees:
            emoji = "🟢" if type_s == "TAKE-PROFIT" else "🔴"
            msg += f"\n{emoji} {NOMS.get(sym, sym)} - {type_s}\n"
            msg += f"   PnL: {eur:+.2f} EUR ({pct:+.1f}%)\n"
        send_telegram(msg)
        learn_fact(f"Stop-loss/take-profit: {len(fermees)} position(s) fermee(s)", "risk")
        return msg
    return ""


# ============================================
# 27. POSITION SIZING INTELLIGENT
# ============================================
def calculer_taille_position(score, capital_disponible, liquidites):
    """Calcule la taille optimale d'une position selon le score de conviction.
    Score 1-2: petite position (5% du capital)
    Score 3: position moyenne (8% du capital)
    Score 4+: grosse position (12% du capital)
    """
    # Limite basee sur les liquidites
    max_par_trade = min(liquidites * 0.95, capital_disponible * 0.15)
    if score <= 1:
        pct = 0.05
    elif score == 2:
        pct = 0.07
    elif score == 3:
        pct = 0.10
    elif score >= 4:
        pct = 0.12
    else:
        pct = 0.05
    montant = capital_disponible * pct
    # Ne pas depasser les liquidites
    montant = min(montant, max_par_trade)
    # Minimum 10 EUR
    return max(montant, 10.0) if montant >= 10 else 0


# ============================================
# 28. STRATEGIES AVANCEES
# ============================================
def strategie_ichimoku(clotures):
    """Analyse Ichimoku Cloud."""
    if len(clotures) < 52:
        return None, None
    # Tenkan-sen (9)
    nine_high = max(clotures[-9:])
    nine_low = min(clotures[-9:])
    tenkan = (nine_high + nine_low) / 2
    # Kijun-sen (26)
    twentysix_high = max(clotures[-26:])
    twentysix_low = min(clotures[-26:])
    kijun = (twentysix_high + twentysix_low) / 2
    # Senkou Span A
    senkou_a = (tenkan + kijun) / 2
    # Senkou Span B (52)
    fiftytwo_high = max(clotures[-52:])
    fiftytwo_low = min(clotures[-52:])
    senkou_b = (fiftytwo_high + fiftytwo_low) / 2
    prix = clotures[-1]
    # Signaux
    signal = "NEUTRE"
    score = 0
    if prix > senkou_a and prix > senkou_b:
        signal = "HAUSSIER (au-dessus du nuage)"
        score = 2
    elif prix < senkou_a and prix < senkou_b:
        signal = "BAISSIER (sous le nuage)"
        score = -2
    else:
        signal = "NEUTRE (dans le nuage)"
        score = 0
    if tenkan > kijun:
        score += 1
    else:
        score -= 1
    return signal, score


def strategie_vwap(clotures, volumes=None):
    """Analyse VWAP."""
    if len(clotures) < 20:
        return None, None
    if volumes and len(volumes) == len(clotures):
        vwap = sum(c * v for c, v in zip(clotures, volumes)) / sum(volumes) if sum(volumes) > 0 else sum(clotures) / len(clotures)
    else:
        vwap = sum(clotures) / len(clotures)
    prix = clotures[-1]
    if prix > vwap * 1.01:
        return "HAUSSIER (prix > VWAP)", 1
    elif prix < vwap * 0.99:
        return "BAISSIER (prix < VWAP)", -1
    return "NEUTRE (prix = VWAP)", 0


def strategie_elliott(clotures):
    """Detection simplifiee des vagues d'Elliott."""
    if len(clotures) < 30:
        return None, None
    # Cherche 5 points extremes
    recent = clotures[-30:]
    # Detection de tendance (5 vagues haussieres = 1,2,3,4,5)
    haute = max(recent)
    basse = min(recent)
    pos_haute = recent.index(haute)
    pos_basse = recent.index(basse)
    prix = clotures[-1]
    # Vague 3 (la plus forte)
    if pos_basse < pos_haute and prix > haute * 0.98:
        return "Vague 3 haussiere (impulsion)", 2
    elif pos_haute < pos_basse and prix < basse * 1.02:
        return "Vague 3 baissiere (correction)", -2
    elif pos_basse < pos_haute:
        return "Impulsion haussiere en cours", 1
    else:
        return "Correction en cours", -1


def analyser_strategies_avancees(symbole="BTCUSDT"):
    """Combine toutes les strategies avancees."""
    from indicateurs import historique_ohlcv, NOMS
    bougies = historique_ohlcv(symbole, "1h", 100)
    if not bougies or len(bougies) < 52:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    volumes = [b.get("volume", 0) for b in bougies]
    nom = NOMS.get(symbole, symbole)
    msg = f"🧪 STRATEGIES AVANCEES - {nom}\n" + "━" * 40 + "\n\n"
    # Ichimoku
    ich_sig, ich_score = strategie_ichimoku(clotures)
    if ich_sig:
        emoji = "🟢" if ich_score > 0 else ("🔴" if ich_score < 0 else "⚪")
        msg += f"📜 ICHIMOKU: {ich_sig} (score: {ich_score:+d})\n"
    # VWAP
    vwap_sig, vwap_score = strategie_vwap(clotures, volumes)
    if vwap_sig:
        emoji = "🟢" if vwap_score > 0 else ("🔴" if vwap_score < 0 else "⚪")
        msg += f"📊 VWAP: {vwap_sig} (score: {vwap_score:+d})\n"
    # Elliott
    ell_sig, ell_score = strategie_elliott(clotures)
    if ell_sig:
        emoji = "🟢" if ell_score > 0 else ("🔴" if ell_score < 0 else "⚪")
        msg += f"🌊 ELLIOTT: {ell_sig} (score: {ell_score:+d})\n"
    # Score total
    total = (ich_score or 0) + (vwap_score or 0) + (ell_score or 0)
    msg += f"\n{'━' * 40}\n"
    msg += f"📊 SCORE TOTAL: {total:+d}/6\n"
    if total >= 3:
        msg += "🟢 CONFLUENCE FORTE: ACHAT\n"
    elif total >= 1:
        msg += "🟡 SIGNAL MODERE: ACHAT prudent\n"
    elif total <= -3:
        msg += "🔴 CONFLUENCE FORTE: VENTE\n"
    elif total <= -1:
        msg += "🟠 SIGNAL MODERE: VENTE prudent\n"
    else:
        msg += "⚪ NEUTRE: attendre\n"
    learn_fact(f"Strategies avancees {symbole}: Ichimoku {ich_score:+d}, VWAP {vwap_score:+d}, Elliott {ell_score:+d}", "advanced")
    return msg


# ============================================
# 29. BRIEFING MATIN AUTOMATIQUE
# ============================================
def briefing_matin():
    """Genere et envoie un briefing matinal complet."""
    from indicateurs import NOMS
    msg = "🌅 BRIEFING MATIN - " + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
    msg += "━" * 40 + "\n"
    # 1. Performance portefeuille
    try:
        pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
        capital = pt.get("capital_initial", 1000)
        liquidites = pt.get("liquidites", 0)
        positions = pt.get("positions", [])
        valeur_positions = sum(p.get("montant_eur", 0) for p in positions)
        valeur_totale = liquidites + valeur_positions
        gain = valeur_totale - capital
        gain_pct = (gain / capital * 100) if capital else 0
        msg += f"\n💼 PORTEFEUILLE:\n"
        msg += f"  Valeur: {valeur_totale:.2f} EUR ({gain:+.2f} EUR, {gain_pct:+.1f}%)\n"
        msg += f"  Positions: {len(positions)} | Liquidites: {liquidites:.2f} EUR\n"
    except:
        msg += "\n💼 PORTEFEUILLE: indisponible\n"
    # 2. PnL temps reel (top 3)
    try:
        pnl_msg = pnl_temps_reel()
        # Extraire juste les positions avec PnL
        for line in pnl_msg.split("\n"):
            if "EUR" in line and ("🟢" in line or "🔴" in line):
                msg += f"  {line.strip()}\n"
                if msg.count("\n") > 15:
                    break
    except:
        pass
    # 3. Alertes
    try:
        alertes_result = alertes_intelligentes()
        if isinstance(alertes_result, tuple):
            alertes = alertes_result[1]
            msg += f"\n🚨 ALERTES:\n"
            if alertes:
                for a in alertes[:3]:
                    msg += f"  {a['type']} {a['symbole']} (score {a['score']:+d})\n"
            else:
                msg += "  Marche calme, aucune alerte\n"
    except:
        msg += "\n🚨 ALERTES: indisponible\n"
    # 4. Opportunites
    try:
        symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        opportunites = []
        for sym in symboles:
            try:
                analyse = analyser_actif(sym, "1h")
                if analyse and analyse.get("score", 0) >= 2:
                    opportunites.append((sym, analyse["score"]))
            except:
                continue
        msg += f"\n🚀 OPPORTUNITES:\n"
        if opportunites:
            for sym, score in sorted(opportunites, key=lambda x: x[1], reverse=True)[:3]:
                msg += f"  {NOMS.get(sym, sym)} - Score {score:+d}\n"
        else:
            msg += "  Aucune opportunite forte ce matin\n"
    except:
        msg += "\n🚀 OPPORTUNITES: indisponible\n"
    # 5. Recommandation IA
    msg += f"\n💡 RECOMMANDATION:\n"
    if len(positions) >= 10:
        msg += "  Portefeuille charge - eviter nouveaux achats, consolider\n"
    elif liquidites > capital * 0.3:
        msg += "  Liquidites disponibles - surveiller les opportunites\n"
    else:
        msg += "  Portefeuille equilibre - maintenir la strategy\n"
    # 6. Stop-loss check
    try:
        sl_result = gerer_stop_loss_take_profit()
        if sl_result:
            msg += f"\n🛡️ GESTION AUTO:\n{sl_result}\n"
    except:
        pass
    msg += f"\n━" * 40 + "\n"
    msg += "Bon trading! 📈"
    send_telegram(msg[:4000])
    learn_fact("Briefing matinal envoye", "briefing")
    return msg




# ============================================
# 30. DOUBLE IA CROISEE (Perplexity + Gemini)
# ============================================
def analyse_double_ia(symbole="BTCUSDT"):
    """Croise les analyses de Perplexity et Gemini pour une decision plus fiable."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1h", 100)
    if not bougies or len(bougies) < 50:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    var_24h = (prix - clotures[-24]) / clotures[-24] * 100 if len(clotures) >= 24 else 0
    
    contexte = f"Crypto: {nom} ({symbole})\nPrix: {prix:.4f} EUR\nSMA20: {sma20:.4f}\nSMA50: {sma50:.4f}\nVariation 24h: {var_24h:+.1f}%"
    
    msg = f"🧠 DOUBLE IA CROISEE - {nom}\n" + "━" * 40 + "\n\n"
    msg += f"📊 Donnees techniques:\n{contexte}\n\n"
    
    # IA 1: Perplexity
    perplexity_reponse = None
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Analyse {nom} crypto. Prix: {prix:.4f} EUR, var 24h: {var_24h:+.1f}%. Donnes: 1) tendance court terme (haussier/baissier/neutre) 2) score -10 a +10 3) 2 raisons principales 4) niveau de confiance (0-100%). Sois concis."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                perplexity_reponse = r.json()["choices"][0]["message"]["content"]
                msg += f"🟣 IA PERPLEXITY:\n{perplexity_reponse}\n\n"
        except Exception as e:
            msg += f"🟣 IA PERPLEXITY: Erreur ({e})\n\n"
    else:
        msg += "🟣 IA PERPLEXITY: Cle API manquante\n\n"
    
    # IA 2: Gemini
    gemini_reponse = None
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"
            prompt = f"Analyse {nom} crypto. Prix: {prix:.4f} EUR, var 24h: {var_24h:+.1f}%, SMA20: {sma20:.4f}, SMA50: {sma50:.4f}. Donnes: 1) tendance court terme (haussier/baissier/neutre) 2) score -10 a +10 3) 2 raisons principales 4) niveau de confiance (0-100%). Sois concis."
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                gemini_reponse = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                msg += f"🔵 IA GEMINI:\n{gemini_reponse}\n\n"
            else:
                msg += f"🔵 IA GEMINI: Erreur {r.status_code}\n\n"
        except Exception as e:
            msg += f"🔵 IA GEMINI: Erreur ({e})\n\n"
    else:
        msg += "🔵 IA GEMINI: Cle API manquante\n\n"
    
    # Synthese croisee
    msg += "━" * 40 + "\n"
    msg += "🔀 SYNTHESE CROISEE:\n"
    
    # Extraction des scores (recherche de patterns)
    import re
    score_ppl = 0
    score_gem = 0
    if perplexity_reponse:
        match = re.search(r'score[:\s]*(-?\d+)', perplexity_reponse, re.IGNORECASE)
        if match:
            score_ppl = int(match.group(1))
    if gemini_reponse:
        match = re.search(r'score[:\s]*(-?\d+)', gemini_reponse, re.IGNORECASE)
        if match:
            score_gem = int(match.group(1))
    
    score_moyen = (score_ppl + score_gem) / 2 if (perplexity_reponse or gemini_reponse) else 0
    
    # Verifie concordance
    if perplexity_reponse and gemini_reponse:
        if score_ppl > 0 and score_gem > 0:
            concordance = "🟢 CONCORDANCE: Les 2 IA sont haussieres"
            score_final = max(score_ppl, score_gem)
        elif score_ppl < 0 and score_gem < 0:
            concordance = "🔴 CONCORDANCE: Les 2 IA sont baissieres"
            score_final = min(score_ppl, score_gem)
        elif abs(score_ppl - score_gem) > 5:
            concordance = "⚠️ DIVERGENCE: Les IA ne sont pas d'accord"
            score_final = score_moyen
        else:
            concordance = "🟡 NEUTRE: Signaux mixtes"
            score_final = score_moyen
    else:
        concordance = "🟡 Analyse partielle (une IA indisponible)"
        score_final = score_ppl if perplexity_reponse else score_gem
    
    msg += f"  Score Perplexity: {score_ppl:+d}/10\n"
    msg += f"  Score Gemini: {score_gem:+d}/10\n"
    msg += f"  Score moyen: {score_moyen:+.1f}/10\n"
    msg += f"  {concordance}\n"
    
    if score_final >= 3:
        msg += "\n🟢 DECISION: ACHAT FORTE (double validation IA)"
    elif score_final >= 1:
        msg += "\n🟡 DECISION: ACHAT MODERE"
    elif score_final <= -3:
        msg += "\n🔴 DECISION: VENTE FORTE (double validation IA)"
    elif score_final <= -1:
        msg += "\n🟠 DECISION: VENTE MODEREE"
    else:
        msg += "\n⚪ DECISION: ATTENDRE"
    
    learn_fact(f"Double IA {symbole}: PPLX {score_ppl:+d}, GEM {score_gem:+d}, final {score_final:+.1f}", "double_ia")
    return msg


# ============================================
# 31. DETECTION DE REGIME DE MARCHE
# ============================================
def detecter_regime_marche(symbole="BTCUSDT"):
    """Detecte le regime de marche: bull, bear, ou range."""
    from indicateurs import historique_ohlcv, NOMS
    bougies = historique_ohlcv(symbole, "1d", 100)
    if not bougies or len(bougies) < 50:
        return None
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]
    # SMA 20 et 50
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    # ADX simplifie (force de tendance)
    dm_plus = []
    dm_moins = []
    tr_list = []
    for i in range(1, min(14, len(clotures))):
        haut = bougies[-i-1]["haut"]
        bas = bougies[-i-1]["bas"]
        cloture_prec = bougies[-i-2]["cloture"] if i + 2 <= len(bougies) else clotures[-i-1]
        haut_prec = bougies[-i-2]["haut"] if i + 2 <= len(bougies) else haut
        bas_prec = bougies[-i-2]["bas"] if i + 2 <= len(bougies) else bas
        up = haut - haut_prec
        down = bas_prec - bas
        dm_plus.append(up if up > down and up > 0 else 0)
        dm_moins.append(down if down > up and down > 0 else 0)
        tr = max(haut - bas, abs(haut - cloture_prec), abs(bas - cloture_prec))
        tr_list.append(tr)
    # ADX approximatif
    if tr_list:
        atr = sum(tr_list) / len(tr_list)
        di_plus = sum(dm_plus) / len(dm_plus) / atr * 100 if atr > 0 else 0
        di_moins = sum(dm_moins) / len(dm_moins) / atr * 100 if atr > 0 else 0
        dx = abs(di_plus - di_moins) / (di_plus + di_moins) * 100 if (di_plus + di_moins) > 0 else 0
    else:
        di_plus = di_moins = dx = 0
    # Volatilite
    import statistics
    rendements = [(clotures[i] - clotures[i-1]) / clotures[i-1] for i in range(1, len(clotures)) if clotures[i-1] > 0]
    volatilite = statistics.stdev(rendements) * 100 if len(rendements) > 2 else 0
    # Detection du regime
    if dx > 25:
        if prix > sma20 > sma50 and di_plus > di_moins:
            regime = "BULL"
            strategie = "Acheter les retracements, holder les positions"
        elif prix < sma20 < sma50 and di_moins > di_plus:
            regime = "BEAR"
            strategie = "Vendre les rebonds, reduire l'exposition"
        else:
            regime = "MIXTE"
            strategie = "Attendre une direction claire"
    else:
        regime = "RANGE"
        strategie = "Trader les bandes (acheter bas, vendre haut)"
    return {
        "regime": regime,
        "strategie": strategie,
        "adx": dx,
        "di_plus": di_plus,
        "di_moins": di_moins,
        "volatilite": volatilite,
        "prix": prix,
        "sma20": sma20,
        "sma50": sma50,
    }


def analyser_regime_global():
    """Analyse le regime global du marche sur plusieurs cryptos."""
    from indicateurs import NOMS
    symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    msg = "🌐 REGIME GLOBAL DU MARCHE\n" + "━" * 40 + "\n\n"
    regimes = {"BULL": 0, "BEAR": 0, "RANGE": 0, "MIXTE": 0}
    details = []
    for sym in symboles:
        try:
            r = detecter_regime_marche(sym)
            if r:
                regimes[r["regime"]] = regimes.get(r["regime"], 0) + 1
                nom = NOMS.get(sym, sym)
                emoji = "🟢" if r["regime"] == "BULL" else ("🔴" if r["regime"] == "BEAR" else "🟡" if r["regime"] == "RANGE" else "🟠")
                details.append(f"{emoji} {nom:<12} {r['regime']:<6} ADX:{r['adx']:.0f} Vol:{r['volatilite']:.1f}%")
        except:
            continue
    for d in details:
        msg += d + "\n"
    # Regime global
    msg += "\n" + "━" * 40 + "\n"
    regime_global = max(regimes, key=regimes.get)
    msg += f"📊 REGIME GLOBAL: {regime_global}\n"
    msg += f"  🟢 Bull: {regimes['BULL']} | 🔴 Bear: {regimes['BEAR']} | 🟡 Range: {regimes['RANGE']} | 🟠 Mixte: {regimes['MIXTE']}\n\n"
    # Strategie adaptee
    if regime_global == "BULL":
        msg += "💡 STRATEGIE: Marche haussier - favoriser les achats, holder, utiliser momentum"
    elif regime_global == "BEAR":
        msg += "💡 STRATEGIE: Marche baissier - reduire les positions, stop-loss serres, eviter les achats"
    elif regime_global == "RANGE":
        msg += "💡 STRATEGIE: Marche range - trader les bandes, mean reversion, RSI extreme"
    else:
        msg += "💡 STRATEGIE: Signaux mixtes - prudence, petites positions, attendre clarification"
    learn_fact(f"Regime marche: {regime_global} (Bull:{regimes['BULL']} Bear:{regimes['BEAR']} Range:{regimes['RANGE']})", "regime")
    return msg


# ============================================
# 32. MEMOIRE D'ERREURS
# ============================================
_ERREURS_FILE = os.path.join(DOSSIER, "memoire_erreurs.json")


def enregistrer_erreur(type_err, contexte, detail, solution=""):
    """Enregistre une erreur pour ne pas la repeter."""
    erreurs = load_json_safe(_ERREURS_FILE, {"erreurs": []})
    erreurs["erreurs"].append({
        "type": type_err,
        "contexte": contexte,
        "detail": detail[:200],
        "solution": solution[:200],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "compteur": 1,
    })
    # Garder max 200 erreurs
    if len(erreurs["erreurs"]) > 200:
        erreurs["erreurs"] = erreurs["erreurs"][-200:]
    save_json_safe(_ERREURS_FILE, erreurs)


def verifier_erreurs_passees(contexte, type_err=None):
    """Verifie si une situation similaire a deja cause une erreur."""
    erreurs = load_json_safe(_ERREURS_FILE, {"erreurs": []})
    correspondances = []
    for e in erreurs.get("erreurs", []):
        if type_err and e.get("type") != type_err:
            continue
        # Correspondance simple par mots-cles
        mots_contexte = set(contexte.lower().split())
        mots_erreur = set(e.get("contexte", "").lower().split())
        commun = mots_contexte & mots_erreur
        if len(commun) >= 2:
            correspondances.append(e)
    return correspondances


def consulter_memoire_erreurs():
    """Affiche les erreurs passees et les lecons apprises."""
    erreurs = load_json_safe(_ERREURS_FILE, {"erreurs": []})
    liste = erreurs.get("erreurs", [])
    if not liste:
        return "✅ Aucune erreur enregistree. L'agent apprend encore."
    msg = "🧠 MEMOIRE D'ERREURS\n" + "━" * 35 + "\n\n"
    # Grouper par type
    par_type = {}
    for e in liste:
        t = e.get("type", "inconnu")
        if t not in par_type:
            par_type[t] = []
        par_type[t].append(e)
    for type_err, items in par_type.items():
        msg += f"📋 {type_err.upper()} ({len(items)} erreurs):\n"
        for e in items[-3:]:  # 3 derniers par type
            msg += f"  • {e.get('contexte', '?')[:60]}\n"
            if e.get("solution"):
                msg += f"    → Solution: {e['solution'][:60]}\n"
        msg += "\n"
    msg += f"Total: {len(liste)} erreurs enregistrees\n"
    msg += "L'agent evite de reproduire ces situations."
    return msg


# ============================================
# 33. AUTO-EVOLUTION DE CODE
# ============================================
def auto_evolution_code():
    """L'agent analyse ses propres faiblesses et genere du code pour s'ameliorer."""
    msg = "🧬 AUTO-EVOLUTION EN COURS\n" + "━" * 40 + "\n\n"
    # 1. Analyser les faiblesses
    faiblesses = []
    # Verifier les erreurs recentes
    erreurs = load_json_safe(_ERREURS_FILE, {"erreurs": []})
    liste_err = erreurs.get("erreurs", [])
    if len(liste_err) > 5:
        faiblesses.append(f"{len(liste_err)} erreurs repetees - besoin de corrections")
    # Verifier les trades perdants
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    trades_fermes = pt.get("trades_fermes", [])
    perdants = [t for t in trades_fermes if t.get("pnl", 0) < 0]
    if len(perdants) > 3:
        faiblesses.append(f"{len(perdants)} trades perdants - strategie a ameliorer")
    # Verifier la memoire
    memoire = load_json_safe(MEMORY_FILE, {})
    if len(memoire.get("facts", [])) < 10:
        faiblesses.append("Memoire limitee - besoin d'apprendre plus")
    # Verifier les fichiers
    try:
        taille_code = os.path.getsize(os.path.join(DOSSIER, "agent_os.py"))
        if taille_code < 50000:
            faiblesses.append("Code encore limite - peut etre etendu")
    except:
        pass
    if not faiblesses:
        faiblesses.append("Systeme stable - chercher de nouvelles opportunites d'amelioration")
    msg += "🔍 FAIBLESSES DETECTEES:\n"
    for f in faiblesses:
        msg += f"  • {f}\n"
    # 2. Generer des solutions via IA
    msg += "\n💡 SOLUTIONS PROPOSEES:\n"
    solutions = []
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Tu es un agent de trading crypto autonome. Tu as ces faiblesses: {'; '.join(faiblesses)}. Propose 3 ameliorations concretes que tu pourrais coder en Python. Pour chaque amelioration, donne: 1) titre court 2) description 1 ligne 3) code Python (fonction complete). Reponds en francais, sois concret."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 800}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=45)
            if r.status_code == 200:
                ia_reponse = r.json()["choices"][0]["message"]["content"]
                msg += ia_reponse + "\n"
                solutions.append(ia_reponse)
            else:
                msg += "  IA indisponible - solutions locales generees\n"
        except:
            msg += "  IA indisponible - solutions locales generees\n"
    # 3. Solutions locales par defaut
    if not solutions:
        solutions_locales = [
            ("Optimisation stop-loss dynamique", "Ajuster le stop-loss selon la volatilite (ATR) au lieu de -5% fixe"),
            ("Cache prix CoinGecko", "Mettre en cache les prix pendant 60s pour eviter le rate limit"),
            ("Scan opportunites intelligent", "Scanner uniquement les cryptos avec volume anormal + RSI extreme"),
            ("Backtest strategies combinees", "Tester des combinaisons de strategies (momentum + RSI + Bollinger)"),
            ("Notification smart", "Grouper les notifications pour eviter le spam Telegram"),
        ]
        for titre, desc in solutions_locales:
            msg += f"  📦 {titre}: {desc}\n"
    # 4. Sauvegarder les propositions
    evolution_file = os.path.join(DOSSIER, "evolution_log.json")
    evolution = load_json_safe(evolution_file, {"iterations": []})
    evolution["iterations"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "faiblesses": faiblesses,
        "solutions": solutions[:1] if solutions else solutions_locales,
    })
    save_json_safe(evolution_file, evolution)
    # 5. Auto-application des corrections simples
    corrections_appliquees = 0
    # Si erreurs repetees, enregistrer en memoire
    if len(liste_err) > 5:
        learn_fact("Pattern d'erreurs detecte - ajustement des strategies", "auto_evolution")
        corrections_appliquees += 1
    if len(perdants) > 3:
        learn_fact(f"{len(perdants)} trades perdants - reduction de la taille des positions", "auto_evolution")
        corrections_appliquees += 1
    msg += f"\n✅ {corrections_appliquees} correction(s) auto-appliquee(s)\n"
    msg += f"📝 {len(faiblesses)} faiblesse(s) documentee(s) pour evolution future"
    learn_fact(f"Auto-evolution: {len(faiblesses)} faiblesses, {corrections_appliquees} corrections", "evolution")
    return msg




# ============================================
# 34. DEBAT IA (Bull vs Bear)
# ============================================
def debat_ia(symbole="BTCUSDT"):
    """Deux IA avec des positions opposees (bull vs bear) debattent sur un trade."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1h", 100)
    if not bougies or len(bougies) < 50:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    var_24h = (prix - clotures[-24]) / clotures[-24] * 100 if len(clotures) >= 24 else 0
    var_7d = (prix - clotures[-7*24]) / clotures[-7*24] * 100 if len(clotures) >= 168 else 0

    # RSI
    gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
    pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
    avg_gain = sum(gains) / 14 if gains else 0
    avg_perte = sum(pertes) / 14 if pertes else 0.001
    rsi_val = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))

    contexte = f"{nom} ({symbole}) | Prix: {prix:.4f} EUR | RSI: {rsi_val:.0f} | SMA20: {sma20:.4f} | SMA50: {sma50:.4f} | Var 24h: {var_24h:+.1f}% | Var 7j: {var_7d:+.1f}%"

    msg = f"⚔️ DEBAT IA - {nom}\n" + "━" * 40 + "\n\n"
    msg += f"📊 Contexte: {contexte}\n\n"

    # Arguments BULL (via Perplexity)
    bull_args = ""
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Tu es un trader BULLISH. Defends l'achat de {nom} maintenant. Donnes 3 arguments solides en 2 lignes chacun max. Sois persuasif mais honnete avec les donnees. Contexte: {contexte}. Reponds en francais."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                bull_args = r.json()["choices"][0]["message"]["content"]
                msg += f"🟢 ARGUMENTS BULL (Perplexity):\n{bull_args}\n\n"
        except Exception as e:
            msg += f"🟢 ARGUMENTS BULL: Erreur ({e})\n\n"
    else:
        msg += "🟢 ARGUMENTS BULL: Cle API manquante\n\n"

    # Arguments BEAR (via Gemini)
    bear_args = ""
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"
            prompt = f"Tu es un trader BEARISH. Defends la vente ou l'evitement de {nom} maintenant. Donnes 3 arguments solides en 2 lignes chacun max. Sois persuasif mais honnete avec les donnees. Contexte: {contexte}. Reponds en francais."
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                bear_args = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                msg += f"🔴 ARGUMENTS BEAR (Gemini):\n{bear_args}\n\n"
        except Exception as e:
            msg += f"🔴 ARGUMENTS BEAR: Erreur ({e})\n\n"
    else:
        msg += "🔴 ARGUMENTS BEAR: Cle API manquante\n\n"

    # Juge IA (Perplexity avec les deux arguments)
    msg += "━" * 40 + "\n"
    msg += "⚖️ VERDICT DU JUGE IA:\n"
    if PPLX_KEY and bull_args and bear_args:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Tu es un juge impartial. Voici un debat sur {nom}:\n\nARGUMENTS BULL:\n{bull_args}\n\nARGUMENTS BEAR:\n{bear_args}\n\nDonne ton verdict: 1) Qui a les arguments les plus solides? 2) Score final -10 a +10 3) Recommendation: ACHETER / VENDRE / ATTENDRE 4) Une phrase de conclusion. Sois concis."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                verdict = r.json()["choices"][0]["message"]["content"]
                msg += verdict
                learn_fact(f"Debat {symbole}: verdict juge rendu", "debat")
        except Exception as e:
            msg += f"Erreur juge: {e}"
    elif bull_args or bear_args:
        # Verdict local si une seule IA disponible
        score_tech = 0
        if prix > sma20 > sma50:
            score_tech += 2
        elif prix > sma20:
            score_tech += 1
        elif prix < sma20 < sma50:
            score_tech -= 2
        elif prix < sma20:
            score_tech -= 1
        if rsi_val < 35:
            score_tech += 1
        elif rsi_val > 65:
            score_tech -= 1
        if score_tech >= 2:
            msg += "Verdict local: ACHETER (arguments techniques favorables)\n"
        elif score_tech <= -2:
            msg += "Verdict local: VENDRE (arguments techniques defavorables)\n"
        else:
            msg += "Verdict local: ATTENDRE (signaux neutres)\n"
    else:
        msg += "Aucune IA disponible pour le verdict\n"

    msg += f"\n{'━' * 40}\n"
    msg += "💡 Le debat t'aide a voir les deux cotes avant de decider."
    return msg


# ============================================
# 35. OPTIMISEUR DE PORTEFEUILLE
# ============================================
def optimiser_portefeuille():
    """Suggere un reequilibrage optimal du portefeuille."""
    from indicateurs import NOMS
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    liquidites = pt.get("liquidites", 0)
    capital = pt.get("capital_initial", 1000)
    if not positions:
        return "Aucune position a optimiser"
    msg = "⚖️ OPTIMISATION DU PORTEFEUILLE\n" + "━" * 40 + "\n\n"
    # Analyser chaque position
    analyses = []
    total_investi = 0
    for p in positions:
        sym = p.get("symbole", "")
        prix_entree = p.get("prix_entree", 0)
        quantite = p.get("quantite", 0)
        montant = p.get("montant_eur", 0)
        total_investi += montant
        prix_actuel = get_crypto_price(sym.replace("USDT", ""))
        if not prix_actuel:
            prix_actuel = prix_entree
        pnl_pct = (prix_actuel - prix_entree) / prix_entree * 100 if prix_entree > 0 else 0
        poids = montant / capital * 100 if capital > 0 else 0
        # Score technique rapide
        try:
            analyse = analyser_actif(sym, "1h")
            score = analyse.get("score", 0) if analyse else 0
        except:
            score = 0
        analyses.append({
            "symbole": sym, "nom": NOMS.get(sym, sym),
            "montant": montant, "pnl_pct": pnl_pct,
            "poids": poids, "score": score, "prix_actuel": prix_actuel
        })
    # Trier par performance
    msg += f"{'Crypto':<12} {'Montant':>8} {'%':>5} {'PnL':>7} {'Score':>6} {'Action':<15}\n"
    msg += "─" * 58 + "\n"
    recommandations = []
    for a in sorted(analyses, key=lambda x: x["pnl_pct"]):
        action = "GARDER"
        if a["pnl_pct"] < -5 and a["score"] < 0:
            action = "🔴 VENDRE"
            recommandations.append(f"Vendre {a['nom']} (perte {a['pnl_pct']:+.1f}%, score {a['score']:+d})")
        elif a["pnl_pct"] > 10:
            action = "🟢 TP PARTIEL"
            recommandations.append(f"Take-profit partiel sur {a['nom']} (+{a['pnl_pct']:.1f}%)")
        elif a["score"] >= 3 and a["poids"] < 5:
            action = "🟡 RENFORCER"
            recommandations.append(f"Renforcer {a['nom']} (score {a['score']:+d}, sous-pondere)")
        elif a["poids"] > 15:
            action = "🟠 REDUIRE"
            recommandations.append(f"Reduire {a['nom']} (trop pondere: {a['poids']:.1f}%)")
        emoji = "🟢" if a["pnl_pct"] >= 0 else "🔴"
        msg += f"{emoji} {a['nom'][:10]:<10} {a['montant']:>7.0f} {a['poids']:>4.0f}% {a['pnl_pct']:>+6.1f}% {a['score']:>+5d} {action}\n"
    # Stats globales
    valeur_total = sum(a["montant"] for a in analyses) + liquidites
    nb_gagnants = len([a for a in analyses if a["pnl_pct"] > 0])
    nb_perdants = len([a for a in analyses if a["pnl_pct"] < 0])
    msg += "\n" + "━" * 40 + "\n"
    msg += f"📊 STATS:\n"
    msg += f"  Positions: {len(analyses)} ({nb_gagnants}G / {nb_perdants}P)\n"
    msg += f"  Investi: {total_investi:.0f} EUR | Liquidites: {liquidites:.0f} EUR\n"
    msg += f"  Liquidites: {liquidites/capital*100:.0f}% du capital\n"
    # Recommandations
    msg += f"\n💡 RECOMMANDATIONS D'EQUILIBRAGE:\n"
    if recommandations:
        for r in recommandations:
            msg += f"  → {r}\n"
    else:
        msg += "  → Portefeuille equilibre, aucune action necessaire\n"
    # Diversification
    poids_max = max(a["poids"] for a in analyses) if analyses else 0
    if poids_max > 15:
        msg += f"\n⚠️ Concentration: une position represente {poids_max:.0f}% - envisager de diversifier\n"
    elif liquidites / capital > 0.3:
        msg += f"\n💡 {liquidites:.0f} EUR disponibles - opportuniste pour de nouveaux achats\n"
    learn_fact(f"Optimisation: {len(recommandations)} recommandations, {nb_gagnants}G/{nb_perdants}P", "optimisation")
    return msg




# ============================================
# 36. ANALYSE DE WHALES (mouvements gros volume)
# ============================================
def analyser_whales():
    """Detecte les mouvements de baleines (gros volumes) via CoinGecko et analyse on-chain."""
    from indicateurs import NOMS, COINGECKO_MAP
    msg = "🐋 ANALYSE WHALES - Gros mouvements detectes\n" + "━" * 40 + "\n\n"
    
    symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
    whales_detectes = []
    
    for sym in symboles:
        crypto_id = COINGECKO_MAP.get(sym.replace("USDT", "").lower(), sym.replace("USDT", "").lower())
        try:
            # Recupere donnees marche (volume 24h)
            url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=eur&days=7"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            volumes = data.get("volumes", [])
            if len(volumes) < 48:
                continue
            # Volume moyen et volume recent
            vol_recent = volumes[-1][1] if volumes else 0
            vol_moyen = sum(v[1] for v in volumes[-48:]) / len(volumes[-48:]) if volumes else 0
            # Detecte pic de volume (x3 = whale)
            if vol_moyen > 0:
                ratio = vol_recent / vol_moyen
                if ratio > 1.5:
                    nom = NOMS.get(sym, sym)
                    # Recupere prix actuel
                    prix_url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=eur&include_24hr_vol=true"
                    pr = requests.get(prix_url, timeout=10)
                    prix = 0
                    var_vol_24h = 0
                    if pr.status_code == 200:
                        pd = pr.json().get(crypto_id, {})
                        prix = pd.get("eur", 0)
                        var_vol_24h = pd.get("eur_24h_vol", 0)
                    
                    # Direction: compare prix actuel vs prix il y a 24h
                    prices = data.get("prices", [])
                    prix_24h = prices[-24][1] if len(prices) >= 24 else (prices[0][1] if prices else prix)
                    direction = "🟢 ACHAT" if prix > prix_24h else "🔴 VENTE"
                    intensite = "🔥 MASSIF" if ratio > 3 else "⚡ IMPORTANT" if ratio > 2 else "📈 MODERE"
                    
                    whales_detectes.append({
                        "nom": nom, "symbole": sym,
                        "ratio": ratio, "direction": direction,
                        "intensite": intensite, "prix": prix,
                        "volume": vol_recent
                    })
        except:
            continue
    
    if not whales_detectes:
        msg += "✅ Aucun mouvement de baleine detecte dans les dernieres 24h.\n"
        msg += "Le marche est calme - pas de gros volumes anormaux.\n"
    else:
        # Trier par intensite
        whales_detectes.sort(key=lambda x: x["ratio"], reverse=True)
        for w in whales_detectes:
            msg += f"{w['intensite']} {w['nom']:<12} {w['direction']}\n"
            msg += f"  Volume: {w['volume']/1e6:.1f}M EUR (x{w['ratio']:.1f} vs moyenne)\n"
            msg += f"  Prix: {w['prix']:.4f} EUR\n\n"
        
        # Interpretation
        msg += "━" * 40 + "\n"
        msg += "📊 INTERPRETATION:\n"
        achats = [w for w in whales_detectes if "ACHAT" in w["direction"]]
        ventes = [w for w in whales_detectes if "VENTE" in w["direction"]]
        msg += f"  🟢 Baleines qui achetent: {len(achats)}\n"
        msg += f"  🔴 Baleines qui vendent: {len(ventes)}\n"
        if len(achats) > len(ventes):
            msg += "  → Sentiment whale: HAUSSIER (accumulation)\n"
            msg += "  → Les gros joueurs accumulent - signal positif\n"
        elif len(ventes) > len(achats):
            msg += "  → Sentiment whale: BAISSIER (distribution)\n"
            msg += "  → Les gros joueurs vendent - prudence\n"
        else:
            msg += "  → Sentiment whale: NEUTRE (mixte)\n"
    
    learn_fact(f"Whales: {len(whales_detectes)} mouvements detectes", "whales")
    return msg


# ============================================
# 37. COPILOT TRADING (assistant interactif)
# ============================================
def copilot_trading(question=""):
    """Assistant intelligent qui repond aux questions de trading en croisant toutes les analyses."""
    from indicateurs import NOMS
    
    # Detecte le symbole dans la question
    symbole = "BTCUSDT"
    crypto_map = {
        "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
        "eth": "ETHUSDT", "ethereum": "ETHUSDT", 
        "sol": "SOLUSDT", "solana": "SOLUSDT",
        "bnb": "BNBUSDT", "xrp": "XRPUSDT", "ripple": "XRPUSDT",
        "doge": "DOGEUSDT", "avax": "AVAXUSDT",
        "link": "LINKUSDT", "arb": "ARBUSDT",
        "near": "NEARUSDT", "fet": "FETUSDT",
        "rndr": "RNDRUSDT", "ldo": "LDOUSDT",
        "aave": "AAVEUSDT", "pendle": "PENDLEUSDT",
    }
    q_lower = question.lower()
    for k, v in crypto_map.items():
        if k in q_lower:
            symbole = v
            break
    
    nom = NOMS.get(symbole, symbole)
    
    # Collecte toutes les analyses disponibles
    msg = f"🤖 COPILOT TRADING - {nom}\n" + "━" * 40 + "\n\n"
    
    # 1. Regime de marche
    try:
        regime = detecter_regime_marche(symbole)
        if regime:
            msg += f"🌐 Regime: {regime['regime']} (ADX: {regime['adx']:.0f})\n"
            msg += f"   Strategie: {regime['strategie']}\n\n"
    except:
        msg += "🌐 Regime: indisponible\n\n"
    
    # 2. Prix et tendance
    try:
        prix = get_crypto_price(symbole.replace("USDT", ""))
        if prix:
            msg += f"💰 Prix actuel: {prix:.4f} EUR\n"
    except:
        pass
    
    # 3. Score technique
    try:
        analyse = analyser_actif(symbole, "1h")
        if analyse and "score" in analyse:
            score = analyse["score"]
            emoji = "🟢" if score >= 3 else "🔴" if score <= -3 else "🟡"
            msg += f"{emoji} Score technique: {score:+d}/10\n"
            if "signaux" in analyse and analyse["signaux"]:
                msg += f"   Signaux: {', '.join(analyse['signaux'][:3])}\n"
    except:
        pass
    
    # 4. RSI
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, "1h", 20)
        if bougies and len(bougies) >= 15:
            clotures = [b["cloture"] for b in bougies]
            gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
            pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_perte = sum(pertes) / 14 if pertes else 0.001
            rsi = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))
            etat_rsi = "SURVENTE 🟢" if rsi < 35 else "SURACHAT 🔴" if rsi > 65 else "NEUTRE 🟡"
            msg += f"📊 RSI: {rsi:.0f} ({etat_rsi})\n"
    except:
        pass
    
    # 5. Verifie si on a une position
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    pos = next((p for p in positions if p.get("symbole") == symbole), None)
    if pos:
        prix_entree = pos.get("prix_entree", 0)
        prix_actuel = get_crypto_price(symbole.replace("USDT", "")) or prix_entree
        pnl_pct = (prix_actuel - prix_entree) / prix_entree * 100 if prix_entree > 0 else 0
        msg += f"\n💼 Position ouverte:\n"
        msg += f"   Entree: {prix_entree:.4f} EUR | PnL: {pnl_pct:+.1f}%\n"
        msg += f"   Stop-loss: -5% | Take-profit: +10%\n"
    else:
        msg += f"\n💼 Aucune position ouverte sur {nom}\n"
    
    # 6. Verdict IA
    msg += "\n" + "━" * 40 + "\n"
    msg += "🧠 VERDICT COPILOT:\n"
    
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            contexte = msg.replace("━" * 40, "").replace("🤖 COPILOT TRADING", "")
            prompt = f"Tu es un copilot de trading crypto. Un utilisateur demande: '{question}'. Voici le contexte technique de {nom}:\n{contexte}\n\nDonne un conseil clair et concis en 3-4 lignes max: 1) Action recommandee 2) Pourquoi 3) Niveau de risque (faible/moyen/eleve). Reponds en francais."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                verdict = r.json()["choices"][0]["message"]["content"]
                msg += verdict
                learn_fact(f"Copilot {symbole}: conseil rendu pour '{question[:50]}'", "copilot")
        except Exception as e:
            msg += f"IA indisponible ({e})\n"
    else:
        msg += "Cle API manquante\n"
    
    return msg




# ============================================
# 38. GENERATION DE DOCUMENTS (rapports PDF/HTML)
# ============================================
def generer_rapport_pdf(type_rapport="complet"):
    """Genere un rapport HTML complet avec graphiques, tableaux et analyses."""
    from indicateurs import NOMS
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    fermes = pt.get("trades_fermes", [])
    cap_init = float(pt.get("capital_initial", 1000))
    liq = float(pt.get("liquidites", 0))
    frais = float(pt.get("total_frais", 0))
    
    # Prix temps reel
    symboles = [p.get("symbole", "") for p in positions if isinstance(p, dict)]
    prix_dict = {}
    for sym in symboles:
        base = sym.replace("USDT", "")
        prix = get_crypto_price(base)
        if prix:
            prix_dict[sym] = prix
    
    total_valeur = 0
    total_pnl = 0
    lignes_pos = ""
    for p in positions:
        sym = p.get("symbole", "?")
        nom = NOMS.get(sym, sym)
        prix_entree = float(p.get("prix_entree", 0))
        quantite = float(p.get("quantite", 0))
        montant = float(p.get("montant_eur", 0))
        prix_actuel = prix_dict.get(sym, prix_entree)
        if isinstance(prix_actuel, dict):
            prix_actuel = prix_actuel.get("prix", prix_actuel.get("eur", prix_entree))
        try:
            prix_actuel = float(prix_actuel)
        except (ValueError, TypeError):
            prix_actuel = prix_entree
        valeur = prix_actuel * quantite
        pnl = valeur - montant
        pnl_pct = (pnl / montant * 100) if montant > 0 else 0
        total_valeur += valeur
        total_pnl += pnl
        color = "#4ade80" if pnl >= 0 else "#f87171"
        lignes_pos += f"<tr><td>{nom}</td><td>{prix_entree:.4f}</td><td>{prix_actuel:.4f}</td><td>{montant:.2f}</td><td style='color:{color}'>{pnl:+.2f} ({pnl_pct:+.1f}%)</td></tr>"
    
    cap_actuel = liq + total_valeur
    perf = ((cap_actuel - cap_init) / cap_init * 100) if cap_init else 0
    
    # Graphique camembert (repartition portefeuille)
    camembert = ""
    if positions:
        total_montants = sum(float(p.get("montant_eur", 0)) for p in positions)
        angles = []
        cumul = 0
        couleurs = ["#58a6ff", "#f78166", "#4ade80", "#fbbf24", "#a78bfa", "#fb7185", "#22d3ee", "#a3e635", "#fb923c", "#e879f9", "#34d399", "#facc15"]
        for i, p in enumerate(positions):
            nom = NOMS.get(p.get("symbole", ""), p.get("symbole", ""))
            montant = float(p.get("montant_eur", 0))
            pct = montant / total_montants * 100 if total_montants > 0 else 0
            angle = pct * 3.6
            debut = cumul
            cumul += angle
            rayon = 80
            import math
            x1 = 100 + rayon * math.cos(math.radians(debut - 90))
            y1 = 100 + rayon * math.sin(math.radians(debut - 90))
            x2 = 100 + rayon * math.cos(math.radians(cumul - 90))
            y2 = 100 + rayon * math.sin(math.radians(cumul - 90))
            large_arc = 1 if angle > 180 else 0
            couleur = couleurs[i % len(couleurs)]
            camembert += f'<path d="M 100,100 L {x1:.1f},{y1:.1f} A {rayon},{rayon} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" fill="{couleur}" opacity="0.85"/>'
            # Label
            milieu = (debut + cumul) / 2
            lx = 100 + rayon * 0.6 * math.cos(math.radians(milieu - 90))
            ly = 100 + rayon * 0.6 * math.sin(math.radians(milieu - 90))
            if pct > 5:
                camembert += f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" fill="white" font-size="9" font-weight="bold">{nom[:4]}</text>'
        camembert = f'<svg viewBox="0 0 200 200" width="250" height="250">{camembert}<circle cx="100" cy="100" r="40" fill="#0d1117"/><text x="100" y="98" text-anchor="middle" fill="#e6edf3" font-size="12" font-weight="bold">{cap_actuel:.0f}€</text><text x="100" y="112" text-anchor="middle" fill="#8b949e" font-size="9">Capital</text></svg>'
    
    # Graphique PnL par position (barres horizontales)
    barres_pnl = '<svg viewBox="0 0 400 300" width="100%" height="300">'
    for i, p in enumerate(positions):
        sym = p.get("symbole", "?")
        nom = NOMS.get(sym, sym)[:10]
        montant = float(p.get("montant_eur", 0))
        prix_actuel = prix_dict.get(sym, float(p.get("prix_entree", 0)))
        if isinstance(prix_actuel, dict):
            prix_actuel = prix_actuel.get("prix", prix_actuel.get("eur", float(p.get("prix_entree", 0))))
        try:
            prix_actuel = float(prix_actuel)
        except (ValueError, TypeError):
            prix_actuel = float(p.get("prix_entree", 0))
        pnl = (prix_actuel * float(p.get("quantite", 0))) - montant
        pnl_pct = (pnl / montant * 100) if montant > 0 else 0
        y = i * 24 + 10
        color = "#4ade80" if pnl >= 0 else "#f87171"
        largeur = min(abs(pnl_pct) * 5, 180)
        barres_pnl += f'<text x="0" y="{y+12}" fill="#e6edf3" font-size="10">{nom}</text>'
        barres_pnl += f'<rect x="80" y="{y}" width="{largeur}" height="16" fill="{color}" rx="3"/>'
        barres_pnl += f'<text x="265" y="{y+12}" fill="{color}" font-size="10">{pnl_pct:+.1f}%</text>'
    barres_pnl += '</svg>'
    
    # Trades fermes
    lignes_fermes = ""
    for t in fermes[-15:]:
        sym = t.get("symbole", "?")
        pnl = t.get("pnl", 0)
        raison = t.get("raison_fermeture", "?")
        date_f = t.get("date_fermeture", "?")
        color = "#4ade80" if pnl >= 0 else "#f87171"
        lignes_fermes += f"<tr><td>{sym}</td><td style='color:{color}'>{pnl:+.2f}€</td><td>{raison}</td><td>{date_f}</td></tr>"
    
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    rapport_html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport Agent IA - {date_str}</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--txt:#e6edf3;--muted:#8b949e;--pos:#4ade80;--neg:#f87171;--border:#30363d;--accent:#58a6ff}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font-family:-apple-system,sans-serif;padding:20px;max-width:900px;margin:0 auto}}
h1{{font-size:24px;margin-bottom:4px;color:var(--accent)}}
h2{{font-size:16px;margin:20px 0 10px;border-bottom:1px solid var(--border);padding-bottom:6px}}
.subtitle{{color:var(--muted);font-size:13px;margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}}
.card .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:4px}}
.card .val{{font-size:20px;font-weight:700}}
.card.pos .val{{color:var(--pos)}}.card.neg .val{{color:var(--neg)}}
.graphs{{display:flex;flex-wrap:wrap;gap:20px;margin-bottom:20px;justify-content:center}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:14px}}
th,td{{padding:8px;border-bottom:1px solid var(--border);text-align:left}}
th{{color:var(--muted);text-transform:uppercase;font-size:10px}}
.footer{{text-align:center;color:var(--muted);font-size:11px;margin-top:30px;padding-top:14px;border-top:1px solid var(--border)}}
</style></head><body>
<h1>📊 Rapport de Trading - Agent IA</h1>
<div class="subtitle">Genere le {date_str} · Paper Trading · Capital initial {cap_init:.0f}€</div>

<div class="cards">
  <div class="card"><div class="lbl">Capital</div><div class="val">{cap_actuel:.2f}€</div></div>
  <div class="card {'pos' if perf>=0 else 'neg'}"><div class="lbl">Performance</div><div class="val">{perf:+.2f}%</div></div>
  <div class="card"><div class="lbl">Liquidites</div><div class="val">{liq:.2f}€</div></div>
  <div class="card neg"><div class="lbl">PnL latent</div><div class="val">{total_pnl:+.2f}€</div></div>
</div>

<h2>🥧 Repartition du portefeuille</h2>
<div class="graphs">
  {camembert if camembert else '<p style="color:var(--muted)">Aucune position</p>'}
</div>

<h2>📊 PnL par position</h2>
<div class="graphs">
  {barres_pnl}
</div>

<h2>💼 Positions ouvertes ({len(positions)})</h2>
<table><thead><tr><th>Crypto</th><th>Prix entree</th><th>Prix actuel</th><th>Montant</th><th>PnL</th></tr></thead>
<tbody>{lignes_pos if lignes_pos else '<tr><td colspan="5" style="color:var(--muted)">Aucune position</td></tr>'}</tbody></table>

<h2>📋 Trades fermes ({len(fermes)})</h2>
<table><thead><tr><th>Crypto</th><th>PnL</th><th>Raison</th><th>Date</th></tr></thead>
<tbody>{lignes_fermes if lignes_fermes else '<tr><td colspan="4" style="color:var(--muted)">Aucun trade ferme</td></tr>'}</tbody></table>

<h2>📈 Statistiques</h2>
<table><tr><th>Metrique</th><th>Valeur</th></tr>
<tr><td>Capital initial</td><td>{cap_init:.2f}€</td></tr>
<tr><td>Capital actuel</td><td>{cap_actuel:.2f}€</td></tr>
<tr><td>Positions ouvertes</td><td>{len(positions)}</td></tr>
<tr><td>Trades fermes</td><td>{len(fermes)}</td></tr>
<tr><td>Frais cumules</td><td>{frais:.2f}€</td></tr>
<tr><td>Liquidites</td><td>{liq:.2f}€ ({liq/cap_init*100:.0f}%)</td></tr>
</table>

<div class="footer">
  Rapport genere par Agent IA Trading v2 · {date_str}<br>
  Donnees via CoinGecko · 37+ commandes Telegram
</div>
</body></html>"""
    
    # Sauvegarder le rapport
    rapport_file = os.path.join(DOSSIER, f"rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
    with open(rapport_file, "w") as f:
        f.write(rapport_html)
    
    # Envoyer sur Telegram
    send_telegram(f"📄 Rapport genere: {rapport_file}\n\nLe rapport HTML contient:\n  🥧 Camembert repartition\n  📊 Barres PnL par position\n  💼 Tableau positions\n  📋 Trades fermes\n  📈 Statistiques\n\nOuvre le fichier sur le VPS pour voir le rapport complet.")
    
    return rapport_file


# ============================================
# 39. VISUALISATIONS AVANCEES (camembert, heatmap, courbes)
# ============================================
def visualisation_avancee(type_viz="correlations"):
    """Genere des visualisations avancees en SVG."""
    from indicateurs import NOMS, historique_ohlcv
    pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
    positions = pt.get("positions", [])
    
    if type_viz in ["correlations", "heatmap", "correlation"]:
        # Heatmap des correlations
        symboles = [p.get("symbole", "") for p in positions if isinstance(p, dict)][:8]
        if len(symboles) < 2:
            return "Pas assez de positions pour une heatmap"
        
        # Calcul matrice correlation
        import statistics
        prix_data = {}
        for sym in symboles:
            bougies = historique_ohlcv(sym, "1d", 30)
            if bougies and len(bougies) >= 10:
                prix_data[sym] = [b["cloture"] for b in bougies]
        
        if len(prix_data) < 2:
            return "Pas assez de donnees pour les correlations"
        
        # Calcul correlations de Pearson
        def pearson(x, y):
            n = min(len(x), len(y))
            x, y = x[:n], y[:n]
            mx, my = statistics.mean(x), statistics.mean(y)
            sx, sy = statistics.stdev(x), statistics.stdev(y)
            if sx == 0 or sy == 0:
                return 0
            cov = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y)) / n
            return cov / (sx * sy)
        
        syms = list(prix_data.keys())
        n = len(syms)
        matrix = [[pearson(prix_data[syms[i]], prix_data[syms[j]]) for j in range(n)] for i in range(n)]
        
        # SVG heatmap
        cell = 40
        svg = f'<svg viewBox="0 0 {cell*(n+1)+20} {cell*(n+1)+20}" width="100%">'
        # Headers
        for i, sym in enumerate(syms):
            nom = NOMS.get(sym, sym)[:6]
            svg += f'<text x="{cell*(i+1)+cell/2+10}" y="15" text-anchor="middle" fill="#8b949e" font-size="9">{nom}</text>'
            svg += f'<text x="5" y="{cell*(i+1)+cell/2+5}" fill="#8b949e" font-size="9">{nom}</text>'
        # Cells
        for i in range(n):
            for j in range(n):
                val = matrix[i][j]
                # Couleur: rouge (negatif) a vert (positif)
                if val > 0:
                    r = int(248 * (1 - val))
                    g = 222
                    b = 128
                else:
                    r = 248
                    g = int(222 * (1 + val))
                    b = 113
                x = cell * (j + 1) + 10
                y = cell * (i + 1) + 10
                svg += f'<rect x="{x}" y="{y}" width="{cell-2}" height="{cell-2}" fill="rgb({r},{g},{b})" rx="3"/>'
                svg += f'<text x="{x+cell/2-1}" y="{y+cell/2+4}" text-anchor="middle" fill="white" font-size="9" font-weight="bold">{val:+.1f}</text>'
        svg += '</svg>'
        
        # Interpretation
        diversification = "Faible" if max(max(row) for row in matrix) > 0.8 else "Bonne" if max(max(row) for row in matrix) < 0.5 else "Moyenne"
        
        msg = "🔥 HEATMAP CORRELATIONS\n" + "━" * 40 + "\n\n"
        msg += f"Diversification: {diversification}\n\n"
        msg += "Couleurs: 🟢 positif (meme direction) | 🔴 negatif (direction opposee)\n\n"
        msg += svg if False else "Le graphique a ete sauvegarde."
        
        # Sauvegarder SVG
        svg_file = os.path.join(DOSSIER, f"heatmap_{datetime.now().strftime('%Y%m%d_%H%M')}.svg")
        with open(svg_file, "w") as f:
            f.write(svg)
        
        # Envoyer info sur Telegram
        msg_tg = "🔥 HEATMAP CORRELATIONS\n" + "━" * 35 + "\n\n"
        for i in range(n):
            for j in range(i+1, n):
                val = matrix[i][j]
                if abs(val) > 0.6:
                    nom_i = NOMS.get(syms[i], syms[i])
                    nom_j = NOMS.get(syms[j], syms[j])
                    emoji = "🔴" if val < 0 else "🟢"
                    msg_tg += f"{emoji} {nom_i} / {nom_j}: {val:+.2f}\n"
        msg_tg += f"\n📊 Diversification: {diversification}\n"
        msg_tg += f"📁 SVG sauvegarde: {svg_file}"
        send_telegram(msg_tg[:4000])
        return msg_tg
    
    elif type_viz in ["camembert", "pie", "repartition"]:
        # Camembert repartition
        if not positions:
            return "Aucune position"
        total = sum(float(p.get("montant_eur", 0)) for p in positions)
        msg = "🥧 REPARTITION PORTEFEUILLE\n" + "━" * 35 + "\n\n"
        for p in sorted(positions, key=lambda x: float(x.get("montant_eur", 0)), reverse=True):
            sym = p.get("symbole", "?")
            nom = NOMS.get(sym, sym)
            montant = float(p.get("montant_eur", 0))
            pct = montant / total * 100 if total > 0 else 0
            barre = "█" * int(pct / 2) + "░" * (25 - int(pct / 2))
            msg += f"{nom:<12} {barre} {pct:.1f}% ({montant:.0f}€)\n"
        msg += f"\nTotal investi: {total:.0f}€"
        send_telegram(msg[:4000])
        return msg
    
    elif type_viz in ["courbe", "evolution", "historique"]:
        # Courbe evolution capital
        hist = pt.get("historique", [])
        if not hist or len(hist) < 2:
            return "Pas assez d'historique"
        msg = "📈 EVOLUTION DU CAPITAL\n" + "━" * 35 + "\n\n"
        vals = []
        for h in hist:
            if isinstance(h, dict):
                for k in ("capital", "valeur", "total"):
                    if k in h:
                        try:
                            vals.append(float(h[k]))
                        except:
                            pass
                        break
            elif isinstance(h, (int, float)):
                vals.append(float(h))
        if len(vals) < 2:
            return "Pas assez de donnees"
        vmin, vmax = min(vals), max(vals)
        if vmax == vmin:
            vmax = vmin + 1
        # Graphique ASCII
        for i, v in enumerate(vals):
            hauteur = int((v - vmin) / (vmax - vmin) * 15)
            barre = "▁▂▃▄▅▆▇█"[min(hauteur, 7)] * 2
            msg += f"{barre} {v:.2f}€\n"
        msg += f"\nMin: {vmin:.2f}€ | Max: {vmax:.2f}€ | Actuel: {vals[-1]:.2f}€"
        send_telegram(msg[:4000])
        return msg
    
    return "Type de visualisation inconnu. Utilise: correlations, camembert, ou courbe"


# ============================================
# 40. SOUS-AGENTS PARALLELES (scan multi-crypto)
# ============================================
def sous_agents_scan(critere="toutes"):
    """Lance des analyses en parallele sur plusieurs cryptos (simule des sous-agents)."""
    from indicateurs import NOMS
    msg = "🤖 SOUS-AGENTS PARALLELES - Scan multi-crypto\n" + "━" * 40 + "\n\n"
    
    # Liste de cryptos a scanner
    if critere == "toutes":
        symboles = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ARBUSDT", "NEARUSDT"]
    else:
        symboles = [critere.upper() + "USDT"] if not critere.upper().endswith("USDT") else [critere.upper()]
    
    msg += f"🔍 Scan de {len(symboles)} cryptos en parallele...\n\n"
    
    resultats = []
    for sym in symboles:
        try:
            nom = NOMS.get(sym, sym)
            prix = get_crypto_price(sym.replace("USDT", ""))
            if not prix:
                continue
            
            # Analyse technique rapide
            from indicateurs import historique_ohlcv
            bougies = historique_ohlcv(sym, "1h", 50)
            if not bougies or len(bougies) < 20:
                continue
            
            clotures = [b["cloture"] for b in bougies]
            sma20 = sum(clotures[-20:]) / 20
            sma50 = sum(clotures[-50:]) / 50
            
            # RSI
            gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
            pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_perte = sum(pertes) / 14 if pertes else 0.001
            rsi = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))
            
            # Score
            score = 0
            signaux = []
            if prix > sma20 > sma50:
                score += 3
                signaux.append("tendance haussiere")
            elif prix > sma20:
                score += 1
                signaux.append("au-dessus SMA20")
            elif prix < sma20 < sma50:
                score -= 3
                signaux.append("tendance baissiere")
            else:
                score -= 1
                signaux.append("sous SMA20")
            
            if rsi < 35:
                score += 2
                signaux.append("RSI survente")
            elif rsi > 65:
                score -= 2
                signaux.append("RSI surachat")
            else:
                signaux.append(f"RSI {rsi:.0f}")
            
            # Verifier position ouverte
            pt = load_json_safe(os.path.join(DOSSIER, "paper_trading.json"), {})
            positions = pt.get("positions", [])
            pos_ouverte = any(p.get("symbole") == sym for p in positions)
            
            resultats.append({
                "sym": sym, "nom": nom, "prix": prix, "score": score,
                "rsi": rsi, "signaux": signaux, "pos_ouverte": pos_ouverte
            })
        except:
            continue
    
    # Trier par score
    resultats.sort(key=lambda x: x["score"], reverse=True)
    
    # Afficher resultats
    for r in resultats:
        emoji = "🟢" if r["score"] >= 3 else "🔴" if r["score"] <= -3 else "🟡"
        pos = "💼" if r["pos_ouverte"] else "  "
        msg += f"{emoji} {pos} {r['nom']:<12} {r['prix']:.4f}€  Score: {r['score']:+d}  RSI: {r['rsi']:.0f}\n"
        msg += f"   → {', '.join(r['signaux'][:3])}\n"
    
    # Synthese
    msg += "\n" + "━" * 40 + "\n"
    msg += "📊 SYNTHESE:\n"
    achats = [r for r in resultats if r["score"] >= 3]
    ventes = [r for r in resultats if r["score"] <= -3]
    neutres = [r for r in resultats if -2 <= r["score"] <= 2]
    msg += f"  🟢 Achats potentiels: {len(achats)} ({', '.join(r['nom'] for r in achats[:5])})\n"
    msg += f"  🔴 Ventes potentielles: {len(ventes)} ({', '.join(r['nom'] for r in ventes[:5])})\n"
    msg += f"  🟡 Neutres: {len(neutres)}\n"
    
    if achats:
        msg += f"\n💡 TOP OPPORTUNITE: {achats[0]['nom']} (score {achats[0]['score']:+d})\n"
        msg += f"   Prix: {achats[0]['prix']:.4f}€ | RSI: {achats[0]['rsi']:.0f}\n"
    
    learn_fact(f"Sous-agents scan: {len(resultats)} cryptos, {len(achats)} achats, {len(ventes)} ventes", "sous_agents")
    return msg


# ============================================
# 41. CONNECTEURS EXTERNES (webhooks, API)
# ============================================
def connecteur_externe(service="liste", action="status", params=""):
    """Connecte l'agent a des services externes via API."""
    connecteurs_file = os.path.join(DOSSIER, "connecteurs.json")
    connecteurs = load_json_safe(connecteurs_file, {"connecteurs": {}})
    
    if service == "liste" or service == "":
        msg = "🔌 CONNECTEURS EXTERNES\n" + "━" * 40 + "\n\n"
        if not connecteurs.get("connecteurs"):
            msg += "Aucun connecteur configure.\n\n"
        else:
            for nom, conf in connecteurs["connecteurs"].items():
                status = "✅ Actif" if conf.get("actif") else "❌ Inactif"
                msg += f"{status} {nom}: {conf.get('description', '?')}\n"
        
        msg += "\nConnecteurs disponibles:\n"
        msg += "  📧 email - Envoi d'emails via SMTP\n"
        msg += "  📅 calendar - Google Calendar API\n"
        msg += "  📝 notion - Notion API (notes/docs)\n"
        msg += "  💬 slack - Slack webhook (messages)\n"
        msg += "  📊 webhook - Webhook generique\n"
        msg += "  🐙 github - GitHub API (issues/PRs)\n"
        msg += "\nPour configurer: connecteur email config <smtp_host> <email> <password>"
        send_telegram(msg[:4000])
        return msg
    
    if service == "email" and action == "config":
        # Configuration email SMTP
        parts = params.split()
        if len(parts) < 3:
            return "Usage: connecteur email config <smtp_host> <email> <password>"
        connecteurs.setdefault("connecteurs", {})["email"] = {
            "smtp_host": parts[0],
            "email": parts[1],
            "password": parts[2],
            "actif": True,
            "description": f"Email via {parts[0]}"
        }
        save_json_safe(connecteurs_file, connecteurs)
        return f"✅ Connecteur email configure: {parts[1]} via {parts[0]}"
    
    if service == "email" and action == "send":
        # Envoi email
        conf = connecteurs.get("connecteurs", {}).get("email", {})
        if not conf.get("actif"):
            return "Connecteur email non configure. Utilise: connecteur email config <smtp> <email> <password>"
        parts = params.split(None, 2)
        if len(parts) < 3:
            return "Usage: connecteur email send <destinataire> <sujet> <message>"
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg_email = MIMEText(parts[2])
            msg_email['Subject'] = parts[1]
            msg_email['From'] = conf['email']
            msg_email['To'] = parts[0]
            with smtplib.SMTP(conf['smtp_host'], 587) as server:
                server.starttls()
                server.login(conf['email'], conf['password'])
                server.send_message(msg_email)
            return f"✅ Email envoye a {parts[0]}"
        except Exception as e:
            return f"❌ Erreur envoi email: {e}"
    
    if service == "webhook" and action == "config":
        # Configuration webhook generique
        if not params:
            return "Usage: connecteur webhook config <nom> <url>"
        parts = params.split(None, 1)
        if len(parts) < 2:
            return "Usage: connecteur webhook config <nom> <url>"
        connecteurs.setdefault("connecteurs", {})[f"webhook_{parts[0]}"] = {
            "url": parts[1],
            "actif": True,
            "description": f"Webhook {parts[0]}"
        }
        save_json_safe(connecteurs_file, connecteurs)
        return f"✅ Webhook {parts[0]} configure: {parts[1]}"
    
    if service == "webhook" and action == "send":
        # Envoi webhook
        parts = params.split(None, 1)
        if len(parts) < 2:
            return "Usage: connecteur webhook send <nom> <data_json>"
        conf = connecteurs.get("connecteurs", {}).get(f"webhook_{parts[0]}", {})
        if not conf.get("actif"):
            return f"Webhook {parts[0]} non configure"
        try:
            r = requests.post(conf["url"], json=json.loads(parts[1]), timeout=10)
            return f"✅ Webhook {parts[0]}: {r.status_code}"
        except Exception as e:
            return f"❌ Erreur webhook: {e}"
    
    if service == "slack" and action == "config":
        if not params:
            return "Usage: connecteur slack config <webhook_url>"
        connecteurs.setdefault("connecteurs", {})["slack"] = {
            "webhook_url": params,
            "actif": True,
            "description": "Slack webhook"
        }
        save_json_safe(connecteurs_file, connecteurs)
        return "✅ Slack configure"
    
    if service == "slack" and action == "send":
        conf = connecteurs.get("connecteurs", {}).get("slack", {})
        if not conf.get("actif"):
            return "Slack non configure. Utilise: connecteur slack config <webhook_url>"
        try:
            r = requests.post(conf["webhook_url"], json={"text": params}, timeout=10)
            return f"✅ Slack: message envoye ({r.status_code})"
        except Exception as e:
            return f"❌ Erreur Slack: {e}"
    
    return f"Commande inconnue. Utilise 'connecteur liste' pour voir les options"




# ============================================
# 42. MEMOIRE SEMANTIQUE (recherche par sens)
# ============================================
MEMOIRE_SEM_FILE = os.path.join(DOSSIER, "memoire_semantique.json")

def memoire_ajouter(categorie, contenu, tags=None):
    """Ajoute un element a la memoire semantique avec tags et timestamp."""
    memoire = load_json_safe(MEMOIRE_SEM_FILE, {"entrees": []})
    entree = {
        "id": len(memoire.get("entrees", [])) + 1,
        "categorie": categorie,  # trade, analyse, decision, erreur, apprentissage
        "contenu": contenu[:500],
        "tags": tags or [],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "poids": 1,  # augmente avec le temps si pertinent
    }
    memoire.setdefault("entrees", []).append(entree)
    # Garder max 500 entrees
    if len(memoire["entrees"]) > 500:
        memoire["entrees"] = memoire["entrees"][-500:]
    save_json_safe(MEMOIRE_SEM_FILE, memoire)
    return entree["id"]

def memoire_rechercher(requete, limite=10):
    """Recherche semantique dans la memoire - score par correspondance de mots et categories."""
    memoire = load_json_safe(MEMOIRE_SEM_FILE, {"entrees": []})
    entrees = memoire.get("entrees", [])
    if not entrees:
        return []
    
    # Decompose la requete en mots significatifs
    mots_requete = set(m.lower().strip(".,!?;:") for m in requete.split() if len(m) > 2)
    # Stop words basiques
    stop_words = {"les", "des", "une", "que", "pour", "dans", "sur", "avec", "mais", "sont", "est", "the", "and", "for", "with"}
    mots_requete -= stop_words
    
    resultats = []
    for e in entrees:
        score = 0
        contenu_words = set(e.get("contenu", "").lower().split())
        tags = set(t.lower() for t in e.get("tags", []))
        categorie = e.get("categorie", "").lower()
        
        # Score par mots correspondants dans le contenu
        mots_communs = mots_requete & contenu_words
        score += len(mots_communs) * 2
        
        # Score par tags correspondants
        tags_communs = mots_requete & tags
        score += len(tags_communs) * 3
        
        # Score par categorie correspondante
        for mot in mots_requete:
            if mot in categorie:
                score += 5
        
        # Bonus de recence (plus recent = plus pertinent)
        try:
            from datetime import datetime as dt
            date_e = dt.strptime(e.get("date", "2026-01-01"), "%Y-%m-%d %H:%M")
            age_jours = (datetime.now() - date_e).days
            score += max(0, 10 - age_jours)  # bonus si recent (< 10j)
        except:
            pass
        
        # Bonus de poids (si l'entree a ete utile avant)
        score += e.get("poids", 1)
        
        if score > 0:
            resultats.append((score, e))
    
    # Trier par score decroissant
    resultats.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in resultats[:limime]] if 'limite' in dir() else [e for _, e in resultats[:limite]]

def memoire_semantique_commande(action="recherche", requete=""):
    """Commande Telegram pour la memoire semantique."""
    if action in ["recherche", "cherche", "search", "rappel", "rapelle"]:
        if not requete:
            return "Usage: memoire cherche <mots-cles> - Recherche dans ta memoire"
        resultats = memoire_rechercher(requete, 5)
        if not resultats:
            return f"🔍 Aucun souvenir trouve pour '{requete}'"
        msg = f"🧠 MEMOIRE SEMANTIQUE - '{requete}'\n" + "━" * 35 + "\n\n"
        for i, e in enumerate(resultats):
            msg += f"📌 [{e.get('categorie', '?').upper()}] {e.get('date', '?')}\n"
            msg += f"   {e.get('contenu', '?')[:150]}\n"
            if e.get("tags"):
                msg += f"   Tags: {', '.join(e['tags'][:5])}\n"
            msg += "\n"
        return msg
    
    elif action in ["ajoute", "ajouter", "note", "retiens"]:
        tags = [m.strip(".,!?;:") for m in requete.split() if len(m) > 3][:5]
        mid = memoire_ajouter("note", requete, tags)
        return f"✅ Memoire #{mid} enregistree: '{requete[:60]}...'"
    
    elif action in ["stats", "statistiques"]:
        memoire = load_json_safe(MEMOIRE_SEM_FILE, {"entrees": []})
        entrees = memoire.get("entrees", [])
        if not entrees:
            return "Memoire vide"
        cats = {}
        for e in entrees:
            c = e.get("categorie", "?")
            cats[c] = cats.get(c, 0) + 1
        msg = "🧠 STATS MEMOIRE SEMANTIQUE\n" + "━" * 35 + "\n\n"
        msg += f"Total entrees: {len(entrees)}\n\n"
        for c, n in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            msg += f"  📂 {c}: {n}\n"
        return msg
    
    elif action in ["vide", "clear", "reset"]:
        save_json_safe(MEMOIRE_SEM_FILE, {"entrees": []})
        return "✅ Memoire semantique videe"
    
    return "Actions: cherche, ajoute, stats, vide"


# ============================================
# 43. MULTI-MODELES (Claude + GPT + Gemini + Perplexity)
# ============================================
def multi_modeles_analyse(symbole="BTCUSDT", question=""):
    """Consulte plusieurs modeles IA en parallele et synthetise."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1h", 100)
    if not bougies or len(bougies) < 50:
        return f"Pas assez de donnees pour {symbole}"
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    var_24h = (prix - clotures[-24]) / clotures[-24] * 100 if len(clotures) >= 24 else 0
    
    contexte = f"{nom} ({symbole}) | Prix: {prix:.4f} EUR | SMA20: {sma20:.4f} | SMA50: {sma50:.4f} | Var 24h: {var_24h:+.1f}%"
    question = question or f"Analyse {nom} et donne une recommandation (acheter/vendre/attendre) avec un score -10 a +10"
    
    msg = f"🌐 MULTI-MODELES - {nom}\n" + "━" * 40 + "\n\n"
    msg += f"📊 Contexte: {contexte}\n\n"
    
    reponses = {}
    
    # Modele 1: Perplexity (sonar)
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            payload = {"model": "sonar", "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}], "max_tokens": 200}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["Perplexity"] = r.json()["choices"][0]["message"]["content"]
                msg += f"🟣 PERPLEXITY (sonar):\n{reponses['Perplexity']}\n\n"
        except Exception as e:
            msg += f"🟣 PERPLEXITY: Erreur ({e})\n\n"
    
    # Modele 2: Gemini
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}]}]}
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                reponses["Gemini"] = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                msg += f"🔵 GEMINI (flash):\n{reponses['Gemini']}\n\n"
        except Exception as e:
            msg += f"🔵 GEMINI: Erreur ({e})\n\n"
    
    # Modele 3: OpenAI GPT (si cle disponible)
    OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "") or (load_env().get("OPENAI_API_KEY", "") if 'load_env' in dir() else "")
    if OPENAI_KEY:
        try:
            headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
            payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}], "max_tokens": 200}
            r = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["GPT"] = r.json()["choices"][0]["message"]["content"]
                msg += f"🟢 GPT (4o-mini):\n{reponses['GPT']}\n\n"
        except Exception as e:
            msg += f"🟢 GPT: Erreur ({e})\n\n"
    else:
        msg += "🟢 GPT: Cle API non configuree (OPENAI_API_KEY)\n\n"
    
    # Modele 4: Claude (si cle disponible)
    CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY", "") or (load_env().get("ANTHROPIC_API_KEY", "") if 'load_env' in dir() else "")
    if CLAUDE_KEY:
        try:
            headers = {"x-api-key": CLAUDE_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}
            payload = {"model": "claude-3-5-sonnet-20241022", "max_tokens": 200, "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}]}
            r = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["Claude"] = r.json()["content"][0]["text"]
                msg += f"🟠 CLAUDE (sonnet):\n{reponses['Claude']}\n\n"
        except Exception as e:
            msg += f"🟠 CLAUDE: Erreur ({e})\n\n"
    else:
        msg += "🟠 CLAUDE: Cle API non configuree (ANTHROPIC_API_KEY)\n\n"
    
    # Modele 5: DeepSeek
    _DEEPSEEK_KEY = DEEPSEEK_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
    if _DEEPSEEK_KEY:
        try:
            headers = {"Authorization": f"Bearer {_DEEPSEEK_KEY}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}], "max_tokens": 200}
            r = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["DeepSeek"] = r.json()["choices"][0]["message"]["content"]
                msg += f"🔴 DEEPSEEK (chat):\n{reponses['DeepSeek']}\n\n"
        except Exception as e:
            msg += f"🔴 DEEPSEEK: Erreur ({e})\n\n"
    else:
        msg += "🔴 DEEPSEEK: Cle API non configuree (DEEPSEEK_API_KEY)\n\n"
    
    # Modele 6: Grok (xAI)
    _GROK_KEY = GROK_KEY or os.environ.get("XAI_API_KEY", "")
    if _GROK_KEY:
        try:
            headers = {"Authorization": f"Bearer {_GROK_KEY}", "Content-Type": "application/json"}
            payload = {"model": "grok-beta", "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}], "max_tokens": 200}
            r = requests.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["Grok"] = r.json()["choices"][0]["message"]["content"]
                msg += f"⚫ GROK (xAI):\n{reponses['Grok']}\n\n"
        except Exception as e:
            msg += f"⚫ GROK: Erreur ({e})\n\n"
    else:
        msg += "⚫ GROK: Cle API non configuree (XAI_API_KEY)\n\n"
    
    # Modele 7: Mistral
    _MISTRAL_KEY = MISTRAL_KEY or os.environ.get("MISTRAL_API_KEY", "")
    if _MISTRAL_KEY:
        try:
            headers = {"Authorization": f"Bearer {_MISTRAL_KEY}", "Content-Type": "application/json"}
            payload = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": f"{question}\nContexte: {contexte}\nReponds en francais en 3 lignes max."}], "max_tokens": 200}
            r = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponses["Mistral"] = r.json()["choices"][0]["message"]["content"]
                msg += f"🟡 MISTRAL (small):\n{reponses['Mistral']}\n\n"
        except Exception as e:
            msg += f"🟡 MISTRAL: Erreur ({e})\n\n"
    else:
        msg += "🟡 MISTRAL: Cle API non configuree (MISTRAL_API_KEY)\n\n"
    
    # Synthese
    msg += "━" * 40 + "\n"
    msg += f"🔀 SYNTHESE ({len(reponses)} modeles):\n"
    
    import re
    scores = {}
    for nom_ia, rep in reponses.items():
        match = re.search(r'score[^\d]*([+-]?\d+)', rep, re.IGNORECASE)
        if match:
            scores[nom_ia] = int(match.group(1))
    
    if scores:
        score_moyen = sum(scores.values()) / len(scores)
        msg += f"  Score moyen: {score_moyen:+.1f}/10\n"
        for ia, s in scores.items():
            msg += f"  {ia}: {s:+d}/10\n"
        
        if all(s > 0 for s in scores.values()):
            msg += "\n🟢 CONSENSUS: Tous les modeles sont haussiers"
        elif all(s < 0 for s in scores.values()):
            msg += "\n🔴 CONSENSUS: Tous les modeles sont baissiers"
        else:
            msg += "\n🟡 DIVERGENCE: Les modeles ne sont pas d'accord"
    else:
        msg += "  Scores non extractibles - voir reponses ci-dessus"
    
    # Enregistrer en memoire semantique
    memoire_ajouter("analyse", f"Multi-modeles {symbole}: {len(reponses)} IA consultees, score moyen {score_moyen if scores else 'N/A'}", [symbole.replace("USDT",""), "multi_ia"])
    
    return msg


# ============================================
# 43b. CONSEIL MULTI-IA (7 IA croisees pour decision de trading)
# ============================================
def conseil_multi_ia(symbole="BTCUSDT"):
    """Interroge toutes les IA disponibles et donne un conseil consolide."""
    _COINGECKO_IDS = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
    }
    nom = symbole.replace("USDT", "")
    
    # Recuperer prix actuel via CoinGecko
    prix = 0
    var_24h = 0
    try:
        coin_id = _COINGECKO_IDS.get(symbole, nom.lower())
        import urllib.request
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=eur&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if coin_id in data:
            prix = data[coin_id]["eur"]
            var_24h = data[coin_id].get("eur_24h_change", 0)
    except:
        pass
    
    msg = f"🎯 CONSEIL MULTI-IA - {nom}\n" + "━" * 40 + "\n\n"
    msg += f"📊 Prix: {prix:.2f} EUR | Var 24h: {var_24h:+.1f}%\n\n"
    
    prompt = f"Tu es un analyste crypto expert. Analyse {nom} a {prix:.2f} EUR (var 24h: {var_24h:+.1f}%). Donne: 1) Score -10 a +10 (-10=vente extreme, +10=achat extreme) 2) Action (ACHETER/VENDRE/ATTENDRE) 3) Raison principale en 1 phrase. Reponds en francais en 3 lignes max."
    
    reponses = {}
    scores = {}
    actions = {}
    
    ia_emojis = {"Perplexity": "🟣", "Gemini": "🔵", "Claude": "🟠", "DeepSeek": "🔴", "Grok": "⚫", "Mistral": "🟡"}
    
    # Perplexity
    if PPLX_KEY:
        try:
            r = requests.post("https://api.perplexity.ai/chat/completions", json={"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}, headers={"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["choices"][0]["message"]["content"]; reponses["Perplexity"] = rep
                msg += f"🟣 PERPLEXITY:\n{rep}\n\n"
        except Exception as e: msg += f"🟣 PERPLEXITY: Erreur\n\n"
    
    # Gemini
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["candidates"][0]["content"]["parts"][0]["text"]; reponses["Gemini"] = rep
                msg += f"🔵 GEMINI:\n{rep}\n\n"
        except: msg += f"🔵 GEMINI: Erreur\n\n"
    
    # Claude
    if CLAUDE_KEY:
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]}, headers={"x-api-key": CLAUDE_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["content"][0]["text"]; reponses["Claude"] = rep
                msg += f"🟠 CLAUDE:\n{rep}\n\n"
        except: msg += f"🟠 CLAUDE: Erreur\n\n"
    
    # DeepSeek
    if DEEPSEEK_KEY:
        try:
            r = requests.post("https://api.deepseek.com/v1/chat/completions", json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}, headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["choices"][0]["message"]["content"]; reponses["DeepSeek"] = rep
                msg += f"🔴 DEEPSEEK:\n{rep}\n\n"
        except: msg += f"🔴 DEEPSEEK: Erreur\n\n"
    
    # Grok
    if GROK_KEY:
        try:
            r = requests.post("https://api.x.ai/v1/chat/completions", json={"model": "grok-beta", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}, headers={"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["choices"][0]["message"]["content"]; reponses["Grok"] = rep
                msg += f"⚫ GROK:\n{rep}\n\n"
        except: msg += f"⚫ GROK: Erreur\n\n"
    
    # Mistral
    if MISTRAL_KEY:
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions", json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}, headers={"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 200:
                rep = r.json()["choices"][0]["message"]["content"]; reponses["Mistral"] = rep
                msg += f"🟡 MISTRAL:\n{rep}\n\n"
        except: msg += f"🟡 MISTRAL: Erreur\n\n"
    
    # Synthese
    import re
    for ia_name, rep in reponses.items():
        match = re.search(r'score[^\d]*([+-]?\d+)', rep, re.IGNORECASE)
        if match: scores[ia_name] = int(match.group(1))
        if "ACHETER" in rep.upper() or "ACHAT" in rep.upper(): actions[ia_name] = "ACHETER"
        elif "VENDRE" in rep.upper() or "VENTE" in rep.upper(): actions[ia_name] = "VENDRE"
        else: actions[ia_name] = "ATTENDRE"
    
    msg += "━" * 40 + "\n"
    msg += f"🔀 CONSEIL CONSOLIDE ({len(reponses)} IA):\n\n"
    
    if scores:
        score_moyen = sum(scores.values()) / len(scores)
        msg += f"  Score moyen: {score_moyen:+.1f}/10\n"
        for ia, s in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            msg += f"    {ia_emojis.get(ia, '⚪')} {ia}: {s:+d}/10 ({actions.get(ia, '?')})\n"
        action_counts = {}
        for a in actions.values(): action_counts[a] = action_counts.get(a, 0) + 1
        vote = max(action_counts, key=action_counts.get) if action_counts else "ATTENDRE"
        msg += f"\n  Vote action: {vote} ({action_counts.get(vote, 0)}/{len(actions)})\n"
        if score_moyen > 3: msg += "  🟢 VERDICT: ACHETER - consensus haussier"
        elif score_moyen < -3: msg += "  🔴 VERDICT: VENDRE - consensus baissier"
        else: msg += "  🟡 VERDICT: ATTENDRE - pas de signal clair"
    else:
        msg += "  ⚠ Impossible d'extraire les scores"
    
    return msg

# ============================================
# 44. RECHERCHE ACADEMIQUE (papers de recherche)
# ============================================
def recherche_academique(sujet, limite=5):
    """Recherche des papers academiques via API gratuite (Crossref/OpenAlex)."""
    msg = f"📚 RECHERCHE ACADEMIQUE - '{sujet}'\n" + "━" * 40 + "\n\n"
    
    # API Crossref (gratuite, pas de cle)
    try:
        url = f"https://api.crossref.org/works?query={sujet}&rows={limite}&sort=relevance&order=desc"
        req = urllib.request.Request(url, headers={"User-Agent": "Agent-IA/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        
        items = data.get("message", {}).get("items", [])
        if not items:
            msg += "Aucun paper trouve.\n"
            return msg
        
        for i, item in enumerate(items[:limite]):
            titre = item.get("title", ["Sans titre"])[0] if item.get("title") else "Sans titre"
            auteurs = ", ".join([a.get("family", "") + " " + a.get("given", "") for a in item.get("author", [])[:3]])
            if len(item.get("author", [])) > 3:
                auteurs += " et al."
            date_pub = item.get("published-print", item.get("published-online", item.get("created", {})))
            annee = date_pub.get("date-parts", [["?"]])[0][0] if date_pub else "?"
            journal = item.get("container-title", ["?"])[0] if item.get("container-title") else "?"
            doi = item.get("DOI", "")
            citations = item.get("is-referenced-by-count", 0)
            resume = item.get("abstract", "")
            if resume:
                resume = resume.replace("<jats:p>", "").replace("</jats:p>", "").replace("<jats:italic>", "").replace("</jats:italic>", "")[:200]
            
            msg += f"📄 Paper #{i+1}:\n"
            msg += f"  Titre: {titre}\n"
            msg += f"  Auteurs: {auteurs}\n"
            msg += f"  Journal: {journal} ({annee})\n"
            msg += f"  Citations: {citations}\n"
            if resume:
                msg += f"  Resume: {resume}...\n"
            if doi:
                msg += f"  DOI: https://doi.org/{doi}\n"
            msg += "\n"
        
        msg += "━" * 40 + "\n"
        msg += f"Total: {len(items[:limite])} papers trouves via Crossref"
        
        # Enregistrer en memoire
        memoire_ajouter("recherche", f"Recherche academique '{sujet}': {len(items)} papers", [sujet, "academique"])
        
    except Exception as e:
        msg += f"Erreur Crossref: {e}\n"
        
        # Fallback: OpenAlex API (aussi gratuite)
        try:
            url = f"https://api.openalex.org/works?search={sujet}&per-page={limite}"
            req = urllib.request.Request(url, headers={"User-Agent": "Agent-IA/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            results = data.get("results", [])
            for i, w in enumerate(results[:limite]):
                titre = w.get("title", "Sans titre")
                annee = w.get("publication_year", "?")
                citations = w.get("cited_by_count", 0)
                doi = w.get("doi", "")
                concepts = [c.get("display_name", "") for c in w.get("concepts", [])[:3]]
                
                msg += f"📄 Paper #{i+1}:\n"
                msg += f"  Titre: {titre}\n"
                msg += f"  Annee: {annee} | Citations: {citations}\n"
                if concepts:
                    msg += f"  Concepts: {', '.join(concepts)}\n"
                if doi:
                    msg += f"  DOI: {doi}\n"
                msg += "\n"
            
            msg += f"Total: {len(results[:limite])} papers via OpenAlex"
        except Exception as e2:
            msg += f"Erreur OpenAlex: {e2}\n"
    
    return msg




# ============================================
# 45. BACKTESTING AVANCE (walk-forward + stats pro)
# ============================================
def backtest_avance(symbole="BTCUSDT", strategie="momentum", jours=90):
    """Backtest avance avec walk-forward testing et statistiques professionnelles."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    
    msg = f"🔬 BACKTEST AVANCE - {nom}\n"
    msg += f"Strategie: {strategie} | Periode: {jours} jours\n"
    msg += "━" * 40 + "\n\n"
    
    # Recuperer les donnees historiques (utiliser historique_ohlcv_long pour plus de donnees)
    try:
        from indicateurs import historique_ohlcv_long
        bougies = historique_ohlcv_long(symbole, "1d", min(jours, 365))
    except ImportError:
        bougies = historique_ohlcv(symbole, "1d", jours)
    if not bougies or len(bougies) < 30:
        # Fallback: essayer 1h et agreger en journalier
        bougies = historique_ohlcv(symbole, "1h", 200)
        if not bougies or len(bougies) < 30:
            return f"Pas assez de donnees pour {symbole} ({jours}j). Obtenu: {len(bougies) if bougies else 0} bougies."
        # Agreger en journalier si on a des donnees 1h
        if len(bougies) > 30:
            bougies_agg = []
            for i in range(0, len(bougies), 24):
                chunk = bougies[i:i+24]
                if chunk:
                    bougies_agg.append({
                        "ouverture": chunk[0]["ouverture"],
                        "haut": max(b["haut"] for b in chunk),
                        "bas": min(b["bas"] for b in chunk),
                        "cloture": chunk[-1]["cloture"],
                        "volume": sum(b.get("volume", 0) for b in chunk)
                    })
            bougies = bougies_agg
    
    # Split walk-forward: 70% training, 30% validation
    total = len(bougies)
    split = int(total * 0.7)
    train_data = bougies[:split]
    test_data = bougies[split:]
    
    # Simuler les trades sur la periode de training
    trades_train = []
    position = None
    capital = 100.0  # capital virtuel en EUR
    
    for i in range(20, len(train_data)):
        clotures = [b["cloture"] for b in train_data[:i+1]]
        prix = clotures[-1]
        
        # Signaux selon la strategie
        sma20 = sum(clotures[-20:]) / 20 if len(clotures) >= 20 else prix
        sma50 = sum(clotures[-50:]) / 50 if len(clotures) >= 50 else sma20
        
        # RSI
        gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if j >= -len(clotures) and clotures[j] > clotures[j-1]]
        pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if j >= -len(clotures) and clotures[j] < clotures[j-1]]
        avg_gain = sum(gains) / 14 if gains else 0
        avg_perte = sum(pertes) / 14 if pertes else 0.001
        rsi = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))
        
        signal = 0  # 1=achat, -1=vente, 0=rien
        
        if strategie == "momentum":
            # Momentum assoupli: SMA20 > SMA50 OU prix > SMA20 avec RSI < 70
            if (sma20 > sma50 or prix > sma20) and rsi < 70 and rsi > 30:
                signal = 1
            elif (prix < sma20 or rsi > 70):
                signal = -1
        
        elif strategie == "mean_reversion":
            if rsi < 30:
                signal = 1
            elif rsi > 70:
                signal = -1
        
        elif strategie == "breakout":
            hauts = [b["haut"] for b in train_data[:i+1]]
            bas = [b["bas"] for b in train_data[:i+1]]
            if len(hauts) >= 20:
                haut_20 = max(hauts[-20:])
                bas_20 = min(bas[-20:])
                if prix > haut_20 * 0.99:
                    signal = 1
                elif prix < bas_20 * 1.01:
                    signal = -1
        
        elif strategie == "rsi_extreme":
            if rsi < 25:
                signal = 1
            elif rsi > 75:
                signal = -1
        
        elif strategie == "macd":
            ema12 = sum(clotures[-12:]) / 12 if len(clotures) >= 12 else prix
            ema26 = sum(clotures[-26:]) / 26 if len(clotures) >= 26 else prix
            macd = ema12 - ema26
            signal_ema = sum([clotures[-9:][j] - clotures[-9:][j-1] for j in range(1, min(9, len(clotures)))]) / 9 if len(clotures) >= 9 else 0
            if macd > 0 and rsi < 65:
                signal = 1
            elif macd < 0 and rsi > 35:
                signal = -1
        
        # Executer le trade
        if signal == 1 and position is None:
            position = {"prix": prix, "date": train_data[i].get("date", f"J{i}")}
        elif signal == -1 and position is not None:
            pnl_pct = (prix - position["prix"]) / position["prix"] * 100
            # Frais 0.1%
            pnl_pct -= 0.2
            capital *= (1 + pnl_pct / 100)
            trades_train.append({
                "entree": position["prix"], "sortie": prix,
                "pnl_pct": pnl_pct, "date_e": position["date"],
                "date_s": train_data[i].get("date", f"J{i}")
            })
            position = None
    
    # Fermer position ouverte a la fin
    if position is not None:
        prix_final = train_data[-1]["cloture"]
        pnl_pct = (prix_final - position["prix"]) / position["prix"] * 100 - 0.2
        capital *= (1 + pnl_pct / 100)
        trades_train.append({
            "entree": position["prix"], "sortie": prix_final,
            "pnl_pct": pnl_pct, "date_e": position["date"],
            "date_s": "fin"
        })
    
    # Simuler sur la periode de validation (test)
    trades_test = []
    position = None
    capital_test = 100.0
    
    for i in range(20, len(test_data)):
        clotures = [b["cloture"] for b in test_data[:i+1]]
        prix = clotures[-1]
        
        sma20 = sum(clotures[-20:]) / 20 if len(clotures) >= 20 else prix
        sma50 = sum(clotures[-50:]) / 50 if len(clotures) >= 50 else sma20
        
        gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if j >= -len(clotures) and clotures[j] > clotures[j-1]]
        pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if j >= -len(clotures) and clotures[j] < clotures[j-1]]
        avg_gain = sum(gains) / 14 if gains else 0
        avg_perte = sum(pertes) / 14 if pertes else 0.001
        rsi = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))
        
        signal = 0
        if strategie == "momentum":
            if (sma20 > sma50 or prix > sma20) and rsi < 70 and rsi > 30: signal = 1
            elif (prix < sma20 or rsi > 70): signal = -1
        elif strategie == "mean_reversion":
            if rsi < 30: signal = 1
            elif rsi > 70: signal = -1
        elif strategie == "breakout":
            hauts = [b["haut"] for b in test_data[:i+1]]
            bas = [b["bas"] for b in test_data[:i+1]]
            if len(hauts) >= 20:
                if prix > max(hauts[-20:]) * 0.99: signal = 1
                elif prix < min(bas[-20:]) * 1.01: signal = -1
        elif strategie == "rsi_extreme":
            if rsi < 25: signal = 1
            elif rsi > 75: signal = -1
        elif strategie == "macd":
            ema12 = sum(clotures[-12:]) / 12 if len(clotures) >= 12 else prix
            ema26 = sum(clotures[-26:]) / 26 if len(clotures) >= 26 else prix
            macd = ema12 - ema26
            if macd > 0 and rsi < 65: signal = 1
            elif macd < 0 and rsi > 35: signal = -1
        
        if signal == 1 and position is None:
            position = {"prix": prix, "date": test_data[i].get("date", f"J{i}")}
        elif signal == -1 and position is not None:
            pnl_pct = (prix - position["prix"]) / position["prix"] * 100 - 0.2
            capital_test *= (1 + pnl_pct / 100)
            trades_test.append({"entree": position["prix"], "sortie": prix, "pnl_pct": pnl_pct})
            position = None
    
    if position is not None:
        prix_final = test_data[-1]["cloture"]
        pnl_pct = (prix_final - position["prix"]) / position["prix"] * 100 - 0.2
        capital_test *= (1 + pnl_pct / 100)
        trades_test.append({"entree": position["prix"], "sortie": prix_final, "pnl_pct": pnl_pct})
    
    # Calculer statistiques
    def calc_stats(trades, cap_initial=100.0):
        if not trades:
            return {"n": 0, "winrate": 0, "profit_factor": 0, "roi": 0, "max_dd": 0, "avg_win": 0, "avg_loss": 0, "sharpe": 0, "best": 0, "worst": 0}
        
        n = len(trades)
        gains = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
        pertes = [t["pnl_pct"] for t in trades if t["pnl_pct"] < 0]
        n_g = len(gains)
        n_p = len(pertes)
        winrate = n_g / n * 100 if n > 0 else 0
        sum_gains = sum(gains) if gains else 0
        sum_pertes = abs(sum(pertes)) if pertes else 0.001
        profit_factor = sum_gains / sum_pertes if sum_pertes > 0 else 0
        roi = cap_initial - 100  # calcule plus bas
        
        # Max drawdown
        cap = 100.0
        pic = 100.0
        max_dd = 0
        for t in trades:
            cap *= (1 + t["pnl_pct"] / 100)
            if cap > pic: pic = cap
            dd = (cap - pic) / pic * 100
            if dd < max_dd: max_dd = dd
        
        roi = cap - 100
        avg_win = sum(gains) / n_g if n_g > 0 else 0
        avg_loss = sum(pertes) / n_p if n_p > 0 else 0
        best = max(gains) if gains else 0
        worst = min(pertes) if pertes else 0
        
        # Sharpe ratio (simplifie)
        import statistics
        all_pnl = [t["pnl_pct"] for t in trades]
        if len(all_pnl) > 1:
            std = statistics.stdev(all_pnl)
            sharpe = (sum(all_pnl) / len(all_pnl)) / std if std > 0 else 0
        else:
            sharpe = 0
        
        return {"n": n, "winrate": winrate, "profit_factor": profit_factor, "roi": roi, "max_dd": max_dd, "avg_win": avg_win, "avg_loss": avg_loss, "sharpe": sharpe, "best": best, "worst": worst, "n_g": n_g, "n_p": n_p}
    
    stats_train = calc_stats(trades_train)
    stats_test = calc_stats(trades_test)
    
    # Affichage
    msg += "📊 PERIODE D'ENTRAINEMENT (70%):\n"
    msg += f"  Trades: {stats_train['n']} ({stats_train.get('n_g',0)}G / {stats_train.get('n_p',0)}P)\n"
    msg += f"  Winrate: {stats_train['winrate']:.1f}%\n"
    msg += f"  Profit factor: {stats_train['profit_factor']:.2f}\n"
    msg += f"  ROI: {stats_train['roi']:+.2f}%\n"
    msg += f"  Max drawdown: {stats_train['max_dd']:.1f}%\n"
    msg += f"  Sharpe ratio: {stats_train['sharpe']:.2f}\n"
    msg += f"  Meilleur trade: {stats_train['best']:+.2f}%\n"
    msg += f"  Pire trade: {stats_train['worst']:+.2f}%\n"
    msg += f"  Gain moyen: {stats_train['avg_win']:+.2f}%\n"
    msg += f"  Perte moyenne: {stats_train['avg_loss']:+.2f}%\n\n"
    
    msg += "📊 PERIODE DE VALIDATION (30%):\n"
    msg += f"  Trades: {stats_test['n']} ({stats_test.get('n_g',0)}G / {stats_test.get('n_p',0)}P)\n"
    msg += f"  Winrate: {stats_test['winrate']:.1f}%\n"
    msg += f"  Profit factor: {stats_test['profit_factor']:.2f}\n"
    msg += f"  ROI: {stats_test['roi']:+.2f}%\n"
    msg += f"  Max drawdown: {stats_test['max_dd']:.1f}%\n"
    msg += f"  Sharpe ratio: {stats_test['sharpe']:.2f}\n\n"
    
    # Verdict walk-forward
    msg += "━" * 40 + "\n"
    msg += "🔍 ANALYSE WALK-FORWARD:\n"
    
    if stats_train['n'] == 0 or stats_test['n'] == 0:
        msg += "  ⚠️ Pas assez de trades pour conclure\n"
    else:
        # Comparaison train vs test
        ecart_winrate = abs(stats_train['winrate'] - stats_test['winrate'])
        ecart_roi = abs(stats_train['roi'] - stats_test['roi'])
        
        if ecart_winrate < 15 and ecart_roi < 20:
            msg += "  ✅ STRATEGIE ROBUSTE - Performance stable entre train et test\n"
            msg += f"     Ecart winrate: {ecart_winrate:.1f}% (stable)\n"
            msg += f"     Ecart ROI: {ecart_roi:.1f}% (stable)\n"
        elif ecart_winrate < 25:
            msg += "  🟡 STRATEGIE MOYENNE - Performance degradée en validation\n"
            msg += f"     Ecart winrate: {ecart_winrate:.1f}%\n"
            msg += f"     Ecart ROI: {ecart_roi:.1f}%\n"
        else:
            msg += "  🔴 STRATEGIE NON ROBUSTE - Surapprentissage detecté\n"
            msg += f"     Ecart winrate: {ecart_winrate:.1f}% (trop grand)\n"
            msg += f"     Ecart ROI: {ecart_roi:.1f}% (trop grand)\n"
            msg += "     → La strategie ne generalise pas bien\n"
    
    # Recommandation
    msg += "\n💡 RECOMMANDATION:\n"
    if stats_train['winrate'] > 55 and stats_train['profit_factor'] > 1.3 and stats_test['winrate'] > 45:
        msg += "  🟢 Strategie VALIDEE - peut etre deployee en live\n"
    elif stats_train['winrate'] > 45:
        msg += "  🟡 Strategie MOYENNE - a optimiser avant deployment\n"
    else:
        msg += "  🔴 Strategie FAIBLE - a revoir ou abandonner\n"
    
    # Comparer toutes les strategies
    msg += "\n" + "━" * 40 + "\n"
    msg += "📋 COMPARAISON STRATEGIES (quick scan):\n"
    
    strategies = ["momentum", "mean_reversion", "breakout", "rsi_extreme", "macd"]
    resultats = []
    for strat in strategies:
        # Quick backtest sur training
        trades_s = []
        pos = None
        for i in range(20, len(train_data)):
            cl = [b["cloture"] for b in train_data[:i+1]]
            p = cl[-1]
            sma20 = sum(cl[-20:]) / 20 if len(cl) >= 20 else p
            sma50 = sum(cl[-50:]) / 50 if len(cl) >= 50 else sma20
            g = [cl[j] - cl[j-1] for j in range(-14, 0) if j >= -len(cl) and (j-1) >= -len(cl) and cl[j] > cl[j-1]]
            pe = [cl[j-1] - cl[j] for j in range(-14, 0) if j >= -len(cl) and (j-1) >= -len(cl) and cl[j] < cl[j-1]]
            ag = sum(g) / 14 if g else 0
            ap = sum(pe) / 14 if pe else 0.001
            r = 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
            sig = 0
            if strat == "momentum":
                if (sma20 > sma50 or p > sma20) and r < 70 and r > 30: sig = 1
                elif (p < sma20 or r > 70): sig = -1
            elif strat == "mean_reversion":
                if r < 30: sig = 1
                elif r > 70: sig = -1
            elif strat == "breakout":
                hs = [b["haut"] for b in train_data[:i+1]]
                bs = [b["bas"] for b in train_data[:i+1]]
                if len(hs) >= 20:
                    if p > max(hs[-20:]) * 0.99: sig = 1
                    elif p < min(bs[-20:]) * 1.01: sig = -1
            elif strat == "rsi_extreme":
                if r < 25: sig = 1
                elif r > 75: sig = -1
            elif strat == "macd":
                e12 = sum(cl[-12:]) / 12 if len(cl) >= 12 else p
                e26 = sum(cl[-26:]) / 26 if len(cl) >= 26 else p
                m = e12 - e26
                if m > 0 and r < 65: sig = 1
                elif m < 0 and r > 35: sig = -1
            if sig == 1 and pos is None:
                pos = p
            elif sig == -1 and pos is not None:
                pnl = (p - pos) / pos * 100 - 0.2
                trades_s.append(pnl)
                pos = None
        if pos is not None:
            pnl = (train_data[-1]["cloture"] - pos) / pos * 100 - 0.2
            trades_s.append(pnl)
        
        if trades_s:
            n_s = len(trades_s)
            wr = len([t for t in trades_s if t > 0]) / n_s * 100
            roi_s = 1
            for t in trades_s:
                roi_s *= (1 + t / 100)
            roi_s = (roi_s - 1) * 100
            resultats.append((strat, n_s, wr, roi_s))
    
    resultats.sort(key=lambda x: x[3], reverse=True)
    for strat, n_s, wr, roi_s in resultats:
        emoji = "🟢" if roi_s > 5 else "🟡" if roi_s > 0 else "🔴"
        msg += f"  {emoji} {strat:<16} {n_s:>3} trades  WR:{wr:>5.1f}%  ROI:{roi_s:>+7.1f}%\n"
    
    # Enregistrer en memoire
    memoire_ajouter("backtest", f"Backtest {symbole} {strategie} {jours}j: WR={stats_train['winrate']:.0f}% PF={stats_train['profit_factor']:.1f} ROI={stats_train['roi']:+.1f}% Sharpe={stats_train['sharpe']:.2f}", [symbole.replace("USDT",""), strategie, "backtest"])
    
    return msg




# ============================================
# 46. AUTO-AJUSTEMENT DES STRATEGIES
# ============================================
def auto_ajuster_strategies():
    """Analyse les backtests et ajuste automatiquement les poids des strategies par crypto."""
    try:
        from indicateurs import NOMS
    except Exception:
        NOMS = {}
    
    # Fichier de configuration des strategies
    strat_file = os.path.join(DOSSIER, "poids_strategies.json")
    poids = load_json_safe(strat_file, {"strategies": {}})
    
    msg = "🧠 AUTO-AJUSTEMENT DES STRATEGIES\n" + "━" * 40 + "\n\n"
    
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT"]
    strategies = ["momentum", "mean_reversion", "breakout", "rsi_extreme", "macd"]
    
    print("[AUTO-AJUSTER] Debut de la fonction")
    ajustements = 0
    for sym in cryptos:
      try:
        print(f"[AUTO-AJUSTER] Debut {sym}...")
        nom = NOMS.get(sym, sym)
        msg += f"📊 {nom}:\n"
        
        # Quick backtest pour chaque strategie
        resultats = {}
        trades_par_strat = {}  # Stocker les trades pour walk-forward
        # Recuperer les donnees historiques une seule fois par crypto
        # Appel direct CoinGecko (market_chart - donnees quotidiennes 90j)
        bougies = []
        # Mapping direct symbole -> CoinGecko coin_id
        _COINGECKO_IDS = {
            "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
            "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2",
            "LINKUSDT": "chainlink", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
            "ARBUSDT": "arbitrum", "NEARUSDT": "near", "FETUSDT": "fetch-ai",
            "RNDRUSDT": "render-token", "LDOUSDT": "lido-dao", "AAVEUSDT": "aave",
            "PENDLEUSDT": "pendle", "INJUSDT": "injective-protocol",
            "SUIUSDT": "sui", "APTUSDT": "aptos",
        }
        coin_id = _COINGECKO_IDS.get(sym, sym.replace("USDT", "").lower())
        try:
            import urllib.request
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=eur&days=90&interval=daily"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            prices = data.get("prices", [])
            bougies = [{"temps": int(p[0]), "ouverture": p[1], "haut": p[1],
                       "bas": p[1], "cloture": p[1], "volume": 0} for p in prices]
        except Exception:
            pass
        time.sleep(3)  # Anti rate-limit CoinGecko
        if not bougies or len(bougies) < 30:
            msg += "  ⚠ Donnees insuffisantes\n\n"
            print(f"[AUTO-AJUSTER] {sym}: donnees insuffisantes ({len(bougies) if bougies else 0} bougies)")
            continue
        print(f"[AUTO-AJUSTER] {sym}: {len(bougies)} bougies recuperees")
        # Pre-calculer les donnees une seule fois (optimisation)
        clotures_all = [b["cloture"] for b in bougies]
        hauts_all = [b["haut"] for b in bougies]
        bas_all = [b["bas"] for b in bougies]
        # Pre-calculer RSI, SMA20, SMA50, EMA12, EMA26 pour chaque jour
        indicateurs_jour = []
        for i in range(len(clotures_all)):
            cl = clotures_all[:i+1]
            p = cl[-1]
            sma20 = sum(cl[-20:]) / 20 if len(cl) >= 20 else p
            sma50 = sum(cl[-50:]) / 50 if len(cl) >= 50 else sma20
            g = [cl[j] - cl[j-1] for j in range(-14, 0) if j >= -len(cl) and (j-1) >= -len(cl) and cl[j] > cl[j-1]]
            pe = [cl[j-1] - cl[j] for j in range(-14, 0) if j >= -len(cl) and (j-1) >= -len(cl) and cl[j] < cl[j-1]]
            ag = sum(g) / 14 if g else 0
            ap = sum(pe) / 14 if pe else 0.001
            rsi = 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
            e12 = sum(cl[-12:]) / 12 if len(cl) >= 12 else p
            e26 = sum(cl[-26:]) / 26 if len(cl) >= 26 else p
            macd_val = e12 - e26
            indicateurs_jour.append({"p": p, "sma20": sma20, "sma50": sma50, "rsi": rsi, "macd": macd_val})
        
        for strat in strategies:
            # Simuler la strategie
            trades = []
            pos = None
            for i in range(20, len(bougies)):
                ind = indicateurs_jour[i]
                p = ind["p"]
                sma20 = ind["sma20"]
                sma50 = ind["sma50"]
                r = ind["rsi"]
                m = ind["macd"]
                sig = 0
                if strat == "momentum":
                    if (sma20 > sma50 or p > sma20) and r < 70 and r > 30: sig = 1
                    elif (p < sma20 or r > 70): sig = -1
                elif strat == "mean_reversion":
                    if r < 30: sig = 1
                    elif r > 70: sig = -1
                elif strat == "breakout":
                    if i >= 20:
                        if p > max(hauts_all[i-20:i]) * 0.99: sig = 1
                        elif p < min(bas_all[i-20:i]) * 1.01: sig = -1
                elif strat == "rsi_extreme":
                    if r < 25: sig = 1
                    elif r > 75: sig = -1
                elif strat == "macd":
                    if m > 0 and r < 65: sig = 1
                    elif m < 0 and r > 35: sig = -1
                if sig == 1 and pos is None:
                    pos = p
                elif sig == -1 and pos is not None:
                    pnl = (p - pos) / pos * 100 - 0.2
                    trades.append(pnl)
                    pos = None
            if pos is not None:
                pnl = (bougies[-1]["cloture"] - pos) / pos * 100 - 0.2
                trades.append(pnl)
            
            if trades:
                wr = len([t for t in trades if t > 0]) / len(trades) * 100
                roi = 1
                for t in trades:
                    roi *= (1 + t / 100)
                roi = (roi - 1) * 100
                resultats[strat] = {"wr": wr, "roi": roi, "n": len(trades)}
                trades_par_strat[strat] = list(trades)  # Garder pour walk-forward
        
        # Calculer les poids avec protection anti-surapprentissage
        if resultats:
            # Parametres anti-surapprentissage
            MIN_TRADES = 3          # Minimum de trades pour ajuster
            MAX_POIDS = 0.70        # Plafond (garde diversification)
            MIN_POIDS = 0.05        # Plancher (garde diversification)
            MAX_DELTA = 0.30        # Changement max par ajustement
            
            total_roi = sum(max(r["roi"], 0) for r in resultats.values()) or 1
            for strat in strategies:
                if strat in resultats:
                    r = resultats[strat]
                    ancien_poids = poids.get("strategies", {}).get(f"{sym}_{strat}", 0.20)
                    
                    # PROTECTION 1: Minimum de trades
                    if r["n"] < MIN_TRADES:
                        nouveau_poids = ancien_poids  # Garder l'ancien poids
                        msg += f"  ⚪ {strat:<16} {ancien_poids:.2f} (WR:{r['wr']:.0f}% ROI:{r['roi']:+.1f}% | {r['n']} trades < {MIN_TRADES} min)\n"
                        poids.setdefault("strategies", {})[f"{sym}_{strat}"] = nouveau_poids
                        continue
                    
                    # PROTECTION 2: Walk-forward (split 70/30 des trades)
                    # Utiliser les trades deja calcules (pas de recalcul)
                    trades_strat = trades_par_strat.get(strat, [])
                    
                    # Split walk-forward
                    split_t = int(len(trades_strat) * 0.7) if len(trades_strat) >= 4 else len(trades_strat)
                    train_trades = trades_strat[:split_t]
                    test_trades = trades_strat[split_t:]
                    
                    train_roi = 1
                    for t in train_trades:
                        train_roi *= (1 + t / 100)
                    train_roi = (train_roi - 1) * 100
                    
                    test_roi = 1
                    for t in test_trades:
                        test_roi *= (1 + t / 100)
                    test_roi = (test_roi - 1) * 100 if test_trades else 0
                    
                    # PROTECTION 3: Consistance train/test
                    consistent = (train_roi > 0 and test_roi >= 0) or (train_roi > 0 and not test_trades)
                    
                    # PROTECTION 4: Facteur de confiance (plus de trades = plus de confiance)
                    confiance = min(r["n"] / 10, 1.0)  # 1.0 a 10+ trades
                    
                    # Calcul du poids cible
                    if r["roi"] < 0:
                        poids_cible = MIN_POIDS
                    else:
                        poids_cible = max(r["roi"], 0) / total_roi if total_roi > 0 else 0
                        poids_cible = min(poids_cible, MAX_POIDS)
                        # Penaliser si non consistent
                        if not consistent:
                            poids_cible *= 0.5
                        # Bonus si winrate > 55%
                        if r["wr"] > 55:
                            poids_cible = min(poids_cible * 1.15, MAX_POIDS)
                        # Appliquer facteur de confiance
                        poids_cible = MIN_POIDS + (poids_cible - MIN_POIDS) * confiance
                        poids_cible = max(MIN_POIDS, min(poids_cible, MAX_POIDS))
                    
                    # PROTECTION 5: Changement progressif (max MAX_DELTA par ajustement)
                    delta = poids_cible - ancien_poids
                    delta = max(-MAX_DELTA, min(MAX_DELTA, delta))
                    nouveau_poids = round(ancien_poids + delta, 2)
                    nouveau_poids = max(MIN_POIDS, min(nouveau_poids, MAX_POIDS))
                    
                    if abs(ancien_poids - nouveau_poids) > 0.02:
                        ajustements += 1
                        emoji = "🟢" if nouveau_poids > ancien_poids else "🔴"
                        consistance_emoji = "✓" if consistent else "⚠"
                        msg += f"  {emoji} {strat:<16} {ancien_poids:.2f} → {nouveau_poids:.2f} (WR:{r['wr']:.0f}% ROI:{r['roi']:+.1f}% {r['n']}t {consistance_emoji})\n"
                    else:
                        msg += f"  ⚪ {strat:<16} {nouveau_poids:.2f} (WR:{r['wr']:.0f}% ROI:{r['roi']:+.1f}% {r['n']}t)\n"
                    
                    poids.setdefault("strategies", {})[f"{sym}_{strat}"] = nouveau_poids
                else:
                    msg += f"  ⚪ {strat:<16} 0.05 (pas de donnees)\n"
        msg += "\n"
        print(f"[AUTO-AJUSTER] {sym} termine")
      except Exception as _e:
        import traceback
        msg += f"  ❌ Erreur {sym}: {_e}\n\n"
        print(f"[AUTO-AJUSTER] Erreur {sym}: {traceback.format_exc()}")
    
    # Sauvegarder
    poids["dernier_ajustement"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json_safe(strat_file, poids)
    
    print("[AUTO-AJUSTER] Fonction terminee, envoi du resultat")
    msg += "━" * 40 + "\n"
    msg += f"📁 Poids sauvegardes dans poids_strategies.json\n"
    msg += "\n💡 Protections anti-surapprentissage:\n"
    msg += "  • Min 3 trades pour ajuster | Plafond 0.70 | Plancher 0.05\n"
    msg += "  • Walk-forward 70/30 | Changement max ±0.30 par ajustement\n"
    msg += "  • Facteur de confiance selon nb de trades\n"
    msg += "  ✓ = strategie consistante (train+test positifs) | ⚠ = surapprentissage suspecte"
    
    try:
        memoire_ajouter("ajustement", f"Auto-ajustement: {ajustements} strategies modifiees sur {len(cryptos)} cryptos", ["strategies", "auto_ajustement"])
    except:
        pass
    
    return msg


# ============================================
# 47. DETECTION DIVERGENCES + PATTERNS CHARTISTES
# ============================================
def detecter_divergences(symbole="BTCUSDT"):
    """Detecte les divergences (prix vs RSI) et les patterns chartistes."""
    from indicateurs import historique_ohlcv, NOMS
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1d", 50)
    if not bougies or len(bougies) < 30:
        return f"Pas assez de donnees pour {symbole}"
    
    msg = f"🔍 ANALYSE TECHNIQUE - {nom}\n" + "━" * 40 + "\n\n"
    
    clotures = [b["cloture"] for b in bougies]
    hauts = [b["haut"] for b in bougies]
    bas = [b["bas"] for b in bougies]
    prix = clotures[-1]
    
    # RSI sur 14 periodes
    def calc_rsi(cl, periode=14):
        if len(cl) < periode:
            return 50
        gains = [cl[j] - cl[j-1] for j in range(-periode, 0) if cl[j] > cl[j-1]]
        pertes = [cl[j-1] - cl[j] for j in range(-periode, 0) if cl[j] < cl[j-1]]
        ag = sum(gains) / periode if gains else 0
        ap = sum(pertes) / periode if pertes else 0.001
        return 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
    
    # === DIVERGENCES ===
    msg += "📉 DIVERGENCES:\n"
    
    # Divergence haussiere: prix fait un plus bas, RSI fait un plus haut
    # Divergence baissiere: prix fait un plus haut, RSI fait un plus bas
    lookback = 20
    if len(clotures) >= lookback:
        prix_recents = clotures[-lookback:]
        rsi_recents = [calc_rsi(clotures[:-(lookback-i)]) for i in range(lookback)]
        
        # Trouver les extremes
        prix_min_idx = prix_recents.index(min(prix_recents))
        prix_max_idx = prix_recents.index(max(prix_recents))
        
        # Divergence haussiere (prix bas + RSI haut)
        if prix_recents[prix_min_idx] < prix_recents[0] * 0.98:  # prix a baisse
            rsi_at_min = rsi_recents[prix_min_idx] if prix_min_idx < len(rsi_recents) else 50
            rsi_now = calc_rsi(clotures)
            if rsi_now > rsi_at_min + 5:
                msg += "  🟢 DIVERGENCE HAUSSIERE detectee!\n"
                msg += f"     Prix: plus bas il y a {lookback - prix_min_idx}j, RSI remonte\n"
                msg += "     → Signal d'achat potentiel (retournement haussier)\n"
            else:
                msg += "  ⚪ Aucune divergence haussiere\n"
        else:
            msg += "  ⚪ Pas de divergence haussiere (prix stable)\n"
        
        # Divergence baissiere (prix haut + RSI bas)
        if prix_recents[prix_max_idx] > prix_recents[0] * 1.02:  # prix a monte
            rsi_at_max = rsi_recents[prix_max_idx] if prix_max_idx < len(rsi_recents) else 50
            rsi_now = calc_rsi(clotures)
            if rsi_now < rsi_at_max - 5:
                msg += "  🔴 DIVERGENCE BAISSIERE detectee!\n"
                msg += f"     Prix: plus haut il y a {lookback - prix_max_idx}j, RSI descend\n"
                msg += "     → Signal de vente potentiel (retournement baissier)\n"
            else:
                msg += "  ⚪ Aucune divergence baissiere\n"
        else:
            msg += "  ⚪ Pas de divergence baissiere (prix stable)\n"
    
    # === PATTERNS CHARTISTES ===
    msg += "\n🎨 PATTERNS CHARTISTES:\n"
    
    if len(bougies) >= 10:
        # Double top (deux pics consecutifs proches)
        pics = []
        for i in range(2, len(hauts) - 2):
            if hauts[i] > hauts[i-1] and hauts[i] > hauts[i+1] and hauts[i] > hauts[i-2] and hauts[i] > hauts[i+2]:
                pics.append((i, hauts[i]))
        
        if len(pics) >= 2:
            ecart = abs(pics[-1][1] - pics[-2][1]) / pics[-2][1] * 100
            if ecart < 3:  # pics proches = double top
                msg += "  🔴 DOUBLE TOP detecte!\n"
                msg += f"     Deux pics a {pics[-2][1]:.2f} et {pics[-1][1]:.2f} (ecart {ecart:.1f}%)\n"
                msg += "     → Signal baissier (echec de cassure)\n"
            else:
                msg += "  ⚪ Pas de double top\n"
        else:
            msg += "  ⚪ Pas de double top\n"
        
        # Double bottom (deux creux consecutifs proches)
        creux = []
        for i in range(2, len(bas) - 2):
            if bas[i] < bas[i-1] and bas[i] < bas[i+1] and bas[i] < bas[i-2] and bas[i] < bas[i+2]:
                creux.append((i, bas[i]))
        
        if len(creux) >= 2:
            ecart = abs(creux[-1][1] - creux[-2][1]) / creux[-2][1] * 100
            if ecart < 3:
                msg += "  🟢 DOUBLE BOTTOM detecte!\n"
                msg += f"     Deux creux a {creux[-2][1]:.2f} et {creux[-1][1]:.2f} (ecart {ecart:.1f}%)\n"
                msg += "     → Signal haussier (rebond attendu)\n"
            else:
                msg += "  ⚪ Pas de double bottom\n"
        else:
            msg += "  ⚪ Pas de double bottom\n"
        
        # Head and shoulders (trois pics: gauche < centre > droite)
        if len(pics) >= 3:
            g, c, d = pics[-3], pics[-2], pics[-1]
            if c[1] > g[1] and c[1] > d[1] and abs(g[1] - d[1]) / c[1] * 100 < 5:
                msg += "  🔴 HEAD AND SHOULDERS detecte!\n"
                msg += f"     Tete: {c[1]:.2f}, epaules: {g[1]:.2f} / {d[1]:.2f}\n"
                msg += "     → Signal baissier fort (retournement de tendance)\n"
        
        # Bougie englobante (marubozu)
        dernier = bougies[-1]
        corps = abs(dernier["cloture"] - dernier["ouverture"])
        mèche_haut = dernier["haut"] - max(dernier["cloture"], dernier["ouverture"])
        mèche_bas = min(dernier["cloture"], dernier["ouverture"]) - dernier["bas"]
        if corps > 0 and (mèche_haut + mèche_bas) / corps < 0.3:
            if dernier["cloture"] > dernier["ouverture"]:
                msg += "  🟢 BOUGIE ENGLOBANTE HAUSSIERE (marubozu vert)\n"
                msg += "     → Fort momentum acheteur\n"
            else:
                msg += "  🔴 BOUGIE ENGLOBANTE BAISSIERE (marubozu rouge)\n"
                msg += "     → Fort momentum vendeur\n"
        
        # Doji (indecision)
        if corps > 0 and corps / (dernier["haut"] - dernier["bas"]) < 0.1:
            msg += "  🟡 DOJI detecte\n"
            msg += "     → Indecision du marche, retournement possible\n"
        
        # Bollinger squeeze (compression)
        if len(clotures) >= 20:
            sma20 = sum(clotures[-20:]) / 20
            import statistics
            std = statistics.stdev(clotures[-20:])
            bande_haute = sma20 + 2 * std
            bande_basse = sma20 - 2 * std
            largeur_bande = (bande_haute - bande_basse) / sma20 * 100
            if largeur_bande < 10:
                msg += "  🟡 BOLLINGER SQUEEZE detecte\n"
                msg += f"     Largeur des bandes: {largeur_bande:.1f}% (compression)\n"
                msg += "     → Fort mouvement imminent (direction a confirmer)\n"
    
    # Synthese
    msg += "\n" + "━" * 40 + "\n"
    msg += "🎯 SYNTHESE:\n"
    rsi_actuel = calc_rsi(clotures)
    msg += f"  RSI: {rsi_actuel:.0f} | Prix: {prix:.4f} EUR\n"
    
    signaux_haussiers = msg.count("🟢")
    signaux_baissiers = msg.count("🔴")
    
    if signaux_haussiers > signaux_baissiers:
        msg += f"  → Signal global: HAUSSIER ({signaux_haussiers} signaux positifs vs {signaux_baissiers} negatifs)\n"
    elif signaux_baissiers > signaux_haussiers:
        msg += f"  → Signal global: BAISSIER ({signaux_baissiers} signaux negatifs vs {signaux_haussiers} positifs)\n"
    else:
        msg += f"  → Signal global: NEUTRE ({signaux_haussiers} vs {signaux_baissiers})\n"
    
    memoire_ajouter("analyse", f"Divergences/patterns {symbole}: {signaux_haussiers}H vs {signaux_baissiers}B", [symbole.replace("USDT",""), "divergence", "pattern"])
    
    return msg


# ============================================
# 48. SENTIMENT TEMPS REEL (Twitter/Reddit/News)
# ============================================
def sentiment_temps_reel(symbole="BTCUSDT"):
    """Analyse le sentiment temps reel depuis plusieurs sources."""
    from indicateurs import NOMS
    nom = NOMS.get(symbole, symbole)
    base = symbole.replace("USDT", "")
    
    msg = f"📰 SENTIMENT TEMPS REEL - {nom}\n" + "━" * 40 + "\n\n"
    
    # 1. Sentiment via Perplexity (news + social)
    score_total = 0
    sources_count = 0
    
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Analyse le sentiment actuel du marche pour {nom} ({base}). Cherche les news recentes, le sentiment Twitter/Reddit, et les opinions d'experts. Donnes: 1) Score sentiment -10 a +10 2) 3 points cles (1 ligne chacun) 3) Tendance sociale (positif/negatif/neutre) 4) Sources principales. Reponds en francais, sois concis."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 400}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                reponse = r.json()["choices"][0]["message"]["content"]
                msg += "🟣 PERPLEXITY (news + social):\n"
                msg += reponse + "\n\n"
                
                # Extraire score (supporte formats: "score: -2", "Score : +6", "score sentiment : -2/10")
                import re
                match = re.search(r'score[^\d]*([+-]?\d+)', reponse, re.IGNORECASE)
                if match:
                    score_total += int(match.group(1))
                    sources_count += 1
        except Exception as e:
            msg += f"🟣 PERPLEXITY: Erreur ({e})\n\n"
    
    # 2. Sentiment via Gemini (autre perspective)
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"
            prompt = f"Analyse le sentiment du marche crypto pour {nom} ({base}). Donnes: 1) Score -10 a +10 2) Sentiment general (positif/negatif/neutre) 3) 2 facteurs qui influencent le sentiment actuellement. Reponds en francais, sois concis."
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                reponse = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                msg += "🔵 GEMINI (sentiment):\n"
                msg += reponse + "\n\n"
                
                import re
                match = re.search(r'score[^\d]*([+-]?\d+)', reponse, re.IGNORECASE)
                if match:
                    score_total += int(match.group(1))
                    sources_count += 1
        except Exception as e:
            msg += f"🔵 GEMINI: Erreur ({e})\n\n"
    
    # 3. Sentiment CoinGecko (community votes)
    try:
        from indicateurs import COINGECKO_MAP
        coin_id = COINGECKO_MAP.get(base.lower(), base.lower())
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        sentiment_up = data.get("sentiment_votes_up_percentage", 0)
        sentiment_down = data.get("sentiment_votes_down_percentage", 0)
        if sentiment_up or sentiment_down:
            msg += "📊 COINGECKO (communaute):\n"
            msg += f"  👍 {sentiment_up:.0f}% positif | 👎 {sentiment_down:.0f}% negatif\n"
            score_cg = int((sentiment_up - sentiment_down) / 10)
            score_total += score_cg
            sources_count += 1
            msg += f"  Score: {score_cg:+d}/10\n\n"
    except:
        msg += "📊 COINGECKO: indisponible\n\n"
    
    # Synthese
    msg += "━" * 40 + "\n"
    msg += "🔀 SYNTHESE SENTIMENT:\n"
    if sources_count > 0:
        score_moyen = score_total / sources_count
        msg += f"  Score moyen: {score_moyen:+.1f}/10 ({sources_count} sources)\n"
        if score_moyen > 3:
            msg += "  🟢 Sentiment TRES POSITIF - favorise les achats\n"
        elif score_moyen > 1:
            msg += "  🟡 Sentiment LEGEREMENT POSITIF - prudence mais tendance acheteuse\n"
        elif score_moyen < -3:
            msg += "  🔴 Sentiment TRES NEGATIF - eviter les achats, considerer la vente\n"
        elif score_moyen < -1:
            msg += "  🟠 Sentiment NEGATIF - prudence, attendre\n"
        else:
            msg += "  ⚪ Sentiment NEUTRE - attendre une direction claire\n"
    else:
        msg += "  Sources indisponibles\n"
    
    memoire_ajouter("sentiment", f"Sentiment {symbole}: score {score_moyen if sources_count else 'N/A'} ({sources_count} sources)", [base, "sentiment"])
    
    return msg


# ============================================
# 49. SIMULATEUR DE SCENARIOS
# ============================================
def simulateur_scenarios(symbole="BTCUSDT"):
    """Genere des scenarios futurs avec probabilites."""
    from indicateurs import historique_ohlcv, NOMS
    import math
    
    nom = NOMS.get(symbole, symbole)
    bougies = historique_ohlcv(symbole, "1d", 90)
    if not bougies or len(bougies) < 30:
        return f"Pas assez de donnees pour {symbole}"
    
    clotures = [b["cloture"] for b in bougies]
    prix = clotures[-1]
    
    # Calculer la volatilite historique
    rendements = [(clotures[i] - clotures[i-1]) / clotures[i-1] for i in range(1, len(clotures)) if clotures[i-1] > 0]
    import statistics
    vol_daily = statistics.stdev(rendements) if len(rendements) > 2 else 0.02
    vol_monthly = vol_daily * math.sqrt(30)
    
    # RSI
    gains = [clotures[j] - clotures[j-1] for j in range(-14, 0) if clotures[j] > clotures[j-1]]
    pertes = [clotures[j-1] - clotures[j] for j in range(-14, 0) if clotures[j] < clotures[j-1]]
    avg_gain = sum(gains) / 14 if gains else 0
    avg_perte = sum(pertes) / 14 if pertes else 0.001
    rsi = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 100)))
    
    # Tendance
    sma20 = sum(clotures[-20:]) / 20
    sma50 = sum(clotures[-50:]) / 50
    tendance = "haussiere" if sma20 > sma50 else "baissiere" if sma20 < sma50 else "neutre"
    
    msg = f"🔮 SIMULATEUR DE SCENARIOS - {nom}\n" + "━" * 40 + "\n\n"
    msg += f"📊 Etat actuel:\n"
    msg += f"  Prix: {prix:.4f} EUR\n"
    msg += f"  RSI: {rsi:.0f}\n"
    msg += f"  Tendance: {tendance}\n"
    msg += f"  Volatilite: {vol_daily*100:.1f}%/jour | {vol_monthly*100:.1f}%/mois\n\n"
    
    # Scenarios a 7 jours
    msg += "📅 SCENARIOS A 7 JOURS:\n\n"
    
    # Scenario 1: haussier (+1 vol mensuelle)
    prix_haut = prix * (1 + vol_monthly * 0.5)
    prob_haut = 25 if tendance == "haussiere" else 15 if tendance == "baissiere" else 20
    msg += f"  🟢 SCENARIO HAUSSIER ({prob_haut}% probabilite):\n"
    msg += f"     Prix cible: {prix_haut:.4f} EUR (+{(prix_haut/prix-1)*100:.1f}%)\n"
    msg += f"     Condition: momentum maintenu + volume positif\n"
    msg += f"     Action: holder / acheter sur retracement\n\n"
    
    # Scenario 2: neutre
    prix_neutre = prix * (1 + vol_daily * 2)
    prob_neutre = 40 if tendance == "neutre" else 35
    msg += f"  🟡 SCENARIO NEUTRE ({prob_neutre}% probabilite):\n"
    msg += f"     Prix cible: {prix_neutre:.4f} EUR (+{(prix_neutre/prix-1)*100:.1f}%)\n"
    msg += f"     Condition: range, pas de direction claire\n"
    msg += f"     Action: attendre, trader les bandes\n\n"
    
    # Scenario 3: baissier
    prix_bas = prix * (1 - vol_monthly * 0.5)
    prob_bas = 35 if tendance == "baissiere" else 25 if tendance == "haussiere" else 30
    msg += f"  🔴 SCENARIO BAISSIER ({prob_bas}% probabilite):\n"
    msg += f"     Prix cible: {prix_bas:.4f} EUR ({(prix_bas/prix-1)*100:+.1f}%)\n"
    msg += f"     Condition: cassure support + volume vendeur\n"
    msg += f"     Action: vendre / stop-loss serre\n\n"
    
    # Scenario 4: extreme (pump/dump)
    prix_pump = prix * (1 + vol_monthly * 1.5)
    prix_dump = prix * (1 - vol_monthly * 1.5)
    prob_extreme = 100 - prob_haut - prob_neutre - prob_bas
    if prob_extreme < 0:
        prob_extreme = 5
    msg += f"  ⚡ SCENARIO EXTREME ({prob_extreme:.0f}% probabilite):\n"
    msg += f"     Pump: {prix_pump:.4f} EUR (+{(prix_pump/prix-1)*100:.1f}%)\n"
    msg += f"     Dump: {prix_dump:.4f} EUR ({(prix_dump/prix-1)*100:+.1f}%)\n"
    msg += f"     Condition: evenement inattendu (news, whale)\n"
    msg += f"     Action: ne pas paniquer, proteger le capital\n\n"
    
    # Niveaux cles
    msg += "━" * 40 + "\n"
    msg += "🎯 NIVEAUX CLES A SURVEILLER:\n"
    
    # Support et resistance
    if len(bougies) >= 20:
        support = min(b["bas"] for b in bougies[-20:])
        resistance = max(b["haut"] for b in bougies[-20:])
        msg += f"  Support 20j: {support:.4f} EUR ({(support/prix-1)*100:+.1f}%)\n"
        msg += f"  Resistance 20j: {resistance:.4f} EUR ({(resistance/prix-1)*100:+.1f}%)\n"
    
    # Stop-loss suggere
    sl = prix * (1 - vol_monthly * 0.3)
    tp = prix * (1 + vol_monthly * 0.5)
    msg += f"  Stop-loss suggere: {sl:.4f} EUR (-{(1-sl/prix)*100:.1f}%)\n"
    msg += f"  Take-profit suggere: {tp:.4f} EUR (+{(tp/prix-1)*100:.1f}%)\n"
    
    # Ratio risque/rendement
    risque = prix - sl
    rendement = tp - prix
    ratio = rendement / risque if risque > 0 else 0
    msg += f"  Ratio risque/rendement: 1:{ratio:.1f}\n"
    
    if ratio > 2:
        msg += "  🟢 Bon ratio - trade rentable\n"
    elif ratio > 1:
        msg += "  🟡 Ratio moyen - prudence\n"
    else:
        msg += "  🔴 Mauvais ratio - risque trop eleve\n"
    
    # Verdict IA
    msg += "\n" + "━" * 40 + "\n"
    if PPLX_KEY:
        try:
            headers = {"Authorization": f"Bearer {PPLX_KEY}", "Content-Type": "application/json"}
            prompt = f"Tu es un analyste crypto. {nom} est a {prix:.4f} EUR, RSI {rsi:.0f}, tendance {tendance}, volatilite {vol_daily*100:.1f}%/jour. Scenarios: haussier {prob_haut}%, neutre {prob_neutre}%, baissier {prob_bas}%. Quel scenario est le plus probable selon toi et pourquoi? Reponds en 3 lignes en francais."
            payload = {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}
            r = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                msg += "🧠 VERDICT IA:\n" + r.json()["choices"][0]["message"]["content"]
        except:
            pass
    
    memoire_ajouter("scenario", f"Scenarios {symbole}: {prob_haut}%H / {prob_neutre}%N / {prob_bas}%B", [symbole.replace("USDT",""), "scenario"])
    
    return msg




# ============================================
# 50. AUTO-OPTIMISATION DES PARAMETRES (RSI/SMA/EMA par crypto)
# ============================================
def optimiser_parametres():
    """Teste differentes combinaisons de parametres RSI/SMA/EMA pour chaque crypto."""
    msg = "⚙️ OPTIMISATION DES PARAMETRES\n" + "━" * 40 + "\n\n"
    
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT"]
    _COINGECKO_IDS = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
    }
    
    # Parametres a tester
    rsi_periods = [14, 21, 28]
    sma_combos = [(10, 20), (20, 50), (9, 26)]
    
    # Charger la config actuelle
    param_file = os.path.join(DOSSIER, "params_optimaux.json")
    params = load_json_safe(param_file, {"cryptos": {}})
    
    for sym in cryptos:
        try:
            nom = _COINGECKO_IDS.get(sym, sym)
            msg += f"📊 {sym.replace('USDT','')}:\n"
            
            # Recuperer donnees CoinGecko
            import urllib.request
            coin_id = _COINGECKO_IDS.get(sym, sym.replace("USDT", "").lower())
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=eur&days=90&interval=daily"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            prices = [p[1] for p in data.get("prices", [])]
            if len(prices) < 30:
                msg += "  ⚠ Donnees insuffisantes\n\n"
                continue
            time.sleep(3)  # Anti rate-limit
            
            best_roi = -999
            best_config = {}
            
            for rsi_p in rsi_periods:
                for sma_fast, sma_slow in sma_combos:
                    # Backtest avec ces parametres
                    trades = []
                    pos = None
                    for i in range(max(sma_slow, rsi_p), len(prices)):
                        cl = prices[:i+1]
                        p = cl[-1]
                        sma_f = sum(cl[-sma_fast:]) / sma_fast if len(cl) >= sma_fast else p
                        sma_s = sum(cl[-sma_slow:]) / sma_slow if len(cl) >= sma_slow else p
                        # RSI calcule
                        gains = [cl[j] - cl[j-1] for j in range(-rsi_p, 0) if (j-1) >= -len(cl) and cl[j] > cl[j-1]]
                        pertes = [cl[j-1] - cl[j] for j in range(-rsi_p, 0) if (j-1) >= -len(cl) and cl[j] < cl[j-1]]
                        ag = sum(gains) / rsi_p if gains else 0
                        ap = sum(pertes) / rsi_p if pertes else 0.001
                        rsi = 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
                        
                        # Signal momentum avec params custom
                        if (sma_f > sma_s or p > sma_f) and rsi < 70 and rsi > 30:
                            if pos is None:
                                pos = p
                        elif (p < sma_f or rsi > 70):
                            if pos is not None:
                                pnl = (p - pos) / pos * 100 - 0.2
                                trades.append(pnl)
                                pos = None
                    if pos is not None:
                        pnl = (prices[-1] - pos) / pos * 100 - 0.2
                        trades.append(pnl)
                    
                    if trades:
                        roi = 1
                        for t in trades:
                            roi *= (1 + t / 100)
                        roi = (roi - 1) * 100
                        wr = len([t for t in trades if t > 0]) / len(trades) * 100
                        
                        if roi > best_roi:
                            best_roi = roi
                            best_config = {
                                "rsi_period": rsi_p, "sma_fast": sma_fast,
                                "sma_slow": sma_slow, "roi": round(roi, 1),
                                "wr": round(wr, 0), "trades": len(trades)
                            }
            
            if best_config:
                params.setdefault("cryptos", {})[sym] = best_config
                msg += f"  🎯 RSI:{best_config['rsi_period']} SMA:{best_config['sma_fast']}/{best_config['sma_slow']}\n"
                msg += f"     ROI:{best_config['roi']:+.1f}% WR:{best_config['wr']:.0f}% ({best_config['trades']}t)\n"
                print(f"[OPTIM] {sym}: {best_config}")
            else:
                msg += "  ⚠ Aucune config rentable\n"
            msg += "\n"
        except Exception as _e:
            msg += f"  ❌ {_e}\n\n"
    
    save_json_safe(param_file, params)
    msg += "━" * 40 + "\n"
    msg += f"📁 Parametres sauves dans params_optimaux.json\n"
    msg += "💡 L'agent utilisera ces params pour ses futures analyses."
    return msg

# ============================================
# 51. PREDICTION ML (Machine Learning simple)
# ============================================
def predire_ml(symbole="BTCUSDT"):
    """Utilise un modele de regression lineaire + decision tree pour predire la direction."""
    _COINGECKO_IDS = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
        "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin", "ARBUSDT": "arbitrum",
        "NEARUSDT": "near", "FETUSDT": "fetch-ai", "RNDRUSDT": "render-token",
    }
    nom = symbole.replace("USDT", "")
    msg = f"🤖 PREDICTION ML - {nom}\n" + "━" * 40 + "\n\n"
    
    # Recuperer donnees
    coin_id = _COINGECKO_IDS.get(symbole, nom.lower())
    prices = []
    try:
        import urllib.request
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=eur&days=90&interval=daily"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        prices = [p[1] for p in data.get("prices", [])]
    except Exception as e:
        # Fallback: essayer l'API simple/ohlc
        try:
            url2 = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=eur&days=90"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                data2 = json.loads(resp2.read().decode())
            prices = [c[4] for c in data2]  # close price
        except Exception as e2:
            return f"❌ Donnees indisponibles (CoinGecko: {e})"
    
    if len(prices) < 30:
        return "❌ Pas assez de donnees"
    
    # Calculer les features (indicateurs) pour chaque jour
    features = []
    labels = []
    for i in range(50, len(prices)-1):
        cl = prices[:i+1]
        p = cl[-1]
        # Features
        sma20 = sum(cl[-20:]) / 20
        sma50 = sum(cl[-50:]) / 50
        # RSI
        gains = [cl[j] - cl[j-1] for j in range(-14, 0) if (j-1) >= -len(cl) and cl[j] > cl[j-1]]
        pertes = [cl[j-1] - cl[j] for j in range(-14, 0) if (j-1) >= -len(cl) and cl[j] < cl[j-1]]
        ag = sum(gains) / 14 if gains else 0
        ap = sum(pertes) / 14 if pertes else 0.001
        rsi = 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
        # Momentum
        mom = (p - cl[-10]) / cl[-10] * 100 if len(cl) >= 10 else 0
        # Volatilite
        vol = (max(cl[-20:]) - min(cl[-20:])) / sma20 * 100 if sma20 > 0 else 0
        # Label: 1 si le prix monte le lendemain, 0 sinon
        label = 1 if prices[i+1] > p else 0
        
        features.append([rsi, (p - sma20) / sma20 * 100, (sma20 - sma50) / sma50 * 100, mom, vol])
        labels.append(label)
    
    if len(features) < 10:
        return "❌ Pas assez de donnees pour ML"
    
    # Split train/test (70/30)
    split = int(len(features) * 0.7)
    X_train, y_train = features[:split], labels[:split]
    X_test, y_test = features[split:], labels[split:]
    
    # --- Modele 1: Regression Logistique simple (from scratch) ---
    # Calculer les poids par gradient descent
    n_features = len(features[0])
    weights = [0.0] * n_features
    bias = 0.0
    lr = 0.01
    for epoch in range(200):
        for x, y in zip(X_train, y_train):
            z = bias + sum(w * xi for w, xi in zip(weights, x))
            pred = 1 / (1 + pow(2.71828, -z)) if z < 100 else 1.0
            error = pred - y
            for j in range(n_features):
                weights[j] -= lr * error * x[j]
            bias -= lr * error
    
    # Accuracy sur test
    correct = 0
    predictions = []
    for x, y in zip(X_test, y_test):
        z = bias + sum(w * xi for w, xi in zip(weights, x))
        pred = 1 if z > 0 else 0
        predictions.append(pred)
        if pred == y:
            correct += 1
    accuracy_log = correct / len(y_test) * 100 if y_test else 0
    
    # --- Modele 2: Decision Tree simple (from scratch) ---
    # Utilise le feature avec le meilleur split
    best_acc_tree = 0
    best_feat = 0
    best_thresh = 0
    for feat_idx in range(n_features):
        vals = sorted([x[feat_idx] for x in X_train])
        for thresh in vals[::3]:  # Test quelques thresholds
            tp = tn = fp = fn = 0
            for x, y in zip(X_train, y_train):
                pred = 1 if x[feat_idx] > thresh else 0
                if pred == 1 and y == 1: tp += 1
                elif pred == 1 and y == 0: fp += 1
                elif pred == 0 and y == 0: tn += 1
                else: fn += 1
            acc = (tp + tn) / len(y_train) * 100
            if acc > best_acc_tree:
                best_acc_tree = acc
                best_feat = feat_idx
                best_thresh = thresh
    
    # Test accuracy du tree
    correct_tree = 0
    for x, y in zip(X_test, y_test):
        pred = 1 if x[best_feat] > best_thresh else 0
        if pred == y:
            correct_tree += 1
    accuracy_tree = correct_tree / len(y_test) * 100 if y_test else 0
    
    # --- Prediction pour demain ---
    last_features = features[-1]
    z = bias + sum(w * xi for w, xi in zip(weights, last_features))
    proba = 1 / (1 + pow(2.71828, -z)) if z < 100 else 1.0
    pred_tree = 1 if last_features[best_feat] > best_thresh else 0
    
    # Consensus
    models_haussier = (1 if proba > 0.5 else 0) + (1 if pred_tree == 1 else 0)
    consensus = "HAUSSIER" if models_haussier == 2 else ("BAISSIER" if models_haussier == 0 else "NEUTRE")
    
    prix_actuel = prices[-1]
    feature_names = ["RSI", "Prix vs SMA20", "SMA20 vs SMA50", "Momentum", "Volatilite"]
    
    msg += f"📊 Prix actuel: {prix_actuel:.2f} EUR\n"
    msg += f"📈 Features analysees: {', '.join(feature_names)}\n\n"
    msg += f"🔮 MODELE 1 - Regression Logistique:\n"
    msg += f"   Accuracy test: {accuracy_log:.0f}%\n"
    msg += f"   Probabilite hausse: {proba*100:.0f}%\n\n"
    msg += f"🌳 MODELE 2 - Decision Tree:\n"
    msg += f"   Feature decisive: {feature_names[best_feat]} (seuil: {best_thresh:.2f})\n"
    msg += f"   Accuracy train: {best_acc_tree:.0f}% | test: {accuracy_tree:.0f}%\n"
    msg += f"   Prediction: {'HAUSSE' if pred_tree == 1 else 'BAISSE'}\n\n"
    msg += "━" * 40 + "\n"
    msg += f"🎯 CONSENSUS ML: {consensus}\n"
    if consensus == "HAUSSIER":
        msg += "🟢 Les 2 modeles prevoyent une hausse demain"
    elif consensus == "BAISSIER":
        msg += "🔴 Les 2 modeles prevoyent une baisse demain"
    else:
        msg += "🟡 Les modeles sont en desaccord - prudence"
    
    return msg

# ============================================
# 52. META-APPRENTISSAGE (strategies par regime de marche)
# ============================================
def meta_apprentissage():
    """Apprend quelles strategies marchent dans quel regime (bull/bear/sideways)."""
    msg = "🧠 META-APPRENTISSAGE\n" + "━" * 40 + "\n\n"
    
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT"]
    _COINGECKO_IDS = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
    }
    strategies = ["momentum", "mean_reversion", "breakout", "rsi_extreme", "macd"]
    
    # Charger le fichier de meta-apprentissage
    meta_file = os.path.join(DOSSIER, "meta_apprentissage.json")
    meta = load_json_safe(meta_file, {"regimes": {}})
    
    for sym in cryptos:
        try:
            coin_id = _COINGECKO_IDS.get(sym, sym.replace("USDT", "").lower())
            import urllib.request
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=eur&days=90&interval=daily"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            prices = [p[1] for p in data.get("prices", [])]
            time.sleep(3)  # Anti rate-limit
            
            if len(prices) < 50:
                continue
            
            # Detecter le regime sur les 90 derniers jours
            sma20 = sum(prices[-20:]) / 20
            sma50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else sma20
            prix = prices[-1]
            var_30j = (prix - prices[-30]) / prices[-30] * 100 if len(prices) >= 30 else 0
            vol_20j = (max(prices[-20:]) - min(prices[-20:])) / sma20 * 100 if sma20 > 0 else 0
            
            # Classification du regime
            if prix > sma20 > sma50 and var_30j > 5:
                regime = "bull"
            elif prix < sma20 < sma50 and var_30j < -5:
                regime = "bear"
            else:
                regime = "sideways"
            
            # Backtest de chaque strategie sur cette periode
            strat_results = {}
            for strat in strategies:
                trades = []
                pos = None
                for i in range(50, len(prices)):
                    cl = prices[:i+1]
                    p = cl[-1]
                    s20 = sum(cl[-20:]) / 20
                    s50 = sum(cl[-50:]) / 50 if len(cl) >= 50 else s20
                    gains = [cl[j] - cl[j-1] for j in range(-14, 0) if (j-1) >= -len(cl) and cl[j] > cl[j-1]]
                    pertes = [cl[j-1] - cl[j] for j in range(-14, 0) if (j-1) >= -len(cl) and cl[j] < cl[j-1]]
                    ag = sum(gains) / 14 if gains else 0
                    ap = sum(pertes) / 14 if pertes else 0.001
                    r = 100 - (100 / (1 + (ag / ap if ap > 0 else 100)))
                    sig = 0
                    if strat == "momentum":
                        if (s20 > s50 or p > s20) and r < 70 and r > 30: sig = 1
                        elif (p < s20 or r > 70): sig = -1
                    elif strat == "mean_reversion":
                        if r < 30: sig = 1
                        elif r > 70: sig = -1
                    elif strat == "breakout":
                        if len(cl) >= 20:
                            if p > max(cl[-20:]) * 0.99: sig = 1
                            elif p < min(cl[-20:]) * 1.01: sig = -1
                    elif strat == "rsi_extreme":
                        if r < 25: sig = 1
                        elif r > 75: sig = -1
                    elif strat == "macd":
                        e12 = sum(cl[-12:]) / 12 if len(cl) >= 12 else p
                        e26 = sum(cl[-26:]) / 26 if len(cl) >= 26 else p
                        m = e12 - e26
                        if m > 0 and r < 65: sig = 1
                        elif m < 0 and r > 35: sig = -1
                    if sig == 1 and pos is None:
                        pos = p
                    elif sig == -1 and pos is not None:
                        pnl = (p - pos) / pos * 100 - 0.2
                        trades.append(pnl)
                        pos = None
                if pos is not None:
                    pnl = (prices[-1] - pos) / pos * 100 - 0.2
                    trades.append(pnl)
                
                if trades:
                    roi = 1
                    for t in trades:
                        roi *= (1 + t / 100)
                    roi = (roi - 1) * 100
                    strat_results[strat] = round(roi, 1)
            
            # Trouver la meilleure strategie pour ce regime
            if strat_results:
                best_strat = max(strat_results, key=strat_results.get)
                meta.setdefault("regimes", {}).setdefault(regime, {})
                meta["regimes"][regime][sym] = {
                    "best_strat": best_strat,
                    "results": strat_results,
                    "var_30j": round(var_30j, 1),
                    "vol_20j": round(vol_20j, 1)
                }
                msg += f"📊 {sym.replace('USDT','')} ({regime.upper()}):\n"
                msg += f"   Meilleure: {best_strat} ({strat_results[best_strat]:+.1f}%)\n"
                msg += f"   Var 30j: {var_30j:+.1f}% | Vol: {vol_20j:.1f}%\n\n"
        except Exception as _e:
            msg += f"❌ {sym}: {_e}\n\n"
    
    # Synthese par regime
    msg += "━" * 40 + "\n"
    msg += "📚 SYNTHÈSE PAR RÉGIME:\n"
    for regime in ["bull", "bear", "sideways"]:
        r_data = meta.get("regimes", {}).get(regime, {})
        if r_data:
            strats = [v["best_strat"] for v in r_data.values()]
            from collections import Counter
            best = Counter(strats).most_common(1)[0]
            msg += f"  {regime.upper()}: stratégie optimale = {best[0]} ({best[1]} cryptos)\n"
    
    save_json_safe(meta_file, meta)
    msg += "\n📁 Sauvegardé dans meta_apprentissage.json\n"
    msg += "💡 L'agent utilisera ces infos pour choisir ses stratégies selon le régime."
    return msg

# ============================================
# 53. AUTO-GÉNÉRATION DE STRATÉGIES (Ichimoku, VWAP, Bollinger)
# ============================================
def auto_generer_strategies():
    """Génère, backteste et valide de nouvelles stratégies automatiquement."""
    msg = "🧬 AUTO-GÉNÉRATION DE STRATÉGIES\n" + "━" * 40 + "\n\n"
    
    _COINGECKO_IDS = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
    }
    
    nouvelles_strategies = {
        "ichimoku": {
            "desc": "Ichimoku Cloud (Tenkan/Kijun cross + cloud)",
            "params": {"tenkan": 9, "kijun": 26, "senkou": 52}
        },
        "vwap": {
            "desc": "VWAP bounce (prix > VWAP = achat, prix < VWAP = vente)",
            "params": {"period": 20}
        },
        "bollinger": {
            "desc": "Bollinger Bands squeeze (bande inferieure = achat, superieure = vente)",
            "params": {"period": 20, "std": 2}
        },
        "stochastic": {
            "desc": "Stochastic Oscillator (%K < 20 = achat, %K > 80 = vente)",
            "params": {"period": 14, "smooth": 3}
        },
        "ema_cross": {
            "desc": "EMA 9/21 cross (EMA9 > EMA21 = achat, EMA9 < EMA21 = vente)",
            "params": {"fast": 9, "slow": 21}
        }
    }
    
    strat_file = os.path.join(DOSSIER, "strategies_generees.json")
    results = load_json_safe(strat_file, {"strategies": {}})
    
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        try:
            coin_id = _COINGECKO_IDS.get(sym)
            import urllib.request
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=eur&days=90&interval=daily"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            prices = [p[1] for p in data.get("prices", [])]
            time.sleep(3)  # Anti rate-limit
            
            if len(prices) < 52:
                continue
            
            msg += f"📊 {sym.replace('USDT','')}:\n"
            
            for strat_name, strat_info in nouvelles_strategies.items():
                trades = []
                pos = None
                p = strat_info["params"]
                
                for i in range(max(p.get("period", 26), p.get("slow", 21), 52), len(prices)):
                    cl = prices[:i+1]
                    prix = cl[-1]
                    sig = 0
                    
                    if strat_name == "ichimoku":
                        tenkan_p = p["tenkan"]
                        kijun_p = p["kijun"]
                        tenkan = (max(cl[-tenkan_p:]) + min(cl[-tenkan_p:])) / 2
                        kijun = (max(cl[-kijun_p:]) + min(cl[-kijun_p:])) / 2
                        senkou_a = (tenkan + kijun) / 2
                        senkou_b = (max(cl[-p["senkou"]:]) + min(cl[-p["senkou"]:])) / 2
                        if tenkan > kijun and prix > senkou_a and senkou_a > senkou_b: sig = 1
                        elif tenkan < kijun and prix < senkou_a: sig = -1
                    
                    elif strat_name == "vwap":
                        period = p["period"]
                        vwap = sum(cl[-period:]) / period  # Simplified VWAP (no volume)
                        if prix > vwap * 1.02: sig = 1
                        elif prix < vwap * 0.98: sig = -1
                    
                    elif strat_name == "bollinger":
                        period = p["period"]
                        sma = sum(cl[-period:]) / period
                        variance = sum((x - sma) ** 2 for x in cl[-period:]) / period
                        std = variance ** 0.5
                        upper = sma + p["std"] * std
                        lower = sma - p["std"] * std
                        if prix < lower: sig = 1
                        elif prix > upper: sig = -1
                    
                    elif strat_name == "stochastic":
                        period = p["period"]
                        high_max = max(cl[-period:])
                        low_min = min(cl[-period:])
                        k = (prix - low_min) / (high_max - low_min) * 100 if high_max > low_min else 50
                        if k < 20: sig = 1
                        elif k > 80: sig = -1
                    
                    elif strat_name == "ema_cross":
                        fast = p["fast"]
                        slow = p["slow"]
                        ema_f = sum(cl[-fast:]) / fast
                        ema_s = sum(cl[-slow:]) / slow
                        if ema_f > ema_s: sig = 1
                        elif ema_f < ema_s: sig = -1
                    
                    if sig == 1 and pos is None:
                        pos = prix
                    elif sig == -1 and pos is not None:
                        pnl = (prix - pos) / pos * 100 - 0.2
                        trades.append(pnl)
                        pos = None
                
                if pos is not None:
                    pnl = (prices[-1] - pos) / pos * 100 - 0.2
                    trades.append(pnl)
                
                if trades:
                    roi = 1
                    for t in trades:
                        roi *= (1 + t / 100)
                    roi = (roi - 1) * 100
                    wr = len([t for t in trades if t > 0]) / len(trades) * 100
                    
                    results.setdefault("strategies", {}).setdefault(strat_name, {})[sym] = {
                        "roi": round(roi, 1), "wr": round(wr, 0), "trades": len(trades),
                        "desc": strat_info["desc"]
                    }
                    
                    emoji = "🟢" if roi > 0 else "🔴"
                    msg += f"  {emoji} {strat_name:<14} ROI:{roi:+.1f}% WR:{wr:.0f}% ({len(trades)}t)\n"
                else:
                    msg += f"  ⚪ {strat_name:<14} Aucun trade\n"
            msg += "\n"
        except Exception as _e:
            msg += f"❌ {sym}: {_e}\n\n"
    
    save_json_safe(strat_file, results)
    
    # Synthese: trouver les meilleures strategies generees
    msg += "━" * 40 + "\n"
    msg += "🏆 TOP STRATÉGIES GÉNÉRÉES:\n"
    all_strats = []
    for strat_name, sym_data in results.get("strategies", {}).items():
        for sym, data in sym_data.items():
            all_strats.append((strat_name, sym, data["roi"], data["wr"], data["trades"]))
    all_strats.sort(key=lambda x: x[2], reverse=True)
    for s, sym, roi, wr, t in all_strats[:5]:
        if roi > 0:
            msg += f"  ✅ {s} sur {sym.replace('USDT','')}: {roi:+.1f}% (WR {wr:.0f}%, {t}t)\n"
    
    msg += f"\n📁 {len(nouvelles_strategies)} stratégies testées sur 3 cryptos\n"
    msg += "💡 Stratégies gagnantes ajoutées au registry."
    return msg

# ============================================
# 50. AUTO-DIAGNOSTIC + AUTO-REPARATION AUTONOME
# ============================================
def auto_diagnostic():
    """Scanne l'agent, repare les problemes, commit et push les fixes."""
    msg = "🔧 AUTO-DIAGNOSTIC EN COURS\n" + " " * 40 + "\n\n"
    msg = "🔧 AUTO-DIAGNOSTIC EN COURS\n" + "━" * 40 + "\n\n"
    problemes = []
    reparations = []
    code_modifie = False
    
    agent_path = os.path.join(DOSSIER, "agent_os.py")
    
    # 1. Verifier la syntaxe de agent_os.py
    msg += "1️⃣ Verification syntaxe agent_os.py...\n"
    try:
        import ast
        with open(agent_path, "r") as f:
            code = f.read()
        ast.parse(code)
        msg += "   ✅ Syntaxe OK\n"
    except SyntaxError as e:
        problemes.append(f"Syntaxe agent_os.py ligne {e.lineno}: {e.msg}")
        msg += f"   ❌ Erreur syntaxe ligne {e.lineno}: {e.msg}\n"
        msg += "   ⚠️ Correction manuelle requise\n"
    
    # 2. Verifier et reparer les imports manquants
    msg += "\n2️⃣ Verification des imports...\n"
    imports_necessaires = [
        ("requests", "requests"),
        ("json", "json"),
        ("os", "os"),
        ("datetime", "datetime"),
        ("urllib.request", "urllib"),
        ("threading", "threading"),
        ("time", "time"),
        ("sys", "sys"),
    ]
    for imp_name, imp_search in imports_necessaires:
        if f"import {imp_search}" not in code and f"from {imp_search}" not in code:
            problemes.append(f"Import manquant: {imp_name}")
            msg += f"   ❌ Import manquant: {imp_name}\n"
            # AUTO-REPARATION: ajouter l'import
            try:
                lignes = code.split("\n")
                # Trouver le dernier import
                dernier_import = 0
                for i, l in enumerate(lignes):
                    if l.startswith("import ") or l.startswith("from "):
                        dernier_import = i
                lignes.insert(dernier_import + 1, f"import {imp_name}")
                nouveau_code = "\n".join(lignes)
                # Valider la syntaxe apres modification
                ast.parse(nouveau_code)
                with open(agent_path, "w") as f:
                    f.write(nouveau_code)
                code = nouveau_code
                code_modifie = True
                reparations.append(f"import {imp_name} ajoute")
                msg += f"   🔧 import {imp_name} ajoute automatiquement\n"
                problemes.pop()  # Retirer des problemes since on l'a repare
            except Exception as e:
                msg += f"   ⚠️ Reparation impossible: {e}\n"
        else:
            msg += f"   ✅ {imp_name} present\n"
    
    # 3. Verifier et reparer les fichiers de donnees
    msg += "\n3️⃣ Verification des fichiers de donnees...\n"
    fichiers = ["paper_trading.json", "memoire.json", "alertes_prix.json", "poids_strategies.json", "diagnostics.json"]
    for f in fichiers:
        path = os.path.join(DOSSIER, f)
        if not os.path.exists(path):
            msg += f"   ❌ {f} manquant\n"
            # AUTO-REPARATION: creer le fichier
            try:
                with open(path, "w") as fp:
                    json.dump({}, fp)
                reparations.append(f"{f} cree")
                msg += f"   🔧 {f} cree automatiquement\n"
            except:
                pass
        else:
            try:
                with open(path) as fp:
                    json.load(fp)
                msg += f"   ✅ {f} OK\n"
            except json.JSONDecodeError:
                msg += f"   ❌ {f} corrompu\n"
                # AUTO-REPARATION: sauvegarder et recreer
                try:
                    os.rename(path, path + ".bak")
                    with open(path, "w") as fp:
                        json.dump({}, fp)
                    reparations.append(f"{f} recre (backup .bak)")
                    msg += f"   🔧 {f} recre (backup .bak)\n"
                except:
                    pass
    
    # 4. Verifier les cles API
    msg += "\n4️⃣ Verification des cles API...\n"
    env_found = False
    for env_path in [os.path.join(DOSSIER, ".env"), "/home/ubuntu/agent-ia/.env", os.path.expanduser("~/agent-ia/.env")]:
        if os.path.exists(env_path):
            env_found = True
            cles_presentes = []
            try:
                with open(env_path, "rb") as ef:
                    raw = ef.read().decode("utf-8", errors="ignore")
                for line in raw.replace("\r", "").split("\n"):
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k = line.split("=", 1)[0].strip()
                        if k:
                            cles_presentes.append(k)
            except:
                pass
            if cles_presentes:
                msg += f"   ✅ .env trouve ({len(cles_presentes)} cles): {', '.join(cles_presentes[:5])}\n"
            else:
                msg += "   ⚠️ .env trouve mais vide\n"
                problemes.append(".env vide")
            break
    if not env_found:
        msg += "   ❌ .env non trouve\n"
        problemes.append(".env manquant")
    
    if TELEGRAM_TOKEN:
        msg += "   ✅ TELEGRAM_BOT_TOKEN actif\n"
    else:
        msg += "   ⚠️ TELEGRAM_BOT_TOKEN non charge\n"
        problemes.append("TELEGRAM_BOT_TOKEN non charge")
    if PPLX_KEY:
        msg += "   ✅ PPLX_API_KEY actif\n"
    else:
        msg += "   ⚠️ PPLX_API_KEY non charge\n"
        problemes.append("PPLX_API_KEY non charge")
    if GEMINI_KEY:
        msg += "   ✅ GEMINI_API_KEY actif\n"
    else:
        msg += "   ⚠️ GEMINI_API_KEY non charge\n"
        problemes.append("GEMINI_API_KEY non charge")
    
    # 5. Test connexion Telegram
    msg += "\n5️⃣ Test connexion Telegram...\n"
    if TELEGRAM_TOKEN:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=10)
            if r.status_code == 200:
                bot_info = r.json().get("result", {})
                msg += f"   ✅ Bot connecte: @{bot_info.get('username', '?')}\n"
            else:
                msg += f"   ⚠️ Telegram API: {r.status_code}\n"
        except Exception as e:
            msg += f"   ⚠️ Telegram: {e}\n"
    else:
        msg += "   ❌ Pas de token Telegram\n"
        problemes.append("Telegram: pas de token")
    
    # 6. Test connexion CoinGecko
    msg += "\n6️⃣ Test connexion CoinGecko...\n"
    try:
        r = requests.get("https://api.coingecko.com/api/v3/ping", timeout=10)
        if r.status_code == 200:
            msg += "   ✅ CoinGecko OK\n"
        else:
            problemes.append(f"CoinGecko: {r.status_code}")
            msg += f"   ❌ CoinGecko: {r.status_code}\n"
    except Exception as e:
        problemes.append(f"CoinGecko: {e}")
        msg += f"   ❌ CoinGecko: {e}\n"
    
    # 7. Verifier les fonctions critiques
    msg += "\n7️⃣ Verification des fonctions critiques...\n"
    fonctions_critiques = [
        ("def send_telegram", "send_telegram"),
        ("def get_crypto_price", "get_crypto_price"),
        ("def analyser_actif", "analyser_actif"),
        ("def gerer_stop_loss_take_profit", "stop_loss/take_profit"),
        ("def pnl_temps_reel", "pnl_temps_reel"),
        ("def briefing", "briefing"),
        ("def auto_diagnostic", "auto_diagnostic"),
    ]
    for pattern, nom in fonctions_critiques:
        if pattern in code:
            msg += f"   ✅ {nom}\n"
        else:
            problemes.append(f"Fonction manquante: {nom}")
            msg += f"   ⚠️ {nom} non trouvee\n"
    
    # 8. Verifier le systeme
    msg += "\n8️⃣ Verification systeme...\n"
    try:
        import shutil
        du = shutil.disk_usage("/")
        pct = du.used / du.total * 100
        if pct > 90:
            problemes.append(f"Disque plein: {pct:.0f}%")
            msg += f"   ❌ Disque: {pct:.0f}% (CRITIQUE)\n"
            # AUTO-REPARATION: nettoyer les gros logs
            try:
                for f in os.listdir(DOSSIER):
                    fp = os.path.join(DOSSIER, f)
                    if f.endswith(".log") and os.path.getsize(fp) > 10_000_000:
                        os.remove(fp)
                        reparations.append(f"{f} supprime (trop gros)")
                        msg += f"   🔧 {f} supprime (>10MB)\n"
            except:
                pass
        else:
            msg += f"   ✅ Disque: {pct:.0f}%\n"
    except:
        msg += "   ⚪ Disque: verification impossible\n"
    
    try:
        import subprocess
        r = subprocess.run(["pgrep", "-f", "agent_os.py"], capture_output=True, text=True, timeout=5)
        nb = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
        if nb == 0:
            problemes.append("Agent OS non lance")
            msg += "   ⚠️ Agent OS: NON LANCE\n"
        else:
            msg += f"   ✅ Agent OS: actif ({nb} processus)\n"
    except:
        msg += "   ⚪ Processus: verification impossible\n"
    
    # === AUTO-REPARATION: commit + push si code modifie ===
    if code_modifie:
        msg += "\n" + "━" * 40 + "\n"
        msg += "📤 SAUVEGARDE DES REPARATIONS...\n"
        try:
            import subprocess
            # Git add + commit + push
            subprocess.run(["git", "add", "-A"], cwd=DOSSIER, capture_output=True, timeout=10)
            commit_msg = f"Auto-reparation: {', '.join(reparations)}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=DOSSIER, capture_output=True, timeout=10)
            subprocess.run(["git", "push"], cwd=DOSSIER, capture_output=True, timeout=30)
            msg += "   ✅ Fixes commites et pousses sur GitHub\n"
            msg += "   📦 Relance necessaire pour appliquer les fixes\n"
        except Exception as e:
            msg += f"   ⚠️ Git push impossible: {e}\n"
    
    # Synthese
    msg += "\n" + "━" * 40 + "\n"
    msg += "📊 SYNTHESE DIAGNOSTIC:\n"
    msg += f"  Problemes restants: {len(problemes)}\n"
    msg += f"  Reparations auto: {len(reparations)}\n"
    
    if reparations:
        msg += "\n🔧 REPARATIONS EFFECTUEES:\n"
        for r in reparations:
            msg += f"  ✅ {r}\n"
    
    if not problemes:
        msg += "\n✅ AUCUN PROBLEME - Agent en parfait etat!"
    else:
        msg += "\n⚠️ PROBLEMES RESTANTS:\n"
        for p in problemes:
            msg += f"  • {p}\n"
    
    # Enregistrer le diagnostic
    diag_file = os.path.join(DOSSIER, "diagnostics.json")
    diags = load_json_safe(diag_file, {"diagnostics": []})
    diags.setdefault("diagnostics", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "problemes": len(problemes),
        "reparations": len(reparations),
        "details": problemes[:10],
        "reparations_details": reparations[:10]
    })
    save_json_safe(diag_file, diags)
    
    memoire_ajouter("diagnostic", f"Diagnostic: {len(problemes)} problemes, {len(reparations)} reparations auto", ["diagnostic", "auto_reparation"])
    
    return msg


def auto_reparation_continue():
    """Boucle autonome: scanne, repare, commit, push, notifie. Toutes les 30 min."""
    while True:
        try:
            time.sleep(1800)  # 30 minutes
            result = auto_diagnostic()
            # Si des reparations ont ete effectuees, notifier
            if "REPARATIONS EFFECTUEES" in result:
                send_telegram("🔧 AUTO-REPARATION: problems detectes et corriges automatiquement!")
                send_telegram(result[:4000])
            # Si problemes non resolus, notifier
            elif "PROBLEMES RESTANTS" in result:
                send_telegram("⚠️ AUTO-DIAGNOSTIC: problemes non resolus detectes")
                send_telegram(result[:4000])
            # Log silencieux
            with open(os.path.join(DOSSIER, "auto_diag.log"), "a") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Diagnostic OK\n")
        except Exception as e:
            try:
                enregistrer_erreur("auto_diagnostic", "boucle diagnostic", str(e), "Verifier les imports et la memoire")
            except:
                pass
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
    elif len(sys.argv) > 1 and sys.argv[1] == "briefing":
        briefing_matin()
    elif len(sys.argv) > 1 and sys.argv[1] == "gestion-auto":
        gerer_stop_loss_take_profit()
    elif len(sys.argv) > 1 and sys.argv[1] == "graph-telegram":
        generer_graphique("BTCUSDT")
        generer_graphique_pnl()
    else:
        autonomous_loop()
