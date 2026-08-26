#!/usr/bin/env python3
"""
Agents Consensus — Intelligence multi-agents pour le bot de trading.

4 agents spécialisés débattent et produisent un score de conviction:
1. Agent Technique — analyse les indicateurs (MACD, RSI, Bollinger, VWAP)
2. Agent Macro — recherche actualité crypto en temps réel (Perplexity)
3. Agent Sentiment — Fear&Greed, regime de marché, flux on-chain
4. Agent Stratège — synthétise les 3 autres + donne le verdict final

Le score (-5 à +5) est ajouté au score existant du trend-following.
Si les API échouent (429/timeout), le module retourne 0 (ne bloque rien).

Optimisations:
- 1 seul appel Gemini (les 4 agents en 1 prompt structuré)
- 1 seul appel Perplexity (actualité macro)
- Cache 5 min (matche l'intervalle du bot)
- Rate limiting intégré (max 2 appels/tick)
"""

import os
import json
import time
import hashlib

# --- Cache simple ---
_cache = {"key": None, "data": None, "ts": 0}
_CACHE_TTL = 280  # 4min40 (sous l'intervalle de 5min)

# --- Rate limiter ---
_last_api_call = 0
_MIN_INTERVAL = 3.0  # min 3s entre appels API


def _rate_limit():
    """Évite le spam API."""
    global _last_api_call
    now = time.time()
    if now - _last_api_call < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - (now - _last_api_call))
    _last_api_call = time.time()


def _cache_key(signaux, prix):
    """Génère une clé de cache basée sur les symboles et prix."""
    sigles = sorted(set(s.get("symbole", "") for s in signaux))
    return hashlib.md5(f"{'-'.join(sigles)}-{len(signaux)}".encode()).hexdigest()


def _call_gemini(prompt):
    """Appel Gemini avec rate limiting."""
    try:
        import agent
        _rate_limit()
        return agent.gemini(prompt)
    except Exception as e:
        return f"[Erreur Gemini: {e}]"


def _call_perplexity(prompt):
    """Appel Perplexity avec rate limiting."""
    try:
        import agent
        _rate_limit()
        return agent.perplexity(prompt)
    except Exception as e:
        return f"[Erreur Perplexity: {e}]"


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


def _build_agent_prompt(signaux, prix, fg_value, fg_class):
    """Construit le prompt multi-agents pour Gemini."""
    # Prépare le résumé des signaux techniques
    signaux_texte = []
    for sig in signaux[:8]:  # max 8 signaux
        sym = sig.get("symbole", "?")
        nom = sig.get("nom", sym)
        score = sig.get("score", 0)
        strategie = sig.get("strategie", "?")
        raison = sig.get("raison", "")
        prix_entree = sig.get("prix_entree", 0)
        signaux_texte.append(f"- {nom} ({sym}): prix {prix_entree:.4f}€, score tech {score:+d}, stratégie {strategie}, raison: {raison[:80]}")

    signaux_str = "\n".join(signaux_texte) if signaux_texte else "Aucun signal technique"

    return f"""Tu es un comité de trading de 4 agents IA spécialisés. Analyse les signaux suivants et donne ton verdict.

CONTEXTE MARCHÉ:
- Fear & Greed Index: {fg_value}/100 ({fg_class})
- Capital: 1000€ paper trading, positions 80-500€ selon sentiment

SIGNAUX TECHNIQUES DÉTECTÉS:
{signaux_str}

Pour CHAQUE symbole avec un signal d'achat, réponds avec ce format exact:

SYMBOLE: [symbole]
TECHNIQUE: [analyse en 1 phrase: momentum, RSI, MACD, Bollinger]
MACRO: [contexte macro en 1 phrase: btc trend, secteur, news]
SENTIMENT: [analyse sentiment en 1 phrase: F&G={fg_value}, peur/avidité]
STRATÈGE: [verdict final: ACHAT_FORT / ACHAT / NEUTRE / ÉVITER]
SCORE: [nombre de -5 à +5]
RAISON: [1 phrase qui justifie le score]

Termine par:
CONSENSUS_GLOBAL: [nombre de -10 à +10]
RECOMMANDATION: [1 phrase sur le marché global]

Réponds uniquement au format ci-dessus, pas d'introduction ni conclusion."""


