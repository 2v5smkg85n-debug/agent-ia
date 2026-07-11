#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FILTRE ML - Integre le machine learning dans le trading live.
Confirmation des signaux par le modele predictif avant d'ouvrir une position.

Principe du double-filtre:
  1. La strategie gagnante (backtest) genere un signal ACHAT
  2. Le modele ML predit la direction de la prochaine bougie
  3. On n'ouvre QUE si les deux sont d'accord

Pourquoi un double-filtre:
  - La strategie a un edge prouve sur 365 jours (backtest)
  - Le ML a un edge predictif (precision > 52% sur walk-forward)
  - Combiner deux edges independants reduit les faux signaux

Regles:
  - Si le modele ML a un edge (precision > SEUIL_EDGE): il CONFIRME ou REJETE le signal
  - Si le modele est faible (< SEUIL_EDGE): on ne l'utilise pas (on garde la strategie seule)
  - Si aucun modele pour cet actif: on garde le signal original

Usage dans paper_trading.py:
  from ml_filtre import confirmer_signaux_ml
  signaux = confirmer_signaux_ml(signaux)

Standalone:
  python ml_filtre.py              # affiche l'etat des modeles + edge
  python ml_filtre.py tester       # simule le filtre sur des signaux factices
"""
import os
import sys
import json
import pickle
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_MODELES = os.path.join(DOSSIER, "modeles_ml")
FICHIER_PERFS = os.path.join(DOSSIER, "ml_performances.json")

# Seuil de precision pour qu'un modele soit utilise comme filtre
# < 52% = pas mieux que le hasard, on ne fait pas confiance au modele
SEUIL_EDGE = 52.0
# Seuil de probabilite pour confirmer un ACHAT (proba hausse > ce seuil)
SEUIL_PROBA_HAUSSE = 0.55

# ============================================
# CHARGER LES PERFORMANCES ML
# ============================================
def charger_perfs_ml():
    if not os.path.exists(FICHIER_PERFS):
        return {}
    try:
        with open(FICHIER_PERFS, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def modeles_avec_edge():
    """Retourne la liste des actifs dont le modele ML a un edge (precision > seuil)."""
    perfs = charger_perfs_ml()
    return [actif for actif, p in perfs.items()
            if p.get("precision_walk_forward", 0) >= SEUIL_EDGE]

def chemin_modele(actif):
    """Chemin du fichier modele pour un actif (normalisation des caracteres speciaux)."""
    return os.path.join(DOSSIER_MODELES, f"{actif.replace('=','_').replace('^','i')}.pkl")

# ============================================
# PREDICTION ML
# ============================================
def predire_direction(actif):
    """
    Utilise le modele ML pour predire la direction de la prochaine bougie.
    Retourne (signal, proba_hausse) ou (None, None) si pas de modele/edge.
    """
    perfs = charger_perfs_ml()
    perf = perfs.get(actif)
    # Si pas de modele ou edge insuffisant, on n'utilise pas le ML
    if not perf or perf.get("precision_walk_forward", 0) < SEUIL_EDGE:
        return None, None

    chemin = chemin_modele(actif)
    if not os.path.exists(chemin):
        return None, None

    try:
        with open(chemin, "rb") as f:
            data = pickle.load(f)
        modele = data["modele"]
    except Exception:
        return None, None

    # Calcule les features pour la derniere bougie
    try:
        from ml_pipeline import calculer_features
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(actif, "1d", 365)
        if not bougies or len(bougies) < 60:
            return None, None
        features = calculer_features(bougies)
        derniere = features[-1]
        X = [list(derniere.values())]
        proba = modele.predict_proba(X)[0]
        classes = modele.classes_
        proba_hausse = proba[list(classes).index(1)] if 1 in classes else 0.5
    except Exception:
        return None, None

    if proba_hausse > SEUIL_PROBA_HAUSSE:
        return "ACHAT", proba_hausse
    elif proba_hausse < (1 - SEUIL_PROBA_HAUSSE):
        return "VENTE", proba_hausse
    else:
        return "NEUTRE", proba_hausse

# ============================================
# FILTRE PRINCIPAL
# ============================================
def confirmer_signaux_ml(signaux, verbose=True):
    """
    Filtre une liste de signaux d'achat via le modele ML.
    Garde seulement les signaux confirmes par le ML (proba hausse > seuil).

    Args:
        signaux: liste de dicts (format attendu par paper_trading.ouvrir_position)
        verbose: affiche les decisions

    Retourne: liste de signaux confirmes
    """
    if not signaux:
        return signaux

    avec_edge = modeles_avec_edge()
    signaux_confirme = []

    for signal in signaux:
        symbole = signal.get("symbole", "")

        # Si pas de modele avec edge pour cet actif -> on garde le signal
        if symbole not in avec_edge:
            signaux_confirme.append(signal)
            if verbose:
                print(f"    [ML] {signal.get('nom','?')}: pas de modele avec edge -> garde")
            continue

        # Demande la prediction ML
        ml_signal, proba = predire_direction(symbole)
        if ml_signal is None or proba is None:
            # Erreur ML -> on garde le signal (ne pas bloquer sur erreur)
            signaux_confirme.append(signal)
            continue

        if ml_signal == "ACHAT":
            # Double confirmation: strategie + ML d'accord
            signal = dict(signal)  # copie pour ne pas modifier l'original
            signal["source"] = "backtest-gagnant + ML confirme"
            signal["score"] = signal.get("score", 2) + 1  # boost le score
            signal["raison"] = signal.get("raison", "") + f" | ML: {proba*100:.0f}% hausse"
            signaux_confirme.append(signal)
            if verbose:
                print(f"    [ML OK] {signal.get('nom','?')}: confirme (proba hausse {proba*100:.0f}%)")
        else:
            # Le ML rejette le signal -> on le supprime
            if verbose:
                print(f"    [ML REJETE] {signal.get('nom','?')}: ML dit {ml_signal} "
                      f"(proba hausse {proba*100:.0f}%) -> signal supprime")

    return signaux_confirme

# ============================================
# AFFICHAGE
# ============================================
def afficher_etat():
    perfs = charger_perfs_ml()
    if not perfs:
        print("Aucun modele ML entraine. Lance 'python ml_pipeline.py entrainer tous' d'abord.")
        return

    print("=" * 60)
    print(f"FILTRE ML - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    print(f"\nSeuil d'edge: {SEUIL_EDGE}% (modeles utilises comme filtre)")
    print(f"Seuil de confirmation: {SEUIL_PROBA_HAUSSE*100:.0f}% proba hausse\n")

    print(f"{'Actif':<12} {'Precision':<12} {'Edge?':<8} {'Utilise?'}")
    print("-" * 50)
    for actif, p in sorted(perfs.items(), key=lambda x: x[1].get("precision_walk_forward", 0), reverse=True):
        prec = p.get("precision_walk_forward", 0)
        edge = prec >= SEUIL_EDGE
        utilise = "OUI (filtre actif)" if edge else "non (edge insuffisant)"
        print(f"{actif:<12} {prec:.1f}%       {'oui' if edge else 'non':<8} {utilise}")

    avec_edge = modeles_avec_edge()
    print(f"\n{len(avec_edge)}/{len(perfs)} modeles ont un edge exploitable:")
    for a in avec_edge:
        print(f"  - {a}: {perfs[a]['precision_walk_forward']:.1f}%")

# ============================================
# TEST
# ============================================
def tester():
    print("=" * 60)
    print("TEST DU FILTRE ML")
    print("=" * 60)

    # Signaux factices
    signaux_test = [
        {"symbole": "BTCUSDT", "nom": "Bitcoin", "marche": "crypto", "score": 2, "raison": "Bollinger"},
        {"symbole": "XRPUSDT", "nom": "Ripple", "marche": "crypto", "score": 2, "raison": "Bollinger"},
        {"symbole": "TSLA", "nom": "Tesla", "marche": "actions", "score": 2, "raison": "Bollinger"},
        {"symbole": "EURUSD=X", "nom": "EUR/USD", "marche": "forex", "score": 2, "raison": "RSI"},
    ]
    print(f"\n{len(signaux_test)} signaux a filtrer:")
    for s in signaux_test:
        print(f"  - {s['nom']} ({s['symbole']}): {s['raison']}")

    print("\nFiltrage ML en cours...")
    confirmes = confirmer_signaux_ml(signaux_test, verbose=True)

    print(f"\nResultat: {len(confirmes)}/{len(signaux_test)} signaux confirmes")
    for s in confirmes:
        print(f"  - {s['nom']}: {s.get('raison','?')}")

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "etat"
    if cmd == "tester":
        tester()
    else:
        afficher_etat()
