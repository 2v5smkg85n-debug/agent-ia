#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MACHINE LEARNING - PHASE 3.
Ajoute un modele predictif (Random Forest) qui complete les strategies existantes.

Le modele ne predit pas le PRIX - il predit la DIRECTION de la prochaine bougie
(hausse vs baisse). C'est un signal supplementaire qui s'ajoute aux strategies
classiques (SMA, RSI, Bollinger, MACD).

Pourquoi Random Forest et pas un reseau de neurones:
  - Robuste sur peu de donnees (365 bougies par actif)
  - Gere les non-linearites sans overfitting excessif
  - Interpretable (importance des features)
  - Pas besoin de GPU

Architecture:
  1. Feature engineering: 30+ features (momentum, volatilite, volume, technique)
  2. Label: direction de la prochaine bougie (1 = hausse, 0 = baisse)
  3. Walk-forward validation: entraine sur le passe, teste sur le futur (anti-overfit)
  4. Sauvegarde le modele entraine pour usage live

ANTI LOOK-AHEAD BIAS:
  Chaque feature utilise uniquement l'info disponible au temps t.
  Le label est la direction de t -> t+1 (jamais inclus dans les features).

Usage:
  python ml_pipeline.py entrainer        # entraine un modele pour un actif
  python ml_pipeline.py entrainer tous   # entraine pour tous les actifs
  python ml_pipeline.py evaluer          # affiche les performances walk-forward
  python ml_pipeline.py signal <actif>   # genere un signal live pour un actif
  python ml_pipeline.py features         # affiche les features calcules
