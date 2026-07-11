#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode AMELIORATION DE STRATEGIES.
L'agent reprend les strategies qu'il a apprises (strategies.json) et les ameliore vraiment:

1. Strategies gagnantes  -> version OPTIMISEE (seuils plus precis, risque resserre, filtre de confirmation)
2. Strategies perdantes  -> diagnostique l'echec + version CORRIGEE qui evite l'ecueil
3. Strategies neutres    -> version AFFINEE pour la rendre decisive
4. Garde l'originale + ajoute la version amelioree (rien n'est jamais perdu)
5. Marque chaque amelioration avec ce qui a change et un score de confiance

Chaque cycle n'en traite que 5 pour eviter les rate-limits et garder le controle.

Usage:
    python amelioration.py              # 1 cycle d'amelioration
    python amelioration.py --stats      # affiche les ameliorations apportees
    python amelioration.py --boucle     # cycles continus (toutes les 3h)
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta

from agent import (
    disponible, meilleur_defaut, appeler_ia, lecons_recentes
)
from strategies import (
    charger_strategies, sauver_strategies
)

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_AMELIORATIONS = os.path.join(DOSSIER, "ameliorations.json")

# ============================================
# MEMOIRE DES AMELIORATIONS
# ============================================
def charger_ameliorations():
    if os.path.exists(FICHIER_AMELIORATIONS):
        try:
            with open(FICHIER_AMELIORATIONS, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "cycles": 0,
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "historique": []  # liste des ameliorations apportees
    }

def sauver_ameliorations(am):
    with open(FICHIER_AMELIORATIONS, "w") as f:
        json.dump(am, f, ensure_ascii=False, indent=2)

# ============================================
# CHOIX DE L'IA (evite Claude pour pas saturer le quota)
# ============================================
def choisir_ia():
    """Perplexity ou Gemini en priorite, Claude en dernier recours."""
    for m in ["perplexity", "gemini", "claude", "chatgpt"]:
        if disponible(m):
            return m
    return "gemini"

# ============================================
# PROMPTS D'AMELIORATION PAR CAS
# ============================================
def _prompt_optimisation(strat):
    """Strategie gagnante -> version optimisee."""
    return (
        "Tu es un trader quantitatif expert. Voici une strategie de trading qui a GAGNE.\n\n"
        f"MARCHÉ: {strat.get('marche','?')}\n"
        f"RÉSULTAT: gagne (win rate {strat.get('win_rate',0):.0%})\n"
        f"STRATÉGIE ORIGINALE:\n{strat.get('contenu','')[:1500]}\n\n"
        "Crée une VERSION OPTIMISÉE de cette strategie. Conserve la logique qui marche mais:\n"
        "1. Affine les seuils d'entrée (ex: RSI 30 -> 28, seuils plus précis)\n"
        "2. Resserre le stop-loss et optimise le take-profit\n"
        "3. Ajoute UN filtre de confirmation pour éviter les faux signaux\n"
        "4. Clarifie la gestion du risque\n\n"
        "Réponds avec le même format:\n"
        "TYPE: ...\nENTREE: ...\nSORTIE: ...\nGESTION RISQUE: ...\nRAISONNEMENT: ...\nCONFIANCE: /10\n\n"
        "Termine par une ligne AMELIORATION: <ce que tu as changé en 1 phrase>."
    )

def _prompt_correction(strat):
    """Strategie perdante -> diagnostique + version corrigee."""
    raison = strat.get("raison_eval", "")
    return (
        "Tu es un trader quantitatif expert. Voici une strategie qui a PERDU.\n\n"
        f"MARCHÉ: {strat.get('marche','?')}\n"
        f"RAISON DE L'ÉCHEC: {raison[:300]}\n"
        f"STRATÉGIE ORIGINALE:\n{strat.get('contenu','')[:1500]}\n\n"
        "1. DIAGNOSTIQUE pourquoi cette strategie a échoué (1-2 phrases)\n"
        "2. Crée une VERSION CORRIGÉE qui évite cet écueil:\n"
        "   - Change les conditions d'entrée problématiques\n"
        "   - Ajoute une protection supplémentaire\n"
        "   - Resserre le risque\n\n"
        "Réponds avec le même format:\n"
        "TYPE: ...\nENTREE: ...\nSORTIE: ...\nGESTION RISQUE: ...\nRAISONNEMENT: ...\nCONFIANCE: /10\n\n"
        "Termine par une ligne AMELIORATION: <ce que tu as corrigé en 1 phrase>."
    )

