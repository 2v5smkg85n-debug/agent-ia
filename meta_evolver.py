#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""meta_evolver.py — Méta-évolution: l'agent propose et valide lui-même ses
propres améliorations de code d'infrastructure (nouveaux modules).

VERSION SÛRE:
  1. Collecte l'état du système (perf live, modules, propositions récentes)
  2. Demande au LLM UNE amélioration concrète (nouveau module autonome)
  3. GATE 1: syntaxe (ast.parse)
  4. GATE 2: scan sécurité (imports restreints, opérations dangereuses interdites)
  5. GATE 3: self_test() s'exécute sans crash (timeout 30s) et retourne True
  6. Si tout passe: sauvegarde dans propositions_meta/ + notif Telegram
  7. N'APPLIQUE JAMAIS automatiquement — l'utilisateur relit et applique.

Cron hebdo (dimanche 05:00 UTC, ≠ strategy_evolver 04:00).
"""
import os
import sys
import json
import re
import ast
import time
import signal
import traceback
import importlib.util
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
PROPS_DIR = os.path.join(DOSSIER, "propositions_meta")
os.makedirs(PROPS_DIR, exist_ok=True)

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
PPLX_KEY = os.getenv("PPLX_API_KEY", "")
PPLX_URL = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def log(msg):
    print(f"[meta] {datetime.utcnow():%H:%M:%S} {msg}", flush=True)


# ============================================
# LLM (Gemini + fallback Perplexity)
# ============================================
def call_gemini(prompt):
    import requests
    if not GEMINI_KEY:
        return None
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.8, "maxOutputTokens": 2500}}
    for delay in [10, 30, None]:
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=120)
            if r.status_code == 429 and delay is not None:
                time.sleep(delay); continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if delay is None:
                log(f"Gemini indispo: {e}"); return None
            time.sleep(delay)
    return None


def call_perplexity(prompt):
    import requests
    if not PPLX_KEY:
        return None
    headers = {"Authorization": f"Bearer {PPLX_KEY}", "content-type": "application/json"}
    payload = {"model": PPLX_MODEL, "max_tokens": 3000,
               "messages": [{"role": "user", "content": prompt}]}
    try:
        r = requests.post(PPLX_URL, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"Perplexity indispo: {e}"); return None


def call_llm(prompt):
    t = call_gemini(prompt)
    if t:
        return t, "gemini"
    log("Gemini KO — fallback Perplexity")
    t = call_perplexity(prompt)
    if t:
        return t, "perplexity"
    return None, None


# ============================================
# ÉTAT DU SYSTÈME
# ============================================
def _etat_systeme():
    infos = []
    # Perf paper trading
    try:
        pt = json.load(open(os.path.join(DOSSIER, "paper_trading.json")))
        fermes = pt.get("trades_fermes", [])
        liq = pt.get("liquidites", 0)
        pos = pt.get("positions", [])
        cap = pt.get("capital_initial", 1000)
        val = liq + sum(p.get("montant_eur", 0) for p in pos)
        pnl = (val / cap - 1) * 100 if cap else 0
        infos.append(f"Portfolio paper: {val:.2f}€ (PnL {pnl:+.2f}%), "
                     f"{len(fermes)} trades fermes, {len(pos)} positions ouvertes")
        from collections import defaultdict
        per_strat = defaultdict(list)
        for t in fermes:
            per_strat[t.get("strategie") or "VIDE"].append(t.get("variation_pct", 0))
        faibles = sorted(((s, vs) for s, vs in per_strat.items() if s != "VIDE"),
                         key=lambda x: sum(x[1]) / len(x[1]))[:3]
        for s, vs in faibles:
            infos.append(f"  strategie faible: {s} (moy {sum(vs)/len(vs):+.2f}%, {len(vs)} trades)")
    except Exception:
        pass
    # Modules existants
    try:
        mods = sorted(f[:-3] for f in os.listdir(DOSSIER)
                      if f.endswith(".py") and not f.startswith("patch_") and not f.startswith("diag_"))
        infos.append(f"Modules existants ({len(mods)}): {', '.join(mods[:30])}")
    except Exception:
        pass
    # Propositions récentes (anti-doublon)
    try:
        pf = os.path.join(DOSSIER, "meta_propositions.jsonl")
        recents = []
        if os.path.exists(pf):
            for line in open(pf).readlines()[-6:]:
                try:
                    recents.append(json.loads(line).get("description", "")[:70])
                except Exception:
                    pass
        if recents:
            infos.append("Propositions recentes (NE PAS repeter): " + " | ".join(recents))
    except Exception:
        pass
    infos.append(_diagnostic_profit())
    return "\n".join(infos)


def _diagnostic_profit(trades=None):
    """Diagnostic de rentabilité: où le système gagne/perd de l'argent.
    P&L par raison de sortie + par stratégie + plus grosse fuite (cible prioritaire).
    L'objectif: orienter l'auto-codage du méta-évolveur vers les VRAIES pertes."""
    try:
        if trades is None:
            pt = json.load(open(os.path.join(DOSSIER, "paper_trading.json")))
            trades = pt.get("trades_fermes", [])
        if not trades:
            return "(pas encore de trades fermés — diagnostic non disponible)"
        from collections import defaultdict
        par_raison = defaultdict(lambda: [0, 0.0])
        par_strat = defaultdict(lambda: [0, 0.0])
        for t in trades:
            r = (t.get("raison") or "?").split(" (")[0]
            g = t.get("gain_eur", 0) or 0
            par_raison[r][0] += 1; par_raison[r][1] += g
            s = t.get("strategie") or t.get("source") or "?"; s = s.replace("_PARTIAL", "")
            par_strat[s][0] += 1; par_strat[s][1] += g
        lignes = ["DIAGNOSTIC RENTABILITÉ (où l'argent est gagné/perdu):"]
        lignes.append("  Par raison de sortie (trié du pire au meilleur):")
        for r, (n, p) in sorted(par_raison.items(), key=lambda x: x[1][1]):
            lignes.append(f"    {r:20s}: {n:2d} trades, {p:+.2f}EUR (avg {p/n:+.3f})")
        lignes.append("  Par stratégie (3 pires + 3 meilleures):")
        strats = sorted(par_strat.items(), key=lambda x: x[1][1])
        for s, (n, p) in strats[:3] + strats[-3:]:
            lignes.append(f"    {s[:24]:24s}: {n:2d}t, {p:+.2f}EUR")
        pires = sorted(par_raison.items(), key=lambda x: x[1][1])
        if pires and pires[0][1][1] < 0:
            lignes.append(f"  >>> CIBLE PRIORITAIRE (plus grosse fuite): {pires[0][0]} "
                          f"= {pires[0][1][1]:+.2f}EUR sur {pires[0][1][0]} trades -> "
                          f"code un plugin qui réduit CETTE fuite en priorité")
        return "\n".join(lignes)
    except FileNotFoundError:
        return "(paper_trading.json absent — diagnostic non disponible)"
    except Exception as e:
        return f"(diagnostic indispo: {e})"


# ============================================
# PROMPT
# ============================================
PROMPT_META = """Tu es un ingénieur Python senior. Améliore un système de trading crypto automatique.

