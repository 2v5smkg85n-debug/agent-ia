#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENT OS - Orchestrateur autonome multi-tâches.
Transforme l'agent de trading en système IA généraliste.

Capabilities:
1. WEB SEARCH - Recherche en temps réel via Perplexity API
2. MARKET ANALYSIS - Analyse crypto avancée avec contexte web
3. PROBLEM SOLVING - Résolution de problèmes avec IA
4. NATURAL LANGUAGE - Interface Telegram en langage naturel
5. AUTONOMOUS DECISIONS - Prend des décisions sans intervention
6. SELF-IMPROVEMENT - Apprend et s'améliore continuellement
7. MULTI-MODEL - Utilise plusieurs IA (Perplexity, Gemini)
8. TASK QUEUE - File d'attente de tâches autonomes
9. MONITORING - Surveillance 24/7 avec alertes intelligentes
10. KNOWLEDGE BASE - Base de connaissances persistante

Usage:
    python agent_os.py            # Démarre l'orchestrateur
    python agent_os.py chat       # Mode chat interactif (Telegram)
    python agent_os.py status    # État du système
"""
import os
import sys
import json
import time
import threading
import requests
from datetime import datetime, timedelta
from collections import defaultdict

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

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
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")

KB_FILE = os.path.join(DOSSIER, "knowledge_base.json")
TASK_QUEUE_FILE = os.path.join(DOSSIER, "task_queue.json")
DECISIONS_LOG = os.path.join(DOSSIER, "decisions_log.jsonl")
CHAT_LOG = os.path.join(DOSSIER, "chat_log.jsonl")

# ============================================
# 1. WEB SEARCH - Recherche temps réel
# ============================================
def web_search(query, num_results=5):
    """Recherche web via Perplexity API avec citations."""
    if not PPLX_KEY:
        return {"error": "PPLX_API_KEY manquant"}
    
    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PPLX_KEY}"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.2,
            },
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "answer": data["choices"][0]["message"]["content"],
                "citations": data.get("citations", []),
                "model": "sonar",
            }
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def crypto_news_search(symbole=None):
    """Recherche les dernières actualités crypto."""
    query = "Latest cryptocurrency market news and analysis today"
    if symbole:
        query = f"{symbole} crypto price prediction and news today"
    return web_search(query)


def market_sentiment_search():
    """Recherche le sentiment général du marché crypto."""
    return web_search(
        "Current crypto market sentiment: fear and greed index, "
        "Bitcoin trend, market cap analysis today. "
        "Bull or bear market? Summarize in 3 points."
    )


# ============================================
# 2. MARKET ANALYSIS - Analyse avancée
# ============================================
def analyze_market(symbole=None):
    """Analyse complète du marché avec données web + techniques."""
    result = {
        "timestamp": datetime.now().isoformat(),
        "symbole": symbole or "GLOBAL",
        "web_analysis": None,
        "news": None,
        "sentiment": None,
        "recommendation": None,
    }
    
    # 1. Recherche web
    if symbole:
        result["web_analysis"] = web_search(
            f"Analyze {symbole} crypto: current price, recent performance, "
            "key support/resistance levels, and short-term outlook. "
            "Is it a good time to buy?"
        )
    else:
        result["sentiment"] = market_sentiment_search()
    
    # 2. Analyse technique (si indicateurs disponibles)
    try:
        from indicateurs import historique_ohlcv, analyser_actif
        if symbole:
            bougies = historique_ohlcv(symbole, "1h", 100)
            if bougies and len(bougies) >= 50:
                clotures = [b["cloture"] for b in bougies]
                prix_actuel = clotures[-1]
                prix_precedent = clotures[-24] if len(clotures) >= 24 else clotures[0]
                variation_24h = (prix_actuel - prix_precedent) / prix_precedent * 100
                highest = max(clotures[-24:])
                lowest = min(clotures[-24:])
                
                # RSI
                gains = []
                pertes = []
                for j in range(1, min(len(clotures), 15)):
                    diff = clotures[j] - clotures[j-1]
                    gains.append(max(diff, 0))
                    pertes.append(max(-diff, 0))
                avg_gain = sum(gains) / len(gains) if gains else 0
                avg_perte = sum(pertes) / len(pertes) if pertes else 0.001
                rsi = 100 - (100 / (1 + avg_gain / avg_perte)) if avg_perte > 0 else 50
                
                # SMA
                sma20 = sum(clotures[-20:]) / 20
                sma50 = sum(clotures[-50:]) / 50
                
                result["technical"] = {
                    "prix": prix_actuel,
                    "variation_24h": round(variation_24h, 2),
                    "highest_24h": highest,
                    "lowest_24h": lowest,
                    "rsi": round(rsi, 1),
                    "sma20": round(sma20, 4),
                    "sma50": round(sma50, 4),
                    "trend": "BULL" if sma20 > sma50 else "BEAR",
                }
    except Exception as e:
        result["technical_error"] = str(e)
    
    # 3. Recommandation IA
    context = json.dumps(result, indent=2, default=str)
    result["recommendation"] = ask_ai(
        f"Based on this market data, give a trading recommendation in JSON:\n{context}\n\n"
        "Respond: {\"action\": \"BUY/SELL/WAIT\", \"confidence\": 0-1, "
        "\"reason\": \"short explanation\", \"target_price\": null}"
    )
    
    return result


# ============================================
# 3. PROBLEM SOLVING - Résolution de problèmes
# ============================================
def solve_problem(problem):
    """Résout un problème en utilisant le raisonnement IA."""
    if not PPLX_KEY:
        return {"error": "PPLX_API_KEY manquant"}
    
    # Étape 1: Analyser le problème
    analysis = ask_ai(
        f"Analyze this problem and break it into steps:\n{problem}\n\n"
        "Respond in JSON: {\"understanding\": \"what the problem is\", "
        "\"steps\": [\"step1\", \"step2\", ...], "
        "\"difficulty\": 1-10, "
        "\"approach\": \"recommended approach\"}"
    )
    
    # Étape 2: Rechercher des solutions
    search_result = web_search(f"How to solve: {problem}")
    
    # Étape 3: Générer une solution
    context = f"Problem: {problem}\nAnalysis: {json.dumps(analysis)}\nSearch results: {search_result.get('answer', '')}"
    solution = ask_ai(
        f"Based on the analysis and search results, provide a concrete solution:\n{context}\n\n"
        "Respond in JSON: {\"solution\": \"detailed steps\", "
        "\"code\": \"python code if applicable\", "
        "\"warnings\": [\"potential issues\"], "
        "\"success_probability\": 0-1}"
    )
    
    return {
        "problem": problem,
        "analysis": analysis,
        "search": search_result,
        "solution": solution,
    }


# ============================================
# 4. AI CORE - Appels IA multi-modèles
# ============================================
def ask_ai(prompt, model=None):
    """Pose une question à l'IA (Perplexity par défaut)."""
    if not PPLX_KEY:
        return {"error": "PPLX_API_KEY manquant"}
    
    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PPLX_KEY}"},
            json={
                "model": model or "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def ask_ai_json(prompt, model=None):
    """Pose une question et tente de parser la réponse en JSON."""
    response = ask_ai(prompt, model)
    if isinstance(response, dict):
        return response
    # Extract JSON from response
    import re
    match = re.search(r'\{[\s\S]*\}', response)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"raw_response": response}


