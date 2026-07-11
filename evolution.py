#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode EVOLUTION AUTONOME.
L'agent s'ameliora tout seul, en boucle:
1. Analyse les marches (temps reel)
2. Genere de nouvelles strategies
3. Evalue les anciennes via BACKTEST REEL (historique 365j, plus de devinette IA)
4. Extrait des lecons de ses echecs
5. Reutilise ses meilleures strategies
6. Ajuste sa confiance en chaque marche

Lance en arriere-plan, il tourne tout seul et devient meilleur chaque cycle.

Usage:
    python evolution.py              # 1 cycle d'evolution
    python evolution.py --boucle     # cycles continus (toutes les 6h)
    python evolution.py --stats      # affiche l'evolution de l'agent
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta

from agent import (
    instruction_memoire, lecons_recentes, ajouter,
    MODELS, disponible, meilleur_defaut, appeler_ia,
    notify_ifft, gemini, claude
)
from strategies import (
    MARCHES, scan_complet,
    charger_strategies, sauver_strategies,
    charger_journal, ajouter_journal,
    recuperer_donnees_marche
)
from evaluation_reelle import evaluer_par_backtest

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_EVOLUTION = os.path.join(DOSSIER, "evolution.json")
FICHIER_STATS = os.path.join(DOSSIER, "stats_marches.json")

# ============================================
# MEMOIRE D'EVOLUTION (meta-apprentissage)
# ============================================
def charger_evolution():
    if os.path.exists(FICHIER_EVOLUTION):
        try:
            with open(FICHIER_EVOLUTION, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "cycles": 0,
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "historique_performance": [],
        "ajustements": []
    }

def sauver_evolution(evo):
    with open(FICHIER_EVOLUTION, "w") as f:
        json.dump(evo, f, ensure_ascii=False, indent=2)

