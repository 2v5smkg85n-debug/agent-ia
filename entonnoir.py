#!/usr/bin/env python3
"""
entonnoir.py — chaque veto du bot est enregistre, juge 8 h apres, et desarme tout seul s'il coute plus qu'il ne protege.

Pourquoi (11/11/2026) : entre un signal et une ouverture, le bot traverse une vingtaine de couches (apprentissage,
trader pro, agents, maitres, professeurs (Hyperliquid + professeur virtuel, voir professeurs_veto.py), intelligence, ML,
sous-agents, cooldowns, volatilite, gates sentiment/macro/social,
bougies, meta-IA, S/R, correlation, regles d'erreur...). Chacune a ete ajoutee pour une bonne raison, aucune n'etait
mesuree : seule la porte l'etait, et son bilan contrefactuel a montre que ses propres filtres avaient coute +119,8 R
en 3 semaines (648 candidats bloques -> 141 objectifs / 212 stops / 295 neutres). Le meme tableau manquait pour tout
ce qui tue un signal AVANT la porte.

Principe (identique a PORTE_AUTO, mesure et reversible) :
  - `veto(couche, signal, prix, pf, msg)` : enregistre le candidat tue (crypto, strategie, prix, stop/objectif estimes)
    et renvoie True si la couche est ARMEE (le bot bloque) ou False si elle est DESARMEE (le signal continue, mais le
    veto reste enregistre et juge : on continue de mesurer la couche).
  - `appliquer(couche, avant, apres, prix)` : meme chose pour une couche qui filtre une liste de signaux.
  - `juger()` : 8 h apres, sur les bougies 1h, chaque veto devient 'tp' (objectif 2 x stop touche d'abord), 'sl' ou
    'neutre' ; en R (1 R = le stop). Appele a chaque cycle du paper trading.
  - `bilan()` : par couche, R evite = -(R des candidats tues). > 0 : la couche protege ; < 0 : elle coute des gains.
  - `armee(couche)` : desarmee quand >= N_MIN vetos juges et R evite <= R_DESARME ; rearmee des que R evite >= 0.
    Les couches de securite (PROTEGEES) ne se desarment jamais : plancher de liquidite, flash crash, circuit breaker,
    nombre max de positions, blacklist/registre (cycle de vie des strategies), tradable sur Revolut X, casier (deja
    mesure), porte (a son propre mecanisme), protection du capital.
Un meme couple (couche, crypto, strategie) n'est enregistre qu'une fois par DEDUP_H heures : les signaux se repetent a
chaque cycle et une seule situation ne doit pas compter 30 fois.
Variables : ENTONNOIR_AUTO (1), ENTONNOIR_N_MIN (30), ENTONNOIR_R_DESARME (-10), ENTONNOIR_HEURES (8), ENTONNOIR_DEDUP_H (2),
ENTONNOIR_<COUCHE>=0 pour couper une couche a la main, =1 pour la forcer armee.
CLI : python3 entonnoir.py [bilan|juger|desarmees]
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DOSSIER, "entonnoir_log.jsonl")
LOG_EVAL = os.path.join(DOSSIER, "entonnoir_eval.jsonl")
_LOCK = threading.Lock()


def _env(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
        if v not in (None, ""):
            return v
    except Exception:
        pass
    return os.getenv(nom, defaut)


N_MIN = int(_env("ENTONNOIR_N_MIN", "30"))
R_DESARME = float(_env("ENTONNOIR_R_DESARME", "-10"))
HEURES = int(_env("ENTONNOIR_HEURES", "8"))
DEDUP_H = float(_env("ENTONNOIR_DEDUP_H", "2"))
TP_RATIO = float(os.getenv("TP_RATIO", "2.0"))
MAX_LIGNES = 20000

PROTEGEES = {"liquidite_plancher", "flash", "circuit_breaker", "max_positions", "blacklist", "registre", "revolut_x",
             "casier", "porte", "protection_capital", "stagger", "montant_min", "anti_gap"}

_DEDUP = {}
_BILAN = {"t": 0.0, "v": None}
_SL_CACHE = {}


# ------------------------------------------------------------------ enregistrement
def _sl_estime(sym, signal):
    """Stop estime en % : celui du signal s'il existe, sinon 2 x ATR(14, 1h) borne comme stop_atr (cache 15 min)."""
    for k in ("sl_pct", "sl_risque", "sl_optimal_pro", "sl_adaptatif"):
        try:
            v = float(signal.get(k) or 0)
            if 0.3 <= v <= 10:
                return round(v, 2)
        except Exception:
            pass
    e = _SL_CACHE.get(sym)
    if e and time.time() - e[0] < 900:
        return e[1]
    sl = 1.0
    try:
        import indicateurs as ind
        import stop_atr as sa
        b = ind.historique_ohlcv(sym, "1h", 30)
        sl = sa.stop_pct(sa.atr_pct(b))
    except Exception:
        pass
    _SL_CACHE[sym] = (time.time(), sl)
    return sl


