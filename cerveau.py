#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cerveau.py — Le cerveau de decision de l'IA, version disciplinee.

Avant: un prompt -> "ACHAT"/"RIEN", jamais evalue.
Maintenant, 5 etapes a chaque analyse:
  1. PRESELECTION chiffree : score composite par crypto (bougies, RSI, regime BTC, volatilite,
     heure, trades similaires, regles apprises). Seules les 3 meilleures passent.
  2. DOSSIER par candidate : bougies 1h + tendance 4h + support/resistance + memoire des trades
     similaires + regles.
  3. ANALYSTE (LLM) : repond en JSON structure avec une checklist de 6 points, une confiance
     0-100, une raison et une condition d'invalidation.
  4. AVOCAT DU DIABLE (2e LLM, modele different si possible) : cherche la faille. Il peut
     opposer son veto.
  5. PORTE : confiance >= seuil adaptatif ET checklist complete ET pas de veto.

Chaque decision (ACHAT ou RIEN) est journalisee puis EVALUEE 4h plus tard sur les bougies:
le cerveau mesure sa propre fiabilite par niveau de confiance (calibration) et releve le
seuil tout seul quand il se surestime. Il apprend aussi ses occasions manquees.
Aucune nouvelle API: Gemini (cle existante) + Ollama local en secours.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta

import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "journal_decisions.json")
_LOCK = threading.Lock()

TP_PCT = 1.5
SEUIL_CONFIANCE_BASE = 65
TOP_N = 3
HEURES_EVAL = 4
MODELE_LOCAL = "qwen2.5:7b"
MODELE_LOCAL_CRITIQUE = "phi4-mini"
THINKING_BUDGET = 512          # Gemini 2.5 Flash: petit budget de raisonnement pour l'analyste (0 = desactive)

CHECKLIST = ["tendance_btc_ok", "pattern_confirme", "pas_au_sommet", "volatilite_ok", "heure_ok", "pas_erreur_passee"]


# ------------------------------------------------------------------ utilitaires
def _gemini_key():
    k = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY") or ""
    if k:
        return k
    try:
        with open(os.path.join(DOSSIER, ".env")) as f:
            for line in f:
                if line.strip().startswith(("GEMINI_KEY", "GEMINI_API_KEY")) and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _llm(prompt, prefer="gemini", temperature=0.2, max_tokens=400, timeout_local=75):
    """Retourne (texte, modele_utilise) ou (None, None). prefer: 'gemini' | 'local' | 'local_critique'."""
    ordre = ["gemini", "local"] if prefer == "gemini" else ([prefer, "gemini", "local"] if prefer != "local" else ["local", "gemini"])
    for m in ordre:
        try:
            if m == "gemini":
                key = _gemini_key()
                if not key:
                    continue
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens + THINKING_BUDGET, "responseMimeType": "application/json",
                                                "thinkingConfig": {"thinkingBudget": THINKING_BUDGET}}}
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    t = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if t:
                        return t, "gemini-2.5-flash"
            else:
                modele = MODELE_LOCAL_CRITIQUE if m == "local_critique" else MODELE_LOCAL
                r = requests.post("http://localhost:11434/api/chat", timeout=timeout_local, json={
                    "model": modele, "stream": False, "format": "json", "messages": [{"role": "user", "content": prompt}],
                    "options": {"temperature": temperature, "num_predict": max_tokens}})
                if r.status_code == 200:
                    t = r.json()["message"]["content"].strip()
                    if t:
                        return t, modele
        except Exception:
            continue
    return None, None


def _json(texte):
    if not texte:
        return None
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        # tolere les virgules finales / quotes simples
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", m.group()).replace("'", '"'))
        except Exception:
            return None


def _charger():
    try:
        with open(FICHIER) as f:
            return json.load(f)
    except Exception:
        return {"cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"), "decisions": [], "calibration": {}, "seuil": SEUIL_CONFIANCE_BASE}


def _sauver(d):
    tmp = FICHIER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, FICHIER)


def _dt(s):
    try:
        return datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


# ------------------------------------------------------------------ regime & dossier
def _ema(vals, n):
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


