#!/usr/bin/env python3
"""
Consensus Multi-IA — Croise les analyses de Perplexity + Gemini pour chaque décision de trading.

FONCTIONNEMENT:
  1. Demande à Perplexity d'analyser le signal (ACHAT/VENTE/HOLD + conviction 0-100)
  2. Demande à Gemini d'analyser le même signal
  3. Si les deux IA sont d'accord (même direction) -> signal validé avec score boosté
  4. Si désaccord -> signal affaibli ou rejeté
  5. Si une IA est indisponible -> utilise l'autre avec un malus de confiance

SÉCURITÉ:
  - Timeout 30s par API
  - Cache 5min pour éviter le spam API
  - Fallback automatique si une IA échoue
"""
import json
import os
import time
import urllib.request
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_CACHE = os.path.join(DOSSIER, "consensus_cache.json")
CACHE_TTL = 300  # 5 minutes


def charger_cache():
    try:
        with open(FICHIER_CACHE) as f:
            return json.load(f)
    except Exception:
        return {}


def sauver_cache(cache):
    try:
        with open(FICHIER_CACHE, "w") as f:
            json.dump(cache, f, indent=2, default=str)
    except Exception:
        pass


def analyse_perplexity(symbole, prix, rsi, sma20, sma50, variation_24h, volume):
    """Demande à Perplexity d'analyser un actif crypto."""
    try:
        pplx_key = os.getenv("PPLX_API_KEY", "")
        if not pplx_key:
            return None, "Pas de clé Perplexity"

        prompt = f"""Analyse cet actif crypto pour un trade court terme (swing trading, horizon 1-4h):

Actif: {symbole}
Prix actuel: {prix}$
RSI: {rsi}
SMA20: {sma20}
SMA50: {sma50}
Variation 24h: {variation_24h}%
Volume: {volume}

Réponds en JSON strictement avec ce format (sans autre texte):
{{"verdict": "ACHAT" ou "VENTE" ou "HOLD", "conviction": 0-100, "raison": "explication courte en français"}}"""

        url = "https://api.perplexity.ai/v1/sonar"
        data = json.dumps({
            "model": "sonar",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
            "search_context_size": "low",
        }).encode()

        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {pplx_key}"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result["choices"][0]["message"]["content"]
            # Nettoyer les citations
            import re
            text = re.sub(r'\[\d+\]', '', text)
            # Extraire le JSON
            return extraire_json(text), "perplexity"
    except Exception as e:
        return None, f"Erreur Perplexity: {e}"


def analyse_gemini(symbole, prix, rsi, sma20, sma50, variation_24h, volume):
    """Demande à Gemini d'analyser un actif crypto."""
    try:
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_key:
            return None, "Pas de clé Gemini"

        prompt = f"""Analyse cet actif crypto pour un trade court terme (swing trading, horizon 1-4h):

Actif: {symbole}
Prix actuel: {prix}$
RSI: {rsi}
SMA20: {sma20}
SMA50: {sma50}
Variation 24h: {variation_24h}%
Volume: {volume}

Réponds en JSON strictement avec ce format (sans autre texte):
{{"verdict": "ACHAT" ou "VENTE" ou "HOLD", "conviction": 0-100, "raison": "explication courte en français"}}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        data = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}
        }).encode()

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return extraire_json(text), "gemini"
    except Exception as e:
        return None, f"Erreur Gemini: {e}"


def extraire_json(text):
    """Extrait un objet JSON d'un texte qui peut contenir du markdown."""
    import re
    # Supprimer markdown
    text = text.replace("```json", "").replace("```", "").strip()
    # Chercher le JSON
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    # Essayer de parser directement
    try:
        return json.loads(text)
    except Exception:
        return None


