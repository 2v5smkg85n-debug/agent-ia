#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
professeur_tabpfn.py — un professeur de plus, en OBSERVATION SEULE : TabPFN (modele de fondation pour tableaux) note
chaque candidat passe par la porte d'entree, et ses notes sont comparees aux resultats. Il ne bloque rien, n'ouvre rien,
et n'est jamais importe par le processus qui gere les positions.

Pourquoi (27/11/2026) : la porte enregistre deja, pour chaque candidat (ouvert OU bloque), une vingtaine de mesures
(tendance lente, regime, ADX, flux d'ordres, liquidite, chaleur, cadence...) et, 8 h plus tard, ce que le trade aurait
donne. Le meta-modele existant (regression logistique) attend un jeu de donnees a part. Ici on reutilise ce que le bot
ecrit deja : aucune nouvelle source, aucune cle.

Matiere premiere : porte_entree_log.jsonl (mesures) + porte_entree_eval.jsonl (resultat 8 h apres, en R).
  - une ligne par (crypto, strategie, heure) : un signal qui insiste pendant une heure ne compte qu'une fois ;
  - etiquette : 1 si le R NET de frais est > 0, sinon 0.

Notation honnete (`noter`) : les candidats sont notes jour par jour. Pour noter le jour J, le modele ne voit que les
candidats dates d'au moins PROF_TABPFN_EMBARGO_H heures avant J 00:00 UTC (leur resultat etait donc connu). Une note
ecrite n'est jamais recalculee. C'est exactement ce que le modele aurait dit en direct.
A cote, une regression logistique simple est notee sur les MEMES donnees : si TabPFN ne fait pas mieux qu'elle, il ne
sert a rien et le bilan le dit.

Bilan (`bilan`) : AUC hors echantillon, et surtout le R moyen net des candidats « retenus » (note >= taux de reussite
de son jeu d'apprentissage + PROF_TABPFN_MARGE), avec un intervalle de confiance calcule PAR JOUR (vingt candidats du
meme jour ne sont pas vingt preuves). Verdict ecrit a l'avance, comme au laboratoire :
  - moins de PROF_TABPFN_BILAN_N candidats notes ou de PROF_TABPFN_BILAN_JOURS jours : trop peu de recul ;
  - AUC >= 0.55 et borne basse du R net des retenus > 0 : prouve en observation ;
  - sinon : pas de preuve.
Meme « prouve », il ne recoit aucun droit tout seul : c'est une decision humaine.

Isolation : les bibliotheques lourdes (torch, tabpfn) sont dans ~/agent-ia/.tabpfn_libs, chargees UNIQUEMENT par
`python3 professeur_tabpfn.py noter` (minuteur systemd a part, priorite basse, memoire plafonnee). Ce module, importe
par le tableau de bord, n'utilise que la bibliotheque standard. Si TabPFN est absent ou plante, rien d'autre ne change.

Variables (.env) : PROF_TABPFN (1 ; 0 = coupe), PROF_TABPFN_N_MAX (1000 exemples au plus, limite du modele sur
processeur), PROF_TABPFN_N_MIN (150), PROF_TABPFN_EMBARGO_H (12), PROF_TABPFN_LOTS (40 jours notes au plus par passage),
PROF_TABPFN_DELAI_S (600), PROF_TABPFN_THREADS (2), PROF_TABPFN_MARGE (0.05), PROF_TABPFN_BILAN_N (200),
PROF_TABPFN_BILAN_JOURS (10), PROF_TABPFN_Z (2.0).
CLI : python3 professeur_tabpfn.py [bilan|donnees|strategies|noter|verifier|etat]
Modele : TabPFN v2 (poids sous licence Prior Labs, Apache 2.0 avec attribution) — https://github.com/PriorLabs/TabPFN
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LOG_PORTE = os.path.join(DOSSIER, "porte_entree_log.jsonl")
EVAL_PORTE = os.path.join(DOSSIER, "porte_entree_eval.jsonl")
NOTES = os.path.join(DOSSIER, "professeur_tabpfn_notes.jsonl")
ETAT = os.path.join(DOSSIER, "professeur_tabpfn.json")
VERROU = os.path.join(DOSSIER, "professeur_tabpfn.lock")
LIBS = os.path.join(DOSSIER, ".tabpfn_libs")

NUMERIQUES = ["heure_sin", "heure_cos", "weekend", "tl_haussiere", "tl_ecart_pct", "tl_pente_pct", "ch_n_crypto",
              "ch_risque_ouvert", "baisse_stops", "cad_depuis_h", "cad_n_jour", "reg_adx", "reg_atr_pct",
              "reg_atr_percentile", "adx_4h", "cusum_evenement", "cusum_barres_depuis", "cusum_seuil_pct",
              "liq_spread_pct", "liq_log_profondeur", "tfi_30m", "sl_pct", "porte_ok", "v_fenetres", "v_casier"]
CATEGORIES = {"regime": ["tendance", "range", "turbulent"], "famille": ["tendance", "reversion", "autre"],
              "cusum_direction": ["hausse", "baisse"]}
STRATEGIES_MAX = 12
AUC_MIN = 0.55


def _env(nom, defaut):
    try:
        from config_env import lire
        v = lire(nom, None)
        if v not in (None, ""):
            return v
    except Exception:
        pass
    return os.getenv(nom, defaut)


def _f(nom, defaut):
    try:
        return float(_env(nom, defaut))
    except Exception:
        return float(defaut)


def actif():
    return str(_env("PROF_TABPFN", "1")) == "1"


def _frais():
    try:
        import stop_atr as _sa
        return float(_sa.FRAIS_AR_PCT)
    except Exception:
        return 0.2


# ------------------------------------------------------------------ lecture
def _lire(chemin):
    try:
        with open(chemin) as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        d = json.loads(l)
                        if isinstance(d, dict):
                            yield d
                    except Exception:
                        continue
    except Exception:
        return


def _ts(date):
    try:
        return datetime.strptime(str(date)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def _num(x):
    """Nombre fini, ou None. True/False deviennent 1/0."""
    if x is None:
        return None
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    try:
        v = float(x)
    except Exception:
        return None
    return v if math.isfinite(v) else None


def _d(x):
    return x if isinstance(x, dict) else {}


def mesures(rec):
    """Les mesures d'un passage a la porte, a plat. Toute valeur absente reste None (le modele sait faire avec)."""
    i = _d(rec.get("infos"))
    tl, ch, ba, ca = _d(i.get("tendance_lente")), _d(i.get("chaleur")), _d(i.get("baisse")), _d(i.get("cadence"))
    rg, cu, li, ve = _d(i.get("regime")), _d(i.get("cusum")), _d(i.get("liquidite")), _d(i.get("verdicts"))
    f = {k: None for k in NUMERIQUES}
    try:
        d = datetime.strptime(str(i.get("date"))[:16], "%Y-%m-%d %H:%M")
        a = 2 * math.pi * (d.hour + d.minute / 60.0) / 24
        f["heure_sin"], f["heure_cos"], f["weekend"] = round(math.sin(a), 4), round(math.cos(a), 4), 1.0 if d.weekday() >= 5 else 0.0
    except Exception:
        pass
    f["tl_haussiere"], f["tl_ecart_pct"], f["tl_pente_pct"] = _num(tl.get("haussiere")), _num(tl.get("ecart_pct")), _num(tl.get("pente_pct"))
    f["ch_n_crypto"], f["ch_risque_ouvert"] = _num(ch.get("n_crypto")), _num(ch.get("risque_ouvert"))
    f["baisse_stops"] = _num(ba.get("stops"))
    f["cad_depuis_h"], f["cad_n_jour"] = _num(ca.get("depuis_h")), _num(ca.get("n_jour"))
    if f["cad_depuis_h"] is not None:
        f["cad_depuis_h"] = min(f["cad_depuis_h"], 240.0)
    f["reg_adx"], f["reg_atr_pct"], f["reg_atr_percentile"] = _num(rg.get("adx")), _num(rg.get("atr_pct")), _num(rg.get("atr_percentile"))
    f["adx_4h"] = _num(i.get("adx_4h"))
    f["cusum_evenement"], f["cusum_barres_depuis"], f["cusum_seuil_pct"] = _num(cu.get("evenement")), _num(cu.get("barres_depuis")), _num(cu.get("seuil_pct"))
    f["liq_spread_pct"] = _num(li.get("spread_pct"))
    p = _num(li.get("profondeur_eur"))
    f["liq_log_profondeur"] = round(math.log10(p), 3) if p and p > 0 else None
    f["tfi_30m"] = _num(i.get("tfi_30m"))
    f["sl_pct"] = _num(rec.get("sl_pct"))
    f["porte_ok"] = _num(bool(rec.get("ok")))
    f["v_fenetres"], f["v_casier"] = _num(ve.get("fenetres")), _num(ve.get("casier"))
    f["regime"] = rg.get("mode") if isinstance(rg.get("mode"), str) else None
    f["famille"] = i.get("famille") if isinstance(i.get("famille"), str) else None
    f["cusum_direction"] = cu.get("direction") if isinstance(cu.get("direction"), str) else None
    f["strategie"] = str(i.get("strategie") or "inconnu")
    return f


def donnees():
    """Candidats juges, du plus ancien au plus recent : [{'cle','date','ts','sym','strategie','f','y','r','resultat'}].
    Une seule ligne par (crypto, strategie, heure)."""
    frais = _frais()
    evals = {}
    for e in _lire(EVAL_PORTE):
        if e.get("resultat") in ("tp", "sl", "neutre") and e.get("cle"):
            evals[e["cle"]] = e
    out, vus = [], set()
    for rec in _lire(LOG_PORTE):
        i = _d(rec.get("infos"))
        cle = f"{i.get('date')}|{i.get('sym')}|{i.get('strategie')}"
        e = evals.get(cle)
        ts = _ts(i.get("date"))
        sl = _num(rec.get("sl_pct"))
        if e is None or ts is None or not sl or sl <= 0:
            continue
        heure = f"{i.get('sym')}|{i.get('strategie')}|{str(i.get('date'))[:13]}"
        if heure in vus:
            continue
        vus.add(heure)
        r = _num(e.get("r"))
        if r is None:
            continue
        r_net = round(r - frais / sl, 3)
        out.append({"cle": cle, "date": str(i.get("date"))[:16], "ts": ts, "sym": i.get("sym"), "strategie": str(i.get("strategie") or "inconnu"),
                    "f": mesures(rec), "y": 1 if r_net > 0 else 0, "r": r_net, "resultat": e.get("resultat"), "ok": bool(rec.get("ok")),
                    "raison": str(rec.get("raison") or "")})
    out.sort(key=lambda x: (x["ts"], x["cle"]))
    return out


def _notes():
    return {n["cle"]: n for n in _lire(NOTES) if n.get("cle")}


def _colonnes(train):
    """Colonnes du tableau : mesures numeriques, puis une colonne 0/1 par categorie et par strategie frequente
    (les strategies sont choisies sur le jeu d'apprentissage seulement)."""
    cols = [("num", k, None) for k in NUMERIQUES]
    for k, valeurs in CATEGORIES.items():
        cols += [("cat", k, v) for v in valeurs]
    freq = {}
    for r in train:
        freq[r["strategie"]] = freq.get(r["strategie"], 0) + 1
    for s, _n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:STRATEGIES_MAX]:
        cols.append(("cat", "strategie", s))
    return cols


def _ligne(r, cols):
    f = r["f"]
    return [(float("nan") if f.get(k) is None else float(f[k])) if t == "num" else (1.0 if f.get(k) == v else 0.0) for t, k, v in cols]


# ------------------------------------------------------------------ notation (seule partie lourde)
def _moteur(threads):
    """Charge torch + TabPFN v2 depuis .tabpfn_libs. Leve une exception si absent : l'appelant l'ecrit dans l'etat."""
    if os.path.isdir(LIBS):
        deja = [m for m in ("numpy", "scipy", "sklearn", "pandas", "torch") if m in sys.modules]
        if deja:        # melanger deux versions d'une bibliotheque dans un meme processus est la panne classique : on refuse
            raise RuntimeError("bibliotheques deja chargees par ce processus (" + ", ".join(deja) + ") : la notation doit tourner dans son propre processus")
        if LIBS in sys.path:
            sys.path.remove(LIBS)
        sys.path.insert(0, LIBS)
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(k, str(threads))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TABPFN_MODEL_CACHE_DIR", os.path.join(LIBS, "modeles"))
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(LIBS, "mpl"))
    try:
        if any(n.endswith(".ckpt") for n in os.listdir(os.environ["TABPFN_MODEL_CACHE_DIR"])):
            os.environ.setdefault("HF_HUB_OFFLINE", "1")     # poids deja telecharges : plus aucun appel reseau
    except Exception:
        pass
    import warnings
    warnings.filterwarnings("ignore")
    import numpy as np
    import torch
    torch.set_num_threads(threads)
    import tabpfn
    from tabpfn import TabPFNClassifier
    from tabpfn.constants import ModelVersion
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def predire(Xtr, ytr, Xte):
        A, B = np.array(Xtr, dtype=float), np.array(Xte, dtype=float)
        garde = [j for j in range(A.shape[1]) if np.isfinite(A[:, j]).sum() >= 5 and float(np.nanstd(A[:, j])) > 0]
        A, B = A[:, garde], B[:, garde]
        y = np.array(ytr, dtype=int)
        clf = TabPFNClassifier.create_default_for_version(ModelVersion.V2, device="cpu", n_estimators=4, random_state=0)
        clf.fit(A, y)
        p_tab = clf.predict_proba(B)[:, list(clf.classes_).index(1)]
        logit = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.3, max_iter=500))
        logit.fit(A, y)
        p_log = logit.predict_proba(B)[:, list(logit.classes_).index(1)]
        return [float(x) for x in p_tab], [float(x) for x in p_log], len(garde)

    return predire, f"tabpfn {getattr(tabpfn, '__version__', '?')} (poids v2), torch {torch.__version__}, numpy {np.__version__}"