def regime_btc():
    """Regime BTC: tendance 4h (EMA20 vs EMA50), variation 1h/24h, volatilite."""
    out = {"tendance_4h": "inconnue", "var_1h": None, "var_24h": None, "atr_1h": None}
    try:
        import indicateurs as ind
        b4 = ind.historique_ohlcv("BTCUSDT", "4h", 60)
        if b4 and len(b4) >= 50:
            cl = [b["cloture"] for b in b4]
            e20, e50 = _ema(cl, 20), _ema(cl, 50)
            if e20 and e50:
                ecart = (e20 - e50) / e50 * 100
                out["tendance_4h"] = "haussiere" if ecart > 0.3 else ("baissiere" if ecart < -0.3 else "neutre")
                out["ecart_ema_4h"] = round(ecart, 2)
        b1 = ind.historique_ohlcv("BTCUSDT", "1h", 30)
        if b1 and len(b1) >= 26:
            out["var_1h"] = round((b1[-1]["cloture"] - b1[-2]["cloture"]) / b1[-2]["cloture"] * 100, 2)
            out["var_24h"] = round((b1[-1]["cloture"] - b1[-25]["cloture"]) / b1[-25]["cloture"] * 100, 2)
            import journal_erreurs as je
            out["atr_1h"] = je._atr_pct(b1)
    except Exception:
        pass
    return out


def dossier(sym, prix, rsi, pattern, reg):
    """Dossier complet d'une candidate (texte + donnees)."""
    d = {"sym": sym, "prix": prix, "rsi": rsi, "biais": (pattern or {}).get("biais", 0), "patterns": (pattern or {}).get("patterns", []),
         "tendance_4h": "inconnue", "support": None, "resistance": None, "atr_pct": None, "dist_haut_24h": None, "similaires": []}
    try:
        import indicateurs as ind
        import journal_erreurs as je
        b4 = ind.historique_ohlcv(sym, "4h", 60)
        if b4 and len(b4) >= 50:
            cl = [b["cloture"] for b in b4]
            e20, e50 = _ema(cl, 20), _ema(cl, 50)
            if e20 and e50:
                ecart = (e20 - e50) / e50 * 100
                d["tendance_4h"] = "haussiere" if ecart > 0.3 else ("baissiere" if ecart < -0.3 else "neutre")
        b1 = ind.historique_ohlcv(sym, "1h", 40)
        if b1 and len(b1) >= 26:
            d["atr_pct"] = je._atr_pct(b1)
            haut24 = max(b["haut"] for b in b1[-24:])
            d["dist_haut_24h"] = round((haut24 - b1[-1]["cloture"]) / haut24 * 100, 2)
            # support / resistance simples (plus bas / plus haut des 48 dernieres bougies, en % du prix)
            bas48 = min(b["bas"] for b in b1[-48:]) if len(b1) >= 48 else min(b["bas"] for b in b1)
            haut48 = max(b["haut"] for b in b1[-48:]) if len(b1) >= 48 else haut24
            d["support"] = round((b1[-1]["cloture"] - bas48) / b1[-1]["cloture"] * 100, 2)      # % au-dessus du support
            d["resistance"] = round((haut48 - b1[-1]["cloture"]) / b1[-1]["cloture"] * 100, 2)  # % sous la resistance
        ctx = {"heure": datetime.now().hour, "btc_var_1h": reg.get("var_1h"), "rsi": rsi}
        d["similaires"] = [{"date": t.get("date_fermeture", "")[5:16], "gain": t.get("gain"), "raison": str(t.get("raison", ""))[:14],
                            "classes": t.get("classes", []), "post_mortem": t.get("post_mortem")} for t in je.similaires(sym, ctx, n=3)]
    except Exception:
        pass
    return d