def multi_model_consensus(question):
    """Consensus entre Perplexity et Gemini."""
    results = {}
    
    # Perplexity
    results["perplexity"] = ask_ai(question)
    
    # Gemini
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": question}]}]},
                timeout=60
            )
            if r.status_code == 200:
                results["gemini"] = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                results["gemini"] = f"Error {r.status_code}"
        except Exception as e:
            results["gemini"] = f"Error: {e}"
    
    # Synthèse
    if "gemini" in results and "error" not in str(results.get("gemini", "")):
        synthesis = ask_ai(
            f"Synthesize these two AI responses into one:\n\n"
            f"Perplexity: {results['perplexity']}\n\n"
            f"Gemini: {results['gemini']}\n\n"
            f"Provide a unified answer."
        )
        results["consensus"] = synthesis
    
    return results


# ============================================
# 5. KNOWLEDGE BASE - Base de connaissances
# ============================================
def load_kb():
    try:
        with open(KB_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"facts": [], "strategies": [], "lessons": [], "market_data": {}}


def save_kb(kb):
    with open(KB_FILE, 'w') as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)


def learn(fact, category="general"):
    """Apprend un nouveau fait et le stocke."""
    kb = load_kb()
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
        kb["market_data"][datetime.now().strftime("%Y-%m-%d")] = fact
    else:
        kb["facts"].append(entry)
    save_kb(kb)
    print(f"[KB] Appris: {fact[:80]}...")


