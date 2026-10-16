#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journal_erreurs.py — Le bot apprend de ses erreurs (pour de vrai). JAMAIS remis a zero.

1. A l'OUVERTURE: photographie le contexte (BTC 1h/24h, RSI, ATR, heure, distance au plus
   haut 24h, stops recents) et verifie les REGLES APPRISES. Calcule le stop adapte a la
   volatilite et le montant a risque fixe (1 EUR / trade).
2. A la FERMETURE: classe l'erreur si perte:
     contre_btc        BTC baissait sur l'heure a l'entree
     cascade           >= 2 stops dans l'heure precedant l'entree
     mauvaise_heure    entree dans une tranche horaire perdante
     achat_sommet      RSI > 65 ou prix a < 0.5% du plus haut 24h
     gain_non_encaisse le prix a monte de >= 1% apres l'entree puis a fini en perte
     stop_trop_serre   (verifie 2h apres) le prix a atteint le TP apres le stop
3. REGLES: quand une classe compte >= 10 cas et >= 8 EUR de pertes, elle devient une regle
   de filtrage active, avec ses stats (bloques, pertes evitees estimees). Jamais supprimee,
   desactivable a la main.
4. MEMOIRE POUR L'IA: trades similaires + regles + erreurs couteuses, injectes dans le prompt.
"""
import json
import os
import threading
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "journal_erreurs.json")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
_LOCK = threading.Lock()

SEUIL_N_REGLE, SEUIL_PERTE_REGLE = 10, -8.0
HEURES_PERDANTES = set(range(12, 16))   # 12h-16h: -46 EUR sur 83 trades (bilan 16/10)
RISQUE_EUR, SL_MIN, SL_MAX, ATR_MULT = 1.0, 0.5, 1.0, 1.2

DESCRIPTIONS = {
    "contre_btc": "Entree pendant que BTC baissait sur l'heure (< -0.3%)",
    "cascade": "Entree juste apres >= 2 stops dans l'heure (marche en train de tomber)",
    "mauvaise_heure": "Entree dans la tranche horaire perdante (12h-16h)",
    "achat_sommet": "Achat au sommet (RSI > 65 ou a moins de 0.5% du plus haut 24h)",
    "gain_non_encaisse": "Le prix a monte de >= 1% puis le trade a fini en perte",
    "stop_trop_serre": "Le prix a atteint le TP dans les 2h apres le stop",
}


# ------------------------------------------------------------------ fichier
def _charger():
    try:
        with open(FICHIER) as f:
            return json.load(f)
    except Exception:
        return {"cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"), "trades": [], "classes": {},
                "regles": {}, "a_verifier": [], "seed_fait": False}


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


# ------------------------------------------------------------------ indicateurs
def _atr_pct(bougies, periode=14):
    if not bougies or len(bougies) < periode + 1:
        return None
    trs = []
    for i in range(-periode, 0):
        b, prev = bougies[i], bougies[i - 1]
        tr = max(b["haut"] - b["bas"], abs(b["haut"] - prev["cloture"]), abs(b["bas"] - prev["cloture"]))
        trs.append(tr)
    atr = sum(trs) / periode
    return round(atr / bougies[-1]["cloture"] * 100, 3) if bougies[-1]["cloture"] else None


def _rsi(clotures, periode=14):
    try:
        import indicateurs as ind
        return ind.rsi(clotures, periode)
    except Exception:
        return None


def _stops_recents(minutes=60):
    try:
        pf = json.load(open(PT_FILE))
        seuil = datetime.now() - timedelta(minutes=minutes)
        n = 0
        for t in pf.get("trades_fermes", [])[-40:]:
            d = _dt(t.get("date_fermeture"))
            if d and d >= seuil and str(t.get("raison", "")).upper().startswith("SL"):
                n += 1
        return n
    except Exception:
        return 0


def contexte_entree(sym, prix):
    """Photo du marche au moment d'entrer. Toutes les cles peuvent etre None si l'API echoue."""
    ctx = {"sym": sym, "prix": prix, "heure": datetime.now().hour, "jour": datetime.now().weekday(),
           "btc_var_1h": None, "btc_var_bougie": None, "btc_var_24h": None,
           "rsi": None, "atr_pct": None, "var_24h": None, "dist_haut_24h": None,
           "sl_recents_1h": _stops_recents(60)}
    try:
        import indicateurs as ind
        if sym != "BTCUSDT":
            bb = ind.historique_ohlcv("BTCUSDT", "1h", 30)
        else:
            bb = None
        bs = ind.historique_ohlcv(sym, "1h", 40)
        if sym == "BTCUSDT":
            bb = bs
        if bb and len(bb) >= 26:
            ctx["btc_var_1h"] = round((bb[-1]["cloture"] - bb[-2]["cloture"]) / bb[-2]["cloture"] * 100, 3)
            ctx["btc_var_bougie"] = round((bb[-1]["cloture"] - bb[-1]["ouverture"]) / bb[-1]["ouverture"] * 100, 3)
            ctx["btc_var_24h"] = round((bb[-1]["cloture"] - bb[-25]["cloture"]) / bb[-25]["cloture"] * 100, 2)
        if bs and len(bs) >= 26:
            cl = [b["cloture"] for b in bs]
            ctx["rsi"] = round(_rsi(cl) or 0, 1) or None
            ctx["atr_pct"] = _atr_pct(bs)
            ctx["var_24h"] = round((cl[-1] - cl[-25]) / cl[-25] * 100, 2)
            # NB: bougies KuCoin en USDT, prix du bot en EUR -> on compare bougie a bougie
            haut24 = max(b["haut"] for b in bs[-24:])
            ctx["dist_haut_24h"] = round((haut24 - cl[-1]) / haut24 * 100, 3) if haut24 else None
    except Exception as e:
        ctx["erreur"] = str(e)[:80]
    return ctx


# ------------------------------------------------------------------ regles
_TESTS_REGLES = {
    "contre_btc": lambda c: (c.get("btc_var_1h") is not None and c["btc_var_1h"] < -0.3)
                            or (c.get("btc_var_bougie") is not None and c["btc_var_bougie"] < -0.3),
    "cascade": lambda c: (c.get("sl_recents_1h") or 0) >= 2,
    "mauvaise_heure": lambda c: c.get("heure") in HEURES_PERDANTES,
    "achat_sommet": lambda c: (c.get("rsi") is not None and c["rsi"] > 65)
                              or (c.get("dist_haut_24h") is not None and c["dist_haut_24h"] < 0.5),
}


def _generer_regles(d):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for cls, st in d["classes"].items():
        if cls not in _TESTS_REGLES:
            continue
        r = d["regles"].setdefault(cls, {"active": False, "forcee": None, "creee_le": None, "n_bloques": 0,
                                         "perte_evitee_est": 0.0, "description": DESCRIPTIONS.get(cls, cls)})
        merite = st["n"] >= SEUIL_N_REGLE and st["perte"] <= SEUIL_PERTE_REGLE
        if r["forcee"] is None:
            if merite and not r["active"]:
                r["active"] = True; r["creee_le"] = r["creee_le"] or now
                print(f"  [REGLE] Nouvelle regle apprise: {cls} ({st['n']} cas, {st['perte']:+.1f} EUR) -> {r['description']}")
        else:
            r["active"] = bool(r["forcee"])
        r["n_cas"] = st["n"]; r["perte_cas"] = round(st["perte"], 2)
        r["perte_moy"] = round(st["perte"] / st["n"], 2) if st["n"] else 0


def regles_bloquent(ctx, compter=True):
    """(bloque, raison). Incremente les stats de la regle declenchee."""
    with _LOCK:
        d = _charger()
        for cls, r in d["regles"].items():
            if not r.get("active"):
                continue
            try:
                if _TESTS_REGLES[cls](ctx):
                    if compter:
                        r["n_bloques"] = r.get("n_bloques", 0) + 1
                        r["perte_evitee_est"] = round(r.get("perte_evitee_est", 0) + abs(r.get("perte_moy", 1.0)), 2)
                        r["dernier_blocage"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        _sauver(d)
                    return True, f"regle apprise '{cls}': {r['description']}"
            except Exception:
                continue
    return False, ""


def forcer_regle(cls, etat):
    """etat: True (forcer active) / False (desactiver) / None (auto)."""
    with _LOCK:
        d = _charger()
        r = d["regles"].setdefault(cls, {"active": False, "forcee": None, "n_bloques": 0, "perte_evitee_est": 0.0,
                                         "description": DESCRIPTIONS.get(cls, cls)})
        r["forcee"] = etat
        _generer_regles(d)
        _sauver(d)


# ------------------------------------------------------------------ entree
def preparer_entree(sym, prix, montant_prevu, liquidites, liquidite_min=200.0):
    """Appele AVANT d'ouvrir. Retourne dict:
       ok, raison, montant, sl_pct, ctx. Applique les regles + stop ATR + risque fixe."""
    ctx = contexte_entree(sym, prix)
    bloque, raison = regles_bloquent(ctx)
    if bloque:
        return {"ok": False, "raison": raison, "ctx": ctx, "montant": 0, "sl_pct": None}
    atr = ctx.get("atr_pct")
    sl = round(min(SL_MAX, max(SL_MIN, ATR_MULT * atr)), 2) if atr else SL_MIN
    montant_risque = RISQUE_EUR / (sl / 100.0)              # 1 EUR / 0.5% = 200 ; 1 EUR / 1% = 100
    dispo = max(0.0, liquidites - liquidite_min)
    montant = min(montant_risque, dispo)
    if montant < 50:
        return {"ok": False, "raison": f"liquidites insuffisantes pour un trade a risque ({dispo:.0f} EUR dispo)", "ctx": ctx, "montant": 0, "sl_pct": sl}
    return {"ok": True, "raison": f"SL {sl}% (ATR {atr if atr is not None else '?'}%) montant {montant:.0f} EUR = risque {montant*sl/100:.2f} EUR",
            "montant": round(montant, 2), "sl_pct": sl, "ctx": ctx}


# ------------------------------------------------------------------ fermeture
def _classes_fermeture(position, raison, gain, prix_sortie):
    ctx = position.get("contexte") or {}
    classes = []
    if gain >= 0:
        return classes
    if _TESTS_REGLES["contre_btc"](ctx): classes.append("contre_btc")
    if _TESTS_REGLES["cascade"](ctx): classes.append("cascade")
    if _TESTS_REGLES["mauvaise_heure"]({"heure": (_dt(position.get("date_ouverture")) or datetime.now()).hour}): classes.append("mauvaise_heure")
    if _TESTS_REGLES["achat_sommet"](ctx): classes.append("achat_sommet")
    # gain_non_encaisse: plus haut atteint depuis l'entree >= +1%
    try:
        import indicateurs as ind
        d0 = _dt(position.get("date_ouverture"))
        if d0:
            heures = max(2, int((datetime.now() - d0).total_seconds() // 3600) + 2)
            bs = ind.historique_ohlcv(position["symbole"], "1h", min(200, heures))
            if bs:
                t0 = d0.timestamp()
                apres = [b for b in bs if float(b.get("temps", 0)) >= t0 - 3600]
                # reference = ouverture de la bougie d'entree (meme devise que les hauts)
                if apres and apres[0]["ouverture"] and max(b["haut"] for b in apres) >= apres[0]["ouverture"] * 1.01:
                    classes.append("gain_non_encaisse")
    except Exception:
        pass
    return classes


def enregistrer_fermeture(position, prix_sortie, raison, gain):
    """Hook appele par fermer_position. Jamais bloquant (try/except chez l'appelant)."""
    classes = _classes_fermeture(position, raison, gain, prix_sortie)
    rec = {
        "id": f"{position.get('date_ouverture','')}|{position.get('symbole','')}",
        "sym": position.get("symbole"), "strategie": position.get("strategie") or position.get("source") or "inconnu",
        "gain": round(float(gain), 2), "raison": str(raison)[:60], "prix_entree": position.get("prix_entree"),
        "prix_sortie": prix_sortie, "montant": position.get("montant_eur"), "sl_pct": position.get("sl_risque"),
        "date_ouverture": position.get("date_ouverture"), "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "contexte": position.get("contexte"), "classes": classes, "post_mortem": None,
    }
    with _LOCK:
        d = _charger()
        d["trades"].append(rec)
        for cls in classes:
            st = d["classes"].setdefault(cls, {"n": 0, "perte": 0.0, "description": DESCRIPTIONS.get(cls, cls)})
            st["n"] += 1; st["perte"] = round(st["perte"] + min(0.0, float(gain)), 2)
        if gain < 0 and str(raison).upper().startswith("SL"):
            tp = float(position.get("tp_adaptatif") or 1.5)
            tp = min(tp, 1.5)
            d["a_verifier"].append({"id": rec["id"], "sym": rec["sym"], "prix_entree": rec["prix_entree"],
                                    "tp_pct": tp, "sl_pct": float(position.get("sl_risque") or 0.5),
                                    "date_fermeture": rec["date_fermeture"], "gain": rec["gain"]})
        _generer_regles(d)
        _sauver(d)
    if classes:
        print(f"  [ERREUR-APPRISE] {rec['sym']} {gain:+.2f} EUR -> {', '.join(classes)}")
    if gain < 0:
        threading.Thread(target=_post_mortem_ia, args=(rec,), daemon=True).start()
    return classes


def verifier_stops_serres():
    """A appeler a chaque tick: 2h apres un stop, regarde si le prix a atteint le TP."""
    with _LOCK:
        d = _charger()
        attente = d.get("a_verifier", [])
    if not attente:
        return 0
    now = datetime.now()
    restants, verifies = [], 0
    try:
        import indicateurs as ind
    except Exception:
        return 0
    for item in attente:
        df = _dt(item["date_fermeture"])
        if not df:
            continue
        age_h = (now - df).total_seconds() / 3600
        if age_h < 2:
            restants.append(item); continue
        if age_h > 48:
            continue  # trop vieux, on abandonne
        try:
            bs = ind.historique_ohlcv(item["sym"], "1h", 6)
            t0 = df.timestamp()
            apres = [b for b in (bs or []) if float(b.get("temps", 0)) >= t0 - 3600]
            # Depuis le niveau du stop, le TP est a (1+tp)/(1-sl)-1 au-dessus (devises differentes -> ratio)
            sl = float(item.get("sl_pct") or 0.5)
            hausse_requise = (1 + item["tp_pct"] / 100) / (1 - sl / 100) - 1
            ref = apres[0]["ouverture"] if apres else None
            serre = bool(ref) and max(b["haut"] for b in apres) >= ref * (1 + hausse_requise)
        except Exception:
            restants.append(item); continue
        verifies += 1
        with _LOCK:
            d = _charger()
            for t in d["trades"]:
                if t["id"] == item["id"]:
                    t["verif_stop"] = {"tp_atteint_apres": serre, "verifie_le": now.strftime("%Y-%m-%d %H:%M")}
                    if serre and "stop_trop_serre" not in t["classes"]:
                        t["classes"].append("stop_trop_serre")
                        st = d["classes"].setdefault("stop_trop_serre", {"n": 0, "perte": 0.0, "description": DESCRIPTIONS["stop_trop_serre"]})
                        st["n"] += 1; st["perte"] = round(st["perte"] + min(0.0, float(item.get("gain", 0))), 2)
                        print(f"  [ERREUR-APPRISE] {item['sym']}: stop trop serre (TP {item['tp_pct']}% atteint dans les 2h apres le stop)")
                    break
            d["a_verifier"] = [x for x in d["a_verifier"] if x["id"] != item["id"]]
            _sauver(d)
    with _LOCK:
        d = _charger()
        ids_restants = {x["id"] for x in restants}
        d["a_verifier"] = [x for x in d["a_verifier"] if x["id"] in ids_restants or (_dt(x["date_fermeture"]) and (now - _dt(x["date_fermeture"])).total_seconds() < 7200)]
        _sauver(d)
    return verifies


# ------------------------------------------------------------------ post-mortem IA (local, en thread)
def _post_mortem_ia(rec):
    try:
        import requests
        ctx = rec.get("contexte") or {}
        prompt = (f"Trade perdant: {rec['sym']} strategie {rec['strategie']}, entree {rec['prix_entree']}, sortie {rec['prix_sortie']}, "
                  f"resultat {rec['gain']:+.2f} EUR, raison de sortie '{rec['raison']}'. Contexte a l'entree: BTC 1h {ctx.get('btc_var_1h')}%, "
                  f"BTC 24h {ctx.get('btc_var_24h')}%, RSI {ctx.get('rsi')}, ATR {ctx.get('atr_pct')}%, heure {ctx.get('heure')}h, "
                  f"distance au plus haut 24h {ctx.get('dist_haut_24h')}%, stops dans l'heure {ctx.get('sl_recents_1h')}. "
                  f"Erreurs detectees: {', '.join(rec.get('classes') or []) or 'aucune'}. "
                  "En UNE phrase en francais (max 25 mots), dis la cause principale de la perte et la lecon.")
        r = requests.post("http://localhost:11434/api/chat", timeout=40, json={
            "model": "qwen2.5:7b", "stream": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.2, "num_predict": 80}})
        if r.status_code != 200:
            return
        texte = r.json()["message"]["content"].strip().replace("\n", " ")[:220]
        with _LOCK:
            d = _charger()
            for t in reversed(d["trades"]):
                if t["id"] == rec["id"]:
                    t["post_mortem"] = texte; break
            _sauver(d)
        print(f"  [POST-MORTEM] {rec['sym']}: {texte}")
    except Exception:
        pass