def _strat(signal):
    return str(signal.get("strategie") or signal.get("source") or "inconnu")


def enregistrer(couche, signal, prix=None, armee_=True):
    """Journalise un veto (dedoublonne par couche/crypto/strategie sur DEDUP_H heures). Renvoie True si ecrit."""
    try:
        sym = str(signal.get("symbole") or "")
        if not sym:
            return False
        cle = f"{couche}|{sym}|{_strat(signal)}"
        now = time.time()
        if now - _DEDUP.get(cle, 0) < DEDUP_H * 3600:
            return False
        _DEDUP[cle] = now
        try:
            px = float(prix if prix is not None else signal.get("prix_entree") or 0)
        except Exception:
            px = 0.0
        if px <= 0:
            return False
        sl = _sl_estime(sym, signal)
        rec = {"ts": round(now), "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "couche": str(couche),
               "sym": sym, "strategie": _strat(signal), "prix": px, "sl_pct": sl, "tp_pct": round(sl * TP_RATIO, 2),
               "armee": bool(armee_), "score": signal.get("score")}
        with _LOCK:
            with open(LOG, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def _lire(chemin, n=MAX_LIGNES):
    out = []
    try:
        with open(chemin) as f:
            lignes = f.readlines()
        for l in lignes[-n:]:
            l = l.strip()
            if l:
                try:
                    out.append(json.loads(l))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _cle(rec):
    return f"{rec.get('couche')}|{rec.get('sym')}|{rec.get('strategie')}|{rec.get('ts')}"


# ------------------------------------------------------------------ jugement contrefactuel
def juger(max_par_appel=15):
    """Juge chaque veto HEURES h apres sur les bougies 1h : objectif TP_RATIO x stop d'abord -> tp, stop -> sl, sinon neutre.
    Ne touche jamais au portefeuille."""
    try:
        import indicateurs as ind
    except Exception:
        return 0
    deja = {e.get("cle") for e in _lire(LOG_EVAL)}
    now = time.time()
    n = 0
    for rec in _lire(LOG, 3000):
        if n >= max_par_appel:
            break
        cle = _cle(rec)
        if cle in deja:
            continue
        age_h = (now - float(rec.get("ts", 0))) / 3600.0
        if age_h < HEURES:
            continue
        res, var_fin = "expire", None
        if age_h <= 72:
            try:
                bs = ind.historique_ohlcv(rec["sym"], "1h", min(72, int(age_h) + 4))
                t0 = float(rec["ts"])
                apres = [b for b in (bs or []) if float(b.get("temps", 0)) >= t0 - 3600]
                if not apres:
                    continue
                ref = float(rec["prix"]) or float(apres[0]["ouverture"])
                sl = float(rec["sl_pct"]); tp = float(rec.get("tp_pct") or sl * TP_RATIO)
                res = "neutre"
                for b in apres[:HEURES + 1]:
                    t_sl = float(b["bas"]) <= ref * (1 - sl / 100)
                    t_tp = float(b["haut"]) >= ref * (1 + tp / 100)
                    if t_sl and t_tp: res = "sl"; break
                    if t_sl: res = "sl"; break
                    if t_tp: res = "tp"; break
                var_fin = round((float(apres[min(len(apres) - 1, HEURES)]["cloture"]) - ref) / ref * 100, 2)
            except Exception:
                continue
        r = (TP_RATIO if res == "tp" else -1.0 if res == "sl" else
             (round(max(-1.0, min(TP_RATIO, var_fin / float(rec["sl_pct"]))), 2) if var_fin is not None else 0.0))
        e = {"cle": cle, "couche": rec.get("couche"), "sym": rec.get("sym"), "strategie": rec.get("strategie"),
             "date": rec.get("date"), "armee": rec.get("armee", True), "sl_pct": rec.get("sl_pct"), "tp_pct": rec.get("tp_pct"),
             "resultat": res, "var_fin": var_fin, "r": r}
        try:
            with _LOCK:
                with open(LOG_EVAL, "a") as f:
                    f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass
        deja.add(cle)
        n += 1
    if n:
        print(f"  [ENTONNOIR] {n} veto(s) juge(s) {HEURES} h apres (contrefactuel)")
        _BILAN["t"] = 0.0
    return n


def bilan(fenetre=400):
    """Par couche : vetos juges (tp/sl/neutre), R evite = -(R des candidats tues), verdict. `fenetre` = derniers vetos
    juges pris en compte par couche (le bilan suit la couche dans le temps, une couche rearmee peut se faire redesarmer)."""
    evs = [e for e in _lire(LOG_EVAL) if e.get("resultat") in ("tp", "sl", "neutre")]
    par = {}
    for e in evs:
        par.setdefault(str(e.get("couche")), []).append(e)
    out = {"n_juges": len(evs), "couches": {}, "n_vetos": 0}
    for c, lst in par.items():
        lst = lst[-fenetre:]
        st = {"n": len(lst), "tp": 0, "sl": 0, "neutre": 0, "r": 0.0, "laisses_passer": 0}
        for e in lst:
            st[e["resultat"]] += 1
            st["r"] = round(st["r"] + float(e.get("r") or 0), 2)
            if e.get("armee") is False:
                st["laisses_passer"] += 1
        st["r_evite"] = round(-st["r"], 2)
        st["protegee"] = c in PROTEGEES
        if st["protegee"]:
            st["verdict"] = "protegee (jamais desarmee)" + (" — couterait" if st["r_evite"] < 0 and st["n"] >= N_MIN else "")
        elif st["n"] < N_MIN:
            st["verdict"] = f"trop peu de cas ({st['n']}/{N_MIN})"
        elif st["r_evite"] <= R_DESARME:
            st["verdict"] = "DESARMEE (nuisible mesuree)"
        elif st["r_evite"] < 0:
            st["verdict"] = "a surveiller (coute un peu)"
        else:
            st["verdict"] = "utile"
        out["couches"][c] = st
    # vetos non encore juges, pour l'affichage
    try:
        out["n_vetos"] = sum(1 for _ in open(LOG))
    except Exception:
        pass
    return out


def _bilan_cache():
    if time.time() - _BILAN["t"] > 600 or _BILAN["v"] is None:
        try:
            _BILAN["v"] = bilan()
        except Exception:
            _BILAN["v"] = {"couches": {}}
        _BILAN["t"] = time.time()
    return _BILAN["v"]


_ETAT = {}   # hysteresis : couche -> True (armee) / False


def armee(couche):
    """True si la couche doit bloquer. Protegee -> toujours. ENTONNOIR_<COUCHE>=0 -> jamais, =1 -> toujours.
    Sinon : desarmee quand >= N_MIN vetos juges et R evite <= R_DESARME ; rearmee quand R evite >= 0."""
    c = str(couche)
    if c in PROTEGEES:
        return True
    force = _env(f"ENTONNOIR_{c.upper()}", None)
    if force == "0":
        return False
    if force == "1":
        return True
    if _env("ENTONNOIR_AUTO", "1") != "1":
        return True
    st = (_bilan_cache().get("couches") or {}).get(c)
    if not st or st["n"] < N_MIN:
        return _ETAT.get(c, True)
    etat = _ETAT.get(c, True)
    if etat and st["r_evite"] <= R_DESARME:
        etat = False
    elif not etat and st["r_evite"] >= 0:
        etat = True
    _ETAT[c] = etat
    return etat


def desarmees():
    return sorted(c for c in (_bilan_cache().get("couches") or {}) if c not in PROTEGEES and not armee(c))


# ------------------------------------------------------------------ branchements
def veto(couche, signal, prix=None, pf=None, msg=""):
    """A mettre a la place de `print(...); return False` : renvoie True s'il faut bloquer."""
    a = armee(couche)
    enregistrer(couche, signal, prix, armee_=a)
    if msg:
        print(msg + ("" if a else f" -> couche '{couche}' DESARMEE (mesuree nuisible), le signal continue"))
    return a


def appliquer(couche, avant, apres, prix=None):
    """Couche qui filtre une liste : enregistre les signaux tues ; renvoie `apres` si la couche est armee, sinon `avant`."""
    try:
        # cle par (crypto, strategie) : certaines couches renvoient des copies des dicts (ml_filtre), pas les memes objets
        def _k(s):
            return (str(s.get("symbole") or ""), str(s.get("strategie") or ""))
        restants = {_k(s) for s in apres}
        tues = [s for s in avant if _k(s) not in restants]
        if not tues:
            return apres
        a = armee(couche)
        for s in tues:
            px = None
            try:
                px = (prix or {}).get(s.get("symbole")) if isinstance(prix, dict) else prix
            except Exception:
                px = None
            enregistrer(couche, s, px, armee_=a)
        if a:
            return apres
        print(f"  [ENTONNOIR] couche '{couche}' DESARMEE (mesuree nuisible) : {len(tues)} signal(aux) qu'elle aurait tue(s) continuent")
        return avant
    except Exception:
        return apres


def contexte_pour_ia():
    """Phrase courte pour le prompt du cerveau / l'analyste."""
    try:
        d = desarmees()
        b = _bilan_cache()
        pires = sorted(((c, st) for c, st in (b.get("couches") or {}).items() if st["n"] >= N_MIN), key=lambda kv: kv[1]["r_evite"])[:3]
        parts = []
        if d:
            parts.append("COUCHES DESARMEES (mesurees nuisibles, elles ne bloquent plus) : " + ", ".join(d))
        if pires:
            parts.append("Couches les plus couteuses : " + ", ".join(f"{c} {st['r_evite']:+.1f} R sur {st['n']}" for c, st in pires))
        return "\n".join(parts)
    except Exception:
        return ""


def resume_court():
    b = _bilan_cache()
    cs = b.get("couches") or {}
    if not cs:
        return f"Entonnoir : {b.get('n_vetos', 0)} veto(s) enregistre(s), aucun encore juge (il faut {HEURES} h)."
    d = desarmees()
    l = [f"Entonnoir : {b['n_juges']} veto(s) juge(s) sur {b.get('n_vetos', 0)} ; desarmees : {', '.join(d) if d else 'aucune'}"]
    for c, st in sorted(cs.items(), key=lambda kv: kv[1]["r_evite"]):
        l.append(f"  {c:18s} {st['n']:4d} tues (objectif {st['tp']}, stop {st['sl']}) -> R evite {st['r_evite']:+.1f} : {st['verdict']}")
    return "\n".join(l)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bilan"
    if cmd == "juger":
        print(juger(max_par_appel=60), "veto(s) juge(s)")
    elif cmd == "desarmees":
        print(desarmees())
    else:
        juger(max_par_appel=60)
        print(resume_court())