def consensus_multi_ia(symbole, prix, rsi, sma20, sma50, variation_24h, volume):
    """
    Point d'entrée principal: demande à Perplexity ET Gemini d'analyser un actif.
    
    Returns:
        {
            "verdict": "ACHAT" / "VENTE" / "HOLD",
            "conviction": 0-100,
            "consensus": True/False (les deux IA sont d'accord),
            "score_boost": int (boost à ajouter au score du signal),
            "perplexity": dict (analyse Perplexity),
            "gemini": dict (analyse Gemini),
            "source": str,
        }
    """
    # Vérifier le cache
    cache = charger_cache()
    cache_key = f"{symbole}_{int(prix * 100)}"
    if cache_key in cache:
        cached = cache[cache_key]
        if time.time() - cached.get("timestamp", 0) < CACHE_TTL:
            return cached["result"]

    # Lancer les deux analyses
    print(f"  [CONSENSUS] Analyse {symbole} - Perplexity + Gemini...")

    pplx_result, pplx_source = analyse_perplexity(symbole, prix, rsi, sma20, sma50, variation_24h, volume)
    gemini_result, gemini_source = analyse_gemini(symbole, prix, rsi, sma20, sma50, variation_24h, volume)

    # Cas: les deux IA ont répondu
    if pplx_result and gemini_result:
        pplx_verdict = pplx_result.get("verdict", "HOLD").upper()
        gemini_verdict = gemini_result.get("verdict", "HOLD").upper()
        pplx_conv = int(pplx_result.get("conviction", 50))
        gemini_conv = int(gemini_result.get("conviction", 50))

        # Consensus: même direction
        if pplx_verdict == gemini_verdict:
            consensus = True
            verdict = pplx_verdict
            conviction = (pplx_conv + gemini_conv) // 2
            # Score boost: consensus fort = gros boost
            if verdict == "ACHAT" and conviction >= 70:
                score_boost = 3
            elif verdict == "ACHAT" and conviction >= 50:
                score_boost = 2
            elif verdict == "ACHAT":
                score_boost = 1
            elif verdict == "VENTE":
                score_boost = -2
            else:
                score_boost = 0
            raison = f"Consensus ACHAT ({pplx_conv}+{gemini_conv}=2IA d'accord)"
        else:
            # Désaccord
            consensus = False
            # Prendre la direction avec la conviction la plus haute
            if pplx_conv > gemini_conv:
                verdict = pplx_verdict
                conviction = pplx_conv
            else:
                verdict = gemini_verdict
                conviction = gemini_conv
            # Désaccord = signal faible
            score_boost = 0
            raison = f"Désaccord IA: Perplexity={pplx_verdict}({pplx_conv}) vs Gemini={gemini_verdict}({gemini_conv})"

        result = {
            "verdict": verdict,
            "conviction": conviction,
            "consensus": consensus,
            "score_boost": score_boost,
            "perplexity": pplx_result,
            "gemini": gemini_result,
            "raison": raison,
            "source": "perplexity+gemini",
            "timestamp": time.time(),
        }

    # Cas: une seule IA a répondu
    elif pplx_result:
        verdict = pplx_result.get("verdict", "HOLD").upper()
        conviction = int(pplx_result.get("conviction", 50))
        score_boost = 1 if verdict == "ACHAT" and conviction >= 50 else 0
        result = {
            "verdict": verdict,
            "conviction": conviction,
            "consensus": False,
            "score_boost": score_boost,
            "perplexity": pplx_result,
            "gemini": None,
            "raison": f"Analyse Perplexity seule (Gemini indisponible): {verdict} conviction {conviction}",
            "source": "perplexity",
            "timestamp": time.time(),
        }

    elif gemini_result:
        verdict = gemini_result.get("verdict", "HOLD").upper()
        conviction = int(gemini_result.get("conviction", 50))
        score_boost = 1 if verdict == "ACHAT" and conviction >= 50 else 0
        result = {
            "verdict": verdict,
            "conviction": conviction,
            "consensus": False,
            "score_boost": score_boost,
            "perplexity": None,
            "gemini": gemini_result,
            "raison": f"Analyse Gemini seule (Perplexity indisponible): {verdict} conviction {conviction}",
            "source": "gemini",
            "timestamp": time.time(),
        }

    # Cas: aucune IA n'a répondu
    else:
        result = {
            "verdict": "HOLD",
            "conviction": 0,
            "consensus": False,
            "score_boost": 0,
            "perplexity": None,
            "gemini": None,
            "raison": f"Aucune IA disponible: {pplx_source} | {gemini_source}",
            "source": "none",
            "timestamp": time.time(),
        }

    # Mettre en cache
    cache[cache_key] = {"result": result, "timestamp": time.time()}
    # Nettoyer le cache (garder max 50 entrées)
    if len(cache) > 50:
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("timestamp", 0))
        for k in sorted_keys[:-50]:
            del cache[k]
    sauver_cache(cache)

    print(f"  [CONSENSUS] {symbole}: {result['verdict']} (conviction {result['conviction']}, boost {result['score_boost']:+d}) - {result['raison'][:60]}")

    return result


def rapport_consensus(symbole, prix, rsi, sma20, sma50, variation_24h, volume):
    """Génère un rapport lisible du consensus pour Telegram."""
    result = consensus_multi_ia(symbole, prix, rsi, sma20, sma50, variation_24h, volume)

    rapport = "🧠 CONSENSUS MULTI-IA\n"
    rapport += "━━━━━━━━━━━━━━━━━━━━\n\n"

    # Verdict global
    emoji = {"ACHAT": "🟢", "VENTE": "🔴", "HOLD": "🟡"}.get(result["verdict"], "⚪")
    rapport += f"Verdict: {emoji} {result['verdict']}\n"
    rapport += f"Conviction: {result['conviction']}/100\n"
    rapport += f"Consensus: {'✅ Les deux IA sont d\'accord' if result['consensus'] else '⚠️ Désaccord'}\n"
    rapport += f"Score boost: {result['score_boost']:+d}\n\n"

    # Perplexity
    if result.get("perplexity"):
        p = result["perplexity"]
        rapport += f"📡 Perplexity: {p.get('verdict', '?')} ({p.get('conviction', 0)}/100)\n"
        rapport += f"   {p.get('raison', '?')[:80]}\n"
    else:
        rapport += "📡 Perplexity: indisponible\n"

    # Gemini
    if result.get("gemini"):
        g = result["gemini"]
        rapport += f"🔮 Gemini: {g.get('verdict', '?')} ({g.get('conviction', 0)}/100)\n"
        rapport += f"   {g.get('raison', '?')[:80]}\n"
    else:
        rapport += "🔮 Gemini: indisponible\n"

    rapport += f"\n💡 {result.get('raison', '')}"

    return rapport


if __name__ == "__main__":
    # Test
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    print(f"Test consensus pour {sym}...")
    r = rapport_consensus(sym, 64000, 45, 63500, 62000, -1.5, 1500000000)
    print(r)