def query_kb(query):
    """Recherche dans la base de connaissances."""
    kb = load_kb()
    results = []
    
    all_entries = kb.get("facts", []) + kb.get("strategies", []) + kb.get("lessons", [])
    for market_date, data in kb.get("market_data", {}).items():
        all_entries.append({"fact": data, "category": "market", "timestamp": market_date})
    
    query_lower = query.lower()
    for entry in all_entries:
        if any(word in entry.get("fact", "").lower() for word in query_lower.split()):
            results.append(entry)
    
    return results[:10]


# ============================================
# 6. TASK QUEUE - File de tâches autonomes
# ============================================
def add_task(task_type, params, priority=0):
    """Ajoute une tâche à la file d'attente."""
    queue = load_json(TASK_QUEUE_FILE, [])
    task = {
        "id": len(queue) + 1,
        "type": task_type,
        "params": params,
        "priority": priority,
        "status": "pending",
        "created": datetime.now().isoformat(),
    }
    queue.append(task)
    save_json(TASK_QUEUE_FILE, queue)
    return task["id"]


def load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def process_task(task):
    """Exécute une tâche."""
    task_type = task.get("type")
    params = task.get("params", {})
    
    if task_type == "search":
        return web_search(params.get("query", ""))
    elif task_type == "analyze":
        return analyze_market(params.get("symbole"))
    elif task_type == "solve":
        return solve_problem(params.get("problem"))
    elif task_type == "trade_analysis":
        return analyze_trading_performance()
    elif task_type == "learn":
        return learn(params.get("fact", ""), params.get("category", "general"))
    else:
        return {"error": f"Unknown task type: {task_type}"}


def run_task_queue():
    """Traite toutes les tâches en attente."""
    queue = load_json(TASK_QUEUE_FILE, [])
    pending = [t for t in queue if t.get("status") == "pending"]
    pending.sort(key=lambda x: x.get("priority", 0), reverse=True)
    
    for task in pending:
        print(f"[TASK] #{task['id']} {task['type']}...")
        result = process_task(task)
        task["status"] = "done"
        task["result"] = json.dumps(result, default=str)[:500]
        task["completed"] = datetime.now().isoformat()
        save_json(TASK_QUEUE_FILE, queue)
        print(f"[TASK] #{task['id']} done")
    
    return len(pending)


# ============================================
# 7. TRADING PERFORMANCE ANALYSIS
# ============================================
def analyze_trading_performance():
    """Analyse les performances de trading avec l'IA."""
    try:
        with open(os.path.join(DOSSIER, "paper_trading.json"), 'r') as f:
            pf = json.load(f)
    except Exception:
        return {"error": "paper_trading.json non trouvé"}
    
    trades = pf.get("trades", [])
    capital = pf.get("capital", 0)
    liquidites = pf.get("liquidites", 0)
    positions = pf.get("positions", [])
    
    # Stats
    gagnes = sum(1 for t in trades if t.get("pnl", 0) > 0)
    perdus = len(trades) - gagnes
    pnl_total = sum(t.get("pnl", 0) for t in trades)
    wr = gagnes / len(trades) * 100 if trades else 0
    
    summary = f"""
Trading Performance Summary:
- Capital: {capital}€
- Liquidités: {liquidites}€
- Positions ouvertes: {len(positions)}
- Trades fermés: {len(trades)} ({gagnes}G/{perdus}P, WR {wr:.0f}%)
- PnL total: {pnl_total:+.2f}€
"""
    
    # Analyse IA
    analysis = ask_ai(
        f"Analyze this trading performance and suggest improvements:\n{summary}\n\n"
        "Respond in JSON: {\"assessment\": \"overall assessment\", "
        "\"strengths\": [\"...\"], \"weaknesses\": [\"...\"], "
        "\"recommendations\": [\"...\"], \"risk_level\": 1-10}"
    )
    
    return {
        "summary": summary,
        "stats": {
            "capital": capital,
            "trades": len(trades),
            "wr": round(wr, 1),
            "pnl": round(pnl_total, 2),
        },
        "ai_analysis": analysis,
    }


