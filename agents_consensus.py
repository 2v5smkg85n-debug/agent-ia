#!/usr/bin/env python3
"""
Agents Consensus — Intelligence multi-agents multi-modèles pour le bot de trading.

8 agents spécialisés × 5 modèles IA = consensus robuste.

Modèles utilisés (2 clés API seulement):
- Perplexity sonar (web temps réel)
- Perplexity sonar-reasoning (raisonnement logique)
- Perplexity sonar-pro (analyse approfondie)
- Gemini 2.5-flash (validation rapide)
- Gemini 2.5-pro (contre-analyse)

Tous les modèles sont appelés EN PARALLÈLE (threads) pour minimiser la latence.
Le consensus pondéré nécessite ≥3/5 modèles d'accord pour valider un ACHAT.
Si ≥2 modèles disent ÉVITER → signal filtré.

Si toutes les API échouent → retourne 0 (ne bloque pas le trend-following).

Optimisations:
- 5 appels parallèles (threads) = latence ~2-3s au lieu de 10s séquentiel
- Cache 5 min (matche l'intervalle du bot)
- Rate limiting intégré
- Prompts différenciés par modèle (évite corrélation)
"""

import os
import json
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Cache simple ---
_cache = {"key": None, "data": None, "ts": 0}
_CACHE_TTL = 280  # 4min40 (sous l'intervalle de 5min)

# --- Rate limiter ---
_last_api_call = 0
_MIN_INTERVAL = 1.0  # min 1s entre appels API (parallèle = moins de pression)
_verrou_rate = threading.Lock()

# --- Clés API (chargées une fois) ---
_PPLX_KEY = None
_GEM_KEY = None


def _load_keys():
    """Charge les clés API depuis l'env ou .env."""
    global _PPLX_KEY, _GEM_KEY
    if _PPLX_KEY and _GEM_KEY:
        return
    _PPLX_KEY = os.getenv("PPLX_API_KEY", "")
    _GEM_KEY = os.getenv("GEMINI_API_KEY", "")
    if not _PPLX_KEY or not _GEM_KEY:
        try:
            from dotenv import load_dotenv
            # Essaie plusieurs chemins
            for p in [os.path.expanduser("~/agent-ia/.env"), ".env", "/home/ubuntu/agent-ia/.env"]:
                if os.path.exists(p):
                    load_dotenv(p)
                    break
            _PPLX_KEY = os.getenv("PPLX_API_KEY", "")
            _GEM_KEY = os.getenv("GEMINI_API_KEY", "")
        except Exception:
            pass


def _rate_limit():
    """Évite le spam API (thread-safe)."""
    global _last_api_call
    with _verrou_rate:
        now = time.time()
        if now - _last_api_call < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - (now - _last_api_call))
        _last_api_call = time.time()


def _cache_key(signaux, prix):
    """Génère une clé de cache basée sur les symboles et prix."""
    sigles = sorted(set(s.get("symbole", "") for s in signaux))
    return hashlib.md5(f"{'-'.join(sigles)}-{len(signaux)}".encode()).hexdigest()


# ============================================
# APPELS API PAR MODÈLE
# ============================================

def _call_perplexity_model(prompt, model_name):
    """Appel Perplexity avec un modèle spécifique. Même clé API."""
    _load_keys()
    if not _PPLX_KEY:
        return model_name, "[Erreur: pas de clé Perplexity]"
    import requests
    _rate_limit()
    try:
        url = "https://api.perplexity.ai/chat/completions"
        headers = {"Authorization": f"Bearer {_PPLX_KEY}", "Content-Type": "application/json"}
        body = {"model": model_name, "messages": [{"role": "user", "content": prompt}]}
        r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code == 200:
            return model_name, r.json()["choices"][0]["message"]["content"]
        elif r.status_code == 429:
            return model_name, f"[Erreur: 429 {model_name}]"
        else:
            return model_name, f"[Erreur: {r.status_code} {model_name}]"
    except Exception as e:
        return model_name, f"[Erreur {model_name}: {e}]"


def _call_gemini_model(prompt, model_name):
    """Appel Gemini avec un modèle spécifique. Même clé API."""
    _load_keys()
    if not _GEM_KEY:
        return model_name, "[Erreur: pas de clé Gemini]"
    import requests
    _rate_limit()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={_GEM_KEY}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        if r.status_code == 200:
            return model_name, r.json()["candidates"][0]["content"]["parts"][0]["text"]
        elif r.status_code == 429:
            return model_name, f"[Erreur: 429 {model_name}]"
        else:
            return model_name, f"[Erreur: {r.status_code} {model_name}]"
    except Exception as e:
        return model_name, f"[Erreur {model_name}: {e}]"


