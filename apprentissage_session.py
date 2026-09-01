#!/usr/bin/env python3
"""
Apprentissage Cross-Session — L'agent mémorise les bugs et leurs solutions.

Comme Perplexity Computer: apprend de chaque session et réutilise la connaissance.

Fonctionnement:
1. Quand le watchdog détecte un problème, il l'enregistre avec sa solution
2. Quand le même problème réapparaît, l'agent applique automatiquement la solution connue
3. Les solutions sont stockées dans solutions_db.json
4. Plus un bug apparaît, plus l'agent est rapide à le réparer

Types de problèmes appris:
- Service crash → restart (déjà auto, mais avec délai optimisé)
- JSON corrompu → restore backup (déjà auto)
- SL-RETARD → ajustement check interval
- Rate limit 429 → retry delay optimal
- Spread anormal → ajout blacklist
- Circuit breaker → reset condition
- Position fantôme → cleanup
- Log rotation → taille optimale

Usage depuis watchdog.py:
    from apprentissage_session import chercher_solution, enregistrer_solution
    sol = chercher_solution("SL-RETARD")
    if sol:
        appliquer_solution(sol)
    else:
        reparer_manuellement()
        enregistrer_solution("SL-RETARD", "Binance batch + check 10s")
"""

import os
import json
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_SOLUTIONS = os.path.join(DOSSIER, "solutions_db.json")
FICHIER_STATS = os.path.join(DOSSIER, "stats_reparation.json")


def _charger_solutions():
    """Charge la base de solutions."""
    if os.path.exists(FICHIER_SOLUTIONS):
        try:
            with open(FICHIER_SOLUTIONS) as f:
                return json.load(f)
        except Exception:
            pass
    return {"solutions": []}