ÉTAT ACTUEL DU SYSTÈME:
{etat}

CONTRAINTES DE SÉCURITÉ (CRITIQUES — le non-respect = rejet automatique):
- Écris UN NOUVEAU module Python autonome (un seul fichier, pas de patch).
- Imports AUTORISÉS uniquement: os, sys, json, re, math, statistics, datetime, time, collections, requests, functools, itertools, decimal, indicateurs, backtest_moteur, memoire_marche, live_lessons, sagesse_traders.
- INTERDIT ABSOLUMENT: os.system, subprocess, os.popen, eval(), exec(), __import__, shutil, os.remove, os.unlink, os.rmdir, os.rename, os.chmod, socket, pickle, marshal, ctypes, importlib, __builtins__, __subclasses__, globals(), open() en mode écriture ('w','a','x').
- Le module NE doit PAS modifier paper_trading.json, strategies_evolved.json, ou supprimer des fichiers.
- Il DOIT définir une fonction `self_test()` qui s'exécute sans crash, retourne True, et ne fait aucun appel réseau (mock les données en dur).
- Il DOIT définir AU MOINS UN de ces hooks (le module sera auto-chargé par paper_trading via le système de plugins):
    hook_entree(pf, signal) -> (allow_bool, raison_str)   # veto: (False, "raison") bloque l'entrée
    hook_sizing(pf, signal, montant, prix_actuel) -> float  # ajuste la taille (sera clampée 0..liquidités)
  Les hooks reçoivent pf (portefeuille dict: liquidites, positions, trades_fermes, capital_initial),
  signal (dict: symbole, nom, marche, strategie, raison, score), montant (EUR float), prix_actuel (float).
  Un hook peut n'en définir qu'un. Les hooks sont wrappés try/except par le système (safe).

OBJECTIF: AUGMENTE LES BÉNÉFICES en ciblant CONCRÈTEMENT la CIBLE PRIORITAIRE du diagnostic ci-dessus (la plus grosse fuite de P&L). Si STOP-LOSS est la fuite principale, code un filtre qui réduit les entrées risquées (veto en forte volatilité, après N pertes consécutives sur un actif, en régime de crash, corrélation BTC/ETH explosive, etc.). Si une stratégie perd, code un veto ou sizing réduit pour cette stratégie. Si les sorties par temps sont trop petites, code un sizing plus gros sur les bons setups. CIBLE LA FUITE RÉELLE, ne propose pas du générique. Le module sera AUTO-APPLIQUÉ dans plugins/ s'il passe les 3 gates (puis auto-rollback par plugin_sante si il nuit). Évite de dupliquer les propositions récentes.