# ============================================
# PROMPTS DIFFÉRENCIÉS PAR MODÈLE
# ============================================

def _build_prompt_base(signaux, prix, fg_value, fg_class):
    """Prompt commun de base avec les données."""
    signaux_texte = []
    for sig in signaux[:8]:
        sym = sig.get("symbole", "?")
        nom = sig.get("nom", sym)
        score = sig.get("score", 0)
        strategie = sig.get("strategie", "?")
        raison = sig.get("raison", "")
        prix_entree = sig.get("prix_entree", 0)
        signaux_texte.append(f"- {nom} ({sym}): prix {prix_entree:.4f}€, score tech {score:+d}, stratégie {strategie}, raison: {raison[:80]}")
    signaux_str = "\n".join(signaux_texte) if signaux_texte else "Aucun signal technique"
    return signaux_str, fg_value, fg_class


def _prompt_sonar(signaux_str, fg_value, fg_class):
    """Perplexity sonar — focus web/actualité temps réel."""
    return f"""Tu es un analyste crypto expert. Analyse ces signaux avec les DONNÉES DU WEB en temps réel.

CONTEXTE: Fear & Greed Index: {fg_value}/100 ({fg_class})
SIGNAUX:
{signaux_str}

Pour CHAQUE symbole, vérifie avec l'actualité récente si c'est un bon moment pour acheter.
Format de réponse (un bloc par symbole):
SYMBOLE: [symbole]
VERDICT: [ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase basée sur l'actualité web]
"""


def _prompt_sonar_reasoning(signaux_str, fg_value, fg_class):
    """Perplexity sonar-reasoning — focus raisonnement logique."""
    return f"""Tu es un logicien du trading. Analyse ces signaux avec un RAISONNEMENT strict cause-effet.

CONTEXTE: Fear & Greed Index: {fg_value}/100 ({fg_class})
SIGNAUX:
{signaux_str}

Pour CHAQUE symbole, raisonne étape par étape:
1. Le signal technique est-il logiquement valide?
2. Y a-t-il une contradiction entre indicateurs?
3. Le risk/reward est-il favorable?

Format de réponse (un bloc par symbole):
SYMBOLE: [symbole]
VERDICT: [ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase de raisonnement logique]
"""


def _prompt_sonar_pro(signaux_str, fg_value, fg_class):
    """Perplexity sonar-pro — analyse approfondie multi-facteurs."""
    return f"""Tu es un comité de trading de 8 agents spécialisés. Analyse approfondie.

CONTEXTE MARCHÉ:
- Fear & Greed Index: {fg_value}/100 ({fg_class})
- Capital: 1000€ paper trading

SIGNAUX TECHNIQUES:
{signaux_str}

Pour CHAQUE symbole avec un signal d'achat, analyse sous 8 angles:
TECHNIQUE: [momentum, RSI, MACD, Bollinger en 1 phrase]
MACRO: [contexte macro en 1 phrase]
SENTIMENT: [analyse sentiment en 1 phrase]
RISQUE: [risk/reward en 1 phrase]
CONTRARIEN: [argument baissier en 1 phrase]
MOMENTUM: [force tendance en 1 phrase]
LIQUIDITÉ: [spread et volume en 1 phrase]
STRATÈGE: [verdict: ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase de synthèse]
"""


def _prompt_gemini_flash(signaux_str, fg_value, fg_class):
    """Gemini 2.5-flash — validation rapide, focus risque."""
    return f"""Tu es un gestionnaire de risque. Valide ou rejette ces signaux rapidement.

CONTEXTE: F&G={fg_value}/100 ({fg_class})
SIGNAUX:
{signaux_str}

Pour CHAQUE symbole, réponds:
SYMBOLE: [symbole]
VERDICT: [ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase sur le risque principal]
"""


def _prompt_gemini_pro(signaux_str, fg_value, fg_class):
    """Gemini 2.5-pro — contre-analyse, devil's advocate."""
    return f"""Tu es un analyste contrarien. Ton rôle est de CHERCHER les failles dans ces signaux d'achat.

CONTEXTE: F&G={fg_value}/100 ({fg_class})
SIGNAUX:
{signaux_str}

Pour CHAQUE symbole, trouve le meilleur argument CONTRE l'achat:
SYMBOLE: [symbole]
VERDICT: [ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase: pourquoi ça pourrait mal tourner]
"""


