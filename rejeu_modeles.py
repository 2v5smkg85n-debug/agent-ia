#!/usr/bin/env python3
"""
rejeu_modeles.py — deux mesures apprises sur les trades du rejeu historique (27/11/2026). OBSERVATION SEULE.

Lance par rejeu_historique.py dans un processus a part, avec les bibliotheques de ~/agent-ia/.rejeu_libs
(numpy, LightGBM, Optuna : un dossier separe, les bibliotheques du bot ne sont ni mises a jour ni remplacees).
Ce module n'ecrit que rejeu_modeles.json. Il ne modifie aucun reglage, n'ouvre rien, ne bloque rien.

    filtre    : LightGBM apprend « ce signal finira-t-il gagnant ? » (meta-etiquetage, Lopez de Prado) sur les
                trades du rejeu. Marche avant : on apprend sur les annees passees, on teste sur l'annee suivante,
                avec 7 jours d'ecart entre les deux. « Retenus » = signaux notes au moins 5 points au-dessus du
                taux de reussite habituel de leur strategie. Temoin : une regression logistique.
                Reglages du modele fixes a l'avance et volontairement prudents (arbres peu profonds).
    reglages  : Optuna cherche un meilleur quadruplet (multiple d'ATR du stop, rapport objectif/stop, barriere
                de temps, stop maximal) sur tout l'historique SAUF les 12 derniers mois, puis le meilleur essai est
                compare au reglage actuel sur ces 12 mois jamais vus. « A proposer » seulement si la probabilite
                de surapprentissage des essais est < 0,30 ET si l'ecart sur 12 mois est positif avec confiance.
                Rien n'est jamais applique par ce module.

Sources : LightGBM https://github.com/microsoft/LightGBM ; Optuna https://github.com/optuna/optuna
CLI : python3 rejeu_modeles.py [tout|filtre|reglages|verifier]
"""
import calendar
import csv
import json
import os
import random
import sys
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(DOSSIER, ".rejeu_libs")
EMBARGO_J = 7
MARGE = 0.05
PARAMS_LGB = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 200, "feature_fraction": 0.7,
              "bagging_fraction": 0.7, "bagging_freq": 1, "lambda_l2": 5.0, "seed": 0, "deterministic": True,
              "force_row_wise": True, "num_threads": 2, "verbose": -1}
ARBRES = 200
EN_PLUS = ["score", "nb", "atr", "sl"]
BARRIERES = [6, 12, 24, 48, 72]


def _libs():
    if os.path.isdir(LIBS) and LIBS not in sys.path:
        sys.path.insert(0, LIBS)
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(k, "2")
    import numpy as np
    try:
        import lightgbm as lgb
    except Exception:
        lgb = None
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except Exception:
        optuna = None
    return np, lgb, optuna


def _rh():
    if DOSSIER not in sys.path:
        sys.path.append(DOSSIER)
    import rejeu_historique as rh
    return rh


# ------------------------------------------------------------------ filtre appris
def charger_trades(np, rh):
    """Trades techniques du rejeu : (ts, code de strategie, r, X) ; X = indicateurs + score, nb, atr, sl."""
    cols = ["ts", "strat", "r", "res"] + rh.FEATURES + EN_PLUS
    T, S, R, X = [], [], [], []
    code = {s: i for i, s in enumerate(rh.TECH)}
    for l in rh.lire_trades(cols):
        if l[3] == "ecart" or l[1] not in code or l[4] == "":
            continue
        T.append(int(l[0]))
        S.append(code[l[1]])
        R.append(float(l[2]))
        X.append([float(v) if v != "" else float("nan") for v in l[4:]])
        if len(X) >= 200000:                      # conversion par paquets : pas de liste geante en memoire
            yield np.array(T), np.array(S), np.array(R), np.array(X, dtype=np.float32)
            T, S, R, X = [], [], [], []
    if X:
        yield np.array(T), np.array(S), np.array(R), np.array(X, dtype=np.float32)


def auc(np, p, y):
    y = np.asarray(y, dtype=bool)
    pos, neg = int(y.sum()), int((~y).sum())
    if not pos or not neg:
        return None
    _, inv, nb = np.unique(np.asarray(p), return_inverse=True, return_counts=True)
    rangs = (np.cumsum(nb) - (nb - 1) / 2.0)[inv]                              # ex aequo : rang moyen
    return round(float((rangs[y].sum() - pos * (pos + 1) / 2.0) / (pos * neg)), 3)


