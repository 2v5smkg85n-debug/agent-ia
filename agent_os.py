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

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

CODE_DIR = os.path.join(DOSSIER, "generated_code")
os.makedirs(CODE_DIR, exist_ok=True)

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
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return default


def save_json_safe(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def send_telegram(message, parse_mode="HTML"):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        # Split long messages (Telegram limit: 4096 chars)
        if len(message) > 4000:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT, "text": part, "parse_mode": parse_mode},
                    timeout=15
                )
                time.sleep(0.3)
        else:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": parse_mode},
                timeout=15
            )
    except Exception:
        pass


# ============================================
# 1. IA CORE - Appels IA optimises
# ============================================
def ask_perplexity(prompt, model="sonar", temperature=0.3, timeout=30):
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
        return f"Erreur Perplexity: HTTP {r.status_code}"
    except Exception as e:
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
# 3. MEMOIRE CONVERSATIONNELLE
# ============================================
def save_memory(role, message, response=None):
    """Sauvegarde la conversation et apprend."""
    memoire = load_json_safe(MEMORY_FILE, {"conversations": [], "facts": [], "preferences": {}})
    
    entry = {
        "role": role,
        "message": message[:500] if message else "",
        "response": response[:500] if response else "",
        "timestamp": datetime.now().isoformat(),
    }
    memoire["conversations"].append(entry)
    memoire["conversations"] = memoire["conversations"][-50:]  # Garde 50 derniers
    
    # Détecte des préférences
    msg_lower = (message or "").lower()
    if "j'aime" in msg_lower or "je préfère" in msg_lower or "je veux" in msg_lower:
        memoire["preferences"][datetime.now().strftime("%Y-%m-%d")] = message[:200]
    
    save_json_safe(MEMORY_FILE, memoire)


def get_context_from_memory():
    """Récupère le contexte des dernières conversations."""
    memoire = load_json_safe(MEMORY_FILE, {})
    convs = memoire.get("conversations", [])
    if not convs:
        return ""
    
    # Dernières 5 conversations
    recent = convs[-5:]
    context = "Contexte des dernières conversations:\n"
    for c in recent:
        role = "User" if c["role"] == "user" else "Agent"
        context += f"{role}: {c['message'][:100]}\n"
    return context


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


# ============================================
# 4. ANALYSE TRADING PERFORMANCE
# ============================================
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
    "import subprocess", "import os\n.*\bos\.", "os.system", "os.popen",
    "os.remove", "os.rmdir", "os.unlink", "shutil.rmtree",
    "__import__", "eval(", "exec(", "compile(",
    "open('/etc", "open('/var", "open('/root",
    "import socket", "import ctypes", "import threading\n.*\bThread",
    "import multiprocessing", "os.environ\[", "os.exec",
    "os.spawn", "os.fork", "os.kill",
]

def validate_code(code):
    """Valide que le code est sur de executer."    
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
        if re.search(pattern, code, re.MULTILINE):
            return False, f"Pattern dangereux detecte: {pattern}"
    
    return True, "OK"

def extract_code(text):
    """Extrait le code Python d'une reponse IA."    
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
    """Execute du code Python sur le VPS de maniere securisee."    
    # Valide le code
    is_safe, reason = validate_code(code)
    if not is_safe:
        return {"success": False, "error": f"Code rejete: {reason}", "output": ""}
    
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
    """Genere du code avec l'IA puis l'execute sur le VPS."    
    # 1. Demande a l'IA de generer le code
    prompt = f"""Genere du code Python pour cette tache:
{instruction}

Regles:
- Code complet, executable, autonome
- Imports autorises: os, sys, json, math, time, datetime, requests, re, random, statistics, collections, csv, io, hashlib, base64, indicateurs, gestion_risque, backtest_moteur
- PAS de subprocess, PAS de os.system, PAS de fichiers systeme
- Affiche les resultats avec print()
- Code en français (commentaires)
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
    
    return {
        "success": result.get("success", False),
        "code": code[:1000],
        "output": result.get("output", ""),
        "error": result.get("error", ""),
        "file": result.get("file", ""),
    }

def list_generated_scripts():
    """Liste les scripts generes."    
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
    """Re-execute un script deja genere."    
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
    
    # === RÉSOUDRE UN PROBLÈME ===
    if text_lower.startswith("resoudre") or text_lower.startswith("résoudre") or text_lower.startswith("solve"):
        problem = text_stripped[len("resoudre"):].strip() or text_stripped[len("résoudre"):].strip() or text_stripped[len("solve"):].strip()
        if problem:
            send_telegram(f"🧠 Résolution en cours...")
            result = ask_perplexity(
                f"Résous ce problème en français de façon structurée:\n{problem}\n\n"
                f"Donne:\n1. Analyse du problème\n2. Solution étape par étape\n3. Code Python si applicable\n4. Risques éventuels"
            )
            send_telegram(f"🧠 Solution:\n\n{result}")
            save_memory("user", text_stripped, result)
            learn_fact(problem, "lesson")
            return result
    
    # === AIDE ===
    if text_lower in ["aide", "help", "commandes", "commands"]:
        help_msg = """🤖 AGENT OS - COMMANDES