# ============================================
# APPEL PARALLÈLE DE TOUS LES MODÈLES
# ============================================

def _call_all_models_parallel(signaux, prix, fg_value, fg_class):
    """
    Appelle les 5 modèles en parallèle (threads).
    Retourne {model_name: response_text}.
    """
    signaux_str, _, _ = _build_prompt_base(signaux, prix, fg_value, fg_class)

    # Prépare les 5 tâches
    tasks = [
        ("sonar",        _call_perplexity_model, _prompt_sonar(signaux_str, fg_value, fg_class), "sonar"),
        ("reasoning",    _call_perplexity_model, _prompt_sonar_reasoning(signaux_str, fg_value, fg_class), "sonar-reasoning"),
        ("pro",          _call_perplexity_model, _prompt_sonar_pro(signaux_str, fg_value, fg_class), "sonar-pro"),
        ("gem-flash",    _call_gemini_model,     _prompt_gemini_flash(signaux_str, fg_value, fg_class), "gemini-2.5-flash"),
        ("gem-pro",      _call_gemini_model,     _prompt_gemini_pro(signaux_str, fg_value, fg_class), "gemini-2.5-pro"),
    ]

    results = {}
    errors = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for label, func, prompt, model_name in tasks:
            future = executor.submit(func, prompt, model_name)
            futures[future] = label

        for future in as_completed(futures, timeout=90):
            label = futures[future]
            try:
                model_name, response = future.result(timeout=90)
                if response and not response.startswith("[Erreur"):
                    results[label] = response
                else:
                    errors += 1
                    print(f"  [AGENTS] {label} échec: {response[:60] if response else 'vide'}")
            except Exception as e:
                errors += 1
                print(f"  [AGENTS] {label} timeout/erreur: {e}")

    return results, errors


# ============================================
# PARSING ET CONSENSUS
# ============================================