def _sauver_etat(d):
    try:
        ancien = etat()
        ancien.update(d)
        with open(ETAT + ".tmp", "w") as f:
            json.dump(ancien, f, indent=1, ensure_ascii=False)
        os.replace(ETAT + ".tmp", ETAT)
    except Exception:
        pass


def etat():
    try:
        with open(ETAT) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def noter(lots=None, verbose=True, predire=None):
    """Note les candidats juges qui n'ont pas encore de note, jour par jour. `predire` est injectable pour les tests.
    Renvoie le nombre de notes ecrites. Ne touche a rien d'autre qu'a ses deux fichiers."""
    dire = print if verbose else (lambda *a, **k: None)
    if not actif():
        dire("Professeur TabPFN coupe (PROF_TABPFN=0).")
        return 0
    try:
        import fcntl
        verrou = open(VERROU, "w")
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        dire("Une notation est deja en cours : rien a faire.")
        return 0
    t0 = time.time()
    n_max = int(min(1000, _f("PROF_TABPFN_N_MAX", "1000")))
    n_min = int(_f("PROF_TABPFN_N_MIN", "150"))
    embargo = _f("PROF_TABPFN_EMBARGO_H", "12") * 3600
    lots = int(lots if lots is not None else _f("PROF_TABPFN_LOTS", "40"))
    delai = _f("PROF_TABPFN_DELAI_S", "600")
    lignes = donnees()
    deja = _notes()
    a_noter = [r for r in lignes if r["cle"] not in deja]
    jours = sorted(set(r["date"][:10] for r in a_noter))
    moteur = "injecte"
    if predire is None and jours:
        try:
            predire, moteur = _moteur(int(_f("PROF_TABPFN_THREADS", "2")))
        except Exception as ex:
            msg = f"{type(ex).__name__}: {str(ex)[:200]}"
            _sauver_etat({"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "erreur": "TabPFN indisponible — " + msg})
            _sauver_etat({"resume": resume()})
            dire("TabPFN indisponible (rien d'autre n'est touche) : " + msg)
            return 0
    ecrites, sans_note, erreur, faits = 0, 0, None, 0
    for jour in jours:
        if faits >= lots or time.time() - t0 > delai * 0.7:
            break
        coupe = _ts(jour + " 00:00") - embargo
        train = [r for r in lignes if r["ts"] <= coupe][-n_max:]
        test = [r for r in a_noter if r["date"][:10] == jour]
        pos = sum(r["y"] for r in train)
        base = round(pos / len(train), 4) if train else None
        commun = {"note_le": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "n_train": len(train), "base": base}
        if len(train) < n_min or pos < 10 or len(train) - pos < 10:
            notes = [dict(commun, cle=r["cle"], date=r["date"], p=None, p_logit=None) for r in test]   # periode d'apprentissage : pas de note
            sans_note += len(notes)
        else:
            cols = _colonnes(train)
            try:
                p_tab, p_log, n_cols = predire([_ligne(r, cols) for r in train], [r["y"] for r in train], [_ligne(r, cols) for r in test])
            except Exception as ex:
                erreur = f"{type(ex).__name__}: {str(ex)[:200]}"
                break               # on n'ecrit rien pour ce jour : nouvel essai au prochain passage
            notes = [dict(commun, cle=r["cle"], date=r["date"], p=round(a, 4), p_logit=round(b, 4), n_cols=n_cols) for r, a, b in zip(test, p_tab, p_log)]
            faits += 1
        with open(NOTES, "a") as f:
            for n in notes:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
        ecrites += len(notes)
    _sauver_etat({"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "moteur": moteur, "duree_s": round(time.time() - t0, 1),
                  "candidats_juges": len(lignes), "notes_ecrites": ecrites, "dont_sans_note": sans_note, "erreur": erreur})
    b = bilan()
    _sauver_etat({"verdict": b.get("verdict"), "bilan": b, "resume": resume(b)})
    dire(f"Professeur TabPFN : {len(lignes)} candidats juges, {ecrites} traites ce passage "
         f"(dont {sans_note} en periode d'apprentissage) en {time.time() - t0:.0f} s" + (f" | ERREUR : {erreur}" if erreur else ""))
    return ecrites


# ------------------------------------------------------------------ bilan (bibliotheque standard seulement)
def _auc(scores, y):
    paires = sorted(zip(scores, y))
    pos = sum(y)
    neg = len(y) - pos
    if not pos or not neg:
        return None
    somme, i = 0.0, 0
    while i < len(paires):
        j = i
        while j < len(paires) and paires[j][0] == paires[i][0]:
            j += 1
        somme += (i + 1 + j) / 2 * sum(1 for k in range(i, j) if paires[k][1] == 1)
        i = j
    return round((somme - pos * (pos + 1) / 2) / (pos * neg), 3)


def _stats_r(cas, z):
    """R moyen net et intervalle de confiance par grappes journalieres (meme calcul que le laboratoire)."""
    n = len(cas)
    st = {"n": n, "jours": 0, "r_moyen": None, "ic_bas": None, "ic_haut": None, "gagnants": sum(c["y"] for c in cas)}
    if not n:
        return st
    m = sum(c["r"] for c in cas) / n
    par_jour = {}
    for c in cas:
        j = c["date"][:10]
        par_jour[j] = par_jour.get(j, 0.0) + (c["r"] - m)
    g = len(par_jour)
    st.update({"jours": g, "r_moyen": round(m, 3)})
    if g >= 2:
        se = ((g / (g - 1.0)) * sum(v * v for v in par_jour.values())) ** 0.5 / n
        st["ic_bas"], st["ic_haut"] = round(m - z * se, 3), round(m + z * se, 3)
    return st


def bilan():
    """Compare les notes aux resultats. Ne charge aucune bibliotheque lourde."""
    z = _f("PROF_TABPFN_Z", "2.0")
    marge = _f("PROF_TABPFN_MARGE", "0.05")
    n_bilan, j_bilan = int(_f("PROF_TABPFN_BILAN_N", "200")), int(_f("PROF_TABPFN_BILAN_JOURS", "10"))
    lignes = {r["cle"]: r for r in donnees()}
    notes = _notes()
    cas = []
    for cle, n in notes.items():
        r = lignes.get(cle)
        if r is None or n.get("p") is None or n.get("base") is None:
            continue
        cas.append({"date": r["date"], "y": r["y"], "r": r["r"], "p": float(n["p"]), "p_logit": n.get("p_logit"), "base": float(n["base"])})
    out = {"actif": actif(), "candidats_juges": len(lignes), "notes": len(cas), "en_apprentissage": sum(1 for n in notes.values() if n.get("p") is None),
           "jours": len(set(c["date"][:10] for c in cas)), "marge": marge}
    if not cas:
        out["verdict"] = ("aucune note pour l'instant" if lignes else "aucun candidat juge par la porte pour l'instant")
        return out
    y = [c["y"] for c in cas]
    out["taux_reussite"] = round(sum(y) / len(y), 3)
    out["auc_tabpfn"] = _auc([c["p"] for c in cas], y)
    avec_logit = [c for c in cas if c.get("p_logit") is not None]
    out["auc_logit"] = _auc([float(c["p_logit"]) for c in avec_logit], [c["y"] for c in avec_logit]) if avec_logit else None
    out["tous"] = _stats_r(cas, z)
    out["retenus"] = _stats_r([c for c in cas if c["p"] >= c["base"] + marge], z)
    out["ecartes"] = _stats_r([c for c in cas if c["p"] < c["base"] + marge], z)
    out["retenus_logit"] = _stats_r([c for c in avec_logit if float(c["p_logit"]) >= c["base"] + marge], z)
    auc, ret, ec = out["auc_tabpfn"], out["retenus"], out["ecartes"]
    if len(cas) < n_bilan or out["jours"] < j_bilan:
        v = f"trop peu de recul ({len(cas)}/{n_bilan} candidats notes, {out['jours']}/{j_bilan} jours)"
    elif auc is not None and auc >= AUC_MIN and ret["ic_bas"] is not None and ret["ic_bas"] > 0:
        v = "PROUVE en observation : ses retenus gagnent net de frais (borne basse > 0)"
    elif auc is not None and auc >= AUC_MIN and ret["r_moyen"] is not None and ec["r_moyen"] is not None and ret["r_moyen"] > ec["r_moyen"]:
        v = "trie mieux que le hasard, mais ses retenus ne gagnent pas avec confiance"
    else:
        v = "pas de preuve : ne trie pas mieux que le hasard"
    out["verdict"] = v
    if auc is not None and out["auc_logit"] is not None:
        out["contre_logit"] = ("mieux que la regression simple" if auc > out["auc_logit"] + 0.01 else
                               "moins bien que la regression simple" if auc < out["auc_logit"] - 0.01 else "comme la regression simple")
    return out


def _txt_stats(nom, st):
    if not st or not st.get("n"):
        return f"  {nom:<26}: aucun"
    ic = f" [{st['ic_bas']:+.2f} ; {st['ic_haut']:+.2f}]" if st.get("ic_bas") is not None else ""
    return f"  {nom:<26}: {st['n']} candidats sur {st['jours']} jours, {st['gagnants']} gagnants, R moyen net {st['r_moyen']:+.3f}{ic}"


def resume(b=None):
    """Texte court pour la ligne de commande (recalcule le bilan si on ne le lui donne pas)."""
    b = b or bilan()
    e = etat()
    l = ["Professeur TabPFN (observation seule : il ne bloque rien et n'ouvre rien) — " + ("actif" if b["actif"] else "COUPE (PROF_TABPFN=0)"),
         f"  candidats juges par la porte : {b['candidats_juges']} | notes : {b['notes']} sur {b['jours']} jours | en periode d'apprentissage : {b['en_apprentissage']}"]
    if b.get("notes"):
        l.append(f"  taux de reussite net de frais : {b['taux_reussite']:.0%} | AUC TabPFN {b.get('auc_tabpfn')} | AUC regression simple {b.get('auc_logit')}"
                 + (f" -> {b['contre_logit']}" if b.get("contre_logit") else ""))
        l.append(_txt_stats("tous les candidats", b.get("tous")))
        l.append(_txt_stats(f"retenus (note>=base+{b['marge']:g})", b.get("retenus")))
        l.append(_txt_stats("ecartes", b.get("ecartes")))
        l.append(_txt_stats("retenus par la regression", b.get("retenus_logit")))
    l.append("  Verdict : " + str(b.get("verdict")))
    if e.get("date"):
        l.append(f"  Dernier passage : {e.get('date')} UTC" + (f", {e.get('duree_s')} s" if e.get("duree_s") is not None else "")
                 + (f", {e.get('moteur')}" if e.get("moteur") else "") + (f" | ERREUR : {e.get('erreur')}" if e.get("erreur") else ""))
    else:
        l.append("  Dernier passage : jamais (python3 professeur_tabpfn.py noter, ou bash installer_professeur_tabpfn.sh)")
    return "\n".join(l)


def resume_enregistre():
    """Pour le tableau de bord : le texte ecrit au dernier passage, sans rien recalculer."""
    e = etat()
    if e.get("resume"):
        return str(e["resume"])
    return ("Professeur TabPFN (observation seule) : pas encore de passage. Installation : bash installer_professeur_tabpfn.sh"
            if actif() else "Professeur TabPFN : COUPE (PROF_TABPFN=0)")


def verifier():
    """Charge TabPFN et lui fait noter un petit tableau invente. Sert a l'installation : dit si tout fonctionne, et en combien de temps."""
    t0 = time.time()
    try:
        predire, moteur = _moteur(int(_f("PROF_TABPFN_THREADS", "2")))
        X = [[((i * 37 + j * 11) % 17) / 17.0 for j in range(6)] for i in range(80)]
        y = [1 if x[0] + x[1] > 1.0 else 0 for x in X]
        p, _q, _n = predire(X[:60], y[:60], X[60:])
        auc = _auc(p, y[60:])
        print(f"TabPFN OK : {moteur} | essai sur un tableau invente : AUC {auc} en {time.time() - t0:.0f} s")
        return True
    except Exception as ex:
        print(f"TabPFN indisponible : {type(ex).__name__}: {str(ex)[:300]}")
        return False


def resume_donnees():
    lignes = donnees()
    if not lignes:
        return "Aucun candidat juge : il faut porte_entree_log.jsonl et porte_entree_eval.jsonl (ecrits par le bot, juges 8 h apres)."
    y = sum(r["y"] for r in lignes)
    strat = {}
    for r in lignes:
        s = strat.setdefault(r["strategie"], [0, 0, 0.0])
        s[0] += 1
        s[1] += r["y"]
        s[2] += r["r"]
    l = [f"{len(lignes)} candidats juges (un par crypto, strategie et heure), du {lignes[0]['date']} au {lignes[-1]['date']} UTC, "
         f"{len(set(r['date'][:10] for r in lignes))} jours",
         f"  gagnants net de frais : {y} ({y / len(lignes):.0%}) | R moyen net : {sum(r['r'] for r in lignes) / len(lignes):+.3f} | "
         f"porte ouverte : {sum(1 for r in lignes if r['ok'])}, bloquee : {sum(1 for r in lignes if not r['ok'])}"]
    for s, (n, g, r) in sorted(strat.items(), key=lambda kv: -kv[1][0])[:12]:
        l.append(f"  {s:<24} {n:>5} candidats, {g / n:>4.0%} gagnants, R moyen net {r / n:+.3f}")
    vides = [k for k in NUMERIQUES if all(r["f"].get(k) is None for r in lignes)]
    if vides:
        l.append("  mesures toujours absentes : " + ", ".join(vides))
    return "\n".join(l)


def _motif(raison):
    """Raison d'un blocage sans ses chiffres, pour pouvoir compter les blocages de meme nature."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"[-+]?\d+(?:[.,:]\d+)*\s*%?", "N", str(raison))).strip()[:48]


def resume_strategies():
    """Par strategie : ce que ses candidats auraient donne 8 h apres (R net de frais, intervalle par jour), porte ouverte
    et porte bloquee separees, avec les blocages les plus frequents. Lecture seule, bibliotheque standard."""
    lignes = donnees()
    if not lignes:
        return "Aucun candidat juge pour l'instant."
    z = _f("PROF_TABPFN_Z", "2.0")

    def txt(nom, cas):
        st = _stats_r(cas, z)
        if not st["n"]:
            return f"{nom} : aucun"
        ic = f" [{st['ic_bas']:+.2f} ; {st['ic_haut']:+.2f}]" if st.get("ic_bas") is not None else " [intervalle impossible : un seul jour]"
        return f"{nom} : {st['n']} sur {st['jours']} jours, {st['gagnants'] / st['n']:.0%} gagnants, R net {st['r_moyen']:+.3f}{ic}"

    par = {}
    for r in lignes:
        par.setdefault(r["strategie"], []).append(r)
    l = [f"Candidats de la porte juges 8 h apres, du {lignes[0]['date'][:10]} au {lignes[-1]['date'][:10]} (R net de frais, intervalle calcule par jour)",
         txt("TOUS", lignes), txt("  porte ouverte", [r for r in lignes if r["ok"]]), txt("  porte bloquee", [r for r in lignes if not r["ok"]])]
    for s, cas in sorted(par.items(), key=lambda kv: -len(kv[1])):
        l.append("")
        l.append(txt(s, cas))
        l.append(txt("  porte ouverte", [r for r in cas if r["ok"]]))
        bloques = [r for r in cas if not r["ok"]]
        l.append(txt("  porte bloquee", bloques))
        motifs = {}
        for r in bloques:
            m = motifs.setdefault(_motif(r.get("raison")), [])
            m.append(r)
        for m, rs in sorted(motifs.items(), key=lambda kv: -len(kv[1]))[:4]:
            l.append(f"    {len(rs)} x {m} -> R net {sum(x['r'] for x in rs) / len(rs):+.2f}")
        mois = {}
        for r in cas:
            mois.setdefault(r["date"][:7], []).append(r["r"])
        l.append("  par mois : " + " | ".join(f"{k} : {len(v)} candidats, R net {sum(v) / len(v):+.2f}" for k, v in sorted(mois.items())))
    l.append("")
    l.append("A lire avec prudence : un candidat juge n'a ni glissement ni les sorties reelles du bot ; un intervalle qui contient 0 ne prouve rien.")
    return "\n".join(l)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bilan"
    if cmd == "noter":
        noter(lots=int(sys.argv[2]) if len(sys.argv) > 2 else None)
        print(resume())
    elif cmd == "verifier":
        sys.exit(0 if verifier() else 1)
    elif cmd == "donnees":
        print(resume_donnees())
    elif cmd == "strategies":
        print(resume_strategies())
    elif cmd == "etat":
        print(json.dumps({"etat": etat(), "bilan": bilan()}, ensure_ascii=False, indent=1))
    else:
        print(resume())
