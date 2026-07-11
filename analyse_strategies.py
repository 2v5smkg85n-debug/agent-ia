#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANALYSE EXPLICATIVE DES STRATEGIES.
Explique en francais quelles strategies marchent, sur quels marches, et pourquoi.
Genere un rapport lisible base sur les 105 backtests reels.

Usage:
    python analyse_strategies.py              # affiche le rapport a l'ecran
    python analyse_strategies.py --rapport    # sauvegarde le rapport en .md
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BACKTESTS_REELS = os.path.join(DOSSIER, "backtests_reels.json")
FICHIER_RAPPORT = os.path.join(DOSSIER, "rapport_strategies.md")

# ============================================
# CHARGER LES DONNEES
# ============================================
def charger_backtests():
    if not os.path.exists(FICHIER_BACKTESTS_REELS):
        return []
    try:
        with open(FICHIER_BACKTESTS_REELS, "r") as f:
            return json.load(f)
    except Exception:
        return []

# ============================================
# ANALYSE STATISTIQUE
# ============================================
def analyser(resultats):
    """Retourne un dict structure avec toutes les analyses."""
    if not resultats:
        return None

    a = {
        "total": len(resultats),
        "gagnantes": [r for r in resultats if r.get("verdict") == "GAGNANTE"],
        "perdantes": [r for r in resultats if r.get("verdict") == "PERDANTE"],
        "neutres": [r for r in resultats if r.get("verdict") == "NEUTRE"],
        "par_marche": defaultdict(list),
        "par_strategie": defaultdict(list),
        "par_actif": defaultdict(list),
    }
    for r in resultats:
        a["par_marche"][r.get("marche", "?")].append(r)
        a["par_strategie"][r.get("strategie", "?")].append(r)
        a["par_actif"][r.get("actif", "?")].append(r)
    return a

def stats_groupe(liste):
    """Calcule les stats d'un groupe de resultats."""
    if not liste:
        return {"n": 0}
    n = len(liste)
    gagnes = sum(1 for r in liste if r.get("verdict") == "GAGNANTE")
    retours = [r.get("retour_pct", 0) for r in liste]
    drawdowns = [r.get("drawdown_max", 0) for r in liste if r.get("drawdown_max")]
    return {
        "n": n,
        "gagnes": gagnes,
        "win_rate": gagnes / n * 100,
        "retour_moyen": sum(retours) / n,
        "meilleur_retour": max(retours),
        "pire_retour": min(retours),
        "drawdown_moyen": sum(drawdowns) / len(drawdowns) if drawdowns else 0,
    }

# ============================================
# EXPLICATIONS STRATEGIES (cause -> effet)
# ============================================
def expliquer_strategie(nom):
    """Explique POURQUOI une strategie marche ou pas."""
    explications = {
        "SMA Crossover": {
            "principe": "Achete quand la moyenne mobile courte (20j) depasse la longue (50j) = tendance haussiere confirmee.",
            "quand_marche": "Marches en tendance claire (actions, matieres premieres avec cycles).",
            "quand_echoue": "Marches ranges/volatiles (crypto) -> beaucoup de faux signaux.",
        },
        "RSI Mean Reversion": {
            "principe": "Achete quand le RSI<30 (survente) en pariant sur un rebond vers la moyenne.",
            "quand_marche": "Marches stables et ranges (forex, or) ou les prix reviennent a la moyenne.",
            "quand_echoue": "Marches en forte tendance (crypto bull) -> le prix peut rester survendu longtemps et continuer a baisser.",
        },
        "Bollinger Breakout": {
            "principe": "Achete quand le prix touche la bande basse (deviation extreme) -> retour vers la moyenne.",
            "quand_marche": "Actions volatiles (Tesla, Nvidia) et indices (DAX) ou les ecarts extremes se corrigent vite.",
            "quand_echoue": "Breakout veritable (le prix sort de la bande et continue) -> on achete dans le vide.",
        },
        "MACD Momentum": {
            "principe": "Achete quand le MACD croise la ligne de signal vers le haut = momentum haussier.",
            "quand_marche": "Actions et matieres premieres avec trends soutenues (Apple, Petrole, Cuivre).",
            "quand_echoue": "Marches choppy -> croisements multiples qui ne mennent nulle part.",
        },
    }
    return explications.get(nom, {"principe": "?", "quand_marche": "?", "quand_echoue": "?"})

