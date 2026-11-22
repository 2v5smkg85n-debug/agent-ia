#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
laboratoire.py — le bot observe TOUTES ses strategies sans argent, les juge sur un seul critere, et donne tout seul le
droit d'ouvrir a celles qui font leurs preuves.

Pourquoi (22/11/2026) : le bot « apprenait » surtout en ajoutant des refus (regles tirees de 3 a 5 trades, strategies
coupees, filtres) ; rien ne faisait le chemin inverse. Une strategie sans droit d'ouverture ne produisait plus aucun
trade, donc plus aucune preuve : elle ne pouvait jamais revenir, sauf decision humaine. Et pendant la fenetre interdite
(13h-15h UTC) le bot ne regardait meme pas le marche.

Principe (meme esprit que entonnoir.py : mesure, reversible, jamais d'argent) :
  - `observer(signaux, prix, contexte)` : chaque signal brut (avant tout filtre, y compris les strategies sans droit et
    la fenetre interdite) devient un TRADE VIRTUEL : stop = celui du signal ou 2 x ATR, objectif = TP_RATIO x stop,
    barriere de temps = LABO_HEURES. Un seul trade virtuel a la fois par (strategie, crypto), comme une vraie position
    (la fenetre interdite est comptee a part pour ne pas priver la mesure normale).
  - `juger()` : entree a l'ouverture de la bougie 1h qui SUIT le signal (aucune information du futur), puis stop /
    objectif / barriere. Resultat en R (1 R = le stop), FRAIS ALLER-RETOUR DEDUITS.
  - `bilan()` : par strategie, R moyen net et intervalle de confiance calcule PAR JOUR (20 cryptos qui montent ensemble
    le meme jour ne comptent pas pour 20 preuves independantes).
  - `promouvoir()` : une strategie sans droit dont la borne BASSE du R moyen net est > 0 sur >= LABO_N_MIN trades
    virtuels etales sur >= LABO_JOURS_MIN jours recoit le droit d'ouvrir, en probation (1 position, demi-risque).
    Une strategie retiree par le registre peut etre reprise de la meme facon, mais seulement sur des preuves
    POSTERIEURES a son dernier vrai trade. Le registre continue de la retirer si ses vrais trades perdent.
    Au plus LABO_PROMO_PAR_JOUR promotion par jour et LABO_PROMOS_MAX par strategie ; un statut force a la main n'est
    jamais touche.

Limites a connaitre : un trade virtuel n'a ni glissement ni les sorties reelles du bot (trailing, sortie « stale ») ;
c'est un tri, pas une preuve. La preuve reste les vrais trades en probation, juges par le registre.

Variables : LABO (1), LABO_AUTO (1 ; 0 = observer sans promouvoir), LABO_HEURES (BARRIERE_H, 24), LABO_N_MIN (60),
LABO_JOURS_MIN (10), LABO_Z (2.0), LABO_JOURS (45, fenetre du bilan), LABO_PROMO_PAR_JOUR (1), LABO_PROMOS_MAX (3),
LABO_FENETRE_MIN (10, minutes entre deux observations pendant la fenetre interdite).
CLI : python3 laboratoire.py [bilan|juger|candidats|promouvoir]
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DOSSIER, "laboratoire_log.jsonl")
LOG_EVAL = os.path.join(DOSSIER, "laboratoire_eval.jsonl")
ETAT = os.path.join(DOSSIER, "laboratoire_etat.json")
_LOCK = threading.Lock()
MAX_LIGNES = 40000


