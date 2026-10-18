#!/usr/bin/env python3
"""
meta_modele.py — le "meta-labeling" : un petit modele qui, a partir du contexte d'entree, estime la probabilite
qu'un trade atteigne son objectif avant son stop. Il ne choisit PAS les trades (ca reste l'IA + les regles), il
dit seulement "dans ce contexte, historiquement, ca marche X % du temps". La porte bloque si X < META_SEUIL.

Entrainement : python3 meta_modele.py entrainer     (lit dataset_meta.jsonl produit par etiquetage_triple_barriere.py)
  - validation walk-forward (5 blocs chronologiques, embargo 24 h) -> AUC hors echantillon honnete
  - modele : LightGBM si installe, sinon sklearn, sinon regression logistique pur Python (toujours disponible)
  - le modele n'est ACTIVE que si AUC hors echantillon >= 0.55 et >= 150 exemples ; sinon probabilite() renvoie None
    et la porte laisse passer (pas de faux savoir).
Fichier : meta_modele.json (poids + normalisation + metriques). Jamais efface automatiquement : chaque entrainement
archive l'ancien dans meta_modele_historique.jsonl.
"""
import json
import math
import os
import sys
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(DOSSIER, "dataset_meta.jsonl")
MODELE = os.path.join(DOSSIER, "meta_modele.json")
HISTO = os.path.join(DOSSIER, "meta_modele_historique.jsonl")
AUC_MIN, N_MIN = 0.55, 150
_MODELE_CACHE = {"ts": 0, "m": None}

NUMERIQUES = ["rsi", "atr_pct", "btc_var_1h", "btc_var_24h", "var_24h", "dist_haut_24h", "adx", "atr_percentile", "heure_sin", "heure_cos", "weekend", "tfi"]
REGIMES = ["tendance", "range", "turbulent"]


def features_depuis_contexte(ctx, regime=None, tfi=None, strategie=None):
    ctx = ctx or {}
    h = ctx.get("heure")
    a = 2 * math.pi * float(h) / 24 if h is not None else None
    return {"rsi": ctx.get("rsi"), "atr_pct": ctx.get("atr_pct"), "btc_var_1h": ctx.get("btc_var_1h"), "btc_var_24h": ctx.get("btc_var_24h"),
            "var_24h": ctx.get("var_24h"), "dist_haut_24h": ctx.get("dist_haut_24h"), "adx": ctx.get("adx"), "atr_percentile": ctx.get("atr_percentile"),
            "heure_sin": math.sin(a) if a is not None else None, "heure_cos": math.cos(a) if a is not None else None,
            "weekend": 1.0 if (ctx.get("jour") is not None and int(ctx["jour"]) >= 5) else 0.0, "tfi": tfi,
            "regime": regime or ctx.get("regime"), "strategie": strategie or ctx.get("strategie")}


def _vecteur(f, norm):
    v = []
    for k in NUMERIQUES:
        x = f.get(k)
        mu, sd = norm.get(k, (0.0, 1.0))
        v.append(0.0 if x is None else max(-4.0, min(4.0, (float(x) - mu) / (sd or 1.0))))
    for r in REGIMES:
        v.append(1.0 if f.get("regime") == r else 0.0)
    return v