# ============================================
# GENERATION DU RAPPORT
# ============================================
def generer_rapport():
    resultats = charger_backtests()
    a = analyser(resultats)
    if not a:
        return "# Aucun backtest disponible\n\nLance `python backtest_moteur.py` d'abord."

    lignes = []
    lignes.append("# Rapport d'analyse des strategies")
    lignes.append(f"\n_Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}_\n")
    lignes.append(f"Base: {a['total']} backtests reels (365 jours de donnees, execution deterministe)\n")

    # --- BILAN GLOBAL ---
    lignes.append("## Bilan global\n")
    g = stats_groupe(resultats)
    lignes.append(f"- {a['total']} strategies testees: **{len(a['gagnantes'])} gagnantes** ({g['win_rate']:.0f}%), {len(a['perdantes'])} perdantes, {len(a['neutres'])} neutres")
    lignes.append(f"- Retour moyen: **{g['retour_moyen']:+.2f}%**")
    lignes.append(f"- Meilleur: {g['meilleur_retour']:+.2f}% | Pire: {g['pire_retour']:+.2f}%\n")

    # --- PAR MARCHE ---
    lignes.append("## Performances par marche\n")
    lignes.append("| Marche | Tests | Gagnantes | Win rate | Retour moyen | Drawdown moyen |")
    lignes.append("|---|---|---|---|---|---|")
    for marche in sorted(a["par_marche"].keys()):
        s = stats_groupe(a["par_marche"][marche])
        lignes.append(f"| {marche} | {s['n']} | {s['gagnes']} | {s['win_rate']:.0f}% | {s['retour_moyen']:+.2f}% | {s['drawdown_moyen']:.1f}% |")
    lignes.append("")

    # --- PAR STRATEGIE ---
    lignes.append("## Performances par strategie\n")
    lignes.append("| Strategie | Tests | Gagnantes | Win rate | Retour moyen |")
    lignes.append("|---|---|---|---|---|")
    for strat in sorted(a["par_strategie"].keys()):
        s = stats_groupe(a["par_strategie"][strat])
        lignes.append(f"| {strat} | {s['n']} | {s['gagnes']} | {s['win_rate']:.0f}% | {s['retour_moyen']:+.2f}% |")
    lignes.append("")

    # --- EXPLICATIONS ---
    lignes.append("## Pourquoi chaque strategie marche (ou pas)\n")
    for strat in sorted(a["par_strategie"].keys()):
        s = stats_groupe(a["par_strategie"][strat])
        exp = expliquer_strategie(strat)
        lignes.append(f"### {strat} (win rate {s['win_rate']:.0f}%, retour moyen {s['retour_moyen']:+.2f}%)\n")
        lignes.append(f"- **Principe**: {exp['principe']}")
        lignes.append(f"- **Marche quand**: {exp['quand_marche']}")
        lignes.append(f"- **Echoue quand**: {exp['quand_echoue']}\n")

    # --- TOP 10 ---
    lignes.append("## Top 10 des meilleures strategies\n")
    top = sorted(a["gagnantes"], key=lambda r: r.get("retour_pct", 0), reverse=True)[:10]
    for i, r in enumerate(top, 1):
        lignes.append(f"{i}. **[{r['marche']}] {r['actif']} x {r['strategie']}** -> +{r['retour_pct']:.2f}% (win rate {r['win_rate']}%, drawdown {r['drawdown_max']}%)")
    lignes.append("")

    # --- PIRE 5 (a eviter) ---
    lignes.append("## Strategies a eviter (pire 5)\n")
    pire = sorted(a["perdantes"], key=lambda r: r.get("retour_pct", 0))[:5]
    for i, r in enumerate(pire, 1):
        lignes.append(f"{i}. **[{r['marche']}] {r['actif']} x {r['strategie']}** -> {r['retour_pct']:+.2f}% (win rate {r['win_rate']}%, drawdown {r['drawdown_max']}%)")
    lignes.append("")

    # --- MEILLEURE PAR MARCHE ---
    lignes.append("## Meilleure strategie par marche\n")
    for marche in sorted(a["par_marche"].keys()):
        gagnantes_m = [r for r in a["par_marche"][marche] if r.get("verdict") == "GAGNANTE"]
        if gagnantes_m:
            best = max(gagnantes_m, key=lambda r: r.get("retour_pct", 0))
            lignes.append(f"- **{marche}**: {best['actif']} x {best['strategie']} (+{best['retour_pct']:.2f}%, win {best['win_rate']}%)")
        else:
            lignes.append(f"- **{marche}**: aucune strategie gagnante")
    lignes.append("")

    # --- CONSEILS ---
    lignes.append("## Conseils tires des donnees\n")
    # Quelle strategie est la plus polyvalente ?
    meilleure_strat = None
    meilleur_wr = -1
    for strat, liste in a["par_strategie"].items():
        s = stats_groupe(liste)
        if s["win_rate"] > meilleur_wr and s["n"] >= 5:
            meilleur_wr = s["win_rate"]
            meilleure_strat = strat
    if meilleure_strat:
        lignes.append(f"1. **Strategie la plus fiable**: {meilleure_strat} ({meilleur_wr:.0f}% de win rate global)")

    # Quel marche est le plus facile
    meilleur_marche = None
    meilleur_m_wr = -1
    for marche, liste in a["par_marche"].items():
        s = stats_groupe(liste)
        if s["win_rate"] > meilleur_m_wr:
            meilleur_m_wr = s["win_rate"]
            meilleur_marche = marche
    if meilleur_marche:
        lignes.append(f"2. **Marche le plus rentable**: {meilleur_marche} ({meilleur_m_wr:.0f}% de win rate)")

    # Quel marche eviter
    pire_marche = None
    pire_m_wr = 100
    for marche, liste in a["par_marche"].items():
        s = stats_groupe(liste)
        if s["win_rate"] < pire_m_wr:
            pire_m_wr = s["win_rate"]
            pire_marche = marche
    if pire_marche:
        lignes.append(f"3. **Marche le plus difficile**: {pire_marche} ({pire_m_wr:.0f}% de win rate) -> a eviter ou optimiser")

    return "\n".join(lignes)

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    rapport = generer_rapport()
    if "--rapport" in sys.argv:
        with open(FICHIER_RAPPORT, "w") as f:
            f.write(rapport)
        print(f"Rapport sauvegarde: {FICHIER_RAPPORT}")
        print(f"({len(rapport)} caracteres)")
    else:
        print(rapport)