# ------------------------------------------------------------------ memoire pour l'IA
def similaires(sym, ctx=None, n=4):
    d = _charger()
    ctx = ctx or {}
    def score(t):
        s = 0
        if t.get("sym") == sym: s += 3
        c = t.get("contexte") or {}
        if ctx.get("heure") is not None and c.get("heure") is not None and abs(c["heure"] - ctx["heure"]) <= 2: s += 1
        if ctx.get("btc_var_1h") is not None and c.get("btc_var_1h") is not None and (c["btc_var_1h"] < 0) == (ctx["btc_var_1h"] < 0): s += 1
        if ctx.get("rsi") and c.get("rsi") and abs(c["rsi"] - ctx["rsi"]) <= 8: s += 1
        return s
    cands = sorted(d["trades"], key=lambda t: (score(t), t.get("date_fermeture", "")), reverse=True)
    return [t for t in cands if score(t) >= 3][:n]


def resume_pour_ia(symboles=None, ctx_par_sym=None):
    """Bloc texte a injecter dans le prompt de l'IA: regles, erreurs couteuses, trades similaires."""
    d = _charger()
    lignes = []
    actives = [(k, r) for k, r in d["regles"].items() if r.get("active")]
    if actives:
        lignes.append("REGLES APPRISES (le bot BLOQUERA ces entrees, ne les propose pas):")
        for k, r in actives:
            lignes.append(f"  - {r['description']} [{r.get('n_cas',0)} pertes, {r.get('perte_cas',0):+.1f} EUR]")
    if d["classes"]:
        top = sorted(d["classes"].items(), key=lambda x: x[1]["perte"])[:4]
        lignes.append("TES ERREURS LES PLUS COUTEUSES:")
        for k, st in top:
            lignes.append(f"  - {st.get('description', k)}: {st['n']} fois, {st['perte']:+.1f} EUR")
    if symboles:
        for sym in list(symboles)[:6]:
            sims = similaires(sym, (ctx_par_sym or {}).get(sym), n=3)
            if sims:
                parts = []
                for t in sims:
                    pm = f" — {t['post_mortem']}" if t.get("post_mortem") else ""
                    parts.append(f"{t['date_fermeture'][5:16]} {t['gain']:+.2f}EUR ({t['raison'][:12]}){pm}")
                lignes.append(f"  {sym} derniers trades: " + " | ".join(parts))
    try:
        import registre_strategies as rs
        lignes.append("REGISTRE DES STRATEGIES:")
        lignes.append(rs.resume_pour_ia())
    except Exception:
        pass
    return "\n".join(lignes)