def _sauver_solutions(data):
    """Sauvegarde la base de solutions."""
    try:
        with open(FICHIER_SOLUTIONS, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _charger_stats():
    """Charge les statistiques de réparation."""
    if os.path.exists(FICHIER_STATS):
        try:
            with open(FICHIER_STATS) as f:
                return json.load(f)
        except Exception:
            pass
    return {"total_reparations": 0, "auto_reparations": 0, "par_type": {}}


def _sauver_stats(data):
    """Sauvegarde les statistiques."""
    try:
        with open(FICHIER_STATS, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def chercher_solution(type_probleme):
    """
    Cherche une solution connue pour un type de problème.
    
    Args:
        type_probleme: string court décrivant le problème
                     (ex: "SL-RETARD", "JSON corrompu", "429 rate limit")
    
    Returns:
        dict avec la solution si trouvée, None sinon:
        {"type": "SL-RETARD", "solution": "Binance batch...", 
         "frequence": 3, "derniere_fois": "2026-08-31", "succes_rate": 100}
    """
    data = _charger_solutions()
    type_lower = type_probleme.lower().strip()
    
    for sol in data["solutions"]:
        if type_lower in sol.get("type", "").lower() or sol.get("type", "").lower() in type_lower:
            return sol
    
    # Recherche fuzzy: mots-clés communs
    mots_cles = set(type_lower.split())
    for sol in data["solutions"]:
        sol_mots = set(sol.get("type", "").lower().split())
        if len(mots_cles & sol_mots) >= 2:  # Au moins 2 mots en commun
            return sol
    
    return None


def enregistrer_solution(type_probleme, solution, details=""):
    """
    Enregistre une nouvelle solution ou met à jour une existante.
    
    Args:
        type_probleme: string court (ex: "SL-RETARD")
        solution: string décrivant la solution appliquée
        details: string avec détails optionnels
    """
    data = _charger_solutions()
    
    # Cherche si la solution existe déjà
    for sol in data["solutions"]:
        if sol.get("type", "").lower() == type_probleme.lower():
            sol["frequence"] = sol.get("frequence", 0) + 1
            sol["derniere_fois"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            sol["succes_rate"] = min(100, sol.get("succes_rate", 0) + 10)
            _sauver_solutions(data)
            print(f"  [APPRENTISSAGE] Solution '{type_probleme}' mise à jour (freq: {sol['frequence']})")
            return
    
    # Nouvelle solution
    data["solutions"].append({
        "type": type_probleme,
        "solution": solution,
        "details": details,
        "frequence": 1,
        "premiere_fois": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "derniere_fois": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "succes_rate": 50,  # Commence à 50%, monte avec chaque succès
    })
    _sauver_solutions(data)
    print(f"  [APPRENTISSAGE] Nouvelle solution enregistrée: '{type_probleme}' → {solution[:60]}")


def enregistrer_echec(type_probleme):
    """
    Enregistre qu'une solution n'a pas marché.
    Baisse le succes_rate pour éviter de répéter une solution inefficace.
    """
    data = _charger_solutions()
    for sol in data["solutions"]:
        if sol.get("type", "").lower() == type_probleme.lower():
            sol["succes_rate"] = max(0, sol.get("succes_rate", 50) - 20)
            sol["echecs"] = sol.get("echecs", 0) + 1
            _sauver_solutions(data)
            return


def stats():
    """Retourne les statistiques d'apprentissage."""
    s = _charger_stats()
    sol = _charger_solutions()
    return {
        "total_solutions": len(sol["solutions"]),
        "total_reparations": s["total_reparations"],
        "auto_reparations": s["auto_reparations"],
        "taux_auto": (s["auto_reparations"] / max(1, s["total_reparations"]) * 100),
        "par_type": s["par_type"],
    }


def incrementer_stat(type_probleme, auto=False):
    """Incrémente les statistiques de réparation."""
    s = _charger_stats()
    s["total_reparations"] += 1
    if auto:
        s["auto_reparations"] += 1
    s["par_type"][type_probleme] = s["par_type"].get(type_probleme, 0) + 1
    _sauver_stats(s)


def rapport():
    """Génère un rapport textuel des apprentissages."""
    sol = _charger_solutions()
    s = _charger_stats()
    
    lignes = ["=== APPRENTISSAGE CROSS-SESSION ===", ""]
    lignes.append(f"Solutions connues: {len(sol['solutions'])}")
    lignes.append(f"Réparations totales: {s['total_reparations']}")
    lignes.append(f"Auto-réparations: {s['auto_reparations']}")
    taux = (s["auto_reparations"] / max(1, s["total_reparations"]) * 100)
    lignes.append(f"Taux d'auto-réparation: {taux:.0f}%")
    lignes.append("")
    lignes.append("Solutions apprises:")
    for sol_entry in sol["solutions"]:
        freq = sol_entry.get("frequence", 0)
        rate = sol_entry.get("succes_rate", 0)
        lignes.append(f"  [{sol_entry['type']}] freq={freq} succès={rate}%")
        lignes.append(f"    → {sol_entry['solution'][:80]}")
    
    if s["par_type"]:
        lignes.append("")
        lignes.append("Réparations par type:")
        for t, n in sorted(s["par_type"].items(), key=lambda x: -x[1]):
            lignes.append(f"  {t}: {n}x")
    
    return "\n".join(lignes)


# ============================================
# SOLUTIONS PRE-CONFIGURÉES (apprises cette session)
# ============================================

def _initialiser_solutions_session():
    """Initialise la base avec les solutions apprises durant cette session."""
    solutions_connues = [
        ("SL-RETARD", "Binance batch (1 appel pour tous) + check 10s", "Remplace Revolut X par-position par Binance batch"),
        ("429 rate limit", "Retry après 2s + CoinGecko fallback + batch delay 1s", "Rate limiting + fallback multi-source"),
        ("JSON corrompu", "Restore backup .bak ou recréer JSON minimal", "Backup auto toutes les 30min"),
        ("Circuit breaker bloqué", "Reset pertes_consecutives=0 + consecutive_losses=0", "Reset automatique via watchdog"),
        ("Spread anormal", "Ajouter à SPREAD_BLACKLIST", "7 assets blacklistés: BNB,AAVE,SUI,XRP,DOGE,AVAX,LINK"),
        ("Volume filter bloque tout", "Binance OHLCV en priorité + pénalité score au lieu de blocage dur", "5 itérations de fix"),
        ("Dashboard down", "sudo systemctl restart dashboard.service", "Watchdog check avec token"),
        ("Service crash", "sudo systemctl restart paper_trading.service", "Watchdog check toutes les 60s"),
        ("Log stale", "Redémarrage service si pas d'écriture >10min", "Watchdog check mtime"),
        ("Position fantôme", "Bloquer prix=0 + retirer PEPE/MATIC", "Blacklist assets à prix trop petit"),
    ]
    
    data = _charger_solutions()
    for type_p, sol, details in solutions_connues:
        # Vérifie si existe déjà
        existe = any(s.get("type", "").lower() == type_p.lower() for s in data["solutions"])
        if not existe:
            data["solutions"].append({
                "type": type_p,
                "solution": sol,
                "details": details,
                "frequence": 1,
                "premiere_fois": "2026-08-31",
                "derniere_fois": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "succes_rate": 90,  # Haute car déjà testées
            })
    _sauver_solutions(data)


# Initialise au premier chargement
_initialiser_solutions_session()


if __name__ == "__main__":
    print(rapport())