def _parse_response(response):
    """Parse la réponse structurée d'un modèle. Retourne {symbole: {score, verdict, raison}}."""
    resultats = {}
    if not response or response.startswith("[Erreur"):
        return resultats

    lignes = response.strip().split("\n")
    symbole_courant = None
    entry = {}

    for ligne in lignes:
        ligne = ligne.strip()
        if ligne.startswith("SYMBOLE:"):
            if symbole_courant and entry:
                resultats[symbole_courant] = entry
            symbole_courant = ligne.replace("SYMBOLE:", "").strip()
            entry = {}
        elif ligne.startswith("SCORE:"):
            try:
                import re
                match = re.search(r'[-+]?\d+\.?\d*', ligne.replace("SCORE:", "").strip())
                entry["score"] = float(match.group()) if match else 0.0
            except Exception:
                entry["score"] = 0.0
        elif ligne.startswith("VERDICT:") or ligne.startswith("STRATÈGE:") or ligne.startswith("STRATEGE:"):
            entry["verdict"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("RAISON:"):
            entry["raison"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("CONSENSUS_GLOBAL:"):
            try:
                import re
                val = ligne.replace("CONSENSUS_GLOBAL:", "").strip()
                match = re.search(r'[-+]?\d+\.?\d*', val)
                if match:
                    entry["consensus_global"] = float(match.group())
            except Exception:
                pass

    if symbole_courant and entry:
        resultats[symbole_courant] = entry

    return resultats


def _build_consensus(all_results, symboles):
    """
    Fusionne les résultats des 5 modèles en un consensus par symbole.

    Règles:
    - ≥3/5 modèles disent ACHAT ou ACHAT_FORT → consensus ACHAT
    - ≥2/5 modèles disent ÉVITER → consensus ÉVITER (filtre)
    - Sinon → NEUTRE (bonus 0)
    - Score final = moyenne pondérée des scores
    - ACHAT_FORT si ≥2 modèles disent ACHAT_FORT ET consensus ACHAT

    Returns: {symbole: {score_agent, verdict, raison, models_agree, models_avoid, models_total}}
    """
    consensus = {}

    for sym in symboles:
        # Variations du symbole (BTCUSDT, BTC, etc.)
        sym_variants = [sym, sym.replace("USDT", ""), sym.replace("USDT", "USDT")]
        sym_upper = sym.upper()
        sym_short = sym.replace("USDT", "").upper()

        scores = []
        verdicts = []
        raisons = []
        nb_achat = 0
        nb_achat_fort = 0
        nb_eviter = 0
        nb_neutre = 0
        models_total = 0

        for model_name, model_results in all_results.items():
            # Cherche le symbole dans les résultats de ce modèle
            res = None
            for variant in sym_variants:
                if variant in model_results:
                    res = model_results[variant]
                    break
            if not res:
                # Recherche case-insensitive
                for key in model_results:
                    if key.upper() == sym_upper or key.upper() == sym_short:
                        res = model_results[key]
                        break
            if not res:
                continue

            models_total += 1
            score = res.get("score", 0)
            verdict = res.get("verdict", "").upper()

            scores.append(score)
            verdicts.append(verdict)
            raisons.append(res.get("raison", ""))

            if "ACHAT_FORT" in verdict or "FORT" in verdict:
                nb_achat_fort += 1
                nb_achat += 1
            elif "ACHAT" in verdict:
                nb_achat += 1
            elif "ÉVITER" in verdict or "EVITER" in verdict:
                nb_eviter += 1
            else:
                nb_neutre += 1

        if models_total == 0:
            continue

        # Score moyen pondéré (sonar-pro a un peu plus de poids car analyse complète)
        if scores:
            score_moyen = sum(scores) / len(scores)
        else:
            score_moyen = 0.0

        # Détermine le verdict de consensus
        if nb_eviter >= 2:
            verdict_consensus = "ÉVITER"
        elif nb_achat >= 3:
            if nb_achat_fort >= 2:
                verdict_consensus = "ACHAT_FORT"
            else:
                verdict_consensus = "ACHAT"
        else:
            verdict_consensus = "NEUTRE"

        # Raison: prend la plus informative (la plus longue)
        raison_finale = max(raisons, key=len) if raisons else ""

        consensus[sym] = {
            "score_agent": round(score_moyen, 1),
            "verdict": verdict_consensus,
            "raison": raison_finale,
            "models_agree": nb_achat,
            "models_avoid": nb_eviter,
            "models_total": models_total,
            "models_achat_fort": nb_achat_fort,
        }

    return consensus


# ============================================
# FONCTION PRINCIPALE
# ============================================

def _get_fear_greed():
    """Récupère le Fear & Greed index."""
    try:
        from sentiment_marche import fetch_fear_greed
        data = fetch_fear_greed(limit=1)
        if data:
            v = int(data[0].get("value", 50))
            c = data[0].get("value_classification", "Neutral")
            return v, c
    except Exception:
        pass
    return 50, "Neutral"


def analyser_avec_agents(signaux, prix, positions_ouvertes=None):
    """
    Lance l'analyse multi-agents multi-modèles sur les signaux.

    5 modèles IA analysent chaque signal en parallèle.
    Le consensus nécessite ≥3/5 modèles d'accord pour ACHAT.
    Si ≥2 modèles disent ÉVITER → signal filtré.

    Args:
        signaux: liste des signaux d'achat détectés
        prix: dict des prix actuels {symbole: prix}
        positions_ouvertes: liste des positions ouvertes

    Returns:
        dict: {symbole: {score_agent, verdict, raison, models_agree, ...}}
        Si erreur API: retourne {} (ne bloque pas le pipeline)
    """
    if not signaux:
        return {}

    # Vérifie le cache
    key = _cache_key(signaux, prix)
    now = time.time()
    if _cache["key"] == key and now - _cache["ts"] < _CACHE_TTL:
        return _cache["data"]

    # Récupère le sentiment
    fg_value, fg_class = _get_fear_greed()

    # Appelle les 5 modèles en parallèle
    all_results, errors = _call_all_models_parallel(signaux, prix, fg_value, fg_class)

    if not all_results:
        print(f"  [AGENTS] Tous les modèles ont échoué ({errors} erreurs) — trend-following seul")
        return {}

    print(f"  [AGENTS] {len(all_results)}/5 modèles ont répondu")

    # Parse chaque réponse
    parsed = {}
    for model_name, response in all_results.items():
        parsed[model_name] = _parse_response(response)

    # Liste des symboles à analyser
    symboles = [s.get("symbole", "") for s in signaux if s.get("symbole")]

    # Construit le consensus
    resultats = _build_consensus(parsed, symboles)

    # Cache les résultats
    _cache["key"] = key
    _cache["data"] = resultats
    _cache["ts"] = now

    return resultats


def enrichir_signaux(signaux, prix, positions_ouvertes=None):
    """
    Enrichit les signaux existants avec le consensus multi-modèles.
    Ne remplace pas le trend-following — ajoute un bonus/malus au score.

    Règles de scoring:
    - ACHAT_FORT (≥3/5 agree, ≥2 FORT): +3 au score
    - ACHAT (≥3/5 agree): +1 au score
    - NEUTRE: +0 (ne modifie pas)
    - ÉVITER (≥2/5 avoid): signal FILTRÉ

    Args:
        signaux: liste des signaux (modifiés in-place)
        prix: dict des prix
        positions_ouvertes: positions ouvertes

    Returns:
        liste des signaux (les mêmes, enrichis ou filtrés)
    """
    try:
        resultats = analyser_avec_agents(signaux, prix, positions_ouvertes)
        if not resultats:
            if not signaux:
                print("  [AGENTS] 0 signal à analyser")
            else:
                print("  [AGENTS] Consensus indisponible (API) — trend-following seul")
            return signaux

        print(f"  [AGENTS] {len(resultats)} consensus multi-modèles construits")
        signaux_filtrés = []

        for sig in signaux:
            sym = sig.get("symbole", "")
            # Cherche le résultat (peut être avec ou sans suffixe USDT)
            res = resultats.get(sym, resultats.get(sym.replace("USDT", ""), {}))
            if not res:
                signaux_filtrés.append(sig)
                continue

            score_agent = res.get("score_agent", 0)
            verdict = res.get("verdict", "").upper()
            models_agree = res.get("models_agree", 0)
            models_avoid = res.get("models_avoid", 0)
            models_total = res.get("models_total", 0)
            models_fort = res.get("models_achat_fort", 0)

            # Le score agent modifie le score existant (ne le remplace pas)
            if "ACHAT_FORT" in verdict or "FORT" in verdict:
                bonus = min(score_agent, 3)
            elif "ACHAT" in verdict:
                bonus = min(score_agent, 1)
            elif "ÉVITER" in verdict or "EVITER" in verdict:
                print(f"  [AGENTS] {sym}: ÉVITER ({models_avoid}/{models_total} modèles contre) — {res.get('raison', '')[:60]}")
                continue  # Filtre le signal
            else:
                bonus = 0

            sig["score"] = sig.get("score", 0) + bonus
            sig["agent_verdict"] = verdict
            sig["agent_score"] = score_agent
            sig["agent_raison"] = res.get("raison", "")
            sig["agent_models"] = f"{models_agree}/{models_total} agree, {models_avoid} avoid, {models_fort} fort"

            if bonus != 0:
                print(f"  [AGENTS] {sym}: {verdict} ({models_agree}/{models_total} modèles d'accord, score moy {score_agent:+.1f}, bonus {bonus:+.0f}) — {res.get('raison', '')[:50]}")
            else:
                print(f"  [AGENTS] {sym}: NEUTRE ({models_agree}/{models_total} agree, {models_avoid} avoid) — trend-following seul")

            signaux_filtrés.append(sig)

        return signaux_filtrés

    except Exception as e:
        print(f"  [AGENTS] Erreur: {e} — trend-following seul")
        return signaux


# ============================================
# TEST STANDALONE
# ============================================
if __name__ == "__main__":
    # Test avec des signaux factices
    signaux_test = [
        {"symbole": "BTCUSDT", "nom": "Bitcoin", "prix_entree": 78000, "score": 3, "strategie": "momentum", "raison": "MACD bull cross"},
        {"symbole": "ETHUSDT", "nom": "Ethereum", "prix_entree": 2400, "score": 2, "strategie": "breakout", "raison": "Bollinger squeeze"},
        {"symbole": "SOLUSDT", "nom": "Solana", "prix_entree": 100, "score": 4, "strategie": "macd_cross", "raison": "MACD bull + VWAP above"},
    ]
    prix_test = {"BTCUSDT": 78000, "ETHUSDT": 2400, "SOLUSDT": 100}

    print("=== TEST MULTI-MODÈLES (5 IA en parallèle) ===")
    print("Modèles: Perplexity sonar + sonar-reasoning + sonar-pro + Gemini 2.5-flash + 2.5-pro")
    print()

    t0 = time.time()
    resultats = enrichir_signaux(signaux_test, prix_test)
    elapsed = time.time() - t0

    print(f"\nTemps total: {elapsed:.1f}s")
    print(f"\n{len(resultats)} signaux après consensus:")
    for s in resultats:
        print(f"  {s['symbole']}: score={s.get('score',0)}, verdict={s.get('agent_verdict','N/A')}, models={s.get('agent_models','N/A')}")
        print(f"    raison: {s.get('agent_raison','')[:80]}")