# ============================================
# 8. TELEGRAM CHAT - Interface naturelle
# ============================================
def send_telegram(message):
    """Envoie un message Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message[:4000], "parse_mode": "HTML"},
            timeout=15
        )
    except Exception:
        pass


def handle_message(text):
    """Traite un message utilisateur en langage naturel."""
    text_lower = text.lower().strip()
    
    # Log
    log_chat("user", text)
    
    # Commandes spéciales
    if text_lower in ["status", "etat", "état"]:
        result = analyze_trading_performance()
        response = result.get("summary", "Erreur")
        send_telegram(response)
        return response
    
    if text_lower.startswith("analyser") or text_lower.startswith("analyse"):
        words = text.split()
        if len(words) > 1:
            symbole = words[1].upper()
            if not symbole.endswith("USDT"):
                symbole += "USDT"
            result = analyze_market(symbole)
            response = f"Analyse {symbole}:\n"
            if "technical" in result:
                t = result["technical"]
                response += f"Prix: {t['prix']}\n"
                response += f"Variation 24h: {t['variation_24h']}%\n"
                response += f"RSI: {t['rsi']}\n"
                response += f"Trend: {t['trend']}\n"
            if result.get("web_analysis"):
                response += f"\nAnalyse web: {str(result['web_analysis'])[:500]}...\n"
            send_telegram(response)
            log_chat("agent", response)
            return response
    
    if text_lower.startswith("recherche") or text_lower.startswith("search"):
        query = text[len("recherche"):].strip() or text[len("search"):].strip()
        if query:
            result = web_search(query)
            response = result.get("answer", str(result))[:3000]
            send_telegram(f"🔍 Recherche: {query}\n\n{response}")
            log_chat("agent", response)
            return response
    
    if text_lower.startswith("resoudre") or text_lower.startswith("solve"):
        problem = text[len("resoudre"):].strip() or text[len("solve"):].strip()
        if problem:
            result = solve_problem(problem)
            response = json.dumps(result.get("solution", result), indent=2, default=str)[:3000]
            send_telegram(f"🧠 Solution:\n{response}")
            log_chat("agent", response)
            return response
    
    if text_lower in ["news", "actu", "actualités"]:
        result = crypto_news_search()
        response = result.get("answer", str(result))[:3000]
        send_telegram(f"📰 Actus crypto:\n{response}")
        log_chat("agent", response)
        return response
    
    if text_lower in ["sentiment", "marche"]:
        result = market_sentiment_search()
        response = result.get("answer", str(result))[:3000]
        send_telegram(f"📊 Sentiment marché:\n{response}")
        log_chat("agent", response)
        return response
    
    # Conversation générale avec IA
    response = ask_ai(
        f"You are a crypto trading assistant. The user asks: {text}\n"
        f"Respond in French, concisly and helpfully."
    )
    send_telegram(str(response)[:3000])
    log_chat("agent", str(response))
    return response


def log_chat(role, message):
    """Logge la conversation."""
    entry = {
        "role": role,
        "message": message[:500],
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHAT_LOG, 'a') as f:
        f.write(json.dumps(entry) + "\n")


def telegram_poll():
    """Écoute les messages Telegram en continu."""
    if not TELEGRAM_TOKEN:
        print("[AGENT OS] Pas de token Telegram")
        return
    
    print("[AGENT OS] Écoute Telegram...")
    offset = 0
    
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            if r.status_code != 200:
                time.sleep(5)
                continue
            
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                if text:
                    print(f"[CHAT] {msg.get('from', {}).get('first_name', '?')}: {text}")
                    handle_message(text)
        except Exception as e:
            print(f"[AGENT OS] Erreur Telegram: {e}")
            time.sleep(10)


# ============================================
# 9. AUTONOMOUS LOOP - Boucle autonome
# ============================================
def autonomous_loop():
    """Boucle principale autonome."""
    print("=" * 60)
    print(f"AGENT OS - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    # 1. Traite la file de tâches
    nb_tasks = run_task_queue()
    if nb_tasks > 0:
        print(f"[AGENT OS] {nb_tasks} tâches traitées")
    
    # 2. Analyse du marché global
    if datetime.now().minute < 5:  # Une fois par heure
        print("[AGENT OS] Analyse du marché global...")
        sentiment = market_sentiment_search()
        if "answer" in sentiment:
            learn(sentiment["answer"][:200], "market")
    
    # 3. Vérifie les positions de trading
    try:
        with open(os.path.join(DOSSIER, "paper_trading.json"), 'r') as f:
            pf = json.load(f)
        positions = pf.get("positions", [])
        if positions:
            print(f"[AGENT OS] {len(positions)} positions ouvertes")
            for pos in positions[:5]:
                sym = pos.get("symbole", "?")
                pnl = pos.get("pnl", 0)
                print(f"  {sym}: {pnl:+.2f}€")
    except Exception:
        pass
    
    print("[AGENT OS] Cycle terminé")


# ============================================
# 10. STATUS
# ============================================
def status():
    """Affiche le statut complet du système."""
    print("=" * 60)
    print(f"AGENT OS - STATUS - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    # APIs
    print("\n=== APIs ===")
    print(f"  Perplexity: {'✓' if PPLX_KEY else '✗'}")
    print(f"  Gemini: {'✓' if GEMINI_KEY else '✗'}")
    print(f"  Telegram: {'✓' if TELEGRAM_TOKEN else '✗'}")
    print(f"  Dashboard: {'✓' if DASHBOARD_TOKEN else '✗'}")
    
    # Trading
    try:
        with open(os.path.join(DOSSIER, "paper_trading.json"), 'r') as f:
            pf = json.load(f)
        print(f"\n=== TRADING ===")
        print(f"  Capital: {pf.get('capital', 0)}€")
        print(f"  Liquidités: {pf.get('liquidites', 0)}€")
        print(f"  Positions: {len(pf.get('positions', []))}")
        trades = pf.get("trades", [])
        gagnes = sum(1 for t in trades if t.get("pnl", 0) > 0)
        print(f"  Trades: {len(trades)} ({gagnes}G/{len(trades)-gagnes}P)")
    except Exception:
        print("\n=== TRADING ===")
        print("  paper_trading.json non trouvé")
    
    # Knowledge base
    kb = load_kb()
    print(f"\n=== KNOWLEDGE BASE ===")
    print(f"  Faits: {len(kb.get('facts', []))}")
    print(f"  Stratégies: {len(kb.get('strategies', []))}")
    print(f"  Leçons: {len(kb.get('lessons', []))}")
    print(f"  Données marché: {len(kb.get('market_data', {}))}")
    
    # Task queue
    queue = load_json(TASK_QUEUE_FILE, [])
    pending = [t for t in queue if t.get("status") == "pending"]
    print(f"\n=== TASK QUEUE ===")
    print(f"  En attente: {len(pending)}")
    print(f"  Total: {len(queue)}")
    
    # Services
    print(f"\n=== SERVICES ===")
    import subprocess
    result = subprocess.run(
        ["systemctl", "is-active", "paper_trading.service"],
        capture_output=True, text=True
    )
    print(f"  paper_trading: {result.stdout.strip()}")
    result = subprocess.run(
        ["systemctl", "is-active", "dashboard.service"],
        capture_output=True, text=True
    )
    print(f"  dashboard: {result.stdout.strip()}")


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    elif len(sys.argv) > 1 and sys.argv[1] == "chat":
        telegram_poll()
    else:
        autonomous_loop()