# ------------------------------------------------------------------ 1. preselection
def preselection(prix_data, rsi_data, patterns_data, positions, reg):
    """Score composite -> liste triee [(score, sym, details)]. Exclut ce que les regles bloquent."""
    try:
        import journal_erreurs as je
    except Exception:
        je = None
    detenus = {p.get("symbole") for p in positions}
    heure = datetime.now().hour
    out = []
    for sym, prix in prix_data.items():
        if sym in detenus or not prix:
            continue
        pat = patterns_data.get(sym, {}) if patterns_data else {}
        biais = float(pat.get("biais", 0) or 0)
        rsi = rsi_data.get(sym)
        s, why = 0.0, []
        s += biais * 3; why.append(f"bougies {biais:+.2f}")
        if rsi is not None:
            if rsi < 35: s += 2; why.append(f"RSI {rsi:.0f} survente")
            elif rsi < 50: s += 1; why.append(f"RSI {rsi:.0f}")
            elif rsi > 65: s -= 3; why.append(f"RSI {rsi:.0f} surachat")
        if reg.get("var_1h") is not None and reg["var_1h"] < -0.3: s -= 3; why.append(f"BTC 1h {reg['var_1h']:+.2f}%")
        if reg.get("tendance_4h") == "baissiere": s -= 1; why.append("BTC 4h baissier")
        elif reg.get("tendance_4h") == "haussiere": s += 0.5
        if heure in getattr(je, "HEURES_PERDANTES", set()): s -= 2; why.append("heure perdante")
        ctx = {"sym": sym, "heure": heure, "btc_var_1h": reg.get("var_1h"), "btc_var_bougie": reg.get("var_1h"), "rsi": rsi,
               "sl_recents_1h": je._stops_recents(60) if je else 0, "dist_haut_24h": None}
        if je:
            bloque, raison = je.regles_bloquent(ctx, compter=False)
            if bloque:
                why.append("BLOQUE: " + raison[:40]); out.append((-99, sym, why)); continue
            sims = je.similaires(sym, ctx, n=3)
            if sims:
                moy = sum(float(t.get("gain", 0) or 0) for t in sims) / len(sims)
                if moy < 0: s -= 1.5; why.append(f"similaires {moy:+.2f}EUR")
                else: s += 1; why.append(f"similaires {moy:+.2f}EUR")
        out.append((round(s, 2), sym, why))
    out.sort(key=lambda x: -x[0])
    return out


# ------------------------------------------------------------------ calibration
def _bucket(c):
    c = int(c or 0)
    return "90+" if c >= 90 else "80-89" if c >= 80 else "70-79" if c >= 70 else "60-69" if c >= 60 else "<60"


def seuil_adaptatif(d=None):
    """Seuil = plus petit niveau de confiance ou le cerveau a >= 55% de reussite (>= 8 cas). Min 60, max 85."""
    d = d or _charger()
    cal = d.get("calibration", {})
    seuil = SEUIL_CONFIANCE_BASE
    ordre = ["60-69", "70-79", "80-89", "90+"]
    for i, b in enumerate(ordre):
        st = cal.get(b, {})
        n = st.get("tp", 0) + st.get("sl", 0)
        if n >= 8:
            wr = st["tp"] / n * 100
            if wr >= 55:
                seuil = [60, 70, 80, 90][i]; break
            else:
                seuil = max(seuil, [70, 80, 90, 90][i])
    return int(min(90, max(60, seuil)))


def resume_calibration(d=None):
    d = d or _charger()
    cal = d.get("calibration", {})
    if not cal:
        return f"CALIBRATION: pas encore de donnees (seuil {SEUIL_CONFIANCE_BASE})."
    parts = []
    for b in ["<60", "60-69", "70-79", "80-89", "90+"]:
        st = cal.get(b)
        if not st:
            continue
        n = st.get("tp", 0) + st.get("sl", 0)
        if n:
            parts.append(f"confiance {b}: {st['tp']}/{n} reussites ({st['tp']/n*100:.0f}%)")
    manq = d.get("manquees", 0)
    return f"TA FIABILITE PASSEE (ACHAT evalues 4h apres): " + "; ".join(parts) + f". Occasions manquees (RIEN puis +{TP_PCT}%): {manq}. Seuil actuel: {seuil_adaptatif(d)}."