# ------------------------------------------------------------------ seed depuis l'historique
def initialiser_depuis_historique():
    """Une seule fois: reconstruit les classes 'mauvaise_heure' et 'cascade' depuis les 400+ trades
    existants (pas de contexte marche pour eux, mais les heures et les sequences sont connues)."""
    with _LOCK:
        d = _charger()
        if d.get("seed_fait"):
            return 0
        try:
            trades = json.load(open(PT_FILE)).get("trades_fermes", [])
        except Exception:
            trades = []
        trades = sorted(trades, key=lambda t: str(t.get("date_fermeture", "")))
        fermetures_sl = [(_dt(t.get("date_fermeture")), t) for t in trades if str(t.get("raison", "")).upper().startswith("SL")]
        n = 0
        for t in trades:
            gain = float(t.get("gain_eur", 0) or 0)
            if gain >= 0:
                continue
            d0 = _dt(t.get("date_ouverture"))
            if not d0:
                continue
            classes = []
            if d0.hour in HEURES_PERDANTES:
                classes.append("mauvaise_heure")
            nb_sl = sum(1 for (df, _) in fermetures_sl if df and d0 - timedelta(minutes=60) <= df < d0)
            if nb_sl >= 2:
                classes.append("cascade")
            if not classes:
                continue
            n += 1
            d["trades"].append({"id": f"{t.get('date_ouverture','')}|{t.get('symbole','')}", "sym": t.get("symbole"),
                                "strategie": t.get("strategie") or t.get("source") or "inconnu", "gain": round(gain, 2),
                                "raison": str(t.get("raison", ""))[:60], "prix_entree": t.get("prix_entree"),
                                "prix_sortie": t.get("prix_sortie"), "montant": t.get("montant_eur"), "sl_pct": None,
                                "date_ouverture": t.get("date_ouverture"), "date_fermeture": t.get("date_fermeture"),
                                "contexte": {"heure": d0.hour, "sl_recents_1h": nb_sl, "historique": True},
                                "classes": classes, "post_mortem": None})
            for cls in classes:
                st = d["classes"].setdefault(cls, {"n": 0, "perte": 0.0, "description": DESCRIPTIONS.get(cls, cls)})
                st["n"] += 1; st["perte"] = round(st["perte"] + gain, 2)
        d["seed_fait"] = True
        _generer_regles(d)
        _sauver(d)
        print(f"  [JOURNAL] Seed depuis l'historique: {n} pertes classees, {len(trades)} trades lus")
        return n