def logistique(np, Xtr, ytr, Xte, l2=1.0):
    """Regression logistique (Newton), variables centrees-reduites sur l'apprentissage, valeurs manquantes -> moyenne."""
    m = np.nanmean(Xtr, axis=0)
    e = np.nanstd(Xtr, axis=0)
    e[~(e > 0)] = 1.0
    m[~np.isfinite(m)] = 0.0

    def prep(X):
        Z = (X - m) / e
        Z[~np.isfinite(Z)] = 0.0
        return np.hstack([np.ones((len(Z), 1)), np.clip(Z, -5, 5)])
    A, B = prep(Xtr.astype(np.float64)), prep(Xte.astype(np.float64))
    w = np.zeros(A.shape[1])
    y = ytr.astype(np.float64)
    reg = l2 * np.eye(A.shape[1])
    reg[0, 0] = 0.0
    for _ in range(20):
        p = 1.0 / (1.0 + np.exp(-np.clip(A @ w, -30, 30)))
        pas = np.linalg.solve(A.T @ (A * (p * (1 - p))[:, None]) + reg, A.T @ (p - y) + reg @ w)
        w -= pas
        if float(np.abs(pas).max()) < 1e-6:
            break
    return 1.0 / (1.0 + np.exp(-np.clip(B @ w, -30, 30)))