def _prompt_affinage(strat):
    """Strategie neutre -> version affinee pour la rendre decisive."""
    return (
        "Tu es un trader quantitatif expert. Voici une strategie NEUTRE (ni gagnée ni perdue).\n\n"
        f"MARCHÉ: {strat.get('marche','?')}\n"
        f"STRATÉGIE ORIGINALE:\n{strat.get('contenu','')[:1500]}\n\n"
        "Crée une VERSION AFFINÉE qui la rend plus decisive:\n"
        "1. Ajoute des conditions plus strictes pour filtrer les trades médiocres\n"
        "2. Optimise le ratio risque/récompense\n"
        "3. Resserre les seuils pour des signaux plus nets\n\n"
        "Réponds avec le même format:\n"
        "TYPE: ...\nENTREE: ...\nSORTIE: ...\nGESTION RISQUE: ...\nRAISONNEMENT: ...\nCONFIANCE: /10\n\n"
        "Termine par une ligne AMELIORATION: <ce que tu as affiné en 1 phrase>."
    )

def _extraire_amelioration(reponse):
    """Extrait la ligne 'AMELIORATION: ...' de la reponse."""
    for ligne in reponse.split("\n"):
        if ligne.strip().upper().startswith("AMELIORATION:"):
            return ligne.split(":", 1)[1].strip()[:200]
    return "version amelioree"

# ============================================
# AMELIORATION D'UNE STRATEGIE
# ============================================
def ameliorer_une(strat):
    """Ameliore une strategie evaluee. Retourne la nouvelle strategie ou None."""
    resultat = strat.get("resultat", "")
    if resultat == "gagne":
        prompt = _prompt_optimisation(strat)
        action = "OPTIMISATION"
    elif resultat == "perdu":
        prompt = _prompt_correction(strat)
        action = "CORRECTION"
    else:
        prompt = _prompt_affinage(strat)
        action = "AFFINAGE"

    ia = choisir_ia()
    print(f"    [{action}] via {ia}...", end=" ", flush=True)
    try:
        reponse, ia_utilisee = appeler_ia(ia, prompt)
        if reponse.startswith("[Erreur") or len(reponse) < 50:
            print("echec")
            return None
    except Exception as e:
        print(f"erreur: {e}")
        return None
    print("OK")

    nouvelle = {
        "contenu": reponse,
        "modele": strat.get("modele", "?"),
        "marche": strat.get("marche", "?"),
        "ia": ia_utilisee,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "evaluee": False,
        "resultat": None,
        "evaluations": 0,
        "gagnes": 0,
        "win_rate": 0,
        # --- metadata d'amelioration ---
        "version": 2,
        "amelioree_de": strat.get("contenu", "")[:80],
        "action_amelioration": action,
        "amelioration": _extraire_amelioration(reponse),
        "strategie_origine_resultat": resultat,
    }
    return nouvelle