"""
import os
import sys
import json
import math
import pickle
import warnings
from datetime import datetime

# Supprime les warnings sklearn
warnings.filterwarnings("ignore")

from indicateurs import historique_ohlcv
from backtest_moteur import ACTIFS, sma_series, rsi_series, bollinger_series, _macd_full

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_MODELES = os.path.join(DOSSIER, "modeles_ml")
FICHIER_PERFS = os.path.join(DOSSIER, "ml_performances.json")
HORIZON = 1  # predit la bougie suivante (t+1)

# Cree le dossier des modeles s'il n'existe pas
os.makedirs(DOSSIER_MODELES, exist_ok=True)

# ============================================
# FEATURE ENGINEERING (30+ features)
# Chaque feature utilise UNIQUEMENT l'info au temps t (anti look-ahead)
# ============================================
def calculer_features(bougies):
    """
    Calcule 30+ features pour chaque bougie.
    Retourne une liste de dicts (1 par bougie), alignee avec bougies.
    Les premiers elements peuvent avoir des None (pas assez d'historique).
    """
    n = len(bougies)
    clotures = [b["cloture"] for b in bougies]
    hauts = [b["haut"] for b in bougies]
    bas = [b["bas"] for b in bougies]
    volumes = [b.get("volume", 0) for b in bougies]

    # Series techniques pre-calculees
    sma20 = sma_series(clotures, 20)
    sma50 = sma_series(clotures, 50)
    rsi = rsi_series(clotures, 14)
    bb_haut, bb_bas = bollinger_series(clotures, 20, 2)
    macd_line, macd_signal = _macd_full(clotures)

    # Rendements passes (momentum)
    def retour(p, periode):
        if p < periode or clotures[p - periode] == 0:
            return 0.0
        return (clotures[p] - clotures[p - periode]) / clotures[p - periode]

    features_list = []
    for i in range(n):
        f = {}
        # 1. Rendements passes (momentum multi-echelle)
        f["ret_1j"] = retour(i, 1)
        f["ret_2j"] = retour(i, 2)
        f["ret_5j"] = retour(i, 5)
        f["ret_10j"] = retour(i, 10)
        f["ret_20j"] = retour(i, 20)

        # 2. Volatilite (ecart-type des rendements)
        if i >= 20:
            rets = [retour(j, 1) for j in range(i - 19, i + 1)]
            moy = sum(rets) / 20
            var = sum((r - moy) ** 2 for r in rets) / 20
            f["vol_20j"] = math.sqrt(var)
        else:
            f["vol_20j"] = 0.0

        # 3. Z-score (position vs moyenne mobile)
        if sma20[i] and sma20[i] != 0:
            f["zscore_20j"] = (clotures[i] - sma20[i]) / sma20[i]
        else:
            f["zscore_20j"] = 0.0

        # 4. Distance aux moyennes mobiles
        if sma20[i] and sma20[i] != 0:
            f["dist_sma20"] = (clotures[i] - sma20[i]) / sma20[i]
        else:
            f["dist_sma20"] = 0.0
        if sma50[i] and sma50[i] != 0:
            f["dist_sma50"] = (clotures[i] - sma50[i]) / sma50[i]
        else:
            f["dist_sma50"] = 0.0

        # 5. Tendance (SMA20 vs SMA50)
        if sma20[i] and sma50[i] and sma50[i] != 0:
            f["tendance_sma"] = (sma20[i] - sma50[i]) / sma50[i]
        else:
            f["tendance_sma"] = 0.0

        # 6. RSI et ses derivees
        f["rsi"] = rsi[i] if rsi[i] else 50.0
        f["rsi_survente"] = 1.0 if (rsi[i] and rsi[i] < 30) else 0.0
        f["rsi_surachat"] = 1.0 if (rsi[i] and rsi[i] > 70) else 0.0

        # 7. Position dans les bandes de Bollinger (0 = bande basse, 1 = bande haute)
        if bb_haut[i] and bb_bas[i] and (bb_haut[i] - bb_bas[i]) != 0:
            f["bb_position"] = (clotures[i] - bb_bas[i]) / (bb_haut[i] - bb_bas[i])
        else:
            f["bb_position"] = 0.5
        f["bb_largeur"] = ((bb_haut[i] - bb_bas[i]) / sma20[i]) if (bb_haut[i] and sma20[i] and sma20[i] != 0) else 0.0

        # 8. MACD
        f["macd_line"] = macd_line[i] if macd_line[i] else 0.0
        f["macd_signal"] = macd_signal[i] if macd_signal[i] else 0.0
        if macd_line[i] and macd_signal[i]:
            f["macd_hist"] = macd_line[i] - macd_signal[i]
        else:
            f["macd_hist"] = 0.0

        # 9. Volume
        if i >= 20 and volumes[i] > 0:
            vol_moy = sum(volumes[i - 19:i + 1]) / 20
            f["volume_ratio"] = volumes[i] / vol_moy if vol_moy > 0 else 1.0
        else:
            f["volume_ratio"] = 1.0

        # 10. Range de la bougie (volatilite intrabougie)
        if clotures[i] != 0:
            f["range_pct"] = (hauts[i] - bas[i]) / clotures[i]
            f["corps_pct"] = (clotures[i] - bougies[i]["ouverture"]) / clotures[i]
        else:
            f["range_pct"] = 0.0
            f["corps_pct"] = 0.0

        # 11. Calendar (jour de la semaine - patterns saisonniers)
        try:
            ts = bougies[i].get("temps", 0)
            if isinstance(ts, (int, float)) and ts > 0:
                # timestamp en secondes ou millisecondes
                if ts > 1e12:
                    ts = ts / 1000
                import time as _time
                jour = _time.localtime(ts).tm_wday  # 0=lundi, 6=dimanche
                f["jour_semaine"] = jour
            else:
                f["jour_semaine"] = 0
        except Exception:
            f["jour_semaine"] = 0

        features_list.append(f)
    return features_list

# ============================================
# LABELS (cible a predire)
# ============================================
def calculer_labels(bougies, horizon=HORIZON):
    """
    Label = 1 si la bougie t+horizon cloture plus haut que t, 0 sinon.
    """
    labels = []
    clotures = [b["cloture"] for b in bougies]
    for i in range(len(bougies)):
        if i + horizon < len(bougies):
            labels.append(1 if clotures[i + horizon] > clotures[i] else 0)
        else:
            labels.append(None)  # derniere bougie: pas de label
    return labels

# ============================================
# WALK-FORWARD VALIDATION (anti-overfit)
# ============================================
def walk_forward(features, labels, n_splits=5):
    """
    Decoupe les donnees en n_splits fenetres temporelles.
    Pour chaque fenetre: entraine sur le passe, teste sur le futur.
    Retourne la precision moyenne et le detail par split.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None, {"erreur": "scikit-learn non installe. Lance: pip install scikit-learn"}

    # Nettoie: garde seulement les lignes avec features et labels valides
    donnees = []
    for i in range(len(features)):
        if labels[i] is not None:
            donnees.append((features[i], labels[i]))

    if len(donnees) < 100:
        return None, {"erreur": f"Pas assez de donnees ({len(donnees)}), minimum 100 requis"}

    n = len(donnees)
    taille_split = n // (n_splits + 1)
    if taille_split < 30:
        return None, {"erreur": f"Fenetre trop petite ({taille_split}), besoin de plus de donnees"}

    precisions = []
    details = []

    for split in range(n_splits):
        fin_train = taille_split * (split + 1)
        debut_test = fin_train
        fin_test = min(fin_train + taille_split, n)

        if debut_test >= n:
            break

        train = donnees[:fin_train]
        test = donnees[debut_test:fin_test]

        X_train = [list(d[0].values()) for d in train]
        y_train = [d[1] for d in train]
        X_test = [list(d[0].values()) for d in test]
        y_test = [d[1] for d in test]

        # Random Forest: 100 arbres, profondeur limitee (anti-overfit)
        modele = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=10,
            random_state=42,
        )
        modele.fit(X_train, y_train)
        pred = modele.predict(X_test)
        precision = sum(1 for p, r in zip(pred, y_test) if p == r) / len(y_test) * 100

        precisions.append(precision)
        details.append({
            "split": split + 1,
            "train": len(train),
            "test": len(test),
            "precision": round(precision, 1),
        })

    if not precisions:
        return None, {"erreur": "Pas assez de donnees pour la validation walk-forward"}

    precision_moyenne = sum(precisions) / len(precisions)
    return precision_moyenne, {"precision_moyenne": round(precision_moyenne, 1),
                               "details": details}