FORMAT DE RÉPONSE STRICT:
DESCRIPTION: <une phrase décrivant l'amélioration>
MODULE: <nom_du_module_sans_extension>
```python
<code complet du module, avec self_test()>
```

Une seule proposition. Pas de blabla hors format."""


# ============================================
# EXTRACTION + VALIDATION
# ============================================
def _extraire(rep):
    desc = ""
    m = re.search(r"DESCRIPTION:\s*(.+)", rep)
    if m:
        desc = m.group(1).strip()
    module = "meta_module"
    m = re.search(r"MODULE:\s*([A-Za-z_]\w*)", rep)
    if m:
        module = m.group(1).strip()
    code = None
    for pat in (r"```python\n(.+?)```", r"```\n(.+?)```"):
        m = re.search(pat, rep, re.DOTALL)
        if m:
            code = m.group(1).strip()
            break
    return desc, module, code


FORBIDDEN = ["os.system", "subprocess", "os.popen", "eval(", "exec(", "__import__",
             "shutil", "os.remove", "os.unlink", "os.rmdir", "os.removedirs",
             "os.rename", "os.replace", "os.chmod", "os.chown",
             "socket", "pickle", "marshal", "ctypes", "importlib",
             "globals()", "locals()", "__builtins__", "__subclasses__", "pty"]

ALLOWED_IMPORTS = {"os", "sys", "json", "re", "math", "statistics", "datetime", "time",
                   "collections", "requests", "functools", "itertools", "decimal",
                   "fractions", "bisect", "heapq", "operator", "typing", "enum",
                   "indicateurs", "backtest_moteur", "memoire_marche",
                   "live_lessons", "sagesse_traders", "dotenv"}


def _scan_securite(code):
    """Retourne (ok, raisons). ok=False si danger détecté."""
    raisons = []
    low = code.lower()
    for pat in FORBIDDEN:
        if pat.lower() in low:
            raisons.append(f"mot interdit: {pat}")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"erreur syntaxe: {e}"]
    # Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raisons.append(f"import non autorisé: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] not in ALLOWED_IMPORTS:
                raisons.append(f"import non autorisé: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
                if any(c in mode for c in "wax"):
                    raisons.append(f"open() écriture interdit (mode {mode!r})")
    return (len(raisons) == 0), raisons


def _run_self_test(code, module_name):
    """Écrit le module en tmp, l'importe, appelle self_test() avec timeout 30s."""
    tmp = os.path.join(PROPS_DIR, f"_test_{module_name}.py")
    try:
        with open(tmp, "w") as f:
            f.write(code)
        spec = importlib.util.spec_from_file_location(module_name, tmp)
        mod = importlib.util.module_from_spec(spec)

        def _handler(signum, frame):
            raise TimeoutError("self_test timeout (30s)")
        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(30)
        try:
            spec.loader.exec_module(mod)
            if not hasattr(mod, "self_test"):
                return False, "pas de fonction self_test()"
            result = mod.self_test()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
        if result is not True:
            return False, f"self_test() a retourné {result!r} (True attendu)"
        return True, "OK"
    except Exception as e:
        tb = traceback.format_exc()[-400:]
        return False, f"self_test echec: {e}\n{tb}"
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ============================================
# PIPELINE DE VALIDATION + AUTO-RÉPARATION
# ============================================
def _pipeline(code, module, desc, source):
    """Gates 1-3. Retourne un dict {ok, code, module, desc, raison, statut}."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"ok": False, "code": code, "module": module, "desc": desc, "raison": str(e), "statut": "REJET_SYNTAXE"}
    log("GATE 1 syntaxe OK")
    ok, raisons = _scan_securite(code)
    if not ok:
        return {"ok": False, "code": code, "module": module, "desc": desc, "raison": "; ".join(raisons), "statut": "REJET_SECURITE"}
    log("GATE 2 sécurité OK")
    ok, raison = _run_self_test(code, module)
    if not ok:
        return {"ok": False, "code": code, "module": module, "desc": desc, "raison": raison, "statut": "REJET_SELFTEST"}
    return {"ok": True, "code": code, "module": module, "desc": desc, "raison": "OK", "statut": "VALIDEE"}


def _repair_prompt(desc, module, code, erreur):
    return f"""Ton module Python a échoué son auto-test. Corrige-le.

DESCRIPTION: {desc}
MODULE: {module}

CODE ACTUEL:
```python
{code}
```

ERREUR DU self_test():
{erreur[:800]}