def filtre(np, lgb, rh, journal=print):
    paquets = list(charger_trades(np, rh))
    if not paquets:
        return {"texte": ["6. FILTRE APPRIS : aucun trade technique a etudier."]}
    ts = np.concatenate([p[0] for p in paquets])
    st = np.concatenate([p[1] for p in paquets])
    r = np.concatenate([p[2] for p in paquets])
    X = np.vstack([p[3] for p in paquets])
    del paquets
    y = r > 0
    annee = ts.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    annees = sorted(int(a) for a in np.unique(annee))
    k = len(rh.TECH)
    Xl = np.hstack([X, st[:, None].astype(np.float32)])                       # LightGBM : la strategie est une categorie
    Xo = np.hstack([X, (st[:, None] == np.arange(k)[None, :]).astype(np.float32)])   # temoin : une colonne par strategie
    noms = rh.FEATURES + EN_PLUS + ["strategie"]
    p_lgb, p_log, base = np.full(len(r), np.nan), np.full(len(r), np.nan), np.full(len(r), np.nan)
    importance = None
    testees = []
    for a in annees[2:]:
        debut = calendar.timegm((a, 1, 1, 0, 0, 0))
        tr, te = ts < debut - EMBARGO_J * 86400, annee == a
        if int(tr.sum()) < 3000 or int(te.sum()) < 300:
            continue
        for c in range(k):
            mc = tr & (st == c)
            base[te & (st == c)] = y[mc].mean() if int(mc.sum()) >= 50 else y[tr].mean()
        if lgb is not None:
            modele = lgb.train(PARAMS_LGB, lgb.Dataset(Xl[tr], label=y[tr].astype(int), feature_name=noms, categorical_feature=["strategie"]),
                               num_boost_round=ARBRES)
            p_lgb[te] = modele.predict(Xl[te])
            importance = modele.feature_importance("gain")
        p_log[te] = logistique(np, Xo[tr], y[tr], Xo[te])
        testees.append(a)
        journal(f"  filtre : annee {a} testee ({int(te.sum())} trades, appris sur {int(tr.sum())})")
    L = ["6. FILTRE APPRIS (LightGBM, marche avant annee par annee, 7 jours d'ecart) — resultats HORS echantillon"]
    out = {"annees_testees": testees, "lightgbm": lgb is not None, "strategies": {}}
    if not testees:
        L.append("   Pas assez d'annees pour apprendre sur le passe et tester sur la suite (il en faut trois).")
        out["texte"] = L
        return out
    teste = np.isfinite(p_log)
    p = p_lgb if lgb is not None else p_log
    out["auc_lightgbm"] = auc(np, p_lgb[teste], y[teste]) if lgb is not None else None
    out["auc_temoin"] = auc(np, p_log[teste], y[teste])
    L.append(f"   {int(teste.sum())} trades testes sur {testees[0]}-{testees[-1]}. Pouvoir de tri (AUC, 0,50 = hasard) : "
             + (f"LightGBM {out['auc_lightgbm']:.3f}, " if lgb is not None else "LightGBM absent, ") + f"regression temoin {out['auc_temoin']:.3f}.")
    L.append(f"   {'strategie':<19}{'testes':>8}{'R tous':>9}{'retenus':>9}  {'R des retenus':<25}{'annees +':>9}  verdict")
    garde = teste & (p >= base + MARGE)

    def ligne(nom, masque):
        tous = [(int(a), float(b)) for a, b in zip(ts[masque & teste], r[masque & teste])]
        ret = [(int(a), float(b)) for a, b in zip(ts[masque & garde], r[masque & garde])]
        s_t, s_r, an = rh.stats(tous), rh.stats(ret), rh.par_annee(ret)
        pleines = [v for n, v in an.values() if n >= 30]
        plus = sum(1 for v in pleines if v > 0)
        if s_r["n"] >= 300 and s_r["bas"] is not None and s_r["bas"] > 0 and len(pleines) >= 3 and plus * 3 >= len(pleines) * 2:
            v = "FILTRE UTILE sur l'historique"
        elif s_r["r"] is not None and s_t["r"] is not None and s_r["r"] > s_t["r"]:
            v = "ameliore sans rendre gagnant" if s_r["r"] <= 0 or (s_r["bas"] or -1) <= 0 else "ameliore, preuve incomplete"
        else:
            v = "n'apporte rien"
        out["strategies"][nom] = {"testes": s_t["n"], "r_tous": s_t["r"], "retenus": s_r["n"], "r_retenus": s_r["r"], "bas": s_r["bas"],
                                  "haut": s_r["haut"], "annees_plus": plus, "annees": len(pleines), "verdict": v}
        L.append(f"   {nom:<19}{s_t['n']:>8}{'-' if s_t['r'] is None else format(s_t['r'], '+.3f'):>9}{s_r['n']:>9}  {rh._ic(s_r):<25}"
                 f"{str(plus) + '/' + str(len(pleines)):>9}  {v}")
    for c, nom in enumerate(rh.TECH):
        if int((teste & (st == c)).sum()) >= 100:
            ligne(nom, st == c)
    ligne("TOUTES", np.ones(len(r), dtype=bool))
    if importance is not None:
        ordre = np.argsort(-importance)[:6]
        out["variables"] = [noms[i] for i in ordre]
        L.append("   Ce que le modele regarde le plus : " + ", ".join(noms[i] for i in ordre) + ".")
    L.append("   Un filtre « utile » ici reste une mesure : il ne filtre rien dans le bot et ne recoit aucun droit.")
    out["texte"] = L
    return out


# ------------------------------------------------------------------ reglages (Optuna)
def choisir(np, ts, heures):
    """Indices des signaux retenus avec la regle du laboratoire : un essai, puis le suivant au plus tot apres
    heures + (instant % 5 h)."""
    out, p, n = [], 0, len(ts)
    while p < n:
        out.append(p)
        p = int(np.searchsorted(ts, ts[p] + heures * 3600 + ts[p] % 18000, side="left"))
    return np.array(out, dtype=np.int64)


def _arrondi(np, x, n):
    """Arrondi de Python (exact) et non celui de numpy : 2,5 x 0,77 = 1,925 doit donner 1,93 comme dans le bot."""
    return np.array([round(float(v), n) if v == v else v for v in x], dtype=np.float64)