def evaluer_decisions():
    """A appeler regulierement: evalue les decisions de plus de 4h sur les bougies 1h (ratios)."""
    with _LOCK:
        d = _charger()
    now = datetime.now()
    a_eval = [x for x in d["decisions"] if not x.get("evaluee") and _dt(x["date"]) and (now - _dt(x["date"])).total_seconds() >= HEURES_EVAL * 3600]
    if not a_eval:
        return 0
    try:
        import indicateurs as ind
    except Exception:
        return 0
    n = 0
    for x in a_eval[:10]:
        try:
            if (now - _dt(x["date"])).total_seconds() > 72 * 3600:
                x["evaluee"] = True; x["resultat"] = "expire"; continue
            bs = ind.historique_ohlcv(x["sym"], "1h", 12)
            t0 = _dt(x["date"]).timestamp()
            apres = [b for b in (bs or []) if float(b.get("temps", 0)) >= t0 - 3600]
            if not apres:
                continue
            ref = apres[0]["ouverture"]
            sl = float(x.get("sl_pct") or 0.7)
            res = "neutre"
            for b in apres[:HEURES_EVAL + 1]:
                touche_sl = b["bas"] <= ref * (1 - sl / 100)
                touche_tp = b["haut"] >= ref * (1 + TP_PCT / 100)
                if touche_sl and touche_tp: res = "sl"; break     # ambigu -> prudent
                if touche_sl: res = "sl"; break
                if touche_tp: res = "tp"; break
            x["evaluee"] = True; x["resultat"] = res
            x["var_4h"] = round((apres[min(len(apres) - 1, HEURES_EVAL)]["cloture"] - ref) / ref * 100, 2)
            if x["action"] == "ACHAT":
                b = _bucket(x.get("confiance"))
                st = d["calibration"].setdefault(b, {"tp": 0, "sl": 0, "neutre": 0})
                st[res if res in st else "neutre"] += 1
            elif res == "tp":
                d["manquees"] = d.get("manquees", 0) + 1
                x["manquee"] = True
            n += 1
        except Exception:
            continue
    d["seuil"] = seuil_adaptatif(d)
    with _LOCK:
        _sauver(d)
    if n:
        print(f"  [CERVEAU] {n} decision(s) evaluee(s) -> seuil de confiance {d['seuil']}")
    return n