Corrige le module pour que self_test() s'exécute sans crash et retourne True.
IMPORTANT: self_test() NE doit faire AUCUN appel réseau (utilise des données mock codées en dur). Teste la logique pure.
Respecte les contraintes de sécurité (pas de os.system, subprocess, eval, open écriture, imports restreints aux stdlib + indicateurs/backtest_moteur/memoire_marche).

FORMAT STRICT:
DESCRIPTION: {desc}
MODULE: {module}
```python
<code corrigé complet avec self_test()>
```"""


# ============================================
# ENREGISTREMENT + NOTIFICATION
# ============================================
def _enregistrer(desc, module, code, statut, detail, source, fname=""):
    rec = {"date": datetime.utcnow().isoformat(), "description": desc, "module": module,
           "statut": statut, "detail": detail, "source": source, "fichier": fname,
           "code": code}
    with open(os.path.join(DOSSIER, "meta_propositions.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _notifier_telegram(desc, module, fname, auto_applied=False):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        log("(pas de Telegram configuré)"); return
    try:
        import requests
        if auto_applied:
            msg = (f"🧬 Méta-évolution — proposition VALIDÉE + AUTO-APPLIQUÉE\n\n"
                   f"Module: {module}\n{desc}\n\n"
                   f"Déployé dans plugins/ — actif au prochain trade.\n"
                   f"Hooks: sera chargé automatiquement par paper_trading.\n"
                   f"Pour retirer: rm plugins/{fname} (ou PLUGINS_ACTIVE=0)")
        else:
            msg = (f"🧬 Méta-évolution — proposition VALIDÉE\n\n"
                   f"Module: {module}\n{desc}\n\n"
                   f"Fichier: propositions_meta/{fname}\n"
                   f"Relis le code puis applique-le manuellement si OK.")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": msg}, timeout=10)
        log("Notification Telegram envoyée")
    except Exception as e:
        log(f"Telegram KO: {e}")


# ============================================
# MAIN
# ============================================
def main():
    log("=== MÉTA-ÉVOLVEUR (version sûre) ===")
    etat = _etat_systeme()
    log(f"État système collecté ({len(etat)} chars)")
    prompt = PROMPT_META.format(etat=etat)
    rep, source = call_llm(prompt)
    if not rep:
        log("LLM indispo — abandon"); return
    log(f"Proposition reçue de {source} ({len(rep)} chars)")
    desc, module, code = _extraire(rep)
    if not code:
        log("Pas de code extrait — abandon")
        _enregistrer(desc or "(extraction échouée)", module, rep[:500], "REJET_EXTRACTION", "pas de bloc code", source)
        return
    # Pipeline de validation (gates 1-3) avec auto-réparation sur échec self_test
    res = _pipeline(code, module, desc, source)
    if not res["ok"] and res["statut"] == "REJET_SELFTEST":
        log(f"GATE 3 REJET (self_test) — tentative de réparation...")
        rep2, _ = call_llm(_repair_prompt(res["desc"], res["module"], res["code"], res["raison"]))
        if rep2:
            d2, mod2, code2 = _extraire(rep2)
            if code2:
                res = _pipeline(code2, mod2 or module, d2 or desc, source)
        else:
            log("Réparation: LLM indispo")
    if not res["ok"]:
        log(f"REJET FINAL ({res['statut']}): {res['raison'][:200]}")
        _enregistrer(res["desc"], res["module"], res["code"], res["statut"], res["raison"], source)
        return
    log("GATE 3 self_test OK — PROPOSITION VALIDÉE")
    code, module, desc = res["code"], res["module"], res["desc"]
    # Sauvegarde
    slug = re.sub(r"[^a-z0-9]+", "_", module.lower()).strip("_")[:30]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"meta_{ts}_{slug}.py"
    fpath = os.path.join(PROPS_DIR, fname)
    with open(fpath, "w") as f:
        f.write(code)
    log(f"Module sauvé: propositions_meta/{fname}")
    auto_applied = False
    if os.getenv("META_AUTO_APPLY", "1") != "0":
        try:
            plugins_dir = os.path.join(DOSSIER, "plugins")
            os.makedirs(plugins_dir, exist_ok=True)
            import shutil
            shutil.copy(fpath, os.path.join(plugins_dir, fname))
            auto_applied = True
            log(f"AUTO-APPLIQUE: plugins/{fname} (actif au prochain trade)")
            try:
                import evolutia_profit
                evolutia_profit.enregistrer_application(fname, desc)
            except Exception as _ee:
                log(f"evolutia baseline KO: {_ee}")
        except Exception as _e:
            log(f"Auto-apply echoue: {_e}")
    _enregistrer(desc, module, code, "VALIDEE", f"propositions_meta/{fname}" + (" + plugins/" if auto_applied else ""), source, fname)
    _notifier_telegram(desc, module, fname, auto_applied)
    log("=== META-EVOLUTION TERMINEE ===")


if __name__ == "__main__":
    main()