def rapport():
    d = _charger()
    lignes = [f"=== JOURNAL DES ERREURS ({len(d['trades'])} pertes analysees, {len(d.get('a_verifier', []))} stops en attente de verification) ==="]
    lignes.append("Classes d'erreur:")
    for k, st in sorted(d["classes"].items(), key=lambda x: x[1]["perte"]):
        lignes.append(f"  {k:18s} {st['n']:4d} cas  {st['perte']:+8.2f} EUR  — {st.get('description','')}")
    lignes.append("Regles:")
    for k, r in d["regles"].items():
        etat = "ACTIVE" if r.get("active") else "inactive"
        f = " (forcee)" if r.get("forcee") is not None else ""
        lignes.append(f"  {etat:8s}{f} {k:18s} bloques {r.get('n_bloques',0):3d} | pertes evitees est. {r.get('perte_evitee_est',0):+.1f} EUR | base {r.get('n_cas',0)} cas")
    recents = [t for t in d["trades"] if not (t.get("contexte") or {}).get("historique")][-6:]
    if recents:
        lignes.append("Dernieres pertes analysees:")
        for t in recents:
            lignes.append(f"  {t['date_fermeture'][5:16]} {t['sym']:10s} {t['gain']:+.2f} {','.join(t['classes']) or '-'}" + (f" | {t['post_mortem']}" if t.get("post_mortem") else ""))
    return "\n".join(lignes)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "seed":
        initialiser_depuis_historique()
    if len(sys.argv) >= 4 and sys.argv[1] == "regle":
        forcer_regle(sys.argv[2], {"on": True, "off": False, "auto": None}[sys.argv[3]])
    print(rapport())