def analyser_avec_agents(signaux, prix, positions_ouvertes=None):
    """
    Lance l'analyse multi-agents sur les signaux.
    
    Args:
        signaux: liste des signaux d'achat détectés (avec score, symbole, etc.)
        prix: dict des prix actuels {symbole: prix}
        positions_ouvertes: liste des positions actuellement ouvertes
    
    Returns:
        dict: {symbole: {"score_agent": float, "verdict": str, "raison": str}}
        Si erreur API: retourne {} (ne bloque pas le pipeline existant)
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

    # Construit et envoie le prompt multi-agents (1 seul appel Gemini)
    prompt = _build_agent_prompt(signaux, prix, fg_value, fg_class)
    response = _call_gemini(prompt)

    # Récupère l'actualité macro (1 seul appel Perplexity)
    # Seulement si on a des signaux (évite le gaspillage)
    macro_context = ""
    try:
        macro_prompt = f"Résume en 3 phrases max l'actualité crypto importante aujourd'hui: BTC trend, news majeures, sentiment marché. Fear&Greed={fg_value}. Sois concis et factuel."
        macro_response = _call_perplexity(macro_prompt)
        if not macro_response.startswith("[Erreur"):
            macro_context = macro_response[:500]
    except Exception:
        pass  # Le macro est optionnel

    # Parse la réponse
    resultats = _parse_response(response)

    # Ajoute le contexte macro aux résultats
    if macro_context:
        for sym in resultats:
            resultats[sym]["macro_context"] = macro_context

    # Cache les résultats
    _cache["key"] = key
    _cache["data"] = resultats
    _cache["ts"] = now

    return resultats


def _parse_response(response):
    """Parse la réponse structurée de Gemini."""
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
                score_str = ligne.replace("SCORE:", "").strip()
                # Extract first number (handles "+3", "3", "-2", etc.)
                import re
                match = re.search(r'[-+]?\d+\.?\d*', score_str)
                if match:
                    entry["score_agent"] = float(match.group())
                else:
                    entry["score_agent"] = 0.0
            except Exception:
                entry["score_agent"] = 0.0
        elif ligne.startswith("STRATÈGE:") or ligne.startswith("STRATEGE:"):
            entry["verdict"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("RAISON:"):
            entry["raison"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("TECHNIQUE:"):
            entry["technique"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("MACRO:"):
            entry["macro"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("SENTIMENT:"):
            entry["sentiment"] = ligne.split(":", 1)[1].strip() if ":" in ligne else ""
        elif ligne.startswith("CONSENSUS_GLOBAL:"):
            try:
                val = ligne.replace("CONSENSUS_GLOBAL:", "").strip()
                import re
                match = re.search(r'[-+]?\d+\.?\d*', val)
                if match:
                    entry["consensus_global"] = float(match.group())
            except Exception:
                pass

    # Dernier symbole
    if symbole_courant and entry:
        resultats[symbole_courant] = entry

    return resultats


def enrichir_signaux(signaux, prix, positions_ouvertes=None):
    """
    Enrichit les signaux existants avec le consensus multi-agents.
    Ne remplace pas le trend-following — ajoute un bonus/malus au score.
    
    Args:
        signaux: liste des signaux (modifiés in-place)
        prix: dict des prix
        positions_ouvertes: positions ouvertes
    
    Returns:
        liste des signaux (les mêmes, enrichis)
    """
    try:
        resultats = analyser_avec_agents(signaux, prix, positions_ouvertes)
        if not resultats:
            print("  [AGENTS] Consensus indisponible (API) — trend-following seul")
            return signaux

        print(f"  [AGENTS] {len(resultats)} analyse(s) multi-agents reçues")
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

            # Le score agent modifie le score existant (ne le remplace pas)
            # ACHAT_FORT: +3, ACHAT: +1, NEUTRE: 0, ÉVITER: -3
            if "ACHAT_FORT" in verdict or "FORT" in verdict:
                bonus = min(score_agent, 3)
            elif "ACHAT" in verdict:
                bonus = min(score_agent, 1)
            elif "ÉVITER" in verdict or "EVITER" in verdict:
                print(f"  [AGENTS] {sym}: ÉVITER — {res.get('raison', '')[:60]}")
                continue  # Filtre le signal
            else:
                bonus = 0

            sig["score"] = sig.get("score", 0) + bonus
            sig["agent_verdict"] = verdict
            sig["agent_score"] = score_agent
            sig["agent_raison"] = res.get("raison", "")
            sig["agent_macro"] = res.get("macro_context", res.get("macro", ""))[:200]

            if bonus != 0:
                print(f"  [AGENTS] {sym}: {verdict} (score agent {score_agent:+.1f}, bonus {bonus:+.0f}) — {res.get('raison', '')[:50]}")
            signaux_filtrés.append(sig)

        # Consensus global
        for res in resultats.values():
            cg = res.get("consensus_global")
            if cg is not None:
                emoji = "🟢" if cg > 2 else ("🔴" if cg < -2 else "🟡")
                print(f"  [AGENTS] Consensus global: {emoji} {cg:+.1f}/10")
                break

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
        {"symbole": "BTCUSDT", "nom": "Bitcoin", "prix_entree": 62000, "score": 3, "strategie": "momentum", "raison": "MACD bull cross"},
        {"symbole": "ETHUSDT", "nom": "Ethereum", "prix_entree": 3400, "score": 2, "strategie": "breakout", "raison": "Bollinger squeeze"},
        {"symbole": "SOLUSDT", "nom": "Solana", "prix_entree": 145, "score": 4, "strategie": "macd_cross", "raison": "MACD bull + VWAP above"},
    ]
    prix_test = {"BTCUSDT": 62000, "ETHUSDT": 3400, "SOLUSDT": 145}
    
    print("=== TEST MULTI-AGENTS ===")
    resultats = enrichir_signaux(signaux_test, prix_test)
    print(f"\n{len(resultats)} signaux après consensus:")
    for s in resultats:
        print(f"  {s['symbole']}: score={s.get('score',0)}, agent={s.get('agent_verdict','N/A')}, raison={s.get('agent_raison','')[:60]}")