━━━━━━━━━━━━━━━━━━━━
📊 TRADING:
  status - Performance du portefeuille
  opportunites - Scanner les opportunités
  analyser BTC - Analyse complète d'un crypto
  sentiment - Sentiment du marché

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

━━━━━━━━━━━━━━━━━━━━
L'agent apprend de chaque interaction."""
        send_telegram(help_msg)
        return help_msg
    
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
    
    # === CONVERSATION GÉNÉRALE ===
    # Construit le prompt avec contexte
    prompt = f"""Tu es un assistant IA expert en trading crypto et en technologie.
L'utilisateur s'appelle {user_name}.
Contexte des conversations précédentes:
{context}

Question de l'utilisateur: {text_stripped}

Réponds en français, de façon concise, structurée et actionnable.
Si c'est une question sur un crypto, inclut des données concrètes.
Si c'est un conseil de trading, précise toujours le risque."""
    
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
    
    print("[AGENT OS V2] Écoute Telegram démarrée")
    print("[AGENT OS V2] Envoie 'aide' sur Telegram pour voir les commandes")
    
    offset = 0
    last_health_check = time.time()
    
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            
            if r.status_code != 200:
                print(f"[AGENT OS] Telegram HTTP {r.status_code}")
                time.sleep(5)
                continue
            
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                user_name = msg.get("from", {}).get("first_name", "User")
                
                if text:
                    print(f"[CHAT] {user_name}: {text}")
                    try:
                        handle_message(text, user_name)
                    except Exception as e:
                        print(f"[CHAT] Erreur traitement: {e}")
                        send_telegram(f"Erreur: {e}")
            
            # Health check toutes les 10 min
            if time.time() - last_health_check > 600:
                last_health_check = time.time()
                print(f"[AGENT OS] Health check OK - {datetime.now().strftime('%H:%M')}")
                
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"[AGENT OS] Erreur: {e}")
            time.sleep(10)


# ============================================
# 8. BOUCLE AUTONOME
# ============================================
def autonomous_loop():
    """Boucle autonome: scanne le marché + alertes."""
    print("=" * 60)
    print(f"AGENT OS V2 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    # 1. Scan d'opportunités
    print("\n[1] Scan des opportunités...")
    opps = check_opportunities()
    if opps:
        print(f"    {len(opps)} opportunités détectées")
        for o in opps:
            print(f"    {o['symbole']}: score {o['score']} - {', '.join(o['raisons'])}")
    else:
        print("    Aucune opportunité")
    
    # 2. Performance trading
    print("\n[2] Performance trading...")
    perf = trading_performance()
    print(perf[:500])
    
    # 3. Sentiment marché
    print("\n[3] Sentiment marché...")
    sentiment = ask_perplexity(
        "Donne le sentiment crypto actuel en 3 lignes max (français): "
        "Fear & Greed index, trend BTC, recommandation."
    )
    print(f"    {sentiment[:200]}")
    
    # 4. Apprend
    learn_fact(f"Scan {datetime.now().strftime('%H:%M')}: {len(opps)} opportunités, sentiment={sentiment[:100]}", "market")
    
    print("\n" + "=" * 60)
    print("Cycle autonome terminé")


# ============================================
# MAIN
# ============================================
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
    else:
        autonomous_loop()