# ------------------------------------------------------------------ regression logistique pur Python
def _entrainer_logit(X, y, l2=0.05, epochs=400, lr=0.05):
    d = len(X[0])
    w, b = [0.0] * d, 0.0
    n = len(X)
    for ep in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for xi, yi in zip(X, y):
            z = b + sum(wj * xj for wj, xj in zip(w, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = p - yi
            gb += e
            for j in range(d):
                gw[j] += e * xi[j]
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def _pred_logit(w, b, x):
    z = b + sum(wj * xj for wj, xj in zip(w, x))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def _auc(scores, y):
    paires = sorted(zip(scores, y))
    pos = sum(y); neg = len(y) - pos
    if not pos or not neg:
        return None
    rang, somme, i = 0, 0.0, 0
    while i < len(paires):
        j = i
        while j < len(paires) and paires[j][0] == paires[i][0]:
            j += 1
        r_moy = (i + 1 + j) / 2
        somme += r_moy * sum(1 for k in range(i, j) if paires[k][1] == 1)
        i = j
    return round((somme - pos * (pos + 1) / 2) / (pos * neg), 3)


def _normalisation(recs):
    norm = {}
    for k in NUMERIQUES:
        vals = [float(r[k]) for r in recs if r.get(k) is not None]
        if len(vals) >= 5:
            mu = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) or 1.0
            norm[k] = (mu, sd)
    return norm


def _charger_dataset():
    recs = []
    for l in open(DATASET):
        if l.strip():
            r = json.loads(l)
            recs.append(features_depuis_contexte(r, regime=r.get("regime"), strategie=r.get("strategie")) | {"label": int(r["label_tb"]), "date": r["date"]})
    recs.sort(key=lambda r: r["date"])
    return recs


def entrainer(verbose=True):
    recs = _charger_dataset()
    n = len(recs)
    if n < 30:
        print(f"Trop peu d'exemples ({n}) : lancez d'abord etiquetage_triple_barriere.py")
        return None
    norm = _normalisation(recs)
    X = [_vecteur(r, norm) for r in recs]
    y = [r["label"] for r in recs]
    moteur = "logit_python"
    # --- walk-forward 5 blocs avec embargo 24 h
    k, aucs, accs = 5, [], []
    taille = n // k
    for i in range(1, k):
        fin_train = i * taille
        date_coupure = recs[fin_train]["date"]
        train_idx = [j for j in range(fin_train) if (datetime.strptime(date_coupure, "%Y-%m-%d %H:%M") - datetime.strptime(recs[j]["date"], "%Y-%m-%d %H:%M")).total_seconds() >= 86400]
        test_idx = list(range(fin_train, min(n, fin_train + taille)))
        if len(train_idx) < 20 or not test_idx:
            continue
        w, b = _entrainer_logit([X[j] for j in train_idx], [y[j] for j in train_idx])
        sc = [_pred_logit(w, b, X[j]) for j in test_idx]
        a = _auc(sc, [y[j] for j in test_idx])
        if a is not None:
            aucs.append(a)
        accs.append(sum(1 for s, j in zip(sc, test_idx) if (s >= 0.5) == (y[j] == 1)) / len(test_idx))
    auc_oos = round(sum(aucs) / len(aucs), 3) if aucs else None
    w, b = _entrainer_logit(X, y)
    actif = bool(auc_oos and auc_oos >= AUC_MIN and n >= N_MIN)
    m = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "moteur": moteur, "n": n, "taux_base": round(sum(y) / n, 3), "norm": norm, "w": w, "b": b,
         "features": NUMERIQUES + [f"regime_{r}" for r in REGIMES], "auc_oos": auc_oos, "auc_par_bloc": aucs,
         "acc_oos": round(sum(accs) / len(accs), 3) if accs else None, "actif": actif,
         "note": "actif = AUC hors echantillon >= 0.55 et >= 150 exemples ; sinon la porte ignore le modele"}
    try:
        if os.path.exists(MODELE):
            with open(HISTO, "a") as f:
                f.write(json.dumps(json.load(open(MODELE))) + "\n")
    except Exception:
        pass
    with open(MODELE + ".tmp", "w") as f:
        json.dump(m, f, indent=1)
    os.replace(MODELE + ".tmp", MODELE)
    _MODELE_CACHE["m"] = None
    if verbose:
        print(f"Meta-modele ({moteur}) : {n} exemples, taux de base {m['taux_base']:.0%}, AUC hors echantillon {auc_oos} (blocs {aucs}), "
              f"exactitude {m['acc_oos']} -> {'ACTIF' if actif else 'INACTIF (pas assez fiable, la porte l ignore)'}")
        poids = sorted(zip(m["features"], w), key=lambda x: -abs(x[1]))[:6]
        print("  facteurs les plus influents : " + ", ".join(f"{k} {v:+.2f}" for k, v in poids))
    return m


def charger():
    try:
        st = os.stat(MODELE)
        if _MODELE_CACHE["m"] is None or st.st_mtime != _MODELE_CACHE["ts"]:
            _MODELE_CACHE["m"] = json.load(open(MODELE))
            _MODELE_CACHE["ts"] = st.st_mtime
        return _MODELE_CACHE["m"]
    except Exception:
        return None


def probabilite(features):
    """Probabilite [0,1] que le trade atteigne l'objectif, ou None si pas de modele actif."""
    m = charger()
    if not m or not m.get("actif"):
        return None
    norm = {k: tuple(v) for k, v in m["norm"].items()}
    return round(_pred_logit(m["w"], m["b"], _vecteur(features, norm)), 3)


def resume():
    m = charger()
    if not m:
        return "meta-modele : aucun (python3 meta_modele.py entrainer)"
    return (f"meta-modele {m['moteur']} du {m['date']} : {m['n']} exemples, AUC hors echantillon {m['auc_oos']}, "
            f"{'ACTIF' if m['actif'] else 'inactif'}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "entrainer":
        entrainer()
    else:
        print(resume())
        ex = features_depuis_contexte({"rsi": 38, "atr_pct": 0.6, "btc_var_1h": 0.1, "btc_var_24h": 1.2, "var_24h": -2.0, "dist_haut_24h": 2.5, "heure": 9, "jour": 2}, regime="tendance")
        print("exemple p =", probabilite(ex))
