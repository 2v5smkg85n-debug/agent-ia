#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reflection_gemini.py — Boucle de reflexion quotidienne (self-improvement).

Realise "etre de plus en plus intelligent de jour en jour":
  - Rassemble le contexte: trades du jour, equity, perf par strategie, pruning
  - Demande a Gemini d'analyser et de produire insights + suggestions
  - Logge dans reflection_log.jsonl + envoie un digest Telegram

Non invasif: lecture seule, n'ecrit rien dans le moteur de trading.
Les suggestions sont enregistrees pour review humaine (le tuning auto viendra
apres validation des suggestions).

CLI:
  python reflection_gemini.py            # reflexion du jour
  python reflection_gemini.py historique # voir les dernieres reflexions
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
EQUITY_FILE = os.path.join(DOSSIER, "equity_history.jsonl")
PRUNING_FILE = os.path.join(DOSSIER, "strategies_desactivees.json")
LOG_FILE = os.path.join(DOSSIER, "reflection_log.jsonl")

# Charger .env
from dotenv import load_dotenv
load_dotenv(os.path.join(DOSSIER, ".env"))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
PPLX_KEY = os.getenv("PPLX_API_KEY", "")
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")
PPLX_URL = "https://api.perplexity.ai/chat/completions"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("reflection")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _extraire_strategie(t):
    strat = (t.get("strategie") or "").strip()
    if strat and strat not in ("legacy", "backtest-gagnant"):
        return strat
    raison = t.get("signal_raison", "") or ""
    m = re.search(r"backtest\s*\(([^[]+)\s*\[", raison)
    if m:
        return m.group(1).strip()
    src = (t.get("source") or "").strip()
    return "backtest-gagnant" if src == "backtest-gagnant" else ""


# ---------------------------------------------------------------- CONTEXTE
def gather_contexte():
    """Rassemble le contexte pour la reflexion."""
    pf = _load(PT_FILE, {})
    aujourd = datetime.now().strftime("%Y-%m-%d")
    trades = pf.get("trades_fermes", [])
    # trades du jour
    trades_jour = [t for t in trades
                   if (t.get("date_fermeture", "") or "").startswith(aujourd)]
    # perf par strategie (tous trades fermes)
    par_strat = {}
    for t in trades:
        s = _extraire_strategie(t)
        if not s:
            continue
        d = par_strat.setdefault(s, {"n": 0, "wins": 0, "pnl": 0.0})
        gain = float(t.get("gain_eur") or 0)
        d["n"] += 1
        d["pnl"] += gain
        if gain > 0:
            d["wins"] += 1
    for d in par_strat.values():
        d["win_rate"] = round(100 * d["wins"] / d["n"], 1) if d["n"] else 0
        d["pnl"] = round(d["pnl"], 2)
    # equity recente
    equity = []
    try:
        with open(EQUITY_FILE, encoding="utf-8") as f:
            for line in f:
                equity.append(json.loads(line))
    except Exception:
        pass
    eq_recent = equity[-20:] if equity else []
    # pruning state
    pruning = _load(PRUNING_FILE, {})
    desact = [k for k, v in pruning.get("desactivees", {}).items() if v.get("disabled")]
    # capital
    capital = pf.get("capital_initial", 1000.0)
    liquidites = pf.get("liquidites", 0)
    positions = pf.get("positions", [])
    expo = sum(p.get("montant_eur", 0) for p in positions)
    total = liquidites + expo

    return {
        "date": aujourd,
        "capital_initial": capital,
        "capital_actuel": round(total, 2),
        "pnl_total": round(total - capital, 2),
        "n_trades_total": len(trades),
        "n_trades_jour": len(trades_jour),
        "trades_jour": [{
            "symbole": t.get("symbole"), "strategie": _extraire_strategie(t),
            "gain": round(float(t.get("gain_eur") or 0), 2),
            "raison": t.get("raison", ""),
            "heure": t.get("date_fermeture", "")} for t in trades_jour],
        "perf_par_strategie": par_strat,
        "equity_recent": [{"ts": e.get("ts"), "capital": e.get("capital")}
                          for e in eq_recent],
        "strategies_desactivees": desact,
        "positions_ouvertes": [{"symbole": p.get("symbole"),
                                "strategie": _extraire_strategie(p),
                                "montant": p.get("montant_eur"),
                                "variation": p.get("variation_pct")}
                               for p in positions],
    }