def charger_stats_marches():
    if os.path.exists(FICHIER_STATS):
        try:
            with open(FICHIER_STATS, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def sauver_stats_marches(stats):
    with open(FICHIER_STATS, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

# ============================================
# META-ANALYSE: l'agent reflechit sur lui-meme
# ============================================
def meta_analyse():
    """L'agent analyse ses propres resultats pour identifier des patterns."""
    strategies = charger_strategies()
    evaluees = [s for s in strategies if s.get("evaluee")]

    if len(evaluees) < 3:
        print("  Pas assez de strategies evaluees pour meta-analyse (min 3).")
        return None

    # Calcule les stats par marche
    stats = charger_stats_marches()
    for cat in MARCHES.keys():
        strats_cat = [s for s in evaluees if s.get("marche") == cat]
        if strats_cat:
            gagnes = sum(1 for s in strats_cat if s.get("resultat") == "gagne")
            perdus = sum(1 for s in strats_cat if s.get("resultat") == "perdu")
            total = len(strats_cat)
            win_rate = gagnes / total if total else 0
            stats[cat] = {
                "total": total,
                "gagnes": gagnes,
                "perdus": perdus,
                "win_rate": win_rate,
                "methode": "backtest_reel",
                "derniere_maj": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
    sauver_stats_marches(stats)

    # L'IA identifie des patterns d'amelioration
    resume = "\n".join(
        f"- {cat}: {s['gagnes']}G/{s['perdus']}P (win rate {s['win_rate']:.0%}) [backtest reel]"
        for cat, s in stats.items()
    )
    lecons = lecons_recentes()

    prompt = (
        f"Tu es un meta-analyste. Analyse les performances d'un agent de trading IA.\n\n"
        f"STATISTIQUES PAR MARCHE (via backtest reel sur historique 365j):\n{resume}\n\n"
        f"{lecons}"
        f"Identifie les PATTERNS d'amelioration:\n"
        f"1. Sur quels marches l'agent performe-t-il le mieux/pire? Pourquoi?\n"
        f"2. Quels types de strategies fonctionnent (breakout, mean reversion, trend following)?\n"
        f"3. Quelles erreurs recurrentes faut-il eviter?\n"
        f"4. UNE recommandation concrete pour le prochain cycle.\n"
        f"Sois concis (max 150 mots). Sois critique et honnete."
    )
    ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else meilleur_defaut())
    print(f"  -> Meta-analyse via {ia}... (stats basees sur backtest reel)", end=" ", flush=True)
    try:
        rep, _ = appeler_ia(ia, prompt)
        if rep.startswith("[Erreur"):
            print("echec")
            return None
        print("OK")
        return rep
    except Exception as e:
        print(f"erreur: {e}")
        return None

# ============================================
# AJUSTEMENT AUTO: l'agent modifie sa confiance
# ============================================
def ajuster_confiance():
    """Ajuste la confiance de l'agent par marche selon les resultats du backtest reel."""
    stats = charger_stats_marches()
    if not stats:
        return

    ajustements = []
    for cat, s in stats.items():
        if s.get("total", 0) < 2:
            continue
        win_rate = s.get("win_rate", 0)
        if win_rate >= 0.6:
            ajustements.append(f"{cat}: PERFORMANT ({win_rate:.0%}) - continuer ces strategies")
        elif win_rate <= 0.3 and s.get("total", 0) >= 3:
            ajustements.append(f"{cat}: SOUS-PERFORMANT ({win_rate:.0%}) - changer d'approche")

    if ajustements:
        evo = charger_evolution()
        evo["ajustements"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "contenu": " | ".join(ajustements)
        })
        evo["ajustements"] = evo["ajustements"][-20:]
        sauver_evolution(evo)

# ============================================
# EXTRACTION DE LECONS AUTO
# ============================================
def extraire_lecons_auto():
    """Extrait des lecons generales des evaluations recentes (backtest reel)."""
    strategies = charger_strategies()
    evaluees_recentes = [s for s in strategies if s.get("evaluee")][-5:]
    if not evaluees_recentes:
        return

    for s in evaluees_recentes:
        resultat = s.get("resultat", "")
        raison = s.get("raison_eval", "")
        if not raison:
            continue

        prompt = (
            f"Une strategie de trading a ete {resultat} lors d'un backtest reel sur 365j. "
            f"Voici les resultats:\n{raison[:300]}\n\n"
            f"Extrait UNE lecon generale et actionnable (max 100 caracteres) "
            f"que l'agent devrait retenir. Si rien de generalisable, reponds 'RIEN'."
        )
        try:
            lecon = gemini(prompt) if disponible("gemini") else claude(prompt)
            if lecon and not lecon.startswith("[") and "RIEN" not in lecon[:10]:
                lecon = lecon.strip().replace("\n", " ")[:120]
                from agent import charger_lecons, sauver_lecons
                lecons = charger_lecons()
                existants = [l.get("contenu", "") for l in lecons]
                if lecon not in existants and len(lecons) < 50:
                    lecons.append({
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "contenu": lecon
                    })
                    sauver_lecons(lecons)
        except:
            pass
        time.sleep(1)

# ============================================
# CYCLE D'EVOLUTION COMPLET
# ============================================
def cycle_evolution():
    """Un cycle complet d'auto-amelioration."""
    print("=" * 55)
    print(f"CYCLE D'EVOLUTION #{charger_evolution()['cycles'] + 1}")
    print(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    evo = charger_evolution()
    evo["cycles"] += 1
    sauver_evolution(evo)

    print("\n[1/5] Analyse des marches + generation de strategies...")
    scan_complet()

    print("\n[2/5] Evaluation des strategies via BACKTEST REEL (historique 365j)...")
    evaluer_par_backtest(limite=5)

    print("\n[3/5] Extraction de lecons auto...")
    extraire_lecons_auto()

    print("\n[4/5] Meta-analyse des performances...")
    meta = meta_analyse()
    if meta:
        print(f"\n--- Meta-analyse ---")
        print(meta[:500])
        print("-" * 50)
        evo = charger_evolution()
        evo["historique_performance"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cycle": evo["cycles"],
            "analyse": meta[:400]
        })
        evo["historique_performance"] = evo["historique_performance"][-20:]
        sauver_evolution(evo)

    print("\n[5/5] Ajustement de la confiance par marche...")
    ajuster_confiance()

    ajouter("apprentissages", f"Cycle evolution #{evo['cycles']} {datetime.now().strftime('%d/%m')}")

    print("\n" + "=" * 55)
    print(f"CYCLE {evo['cycles']} TERMINE")
    print("=" * 55)
    afficher_stats()

def afficher_stats():
    """Affiche les statistiques d'evolution."""
    evo = charger_evolution()
    stats = charger_stats_marches()

    print(f"\nCycles realises: {evo['cycles']}")
    print(f"Agent cree le: {evo.get('date_creation','?')}")
    print(f"Meta-analyses: {len(evo.get('historique_performance',[]))}")
    print(f"Ajustements: {len(evo.get('ajustements',[]))}")

    if stats:
        print(f"\nPerformances par marche (BACKTEST REEL):")
        for cat, s in stats.items():
            print(f"  {cat}: {s.get('gagnes',0)}G/{s.get('perdus',0)}P "
                  f"(win rate {s.get('win_rate',0):.0%}, {s.get('total',0)} evals)")

    print(f"\nDerniers ajustements:")
    for aj in evo.get("ajustements", [])[-3:]:
        print(f"  [{aj['date']}] {aj['contenu']}")

# ============================================
# BOUCLE CONTINUE
# ============================================
def boucle_continue(intervalle_heures=6):
    """Lance des cycles d'evolution en continu."""
    print(f"MODE EVOLUTION CONTINUE - cycle toutes les {intervalle_heures}h")
    print("Evaluation par BACKTEST REEL (plus de devinette IA)")
    print("Pour arreter: Ctrl+C")
    print("=" * 55)

    while True:
        try:
            cycle_evolution()
        except Exception as e:
            print(f"\nErreur dans le cycle: {e}")
            print("Reprise dans 60s...")
            time.sleep(60)

        prochaine = datetime.now() + timedelta(hours=intervalle_heures)
        print(f"\nProchain cycle: {prochaine.strftime('%d/%m/%Y %H:%M')}")
        print(f"Attente de {intervalle_heures}h... (Ctrl+C pour arreter)")
        time.sleep(intervalle_heures * 3600)

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--stats" in args:
        afficher_stats()
    elif "--boucle" in args:
        intervalle = 6
        for a in args:
            if a.isdigit():
                intervalle = int(a)
        boucle_continue(intervalle)
    else:
        cycle_evolution()