def _env(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
        if v not in (None, ""):
            return v
    except Exception:
        pass
    return os.getenv(nom, defaut)


try:
    import stop_atr as _sa
    _BARRIERE, _FRAIS, _RATIO = _sa.BARRIERE_H, _sa.FRAIS_AR_PCT, _sa.TP_RATIO
except Exception:
    _BARRIERE, _FRAIS, _RATIO = 24, 0.2, 2.0

HEURES = int(_env("LABO_HEURES", str(_BARRIERE)))
N_MIN = int(_env("LABO_N_MIN", "60"))
JOURS_MIN = int(_env("LABO_JOURS_MIN", "10"))
Z = float(_env("LABO_Z", "2.0"))
JOURS = int(_env("LABO_JOURS", "45"))
PROMO_PAR_JOUR = int(_env("LABO_PROMO_PAR_JOUR", "1"))
PROMOS_MAX = int(_env("LABO_PROMOS_MAX", "3"))
FENETRE_MIN = float(_env("LABO_FENETRE_MIN", "10"))
FRAIS_AR_PCT = float(_FRAIS)
TP_RATIO = float(_RATIO)
EXPIRE_H = HEURES + 72          # au-dela, les bougies 1h ne sont plus recherchees : l'observation est classee 'expire'
MAX_PAR_CYCLE = 60

_DEDUP = {"src": None, "d": {}}
_DERNIER = {"juger": 0.0, "promouvoir": 0.0, "fenetre": 0.0}


def actif():
    return str(_env("LABO", "1")) == "1"


def auto():
    return actif() and str(_env("LABO_AUTO", "1")) == "1"


# ------------------------------------------------------------------ fichiers
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


def _ecrire(chemin, rec):
    with _LOCK:
        with open(chemin, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _charger_etat():
    try:
        with open(ETAT) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _sauver_etat(d):
    tmp = ETAT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ETAT)


def _strat(signal):
    return str(signal.get("strategie") or signal.get("source") or "inconnu")


def _cle(rec):
    return f"{rec.get('strategie')}|{rec.get('sym')}|{rec.get('ts')}"


# ------------------------------------------------------------------ observation
def _libre_a(ts):
    """Instant a partir duquel un nouveau trade virtuel est permis : la barriere de temps + un decalage de 0 a 5 h tire
    de l'horodatage. Sans lui, un signal permanent serait rejoue chaque jour exactement a la meme heure et le laboratoire
    mesurerait « entrer a 15 h » au lieu de mesurer la strategie."""
    return float(ts) + HEURES * 3600 + int(ts) % 18000


def _dedup():
    """Prochain instant libre par (strategie, crypto, contexte), relu depuis le journal : survit aux redemarrages."""
    if _DEDUP["src"] != LOG:
        d = {}
        for r in _lire(LOG, 5000):
            try:
                d[f"{r.get('strategie')}|{r.get('sym')}|{r.get('contexte', 'normal')}"] = _libre_a(r.get("ts", 0))
            except Exception:
                pass
        _DEDUP["src"], _DEDUP["d"] = LOG, d
    return _DEDUP["d"]


def _sl(sym, signal):
    try:
        import entonnoir as _en
        return float(_en._sl_estime(sym, signal))
    except Exception:
        try:
            v = float(signal.get("sl_pct") or 0)
            return v if 0.3 <= v <= 10 else 1.0
        except Exception:
            return 1.0


def _droit(strat):
    try:
        import registre_strategies as rs
        return bool(rs.a_le_droit(strat)), rs.statut(strat)
    except Exception:
        return None, None


def observer(signaux, prix=None, contexte="normal"):
    """Enregistre chaque signal brut comme trade virtuel. Ne touche jamais au portefeuille. Renvoie le nombre ecrit."""
    if not actif() or not signaux:
        return 0
    n = 0
    try:
        vus = _dedup()
        now = time.time()
        for s in signaux:
            if n >= MAX_PAR_CYCLE:
                break
            try:
                sym = str(s.get("symbole") or "")
                if not sym:
                    continue
                strat = _strat(s)
                k = f"{strat}|{sym}|{contexte}"
                if now < vus.get(k, 0):
                    continue            # un trade virtuel a la fois par (strategie, crypto) dans chaque contexte
                px = (prix or {}).get(sym) if isinstance(prix, dict) else prix
                px = float(px if px is not None else s.get("prix_entree") or 0)
                if px <= 0:
                    continue
                sl = _sl(sym, s)
                droit, statut = _droit(strat)
                rec = {"ts": round(now), "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "strategie": strat,
                       "sym": sym, "prix": px, "sl_pct": sl, "tp_pct": round(sl * TP_RATIO, 2), "score": s.get("score"),
                       "contexte": str(contexte), "droit": droit, "statut": statut}
                _ecrire(LOG, rec)
                vus[k] = _libre_a(rec["ts"])
                n += 1
            except Exception:
                continue
    except Exception:
        pass
    return n


def doit_observer_hors_ouverture():
    """Pendant une fenetre interdite : True au plus une fois toutes les LABO_FENETRE_MIN minutes."""
    if not actif():
        return False
    now = time.time()
    if now - _DERNIER["fenetre"] < FENETRE_MIN * 60:
        return False
    _DERNIER["fenetre"] = now
    return True


# ------------------------------------------------------------------ jugement
def _secondes(t):
    t = float(t or 0)
    return t / 1000.0 if t > 1e11 else t


def jouer(rec, bougies, heures=None):
    """Joue le trade virtuel sur des bougies 1h. Entree a l'ouverture de la premiere bougie qui commence apres le signal.
    Renvoie None si les bougies ne couvrent pas encore la barriere de temps, sinon
    {'resultat': tp|sl|neutre|ecart, 'r_brut', 'r' (net de frais), 'var_fin', 'ref'}."""
    heures = int(heures or HEURES)
    t0 = float(rec["ts"])
    bs = sorted((b for b in (bougies or []) if _secondes(b.get("temps")) >= t0), key=lambda b: _secondes(b.get("temps")))
    if len(bs) < heures or _secondes(bs[0]["temps"]) - t0 > 2 * 3600:
        return None
    ref = float(bs[0]["ouverture"])
    if ref <= 0:
        return None
    px = float(rec.get("prix") or 0)
    if px > 0 and abs(ref / px - 1) > 0.10:
        return {"resultat": "ecart", "r_brut": 0.0, "r": 0.0, "var_fin": None, "ref": ref}   # prix et bougies ne parlent pas du meme actif
    sl = float(rec["sl_pct"])
    tp = float(rec.get("tp_pct") or sl * TP_RATIO)
    res = "neutre"
    for b in bs[:heures]:
        if float(b["bas"]) <= ref * (1 - sl / 100):
            res = "sl"          # stop et objectif dans la meme bougie : on compte le stop (prudent)
            break
        if float(b["haut"]) >= ref * (1 + tp / 100):
            res = "tp"
            break
    var_fin = round((float(bs[heures - 1]["cloture"]) - ref) / ref * 100, 2)
    ratio = tp / sl if sl > 0 else TP_RATIO
    r_brut = ratio if res == "tp" else -1.0 if res == "sl" else max(-1.0, min(ratio, var_fin / sl))
    r = r_brut - FRAIS_AR_PCT / sl
    return {"resultat": res, "r_brut": round(r_brut, 3), "r": round(r, 3), "var_fin": var_fin, "ref": ref}


def juger(max_par_appel=20, force=False):
    """Juge les trades virtuels arrives a leur barriere de temps. Au plus une passe toutes les 5 minutes."""
    if not actif():
        return 0
    now = time.time()
    if not force and now - _DERNIER["juger"] < 300:
        return 0
    _DERNIER["juger"] = now
    try:
        import indicateurs as ind
    except Exception:
        return 0
    deja = {e.get("cle") for e in _lire(LOG_EVAL)}
    bougies, n, essais = {}, 0, 0
    for rec in _lire(LOG):
        if n >= max_par_appel or essais >= max_par_appel * 3:
            break
        cle = _cle(rec)
        if cle in deja:
            continue
        try:
            age_h = (now - float(rec.get("ts", 0))) / 3600.0
        except Exception:
            continue
        if age_h < HEURES + 1.1:
            continue
        v = {"resultat": "expire", "r_brut": 0.0, "r": 0.0, "var_fin": None, "ref": None}
        if age_h <= EXPIRE_H:
            essais += 1
            sym = rec.get("sym")
            try:
                if sym not in bougies:
                    bougies[sym] = ind.historique_ohlcv(sym, "1h", min(1000, EXPIRE_H + 6))
                v = jouer(rec, bougies[sym])
            except Exception:
                v = None
            if v is None:
                continue            # bougies pas encore disponibles : nouvel essai a la prochaine passe
        e = {"cle": cle, "ts": rec.get("ts"), "date": rec.get("date"), "strategie": rec.get("strategie"), "sym": rec.get("sym"),
             "contexte": rec.get("contexte", "normal"), "droit": rec.get("droit"), "sl_pct": rec.get("sl_pct")}
        e.update(v)
        try:
            _ecrire(LOG_EVAL, e)
        except Exception:
            pass
        deja.add(cle)
        n += 1
    if n:
        print(f"  [LABO] {n} trade(s) virtuel(s) juge(s) ({HEURES} h, frais deduits)")
    return n


# ------------------------------------------------------------------ bilan
def _stats(evs):
    """R moyen net et intervalle de confiance par grappes journalieres (les signaux d'un meme jour sont correles)."""
    n = len(evs)
    st = {"n": n, "jours": 0, "tp": 0, "sl": 0, "neutre": 0, "r_total": 0.0, "r_moyen": None, "ic_bas": None, "ic_haut": None}
    if not n:
        return st
    rs = [float(e.get("r") or 0) for e in evs]
    m = sum(rs) / n
    par_jour = {}
    for e, r in zip(evs, rs):
        j = str(e.get("date") or "")[:10]
        par_jour[j] = par_jour.get(j, 0.0) + (r - m)
        if e.get("resultat") in st:
            st[e["resultat"]] += 1
    g = len(par_jour)
    st.update({"jours": g, "r_total": round(sum(rs), 2), "r_moyen": round(m, 3)})
    if g >= 2:
        se = ((g / (g - 1.0)) * sum(v * v for v in par_jour.values())) ** 0.5 / n
        st["ic_bas"], st["ic_haut"] = round(m - Z * se, 3), round(m + Z * se, 3)
    return st


def _verdict(st):
    if st["n"] < N_MIN or st["jours"] < JOURS_MIN or st["ic_bas"] is None:
        return f"trop peu de recul ({st['n']}/{N_MIN} trades virtuels, {st['jours']}/{JOURS_MIN} jours)"
    if st["ic_bas"] > 0:
        return "PROUVEE en observation (borne basse du R net > 0)"
    if st["ic_haut"] < 0:
        return "perdante en observation (borne haute du R net < 0)"
    return "indecise (ni gagnante ni perdante avec confiance)"


def _juges(depuis_ts=None, jours=None):
    lim = time.time() - (jours or JOURS) * 86400
    if depuis_ts:
        lim = max(lim, float(depuis_ts))
    return [e for e in _lire(LOG_EVAL) if e.get("resultat") in ("tp", "sl", "neutre") and float(e.get("ts") or 0) >= lim]


def bilan(jours=None):
    """{'strategies': {nom: stats + verdict}, 'fenetre_interdite': stats, 'hors_fenetre': stats, 'n_observes', 'n_juges'}.
    Les strategies sont jugees hors fenetre interdite (le bot ne peut pas y ouvrir)."""
    evs = _juges(jours=jours)
    normaux = [e for e in evs if e.get("contexte", "normal") != "fenetre_interdite"]
    fen = [e for e in evs if e.get("contexte") == "fenetre_interdite"]
    par = {}
    for e in normaux:
        par.setdefault(str(e.get("strategie")), []).append(e)
    out = {"strategies": {}, "fenetre_interdite": _stats(fen), "hors_fenetre": _stats(normaux), "n_juges": len(evs),
           "n_observes": 0, "heures": HEURES}
    for k, lst in par.items():
        st = _stats(lst)
        st["verdict"] = _verdict(st)
        st["droit"], st["statut"] = _droit(k)
        out["strategies"][k] = st
    try:
        out["n_observes"] = sum(1 for _ in open(LOG))
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ promotion automatique
def _ts(date_str):
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(str(date_str)[:n], fmt).timestamp()
        except Exception:
            continue
    return None


def candidats():
    """Strategies que le laboratoire promouvrait maintenant : [{'strategie', 'action': 'droit'|'reprise', 'stats', 'motif'}]."""
    try:
        import registre_strategies as rs
        reg = rs._charger()
    except Exception:
        return []
    forces = reg.get("forces") or {}
    promos = reg.get("promotions_labo") or {}
    fiches = reg.get("strategies") or {}
    noms = {str(e.get("strategie")) for e in _juges()}
    out = []
    for k in sorted(noms):
        if k in forces or int((promos.get(k) or {}).get("n", 0)) >= PROMOS_MAX:
            continue
        fiche = fiches.get(k) or {}
        statut = fiche.get("statut") or "candidate"
        droit = rs.a_le_droit(k)
        if statut == "retiree":
            # reprise : seules comptent les preuves posterieures au dernier vrai trade (les vrais trades priment)
            depuis = _ts(fiche.get("dernier")) or time.time()
            action = "reprise"
        elif not droit:
            depuis, action = None, "droit"
        else:
            continue                # a deja le droit et n'est pas retiree : c'est le registre qui la juge sur ses vrais trades
        evs = [e for e in _juges(depuis_ts=depuis) if str(e.get("strategie")) == k and e.get("contexte", "normal") != "fenetre_interdite"]
        st = _stats(evs)
        if st["n"] >= N_MIN and st["jours"] >= JOURS_MIN and st["ic_bas"] is not None and st["ic_bas"] > 0:
            motif = (f"laboratoire : {st['n']} trades virtuels sur {st['jours']} jours, R moyen net {st['r_moyen']:+.3f} "
                     f"[{st['ic_bas']:+.3f} ; {st['ic_haut']:+.3f}]")
            out.append({"strategie": k, "action": action, "stats": st, "motif": motif})
    out.sort(key=lambda c: -c["stats"]["ic_bas"])
    return out


def promouvoir(force=False):
    """Donne le droit d'ouvrir (probation) aux strategies prouvees en observation. Une verification par heure, au plus
    LABO_PROMO_PAR_JOUR promotion par jour. Renvoie la liste des promotions faites."""
    if not auto():
        return []
    now = time.time()
    if not force and now - _DERNIER["promouvoir"] < 3600:
        return []
    _DERNIER["promouvoir"] = now
    faits = []
    try:
        import registre_strategies as rs
        etat = _charger_etat()
        hist = etat.setdefault("historique", [])
        jour = datetime.now().strftime("%Y-%m-%d")
        deja_auj = sum(1 for h in hist if str(h.get("date", ""))[:10] == jour)
        for c in candidats():
            if deja_auj >= PROMO_PAR_JOUR:
                break
            rs.promotion_labo(c["strategie"], reprise=(c["action"] == "reprise"), motif=c["motif"])
            h = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "strategie": c["strategie"], "action": c["action"], "motif": c["motif"]}
            hist.append(h)
            faits.append(h)
            deja_auj += 1
            txt = (f"[LABO] {c['strategie']} : {'reprise' if c['action'] == 'reprise' else 'droit d ouverture'} en probation "
                   f"(1 position, demi-risque). {c['motif']}. Le registre la retire si ses vrais trades perdent.")
            print("  " + txt)
            try:
                from telegram_alerte import envoyer
                envoyer(txt)
            except Exception:
                pass
        etat["derniere_verif"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _sauver_etat(etat)
    except Exception as e:
        print(f"  [LABO] promotion impossible: {e}")
    return faits


# ------------------------------------------------------------------ affichage
def _ligne(nom, st):
    if not st.get("n"):
        return f"  {nom:24s} aucun trade virtuel juge"
    ic = f"[{st['ic_bas']:+.2f} ; {st['ic_haut']:+.2f}]" if st.get("ic_bas") is not None else "[intervalle indisponible]"
    return (f"  {nom:24s} {st['n']:4d} juges / {st['jours']:2d} j | obj {st['tp']:3d} stop {st['sl']:3d} neutre {st['neutre']:3d} | "
            f"R net moyen {st['r_moyen']:+.3f} {ic} | total {st['r_total']:+.1f} R")


def rapport():
    b = bilan()
    l = [f"=== LABORATOIRE (trades virtuels, barriere {HEURES} h, frais {FRAIS_AR_PCT} % deduits, {JOURS} derniers jours) ===",
         f"  {b['n_observes']} observe(s), {b['n_juges']} juge(s). Promotion automatique : {'OUI' if auto() else 'NON (LABO_AUTO=0)'} "
         f"(il faut >= {N_MIN} trades virtuels sur >= {JOURS_MIN} jours et une borne basse > 0)."]
    for k, st in sorted(b["strategies"].items(), key=lambda kv: -(kv[1].get("r_total") or 0)):
        droit = "ouvre" if st.get("droit") else "n'ouvre pas"
        l.append(_ligne(k, st))
        l.append(f"      -> {st['verdict']} ; registre : {st.get('statut') or '?'}, {droit}")
    l.append("  --- fenetre interdite (le bot n'y ouvre pas) contre le reste ---")
    l.append(_ligne("dans la fenetre", b["fenetre_interdite"]))
    l.append(_ligne("hors fenetre", b["hors_fenetre"]))
    c = candidats()
    l.append("  Promotions possibles maintenant : " + (", ".join(f"{x['strategie']} ({x['action']})" for x in c) if c else "aucune"))
    for h in (_charger_etat().get("historique") or [])[-5:]:
        l.append(f"  [fait] {h.get('date')} {h.get('strategie')} : {h.get('action')} — {h.get('motif')}")
    return "\n".join(l)


def resume_court():
    try:
        b = bilan()
        pr = [k for k, st in b["strategies"].items() if st["verdict"].startswith("PROUVEE")]
        return (f"Laboratoire : {b['n_juges']} trade(s) virtuel(s) juge(s) sur {b['n_observes']} ; "
                f"prouvees en observation : {', '.join(sorted(pr)) if pr else 'aucune pour l instant'}")
    except Exception:
        return "Laboratoire : indisponible"


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bilan"
    if cmd == "juger":
        print(f"{juger(max_par_appel=200, force=True)} trade(s) virtuel(s) juge(s)")
    elif cmd == "candidats":
        for c in candidats():
            print(f"{c['strategie']} : {c['action']} — {c['motif']}")
        if not candidats():
            print("aucune strategie ne remplit les conditions de promotion")
    elif cmd == "promouvoir":
        f = promouvoir(force=True)
        print(f"{len(f)} promotion(s)" + ("" if auto() else " (LABO_AUTO=0 : rien n'est fait)"))
    else:
        print(rapport())