# ------------------------------------------------------------------ 2-5. decision
def decider(prix_data, rsi_data, patterns_data, lignes_marche, positions, liquidites, memoire_txt="", prof_txt=""):
    """Retourne {"action": "ACHAT"/"RIEN", "symbole", "raison", "confiance", "sl_pct"...} ou None si indisponible."""
    d = _charger()
    seuil = seuil_adaptatif(d)
    reg = regime_btc()
    pre = preselection(prix_data, rsi_data, patterns_data, positions, reg)
    print(f"  [CERVEAU] Regime BTC: {reg.get('tendance_4h')} (1h {reg.get('var_1h')}%, 24h {reg.get('var_24h')}%) | seuil confiance {seuil}")
    for s, sym, why in pre[:6]:
        print(f"  [CERVEAU] preselection {sym:10s} {s:+5.2f}  {'; '.join(why)[:90]}")
    candidats = [(s, sym) for s, sym, _ in pre if s > 0][:TOP_N]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not candidats:
        _journaliser(d, {"date": now, "action": "RIEN", "sym": pre[0][1] if pre else None, "confiance": 0, "etape": "preselection",
                         "raison": "aucun score positif", "sl_pct": None})
        return {"action": "RIEN", "raison": "preselection: aucune crypto avec un score positif", "etape": "preselection"}

    dossiers = [dossier(sym, prix_data[sym], rsi_data.get(sym), (patterns_data or {}).get(sym), reg) for _, sym in candidats]
    lignes_dossiers = []
    for (s, sym), dd in zip(candidats, dossiers):
        bougies = next((l for l in lignes_marche if l.startswith(sym)), "")
        sims = " | ".join(f"{t['date']} {t['gain']:+.2f}EUR ({t['raison']}{', ' + ','.join(t['classes']) if t['classes'] else ''})" for t in dd["similaires"]) or "aucun"
        pm = next((t["post_mortem"] for t in dd["similaires"] if t.get("post_mortem")), None)
        lignes_dossiers.append(
            f"### {sym} (score preselection {s:+.1f})\n{bougies}\n"
            f"Tendance 4h: {dd['tendance_4h']} | ATR 1h: {dd['atr_pct']}% | sous le plus haut 24h: {dd['dist_haut_24h']}% | "
            f"support a {dd['support']}% dessous, resistance a {dd['resistance']}% dessus\n"
            f"Tes trades passes similaires: {sims}" + (f"\nLecon retenue: {pm}" if pm else ""))

    prompt_analyste = f"""Tu es l'analyste d'un desk de trading crypto. Tu dois choisir AU PLUS UNE entree (achat spot, TP +{TP_PCT}%, stop 0.5-1% selon volatilite, horizon quelques heures) ou RIEN.

REGIME BTC: tendance 4h {reg.get('tendance_4h')}, 1h {reg.get('var_1h')}%, 24h {reg.get('var_24h')}%, ATR 1h {reg.get('atr_1h')}%.
Heure locale: {datetime.now().hour}h. Portefeuille: {len(positions)} positions, {liquidites:.0f} EUR.

CANDIDATES (preselectionnees par le systeme):
{chr(10).join(lignes_dossiers)}

{memoire_txt}
{resume_calibration(d)}
{prof_txt}

METHODE (obligatoire):
1. Pour chaque candidate, verifie la checklist: tendance_btc_ok (BTC ne baisse pas sur l'heure et 4h pas baissier), pattern_confirme (pattern haussier 1h avec contexte: fin de baisse, support, volume), pas_au_sommet (RSI < 60 et > 1% sous le plus haut 24h), volatilite_ok (ATR entre 0.3% et 1.5%), heure_ok (pas 12h-16h), pas_erreur_passee (les trades similaires n'ont pas perdu pour une raison toujours presente).
2. Choisis la meilleure SEULEMENT si tous les points sont vrais. Sinon RIEN.
3. Donne une confiance 0-100 honnete: ta fiabilite passee est affichee ci-dessus, ne te surestime pas.
4. Precise ce qui invaliderait l'idee (ex: cloture 1h sous le support).

Reponds UNIQUEMENT en JSON:
{{"action": "ACHAT"|"RIEN", "symbole": "XXXUSDT"|null, "confiance": 0-100,
 "checklist": {{"tendance_btc_ok": true|false, "pattern_confirme": true|false, "pas_au_sommet": true|false, "volatilite_ok": true|false, "heure_ok": true|false, "pas_erreur_passee": true|false}},
 "raison": "2 phrases max, cite pattern + RSI + ce qui differe des pertes passees", "invalidation": "..."}}"""

    texte, modele = _llm(prompt_analyste, prefer="gemini", temperature=0.2, max_tokens=500)
    dec = _json(texte)
    if not dec:
        print("  [CERVEAU] analyste: reponse illisible -> RIEN")
        return None  # laisse l'ancien flux prendre le relais
    dec["modele_analyste"] = modele
    action = str(dec.get("action", "RIEN")).upper()
    sym = str(dec.get("symbole") or "").upper()
    conf = int(float(dec.get("confiance", 0) or 0))
    chk = dec.get("checklist") or {}
    manquants = [k for k in CHECKLIST if not chk.get(k)]
    dd = next((x for x in dossiers if x["sym"] == sym), None)
    sl_pct = None
    if dd and dd.get("atr_pct"):
        sl_pct = round(min(1.0, max(0.5, 1.2 * dd["atr_pct"])), 2)

    if action != "ACHAT" or sym not in prix_data:
        print(f"  [CERVEAU] analyste ({modele}): RIEN — {str(dec.get('raison',''))[:120]}")
        _journaliser(d, {"date": now, "action": "RIEN", "sym": candidats[0][1], "confiance": conf, "etape": "analyste",
                         "raison": str(dec.get("raison", ""))[:200], "sl_pct": sl_pct, "modele": modele})
        return {"action": "RIEN", "raison": dec.get("raison", ""), "etape": "analyste"}

    if manquants or conf < seuil:
        motif = f"checklist incomplete ({', '.join(manquants)})" if manquants else f"confiance {conf} < seuil {seuil}"
        print(f"  [CERVEAU] analyste voulait {sym} (confiance {conf}) mais {motif} -> RIEN")
        _journaliser(d, {"date": now, "action": "RIEN", "sym": sym, "confiance": conf, "etape": "porte", "raison": motif,
                         "sl_pct": sl_pct, "modele": modele, "raison_analyste": str(dec.get("raison", ""))[:200]})
        return {"action": "RIEN", "raison": motif, "etape": "porte"}

    # 4. Avocat du diable (modele different si possible)
    prompt_critique = f"""Tu es l'avocat du diable d'un desk de trading. Un analyste propose d'ACHETER {sym} maintenant.
Sa these: {dec.get('raison')}
Son invalidation: {dec.get('invalidation')}
Sa confiance: {conf}/100.
Dossier: {next((l for l in lignes_dossiers if l.startswith('### ' + sym)), '')}
Regime BTC: {reg}
Regles et erreurs passees du desk:
{memoire_txt[:1500]}

Cherche la FAILLE: contradiction avec le regime BTC, pattern sur-interprete, achat au sommet, volatilite incompatible avec un stop de {sl_pct or 0.7}%, repetition d'une erreur passee, heure defavorable.
Reponds UNIQUEMENT en JSON: {{"verdict": "OK"|"REFUS", "faille": "1 phrase", "confiance_corrigee": 0-100}}"""
    texte_c, modele_c = _llm(prompt_critique, prefer="local_critique" if modele and modele.startswith("gemini") else "gemini", temperature=0.1, max_tokens=200, timeout_local=60)
    crit = _json(texte_c) or {}
    verdict = str(crit.get("verdict", "OK")).upper()
    conf_c = crit.get("confiance_corrigee")
    try:
        conf_c = int(float(conf_c)) if conf_c is not None else None
    except Exception:
        conf_c = None
    conf_finale = int((conf + conf_c) / 2) if conf_c is not None else conf
    if verdict == "REFUS" or conf_finale < seuil:
        motif = f"veto avocat du diable ({modele_c}): {str(crit.get('faille',''))[:140]}" if verdict == "REFUS" else f"confiance corrigee {conf_finale} < seuil {seuil}"
        print(f"  [CERVEAU] {sym}: {motif}")
        _journaliser(d, {"date": now, "action": "RIEN", "sym": sym, "confiance": conf_finale, "etape": "critique", "raison": motif,
                         "sl_pct": sl_pct, "modele": modele, "modele_critique": modele_c, "raison_analyste": str(dec.get("raison", ""))[:200]})
        return {"action": "RIEN", "raison": motif, "etape": "critique"}

    raison = f"{str(dec.get('raison',''))[:160]} | confiance {conf_finale} (analyste {modele}, critique {modele_c or 'n/a'}: {str(crit.get('faille','RAS'))[:60]}) | invalidation: {str(dec.get('invalidation',''))[:60]}"
    print(f"  [CERVEAU] ACHAT {sym} confiance {conf_finale} >= {seuil} | checklist OK | critique OK")
    _journaliser(d, {"date": now, "action": "ACHAT", "sym": sym, "confiance": conf_finale, "etape": "achat", "raison": raison[:300],
                     "sl_pct": sl_pct, "modele": modele, "modele_critique": modele_c, "checklist": chk, "invalidation": str(dec.get("invalidation", ""))[:160]})
    return {"action": "ACHAT", "symbole": sym, "raison": raison, "confiance": conf_finale, "sl_pct": sl_pct,
            "invalidation": dec.get("invalidation", ""), "etape": "achat"}