def issues(np, O, H, L, C, idx, atr, ts, p, sl_min, rapport_us, frais):
    """Version vectorisee de rejeu_historique.jouer pour des reglages p = {atr_mult, tp_ratio, barriere, sl_max}.
    Renvoie (ts, r_net) des trades juges (les 'ecart' et ceux que l'historique ne couvre pas sont retires)."""
    hrs = int(p["barriere"])
    ok = idx + 1 + hrs <= len(C)
    idx, atr, ts = idx[ok], atr[ok], ts[ok]
    if not len(idx):
        return ts, np.zeros(0)
    heure = (ts // 3600) % 24
    mult = np.where((heure >= 13) & (heure < 17), p["atr_mult"] * rapport_us, p["atr_mult"])
    sl = _arrondi(np, np.minimum(p["sl_max"], np.maximum(sl_min, mult * atr)), 2)
    sl[~(atr > 0)] = sl_min
    ref, prix = O[idx + 1], C[idx]
    bon = (ref > 0) & ~(np.abs(ref / prix - 1) > 0.10)
    tp = sl * p["tp_ratio"]
    W = idx[:, None] + 1 + np.arange(hrs)[None, :]
    bas = L[W] <= (ref * (1 - sl / 100))[:, None]
    haut = H[W] >= (ref * (1 + tp / 100))[:, None]
    i_sl = np.where(bas.any(axis=1), bas.argmax(axis=1), hrs)
    i_tp = np.where(haut.any(axis=1), haut.argmax(axis=1), hrs)
    est_sl = (i_sl < hrs) & (i_sl <= i_tp)
    est_tp = (i_tp < hrs) & (i_tp < i_sl)
    var_fin = _arrondi(np, (C[idx + hrs] - ref) / ref * 100, 2)
    rapport = tp / sl
    r_brut = np.where(est_tp, rapport, np.where(est_sl, -1.0, np.maximum(-1.0, np.minimum(rapport, var_fin / sl))))
    return ts[bon], _arrondi(np, r_brut - frais / sl, 3)[bon]


def preparer(np, rh, strategies):
    """Bougies et signaux de chaque crypto en tableaux numpy."""
    data = []
    try:
        fichiers = sorted(f for f in os.listdir(rh.SIGNAUX) if f.endswith(".csv"))
    except OSError:
        fichiers = []
    bits = [1 << rh.TECH.index(s) for s in strategies]
    for f in fichiers:
        sym = f[:-4]
        d = rh.charger_bougies(sym)
        if not d:
            continue
        ts, masque, atr = [], [], []
        with open(os.path.join(rh.SIGNAUX, f), newline="") as g:
            for l in csv.reader(g):
                ts.append(int(l[0]))
                masque.append(int(l[1]))
                atr.append(float(l[2]) if l[2] != "" else float("nan"))
        ts, masque, atr = np.array(ts, dtype=np.int64), np.array(masque, dtype=np.int64), np.array(atr)
        idx = (ts - d["t0"]) // 3600 - 1
        c = {"sym": sym, "O": np.array(d["O"]), "H": np.array(d["H"]), "L": np.array(d["L"]), "C": np.array(d["C"]), "signaux": []}
        for b in bits:
            m = (masque & b) > 0
            if int(m.sum()):
                c["signaux"].append((idx[m], atr[m], ts[m]))
        data.append(c)
    return data


def reglages(np, optuna, rh, journal=print):
    sa = _stop_atr()
    strategies = [s.strip() for s in str(rh._env("REJEU_STRATS_REGLAGES", "rsi_oversold,pattern_reversal,volume_spike")).split(",") if s.strip() in rh.TECH]
    try:
        n_essais = max(5, int(rh._env("REJEU_ESSAIS", "60")))
    except Exception:
        n_essais = 60
    actuel = {"atr_mult": float(sa["ATR_MULT"]), "tp_ratio": float(sa["TP_RATIO"]), "barriere": int(sa["BARRIERE_H"]), "sl_max": float(sa["SL_MAX"])}
    rapport_us = float(sa["ATR_MULT_US"]) / float(sa["ATR_MULT"]) if sa["ATR_MULT"] else 1.25
    data = preparer(np, rh, strategies)
    L = [f"7. REGLAGES DU STOP ET DE L'OBJECTIF (Optuna) — strategies : {', '.join(strategies)}"]
    out = {"strategies": strategies, "actuel": actuel, "optuna": optuna is not None}
    if not data:
        out["texte"] = L + ["   Aucun signal a etudier."]
        return out
    fin = max(int(s[2].max()) for c in data for s in c["signaux"] if len(s[2]))
    coupure = fin - 365 * 86400
    choix, cache = {}, {}

    def evaluer(p):
        cle = (round(p["atr_mult"], 3), round(p["tp_ratio"], 3), int(p["barriere"]), round(p["sl_max"], 3))
        if cle not in cache:
            T, R = [], []
            for ci, c in enumerate(data):
                for si, (idx, atr, ts) in enumerate(c["signaux"]):
                    k = (ci, si, cle[2])
                    if k not in choix:
                        choix[k] = choisir(np, ts, cle[2])
                    g = choix[k]
                    t, r = issues(np, c["O"], c["H"], c["L"], c["C"], idx[g], atr[g], ts[g], p, float(sa["SL_MIN"]), rapport_us, float(sa["FRAIS_AR_PCT"]))
                    T.append(t)
                    R.append(r)
            cache[cle] = (np.concatenate(T), np.concatenate(R))
        return cache[cle]

    def moyenne(p, apres):
        t, r = evaluer(p)
        m = (t >= coupure) if apres else (t < coupure)
        return (float(r[m].mean()) if int(m.sum()) else float("nan")), int(m.sum())

    essais = [dict(actuel)]
    if optuna is not None:
        etude = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=0))
        etude.enqueue_trial({"atr_mult": actuel["atr_mult"], "tp_ratio": actuel["tp_ratio"], "barriere": actuel["barriere"], "sl_max": actuel["sl_max"]})

        def objectif(trial):
            p = {"atr_mult": trial.suggest_float("atr_mult", 1.0, 4.0, step=0.25), "tp_ratio": trial.suggest_float("tp_ratio", 1.0, 4.0, step=0.25),
                 "barriere": trial.suggest_categorical("barriere", BARRIERES), "sl_max": trial.suggest_float("sl_max", 2.0, 6.0, step=0.5)}
            essais.append(p)
            return moyenne(p, False)[0]
        etude.optimize(objectif, n_trials=n_essais)
    else:
        alea = random.Random(0)
        for _ in range(n_essais):
            p = {"atr_mult": alea.randrange(4, 17) / 4.0, "tp_ratio": alea.randrange(4, 17) / 4.0, "barriere": alea.choice(BARRIERES),
                 "sl_max": alea.randrange(4, 13) / 2.0}
            essais.append(p)
            moyenne(p, False)
    uniques = {}
    for p in essais:
        uniques[(round(p["atr_mult"], 3), round(p["tp_ratio"], 3), int(p["barriere"]), round(p["sl_max"], 3))] = p
    meilleur = max(uniques.values(), key=lambda p: moyenne(p, False)[0])

    def par_jour(p, apres):
        t, r = evaluer(p)
        m = (t >= coupure) if apres else (t < coupure)
        j, inv = np.unique(t[m] // 86400, return_inverse=True)
        return dict(zip((int(x) for x in j), (float(x) for x in np.bincount(inv, weights=r[m]))))
    surapp = rh.pbo({str(k): par_jour(p, False) for k, p in uniques.items()})
    a, b = par_jour(actuel, True), par_jour(meilleur, True)
    jours = sorted(set(a) | set(b))
    ecarts = [b.get(j, 0.0) - a.get(j, 0.0) for j in jours]
    m_e = sum(ecarts) / len(ecarts) if ecarts else 0.0
    se = (sum((x - m_e) ** 2 for x in ecarts) / max(1, len(ecarts) - 1)) ** 0.5 / max(1, len(ecarts)) ** 0.5
    bas, haut = m_e - rh.Z * se, m_e + rh.Z * se

    def dire(p):
        return f"stop {p['atr_mult']:g} x ATR (max {p['sl_max']:g} %), objectif {p['tp_ratio']:g} x stop, barriere {int(p['barriere'])} h"
    ra, rb, va, vb = moyenne(actuel, False), moyenne(meilleur, False), moyenne(actuel, True), moyenne(meilleur, True)
    identique = all(abs(float(meilleur[k]) - float(actuel[k])) < 1e-9 for k in actuel)
    t_v, r_v = evaluer(meilleur)
    st_v = rh.stats([(int(x), float(v)) for x, v in zip(t_v[t_v >= coupure], r_v[t_v >= coupure])])
    if identique:
        verdict = "aucun essai ne fait mieux que le reglage actuel sur la periode de recherche : ne rien changer."
    elif st_v["bas"] is None or st_v["bas"] <= 0:
        verdict = ("ne rien changer : meme le meilleur essai ne gagne pas avec confiance sur les 12 mois jamais vus "
                   f"(R net {rh._ic(st_v)}).")
        if meilleur["atr_mult"] > actuel["atr_mult"] or meilleur["sl_max"] > actuel["sl_max"]:
            verdict += " Un stop plus large dilue surtout les frais (0,2 % / stop), il ne cree pas d'avantage."
    elif surapp and surapp["pbo"] < 0.30 and bas > 0:
        verdict = "A PROPOSER — decision commune, rien n'est applique par ce module."
    else:
        verdict = "ne rien changer : " + ("essais trop surappris" if surapp and surapp["pbo"] >= 0.30 else "ecart non etabli sur les 12 mois jamais vus") + "."
    L.append(f"   {len(uniques)} reglages essayes sur tout l'historique sauf les 12 derniers mois ; verification sur ces 12 mois.")
    L.append(f"   Actuel   : {dire(actuel)}")
    L.append(f"              R net {ra[0]:+.3f} sur la recherche ({ra[1]} trades), {va[0]:+.3f} sur les 12 derniers mois ({va[1]}).")
    L.append(f"   Meilleur : {dire(meilleur)}")
    L.append(f"              R net {rb[0]:+.3f} sur la recherche ({rb[1]} trades), {vb[0]:+.3f} sur les 12 derniers mois ({vb[1]}).")
    L.append(f"   Surapprentissage des essais (PBO) : {'-' if not surapp else format(surapp['pbo'], '.2f')} ; ecart par jour sur 12 mois : {m_e:+.3f} R [{bas:+.3f} ; {haut:+.3f}].")
    L.append(f"   Verdict : {verdict}")
    if optuna is None:
        L.append("   (Optuna absent : tirage aleatoire a graine fixe.)")
    out.update({"meilleur": meilleur, "essais": len(uniques), "pbo": surapp, "r_recherche": [ra[0], rb[0]], "r_12_mois": [va[0], vb[0]],
                "ecart_jour": [m_e, bas, haut], "verdict": verdict, "texte": L})
    return out


def _stop_atr():
    """Reglages actuels du stop, lus dans stop_atr.py (module sans dependance)."""
    if DOSSIER not in sys.path:
        sys.path.append(DOSSIER)
    import stop_atr as sa
    return {k: getattr(sa, k) for k in ("ATR_MULT", "ATR_MULT_US", "SL_MIN", "SL_MAX", "TP_RATIO", "BARRIERE_H", "FRAIS_AR_PCT")}


def tout(journal=print):
    np, lgb, optuna = _libs()
    rh = _rh()
    res = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "texte": []}
    for nom, f in (("filtre", lambda: filtre(np, lgb, rh, journal)), ("reglages", lambda: reglages(np, optuna, rh, journal))):
        try:
            res[nom] = f()
            res["texte"].extend(res[nom].pop("texte", []))
        except Exception as e:
            res[nom] = {"erreur": f"{type(e).__name__}: {str(e)[:200]}"}
            res["texte"].append(f"{'6. FILTRE APPRIS' if nom == 'filtre' else '7. REGLAGES'} : calcul impossible ({res[nom]['erreur']}).")
        if nom == "filtre":
            res["texte"].append("")
    with open(rh.MODELES_JSON + ".tmp", "w") as g:
        json.dump(res, g, ensure_ascii=False)
    os.replace(rh.MODELES_JSON + ".tmp", rh.MODELES_JSON)
    return res


def main(argv):
    cmd = argv[0] if argv else "tout"
    if cmd == "verifier":
        np, lgb, optuna = _libs()
        print(f"numpy {np.__version__} ; LightGBM {'absent' if lgb is None else lgb.__version__} ; Optuna {'absent' if optuna is None else optuna.__version__}")
        return 0 if lgb is not None and optuna is not None else 1
    np, lgb, optuna = _libs()
    rh = _rh()
    if cmd == "filtre":
        print("\n".join(filtre(np, lgb, rh)["texte"]))
    elif cmd == "reglages":
        print("\n".join(reglages(np, optuna, rh)["texte"]))
    else:
        print("\n".join(tout()["texte"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