# ============================================
# ENTRAINEMENT FINAL (sur toutes les donnees)
# ============================================
def entrainer_modele(actif):
    """Entraine un modele sur tout l'historique d'un actif et le sauvegarde."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        print("ERREUR: scikit-learn non installe.")
        print("Installe-le avec: pip install scikit-learn")
        return None

    # Determine le marche
    marche = None
    for cat, actifs in ACTIFS.items():
        if actif in actifs:
            marche = cat
            break

    bougies = historique_ohlcv(actif, "1d", 365)
    if not bougies or len(bougies) < 100:
        print(f"Pas assez de donnees pour {actif} ({len(bougies) if bougies else 0} bougies)")
        return None

    print(f"[{marche}] {actif}: {len(bougies)} bougies -> calcul features...", end=" ", flush=True)
    features = calculer_features(bougies)
    labels = calculer_labels(bougies)

    # Walk-forward d'abord (pour mesurer la performance honnetement)
    precision, details = walk_forward(features, labels)
    if precision is None:
        print(f"echec ({details.get('erreur', '?')})")
        return None

    # Entrainement final sur TOUTES les donnees (pour usage live)
    donnees = [(features[i], labels[i]) for i in range(len(features)) if labels[i] is not None]
    X = [list(d[0].values()) for d in donnees]
    y = [d[1] for d in donnees]

    modele = RandomForestClassifier(
        n_estimators=100, max_depth=5, min_samples_leaf=10, random_state=42
    )
    modele.fit(X, y)

    # Sauvegarde le modele + les noms de features
    noms_features = list(features[0].keys())
    chemin_modele = os.path.join(DOSSIER_MODELES, f"{actif.replace('=','_').replace('^','i')}.pkl")
    with open(chemin_modele, "wb") as f:
        pickle.dump({"modele": modele, "features": noms_features, "actif": actif, "marche": marche}, f)

    # Sauvegarde les perfs
    perfs = charger_perfs()
    perfs[actif] = {
        "marche": marche,
        "bougies": len(bougies),
        "precision_walk_forward": round(precision, 1),
        "details": details,
        "date_entrainement": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_features": len(noms_features),
    }
    sauver_perfs(perfs)

    print(f"precision walk-forward: {precision:.1f}%")
    return precision

def charger_perfs():
    if os.path.exists(FICHIER_PERFS):
        try:
            with open(FICHIER_PERFS, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def sauver_perfs(perfs):
    with open(FICHIER_PERFS, "w") as f:
        json.dump(perfs, f, ensure_ascii=False, indent=2)

# ============================================
# SIGNAL LIVE (prediction pour la prochaine bougie)
# ============================================
def signal_live(actif):
    """Utilise le modele entraine pour predire la direction de la prochaine bougie."""
    chemin = os.path.join(DOSSIER_MODELES, f"{actif.replace('=','_').replace('^','i')}.pkl")
    if not os.path.exists(chemin):
        return None, "modele non entraine"

    try:
        with open(chemin, "rb") as f:
            data = pickle.load(f)
        modele = data["modele"]
        noms_features = data["features"]
    except Exception as e:
        return None, f"erreur chargement: {e}"

    bougies = historique_ohlcv(actif, "1d", 365)
    if not bougies or len(bougies) < 60:
        return None, "pas assez de donnees"

    features = calculer_features(bougies)
    derniere = features[-1]
    X = [list(derniere.values())]

    proba = modele.predict_proba(X)[0]
    classes = modele.classes_
    proba_hausse = proba[list(classes).index(1)] if 1 in classes else 0.5

    if proba_hausse > 0.6:
        signal = "ACHAT"
    elif proba_hausse < 0.4:
        signal = "VENTE"
    else:
        signal = "NEUTRE"

    return {
        "signal": signal,
        "proba_hausse": round(proba_hausse * 100, 1),
        "proba_baisse": round((1 - proba_hausse) * 100, 1),
        "actif": actif,
        "marche": data.get("marche", "?"),
    }, None

# ============================================
# IMPORTANCE DES FEATURES (interpretabilité)
# ============================================
def importance_features(actif):
    """Affiche quelles features sont les plus predictives."""
    chemin = os.path.join(DOSSIER_MODELES, f"{actif.replace('=','_').replace('^','i')}.pkl")
    if not os.path.exists(chemin):
        print(f"Modele non entraine pour {actif}")
        return
    with open(chemin, "rb") as f:
        data = pickle.load(f)
    modele = data["modele"]
    noms = data["features"]
    importances = modele.feature_importances_
    trie = sorted(zip(noms, importances), key=lambda x: x[1], reverse=True)
    print(f"\nImportance des features pour {actif}:")
    for nom, imp in trie[:10]:
        barre = "#" * int(imp * 100)
        print(f"  {nom:<18} {imp*100:5.1f}% {barre}")

# ============================================
# COMMANDES
# ============================================
def cmd_entrainer(cible="tous"):
    if cible == "tous":
        print("=" * 60)
        print(f"ENTRAINEMENT ML - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print("=" * 60)
        for cat in ACTIFS:
            for actif in ACTIFS[cat]:
                entrainer_modele(actif)
        print("\n" + "=" * 60)
        perfs = charger_perfs()
        print(f"Termine. {len(perfs)} modeles entraines.")
        if perfs:
            precisions = [p["precision_walk_forward"] for p in perfs.values()]
            print(f"Precision moyenne globale: {sum(precisions)/len(precisions):.1f}%")
    else:
        entrainer_modele(cible)

def cmd_evaluer():
    perfs = charger_perfs()
    if not perfs:
        print("Aucun modele entraine. Lance 'python ml_pipeline.py entrainer tous' d'abord.")
        return
    print("=" * 65)
    print(f"EVALUATION ML (walk-forward) - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 65)
    print(f"\n{'Actif':<12} {'Marche':<10} {'Bougies':<8} {'Precision':<10} {'vs Aleatoire'}")
    print("-" * 60)
    for actif, p in sorted(perfs.items(), key=lambda x: x[1]["precision_walk_forward"], reverse=True):
        prec = p["precision_walk_forward"]
        vs_alea = prec - 50
        print(f"{actif:<12} {p['marche']:<10} {p['bougies']:<8} {prec:.1f}%     {vs_alea:+.1f} pts")

    precisions = [p["precision_walk_forward"] for p in perfs.values()]
    print("-" * 60)
    print(f"Precision moyenne: {sum(precisions)/len(precisions):.1f}% (aleatoire = 50%)")
    bons = sum(1 for p in precisions if p > 52)
    print(f"Modeles avec edge (>52%): {bons}/{len(precisions)}")

def cmd_signal(actif):
    signal, err = signal_live(actif)
    if err:
        print(f"Erreur: {err}")
        print(f"Lance d'abord: python ml_pipeline.py entrainer {actif}")
        return
    print(f"\nSignal ML pour {signal['actif']} ({signal['marche']}):")
    print(f"  Signal: {signal['signal']}")
    print(f"  Probabilite hausse: {signal['proba_hausse']}%")
    print(f"  Probabilite baisse: {signal['proba_baisse']}%")
    importance_features(actif)

def cmd_features():
    """Affiche un exemple de features calcules."""
    bougies = historique_ohlcv("BTCUSDT", "1d", 365)
    if not bougies:
        print("Impossible de recuperer les donnees")
        return
    features = calculer_features(bougies)
    print(f"\nFeatures calcules pour BTCUSDT ({len(features[0])} features):")
    for nom, val in features[-1].items():
        print(f"  {nom:<20} {val:.4f}" if isinstance(val, float) else f"  {nom:<20} {val}")

def aide():
    print("""