def _journaliser(d, rec):
    with _LOCK:
        dd = _charger()
        dd["decisions"].append(rec)
        dd["decisions"] = dd["decisions"][-2000:]
        _sauver(dd)


def rapport():
    d = _charger()
    decs = d.get("decisions", [])
    achats = [x for x in decs if x["action"] == "ACHAT"]
    riens = [x for x in decs if x["action"] == "RIEN"]
    lignes = [f"=== CERVEAU ({len(decs)} decisions, {len(achats)} ACHAT, {len(riens)} RIEN) — seuil de confiance {seuil_adaptatif(d)} ==="]
    lignes.append(resume_calibration(d))
    from collections import Counter
    lignes.append("Pourquoi RIEN: " + ", ".join(f"{k}: {v}" for k, v in Counter(x.get("etape") for x in riens).items()))
    for x in decs[-8:]:
        ev = f" -> {x.get('resultat')} ({x.get('var_4h'):+.2f}% a 4h)" if x.get("evaluee") and x.get("var_4h") is not None else (" -> " + x.get("resultat", "") if x.get("evaluee") else "")
        lignes.append(f"  {x['date'][5:16]} {x['action']:5s} {str(x.get('sym') or '-'):10s} conf {x.get('confiance',0):3d} [{x.get('etape','')}] {str(x.get('raison',''))[:70]}{ev}")
    return "\n".join(lignes)


if __name__ == "__main__":
    evaluer_decisions()
    print(rapport())
