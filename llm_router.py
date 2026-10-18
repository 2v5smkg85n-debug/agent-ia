#!/usr/bin/env python3
"""
llm_router.py — un seul point d'appel pour tous les modeles de langage du bot.

Ordre par role (le premier disponible qui a encore du quota gagne) :
  decision : Groq -> OpenRouter -> OVH Llama 3.3 70B (sans cle) -> LLM7 DeepSeek (sans cle) -> Gemini -> OVH gpt-oss-120b (sans cle) -> Pollinations (sans cle) -> Ollama local
  critique : OpenRouter -> OVH gpt-oss-120b -> LLM7 -> Gemini -> Groq -> OVH Llama -> Pollinations -> Ollama local (modele critique)
  leger    : OVH Llama -> LLM7 -> Ollama local -> Groq -> OpenRouter -> Gemini

FOURNISSEURS SANS CLE (aucune inscription) : OVHcloud AI Endpoints (2 req/min par modele et par IP), LLM7.io (~60 req/h),
Pollinations (1 reponse / 30 s). Ce sont des acces publics non garantis : le routeur les met en pause automatiquement
quand ils repondent 429/402 ou tombent, et retombe toujours sur le modele local. LLM_LIBRE=0 pour les couper.

Quotas gratuits connus (verifies le 18/10/2026) :
  Groq       30 req/min, 1 000 req/jour, 8 000 tokens/min, 200 000 tokens/jour par modele
  OpenRouter 20 req/min, 50 req/jour (ou 1 000 req/jour apres un achat unique de 10 $ de credits)
  Gemini     quotas par projet, remise a zero a minuit heure du Pacifique (10 req/min et ~250 req/jour en pratique)
Le routeur garde une marge de 10 % sous chaque limite et compte tout dans llm_quota.json (visible sur le dashboard).

Cles (dans .env ou en variables d'environnement) :
  GROQ_KEY (ou GROQ_API_KEY), OPENROUTER_KEY (ou OPENROUTER_API_KEY), GEMINI_KEY (ou GEMINI_API_KEY)
  OPENROUTER_PAID=1   si vous avez achete 10 $ de credits (passe le quota a 1 000/jour)
  OPENROUTER_MODELS   liste separee par des virgules (defaut : voir OPENROUTER_MODELES)
  LLM_MODELE_LOCAL / LLM_MODELE_LOCAL_CRITIQUE   modeles Ollama (defaut qwen3.5:4b / llama3.2:3b)

Usage : python3 llm_router.py test      -> teste chaque fournisseur
        python3 llm_router.py quotas    -> affiche la consommation du jour
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_QUOTA = os.path.join(DOSSIER, "llm_quota.json")
_LOCK = threading.Lock()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELE = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELES = [m.strip() for m in os.getenv(
    "OPENROUTER_MODELS",
    "nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free,nvidia/nemotron-3-super-120b-a12b:free").split(",") if m.strip()]
GEMINI_MODELE = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODELE_LOCAL = os.getenv("LLM_MODELE_LOCAL", "qwen3.5:4b")
MODELE_LOCAL_CRITIQUE = os.getenv("LLM_MODELE_LOCAL_CRITIQUE", "llama3.2:3b")

# ------------------------------------------------------------------ fournisseurs SANS CLE
# Points d'acces publics anonymes (verifies le 18/10/2026). Limites par IP, non contractuels :
# ils peuvent disparaitre -> le routeur les saute automatiquement et retombe sur le modele local.
# LLM_LIBRE=0 pour les desactiver.
LIBRE_ACTIF = os.getenv("LLM_LIBRE", "1") == "1"
OVH_URL = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"   # 2 req/min/IP/modele
LIBRES = {
    # nom          : (url, modele, raisonneur ?)   raisonneur = le modele "reflechit" avant de repondre -> plus de tokens
    "ovh_llama":    (OVH_URL, os.getenv("OVH_MODEL_1", "Meta-Llama-3_3-70B-Instruct"), False),
    "ovh_gptoss":   (OVH_URL, os.getenv("OVH_MODEL_2", "gpt-oss-120b"), True),
    "llm7":         ("https://api.llm7.io/v1/chat/completions", os.getenv("LLM7_MODEL", "DeepSeek-V4-Flash-0731"), True),   # ~60 req/h anonyme
    "pollinations": ("https://text.pollinations.ai/openai", os.getenv("POLLINATIONS_MODEL", "openai"), True),              # 1 reponse / 30 s / IP
}

# (req/min, req/jour, tokens/min) — marge de securite appliquee dans _quota_ok
LIMITES = {
    "groq": (30, 1000, 8000),
    "openrouter": (20, 1000 if os.getenv("OPENROUTER_PAID", "0") == "1" else 50, None),
    "gemini": (10, int(os.getenv("GEMINI_RPD", "100")), None),   # le quota reel du palier gratuit varie : le 429 declenche une pause de 30 min
    "ovh_llama": (2, 1500, None),
    "ovh_gptoss": (2, 1500, None),
    "llm7": (1, 1000, None),
    "pollinations": (1, 1000, None),
    "local": (None, None, None),
}
MARGE = 0.9
MAX_CHARS_PROMPT = 24000     # ~6 000 tokens : au-dela on coupe le debut (garde la fin = la question)
TIMEOUT_LOCAL_MIN = int(os.getenv("LLM_TIMEOUT_LOCAL", "180"))   # CPU : un prompt de 3 000 tokens met 1-2 min sur un 4B
NUM_CTX_LOCAL = int(os.getenv("LLM_NUM_CTX", "8192"))

# Ordre d'essai par role. Les fournisseurs a cle sont sautes s'il n'y a pas de cle ; les "libres" si LLM_LIBRE=0.
ORDRE = {
    "decision": ["groq", "openrouter", "ovh_llama", "llm7", "gemini", "ovh_gptoss", "pollinations", "local"],
    "critique": ["openrouter", "ovh_gptoss", "llm7", "gemini", "groq", "ovh_llama", "pollinations", "local_critique"],
    "leger": ["ovh_llama", "llm7", "local", "groq", "openrouter", "gemini"],
}


# ------------------------------------------------------------------ cles
def _cle(*noms):
    for n in noms:
        v = os.getenv(n)
        if v:
            return v.strip()
    try:
        with open(os.path.join(DOSSIER, ".env")) as f:
            for line in f:
                s = line.strip()
                if "=" in s and not s.startswith("#"):
                    k, v = s.split("=", 1)
                    if k.strip() in noms and v.strip():
                        return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def cle_groq():
    return _cle("GROQ_KEY", "GROQ_API_KEY")


def cle_openrouter():
    return _cle("OPENROUTER_KEY", "OPENROUTER_API_KEY")


def cle_gemini():
    return _cle("GEMINI_KEY", "GEMINI_API_KEY")


# ------------------------------------------------------------------ quotas
def _charger_quota():
    try:
        with open(FICHIER_QUOTA) as f:
            d = json.load(f)
    except Exception:
        d = {}
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if d.get("jour") != jour:
        d = {"jour": jour, "fournisseurs": {}, "historique": d.get("historique", [])[-30:]}
    d.setdefault("fournisseurs", {})
    return d


def _sauver_quota(d):
    try:
        tmp = FICHIER_QUOTA + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, FICHIER_QUOTA)
    except Exception:
        pass


def _quota_ok(fournisseur, tokens_estimes=0):
    rpm, rpd, tpm = LIMITES.get(fournisseur, (None, None, None))
    if rpm is None and rpd is None:
        return True
    d = _charger_quota()
    f = d["fournisseurs"].setdefault(fournisseur, {"jour": 0, "minute": [], "tokens_minute": [], "erreurs": 0, "latence_ms": []})
    now = time.time()
    f["minute"] = [t for t in f["minute"] if now - t < 60]
    f["tokens_minute"] = [(t, n) for t, n in f.get("tokens_minute", []) if now - t < 60]
    if rpd and f["jour"] >= int(rpd * MARGE):
        return False
    if rpm and len(f["minute"]) >= max(1, int(rpm * MARGE + 0.5)):
        return False
    if tpm and sum(n for _, n in f["tokens_minute"]) + tokens_estimes > tpm * MARGE:
        return False
    # Fournisseur en panne recente : on le saute 10 minutes apres 3 erreurs d'affilee
    if f.get("erreurs", 0) >= 3 and now - f.get("derniere_erreur", 0) < 600:
        return False
    # Quota epuise cote fournisseur (HTTP 429) : pause explicite
    if f.get("pause_jusqua", 0) > now:
        return False
    return True


def _noter(fournisseur, ok, tokens=0, latence_ms=0, modele="", pause_s=0):
    with _LOCK:
        d = _charger_quota()
        f = d["fournisseurs"].setdefault(fournisseur, {"jour": 0, "minute": [], "tokens_minute": [], "erreurs": 0, "latence_ms": []})
        now = time.time()
        f["minute"].append(now)
        f["tokens_minute"] = f.get("tokens_minute", [])[-60:] + [(now, tokens)]
        f["jour"] += 1
        if ok:
            f["erreurs"] = 0
            f["ok"] = f.get("ok", 0) + 1
            f["latence_ms"] = (f.get("latence_ms", []) + [int(latence_ms)])[-50:]
            f["dernier_modele"] = modele
        else:
            f["erreurs"] = f.get("erreurs", 0) + 1
            f["derniere_erreur"] = now
            f["echecs"] = f.get("echecs", 0) + 1
            if pause_s:
                f["pause_jusqua"] = now + pause_s
        _sauver_quota(d)


def _a_cle(nom):
    if nom in LIBRES:
        return LIBRE_ACTIF
    return {"groq": cle_groq, "openrouter": cle_openrouter, "gemini": cle_gemini}.get(nom, lambda: True)()


def quotas():
    """Resume pour le dashboard / Telegram."""
    d = _charger_quota()
    out = {"jour": d.get("jour"), "fournisseurs": {}}
    for nom, (rpm, rpd, tpm) in LIMITES.items():
        f = d["fournisseurs"].get(nom, {})
        lat = f.get("latence_ms", [])
        out["fournisseurs"][nom] = {
            "appels_jour": f.get("jour", 0), "limite_jour": rpd, "ok": f.get("ok", 0), "echecs": f.get("echecs", 0),
            "latence_moy_ms": int(sum(lat) / len(lat)) if lat else None, "dernier_modele": f.get("dernier_modele"),
            "pause_min": max(0, int((f.get("pause_jusqua", 0) - time.time()) / 60)),
            "cle": bool(_a_cle(nom)),
        }
    return out


# ------------------------------------------------------------------ appels
def _tronquer(prompt):
    if len(prompt) <= MAX_CHARS_PROMPT:
        return prompt
    return "[...debut du contexte coupe pour respecter le quota de tokens...]\n" + prompt[-MAX_CHARS_PROMPT:]


def _openai_compatible(url, cle, modele, prompt, json_mode, temperature, max_tokens, timeout, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if cle:                                   # les points d'acces anonymes refusent un en-tete Authorization
        headers["Authorization"] = f"Bearer {cle}"
    if extra_headers:
        headers.update(extra_headers)
    payload = {"model": modele, "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    texte = (j["choices"][0]["message"].get("content") or "").strip()
    usage = j.get("usage", {}) or {}
    return texte, int(usage.get("total_tokens") or (len(prompt) // 4 + len(texte) // 4))


def _libre(nom, prompt, json_mode, temperature, max_tokens):
    url, modele, raisonneur = LIBRES[nom]
    # Un modele raisonneur consomme des tokens de reflexion avant la reponse : on lui laisse de la place
    mt = max_tokens + (700 if raisonneur else 0)
    texte, tokens = _openai_compatible(url, None, modele, prompt, json_mode, temperature, mt, timeout=60)
    if not texte:
        raise RuntimeError("reponse vide (reflexion trop longue ?)")
    return (texte, tokens), modele


def _groq(prompt, json_mode, temperature, max_tokens):
    cle = cle_groq()
    if not cle:
        raise RuntimeError("pas de cle GROQ_KEY")
    return _openai_compatible(GROQ_URL, cle, GROQ_MODELE, prompt, json_mode, temperature, max_tokens, 40), GROQ_MODELE


def _openrouter(prompt, json_mode, temperature, max_tokens):
    cle = cle_openrouter()
    if not cle:
        raise RuntimeError("pas de cle OPENROUTER_KEY")
    derniere = None
    for modele in OPENROUTER_MODELES:
        try:
            res = _openai_compatible(OPENROUTER_URL, cle, modele, prompt, json_mode, temperature, max_tokens, 60,
                                     {"HTTP-Referer": "https://github.com/2v5smkg85n-debug/agent-ia", "X-Title": "agent-ia"})
            if res[0]:
                return res, modele
        except Exception as e:  # modele retire / 429 / 404 -> on essaie le suivant
            derniere = e
            continue
    raise RuntimeError(f"aucun modele OpenRouter n'a repondu ({derniere})")


def _gemini(prompt, json_mode, temperature, max_tokens):
    cle = cle_gemini()
    if not cle:
        raise RuntimeError("pas de cle GEMINI_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODELE}:generateContent?key={cle}"
    gen = {"temperature": temperature, "maxOutputTokens": max_tokens + 512, "thinkingConfig": {"thinkingBudget": 512}}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    def _appel(g):
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": g}, timeout=45)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return r.json()
    j = _appel(gen)
    try:
        texte = j["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        # reponse vide (MAX_TOKENS avale par la reflexion, ou filtre) : on retente sans reflexion, plus de place
        gen2 = dict(gen, maxOutputTokens=max_tokens + 300, thinkingConfig={"thinkingBudget": 0})
        j = _appel(gen2)
        try:
            texte = j["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"reponse vide: {str(j)[:200]}")
    tokens = int((j.get("usageMetadata") or {}).get("totalTokenCount") or (len(prompt) // 4 + len(texte) // 4))
    return (texte, tokens), GEMINI_MODELE


def _local(prompt, json_mode, temperature, max_tokens, modele, timeout):
    payload = {"model": modele, "stream": False, "messages": [{"role": "user", "content": prompt}],
               "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": NUM_CTX_LOCAL}, "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m")}
    if json_mode:
        payload["format"] = "json"
    if any(k in modele.lower() for k in ("qwen3", "deepseek-r1", "gpt-oss", "think")):
        payload["think"] = False          # modeles "raisonnants" : pas de chaine de pensee (sinon num_predict part en reflexion)
    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    texte = (j.get("message") or {}).get("content", "").strip()
    return (texte, int(j.get("eval_count", 0) + j.get("prompt_eval_count", 0))), modele


def appeler(prompt, role="decision", json_mode=True, temperature=0.2, max_tokens=400, timeout_local=75, eviter=None):
    """Retourne (texte, nom_du_modele) ou (None, None). Ne leve jamais.
    role: 'decision' | 'critique' | 'leger'. eviter: fournisseur a ne pas utiliser (ex: celui de l'analyste)."""
    if requests is None:
        return None, None
    prompt = _tronquer(prompt)
    tokens_est = len(prompt) // 4 + max_tokens
    for f in ORDRE.get(role, ORDRE["decision"]):
        base = "local" if f.startswith("local") else f
        if eviter and base == eviter and base != "local":
            continue
        if base in ("groq", "openrouter", "gemini") and not {"groq": cle_groq, "openrouter": cle_openrouter, "gemini": cle_gemini}[base]():
            continue                                   # pas de cle : on saute sans compter d'echec
        if base in LIBRES and not LIBRE_ACTIF:
            continue
        if not _quota_ok(base, tokens_est):
            continue
        t0 = time.time()
        try:
            if f == "groq":
                (texte, tokens), modele = _groq(prompt, json_mode, temperature, max_tokens)
            elif f == "openrouter":
                (texte, tokens), modele = _openrouter(prompt, json_mode, temperature, max_tokens)
            elif f == "gemini":
                (texte, tokens), modele = _gemini(prompt, json_mode, temperature, max_tokens)
            elif f in LIBRES:
                (texte, tokens), modele = _libre(f, prompt, json_mode, temperature, max_tokens)
            else:
                m = MODELE_LOCAL_CRITIQUE if f == "local_critique" else MODELE_LOCAL
                (texte, tokens), modele = _local(prompt, json_mode, temperature, max_tokens, m, max(timeout_local, TIMEOUT_LOCAL_MIN))
            if texte:
                _noter(base, True, tokens, (time.time() - t0) * 1000, modele)
                return texte, modele
            _noter(base, False)
        except Exception as e:
            msg = str(e)
            # 429/402 = quota epuise : Gemini -> pause 30 min ; fournisseur libre -> pause 3 min ; 5xx/absent -> 10 min
            if "429" in msg or "402" in msg:
                pause = 180 if base in LIBRES else 1800
            elif base in LIBRES and any(k in msg for k in ("HTTP 5", "HTTP 404", "HTTP 401", "HTTP 403", "resolve", "Connection")):
                pause = 600
            else:
                pause = 0
            _noter(base, False, pause_s=pause)
            _log(f"{f} echec ({role}, {len(prompt)} car.): {msg[:200]}")
            continue
    return None, None


def fournisseur_de(modele):
    """'openai/gpt-oss-120b' -> 'groq', 'gemini-2.5-flash' -> 'gemini', etc."""
    if not modele:
        return None
    if modele == GROQ_MODELE:
        return "groq"
    if modele in OPENROUTER_MODELES or ":free" in modele:
        return "openrouter"
    if modele.startswith("gemini"):
        return "gemini"
    for nom, (_, m, _) in LIBRES.items():
        if modele == m:
            return nom
    return "local"


def extraire_json(texte):
    if not texte:
        return None
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", m.group()))
        except Exception:
            return None


def _log(msg):
    try:
        with open(os.path.join(DOSSIER, "llm_router.log"), "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ------------------------------------------------------------------ CLI
def _test():
    prompt = 'Reponds uniquement en JSON: {"ok": true, "modele": "<ton nom>", "calcul": <resultat de 17*23>}'
    for f in ["groq", "openrouter", "gemini"] + list(LIBRES) + ["local"]:
        t0 = time.time()
        try:
            if f == "groq":
                (t, n), m = _groq(prompt, True, 0, 60)
            elif f == "openrouter":
                (t, n), m = _openrouter(prompt, True, 0, 60)
            elif f == "gemini":
                (t, n), m = _gemini(prompt, True, 0, 60)
            elif f in LIBRES:
                (t, n), m = _libre(f, prompt, True, 0, 60)
            else:
                (t, n), m = _local(prompt, True, 0, 60, MODELE_LOCAL, 120)
            j = extraire_json(t) or {}
            print(f"  {f:12s} OK  {m}  {int((time.time()-t0)*1000)} ms  calcul={j.get('calcul')} (attendu 391)")
        except Exception as e:
            print(f"  {f:12s} --  {str(e)[:120]}")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "quotas"
    if cmd == "test":
        print("Test des fournisseurs :")
        _test()
    else:
        q = quotas()
        print(f"Quotas LLM du {q['jour']} (UTC) :")
        for nom, v in q["fournisseurs"].items():
            lim = v["limite_jour"] or "illimite"
            pause = f"  PAUSE {v['pause_min']} min (quota 429)" if v.get("pause_min") else ""
            print(f"  {nom:12s} cle={'oui' if v['cle'] else 'NON'}  appels={v['appels_jour']}/{lim}  ok={v['ok']}  echecs={v['echecs']}  latence={v['latence_moy_ms']} ms  {v['dernier_modele'] or ''}{pause}")