def _prompt(ctx):
    return f"""Tu es l'IA centrale d'un systeme de trading automatique. Ton role:
analyser les performances et proposer des ameliorations concretes (self-improvement).

CONTEXTE DU JOUR ({ctx['date']}):
- Capital initial: {ctx['capital_initial']} EUR | Capital actuel: {ctx['capital_actuel']} EUR
- PnL total: {ctx['pnl_total']:+.2f} EUR
- Trades fermes total: {ctx['n_trades_total']} | Trades du jour: {ctx['n_trades_jour']}
- Strategies desactivees (auto-pruning): {ctx['strategies_desactivees'] or 'aucune'}

TRADES DU JOUR:
{json.dumps(ctx['trades_jour'], ensure_ascii=False, indent=2) or '(aucun aujourd hui)'}

PERFORMANCE PAR STRATEGIE (tous trades fermes):
{json.dumps(ctx['perf_par_strategie'], ensure_ascii=False, indent=2) or '(aucune donnee)'}

EQUITY RECENTE (20 derniers points):
{json.dumps(ctx['equity_recent'], ensure_ascii=False)}

POSITIONS OUVERTES ACTUELLES:
{json.dumps(ctx['positions_ouvertes'], ensure_ascii=False, indent=2) or '(aucune)'}

ANALYSE et reponds en JSON STRICT (sans markdown, sans texte autour) avec ce schema:
{{
  "synthese": "resume en 1-2 phrases de l'etat global",
  "points_forts": ["..."],
  "points_faibles": ["..."],
  "insights": ["observation concrete, ex: strategie X performe mieux en regime Y"],
  "suggestions": ["action concrete d'amelioration, ex: reduire TP sur SOL, desactiver Z si n>3"],
  "priorite": "la suggestion la plus importante a court terme"
}}
Reponds UNIQUEMENT avec le JSON."""


def call_gemini(ctx):
    """Appelle Gemini avec retry/backoff. Retourne le texte de reponse."""
    import requests
    import time
    if not GEMINI_KEY:
        return '{"synthese":"GEMINI_API_KEY manquant","insights":[],"suggestions":["Configurer GEMINI_API_KEY"]}'
    payload = {"contents": [{"parts": [{"text": _prompt(ctx)}]}],
               "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500}}
    backoff = [10, 30, 60]  # secondes entre tentatives
    for tentative, delay in enumerate(backoff + [None]):
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=90)
            if r.status_code == 429 and delay is not None:
                log.warning("Gemini 429 (quota) — retry dans %ss (tentative %d/%d)",
                            delay, tentative + 1, len(backoff))
                time.sleep(delay)
                continue
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"], "gemini"
        except Exception as e:
            if delay is None:
                log.warning("Gemini indispo: %s", e)
                return None, None
            log.warning("Gemini erreur (%s) — retry dans %ss", e, delay)
            time.sleep(delay)
    return None, None


def call_anthropic(ctx):
    """Fallback: appel Anthropic Claude. Retourne (texte, 'anthropic')."""
    import requests
    if not ANTHROPIC_KEY:
        return None, None
    headers = {"x-api-key": ANTHROPIC_KEY,
               "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    # essaie plusieurs noms de modeles (certains de 2024 sont deprecies en 2026)
    candidats = [ANTHROPIC_MODEL,
                 "claude-3-5-haiku-20241022",
                 "claude-3-5-sonnet-20241022",
                 "claude-sonnet-4-20250514",
                 "claude-opus-4-20250918"]
    vus = set()
    for modele in candidats:
        if modele in vus:
            continue
        vus.add(modele)
        payload = {"model": modele, "max_tokens": 1500,
                   "messages": [{"role": "user", "content": _prompt(ctx)}]}
        try:
            r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=90)
            if r.status_code == 404:
                log.warning("Anthropic modele %s introuvable (404)", modele)
                continue
            r.raise_for_status()
            data = r.json()
            log.info("Anthropic OK avec modele %s", modele)
            return data["content"][0]["text"], "anthropic"
        except requests.exceptions.HTTPError:
            continue
        except Exception as e:
            log.warning("Anthropic %s erreur: %s", modele, e)
            continue
    return None, None