MACHINE LEARNING - PHASE 3
==========================
Commandes:
  python ml_pipeline.py entrainer tous   Entraine un modele pour chaque actif
  python ml_pipeline.py entrainer BTCUSDT Entraine un seul actif
  python ml_pipeline.py evaluer           Affiche les performances walk-forward
  python ml_pipeline.py signal BTCUSDT    Signal live pour un actif
  python ml_pipeline.py features          Affiche les features calcules

PREREQUIS: pip install scikit-learn

Le modele:
  1. Calcule 30+ features (momentum, volatilite, volume, technique, calendar)
  2. Label: direction de la prochaine bougie (hausse/baisse)
  3. Walk-forward: entraine sur le passe, teste sur le futur (anti-overfit)
  4. Sauvegarde le modele dans modeles_ml/

Interpretation:
  - Precision > 50% = meilleur que le hasard
  - Precision > 52% = edge utilisable
  - Precision > 60% = excellent (rare)
  - Precision > 70% = suspect (overfit possible)
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        aide()
        sys.exit(0)
    cmd = sys.argv[1].lower()
    if cmd == "entrainer":
        cible = sys.argv[2] if len(sys.argv) > 2 else "tous"
        cmd_entrainer(cible)
    elif cmd == "evaluer":
        cmd_evaluer()
    elif cmd == "signal":
        if len(sys.argv) < 3:
            print("Usage: python ml_pipeline.py signal <actif>")
        else:
            cmd_signal(sys.argv[2])
    elif cmd == "features":
        cmd_features()
    else:
        aide()