# ============================================
# CYCLE D'AMELIORATION
# ============================================
def cycle_amelioration():
    print("=" * 55)
    am = charger_ameliorations()
    print(f"CYCLE D'AMÉLIORATION #{am['cycles'] + 1}")
    print(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    strategies = charger_strategies()
    # On n'ameliore que les strategies evaluees (on connait leur resultat)
    candidates = [s for s in strategies if s.get("evaluee") and not s.get("amelioree_de") and not s.get("deja_amelioree")]
    # Priorise les perdantes (urgent a corriger) puis les gagnantes a optimiser
    candidates.sort(key=lambda s: 0 if s.get("resultat") == "perdu" else 1)

    if not candidates:
        print("\nAucune stratégie évaluée à améliorer.")
        print("Lance d'abord 'python evolution.py' pour générer + évaluer des stratégies.")
        return

    # Traite au max 5 par cycle (limite les appels IA et les rate-limits)
    a_traiter = candidates[:5]
    print(f"\n{len(candidates)} stratégies évaluées, traitement de {len(a_traiter)} ce cycle.")

    ameliorations_cycle = []
    for i, strat in enumerate(a_traiter, 1):
        print(f"\n[{i}/{len(a_traiter)}] {strat.get('marche','?')} ({strat.get('resultat','?')})")
        nouvelle = ameliorer_une(strat)
        if nouvelle:
            strategies.append(nouvelle)
            # Marque l'originale comme deja amelioree pour ne plus la reprendre
            strat["deja_amelioree"] = True
            ameliorations_cycle.append({
                "date": nouvelle["date"],
                "marche": nouvelle["marche"],
                "action": nouvelle["action_amelioration"],
                "amelioration": nouvelle["amelioration"],
                "origine_resultat": strat.get("resultat", "?"),
            })
        time.sleep(1)

    # Tronque a 80 strategies max (garde les plus recentes)
    strategies = strategies[-80:]
    sauver_strategies(strategies)

    # Met a jour l'historique d'ameliorations
    am["cycles"] += 1
    am["historique"].extend(ameliorations_cycle)
    am["historique"] = am["historique"][-50:]
    sauver_ameliorations(am)

    print("\n" + "=" * 55)
    print(f"CYCLE {am['cycles']} TERMINÉ")
    print(f"{len(ameliorations_cycle)} stratégie(s) améliorée(s) ce cycle")
    print(f"Total stratégies: {len(strategies)}")
    print("=" * 55)

# ============================================
# AFFICHAGE DES STATS
# ============================================
def afficher_stats():
    am = charger_ameliorations()
    strategies = charger_strategies()

    ameliorees = [s for s in strategies if s.get("amelioree_de")]
    optimisees = [s for s in ameliorees if s.get("action_amelioration") == "OPTIMISATION"]
    corrigees = [s for s in ameliorees if s.get("action_amelioration") == "CORRECTION"]
    affinees = [s for s in ameliorees if s.get("action_amelioration") == "AFFINAGE"]

    print("=" * 55)
    print("STATISTIQUES D'AMÉLIORATION")
    print("=" * 55)
    print(f"Cycles réalisés: {am['cycles']}")
    print(f"Agent créé le: {am.get('date_creation','?')}")
    print(f"\nStratégies améliorées: {len(ameliorees)}")
    print(f"  • Optimisées (gagnantes): {len(optimisees)}")
    print(f"  • Corrigées (perdantes): {len(corrigees)}")
    print(f"  • Affinées (neutres):    {len(affinees)}")
    print(f"Total stratégies en base: {len(strategies)}")

    if am.get("historique"):
        print(f"\nDernières améliorations:")
        for h in am["historique"][-5:]:
            print(f"  [{h['date']}] {h['marche']} - {h['action']}")
            print(f"    -> {h['amelioration']}")

# ============================================
# BOUCLE CONTINUE
# ============================================
def boucle_continue(intervalle_heures=3):
    print(f"MODE AMÉLIORATION CONTINUE - cycle toutes les {intervalle_heures}h")
    print("Pour arrêter: Ctrl+C")
    print("=" * 55)
    while True:
        try:
            cycle_amelioration()
        except Exception as e:
            print(f"\nErreur dans le cycle: {e}")
            print("Reprise dans 60s...")
            time.sleep(60)
        prochaine = datetime.now() + timedelta(hours=intervalle_heures)
        print(f"\nProchain cycle: {prochaine.strftime('%d/%m/%Y %H:%M')}")
        print(f"Attente de {intervalle_heures}h... (Ctrl+C pour arrêter)")
        time.sleep(intervalle_heures * 3600)

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--stats" in args:
        afficher_stats()
    elif "--boucle" in args:
        intervalle = 3
        for a in args:
            if a.isdigit():
                intervalle = int(a)
        boucle_continue(intervalle)
    else:
        cycle_amelioration()