def call_perplexity(ctx):
    """Fallback 2: Perplexity API (format OpenAI-compatible)."""
    import requests
    if not PPLX_KEY:
        return None, None
    headers = {"Authorization": f"Bearer {PPLX_KEY}",
               "content-type": "application/json"}
    payload = {"model": PPLX_MODEL, "max_tokens": 1500,
               "messages": [{"role": "user", "content": _prompt(ctx)}]}
    try:
        r = requests.post(PPLX_URL, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"], "perplexity"
    except Exception as e:
        log.warning("Perplexity indispo: %s", e)
        return None, None


def call_llm(ctx):
    """Chaine: Gemini -> Perplexity -> Anthropic."""
    texte, source = call_gemini(ctx)
    if texte:
        return texte, source
    log.info("Gemini KO — fallback Perplexity...")
    texte, source = call_perplexity(ctx)
    if texte:
        return texte, source
    log.info("Perplexity KO — fallback Anthropic...")
    return call_anthropic(ctx)


def _parse_json(texte):
    """Extrait le JSON de la reponse (parfois avec backticks)."""
    if not texte:
        return None
    # retirer backticks markdown
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ---------------------------------------------------------------- REFLEXION
def reflechir():
    ctx = gather_contexte()
    log.info("Reflexion Gemini — %s (%d trades jour, %d total)",
             ctx["date"], ctx["n_trades_jour"], ctx["n_trades_total"])
    resp, source = call_llm(ctx)
    if not resp:
        _tel("⚠️ Reflexion IA: echec appel LLM (Gemini + Anthropic KO)")
        return None
    analyse = _parse_json(resp)
    entry = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "source": source,
             "ctx_summary": {"capital": ctx["capital_actuel"],
                             "pnl": ctx["pnl_total"],
                             "trades_jour": ctx["n_trades_jour"]},
             "analyse": analyse, "raw": resp[:500]}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # digest Telegram
    if analyse:
        msg = (f"🧠 REFLEXION IA — {ctx['date']}\n"
               f"Capital: {ctx['capital_actuel']}€ (PnL {ctx['pnl_total']:+.2f}€)\n"
               f"Synthese: {analyse.get('synthese','')}\n"
               f"Priorite: {analyse.get('priorite','')}")
        _tel(msg)
    return entry


def cmd_historique():
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lignes = f.readlines()
    except Exception:
        lignes = []
    if not lignes:
        print("(aucune reflexion enregistree)")
        return
    print(f"=== {len(lignes)} reflexions enregistrees (dernieres 5) ===")
    for line in lignes[-5:]:
        e = json.loads(line)
        a = e.get("analyse", {}) or {}
        print(f"\n[{e['ts']}] capital={e['ctx_summary'].get('capital')}€ "
              f"pnl={e['ctx_summary'].get('pnl')}€")
        print(f"  Synthese: {a.get('synthese','?')}")
        print(f"  Priorite: {a.get('priorite','?')}")


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "historique":
        cmd_historique()
        return
    entry = reflechir()
    if entry:
        a = entry.get("analyse", {}) or {}
        print("=" * 55)
        print(f"REFLEXION GEMINI — {entry['ts']}")
        print("=" * 55)
        print(f"Synthese: {a.get('synthese','?')}")
        print(f"\nPoints forts: {a.get('points_forts',[])}")
        print(f"Points faibles: {a.get('points_faibles',[])}")
        print(f"\nInsights:")
        for i in a.get("insights", []):
            print(f"  - {i}")
        print(f"\nSuggestions:")
        for s in a.get("suggestions", []):
            print(f"  - {s}")
        print(f"\n>>> PRIORITE: {a.get('priorite','?')}")


if __name__ == "__main__":
    main()
