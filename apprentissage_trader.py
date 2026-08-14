#!/usr/bin/env python3
"""
Apprentissage Trader — Le bot apprend de ses propres trades et adapte ses strategies.
Analyse les trades gagnants/perdants pour trouver les meilleurs conditions d'entree.
Ajuste TP/SL/strategies dynamiquement selon la performance recente.
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_LEARNING = os.path.join(DOSSIER, "learning_trader.json")
FICHIER_PORTFOLIO = os.path.join(DOSSIER, "paper_trading.json")


def charger_learning():
    """Charge le fichier d'apprentissage. Cree s'il n'existe pas."""
    try:
        with open(FICHIER_LEARNING) as f:
            return json.load(f)
    except Exception:
        return {
            "trades_analyses": [],
            "patterns_gagnants": {},
            "patterns_perdants": {},
            "stats_strategies": {},
            "stats_horaires": {},
            "stats_par_regime": {},
            "tp_optimal_par_crypto": {},
            "sl_optimal_par_crypto": {},
            "derniere_analyse": None,
            "version": 1,
        }


def sauver_learning(data):
    with open(FICHIER_LEARNING, "w") as f:
        json.dump(data, f, indent=2, default=str)


def analyser_trade_ferme(trade):
    """Extrait les donnees d'un trade ferme pour l'apprentissage."""
    return {
        "symbole": trade.get("symbole", ""),
        "strategie": trade.get("strategie", ""),
        "source": trade.get("source", ""),
        "gain_eur": trade.get("gain_eur", 0),
        "gain_pct": trade.get("gain_pct", 0),
        "prix_entree": trade.get("prix_entree", 0),
        "prix_sortie": trade.get("prix_sortie", 0),
        "date_ouverture": trade.get("date_ouverture", ""),
        "date_fermeture": trade.get("date_fermeture", ""),
        "raison_fermeture": trade.get("raison", ""),
        "duree_min": trade.get("duree_min", 0),
        "marche": trade.get("marche", ""),
        "gagnant": trade.get("gain_eur", 0) > 0,
    }


def analyser_trades(trades_fermes):
    """Analyse TOUS les trades fermes pour extraire les patterns gagnants/perdants."""
    if not trades_fermes:
        return {}

    learning = charger_learning()
    trades_analyses = []

    # Stats accumulees
    stats_strategies = defaultdict(lambda: {"n": 0, "gagnants": 0, "pnl_total": 0, "win_rate": 0})
    stats_horaires = defaultdict(lambda: {"n": 0, "gagnants": 0, "pnl_total": 0})
    stats_par_regime = defaultdict(lambda: {"n": 0, "gagnants": 0, "pnl_total": 0})
    stats_par_crypto = defaultdict(lambda: {"n": 0, "gagnants": 0, "pnl_total": 0, "meilleur_tp": 2.0, "meilleur_sl": 1.5})
    stats_raison = defaultdict(lambda: {"n": 0, "gagnants": 0, "pnl_total": 0})

    for trade in trades_fermes:
        t = analyser_trade_ferme(trade)
        trades_analyses.append(t)

        # Stats par strategie
        strat = t["strategie"]
        s = stats_strategies[strat]
        s["n"] += 1
        s["pnl_total"] += t["gain_eur"]
        if t["gagnant"]:
            s["gagnants"] += 1

        # Stats par heure (quel moment de la journee)
        try:
            dt = datetime.strptime(t["date_ouverture"][:16], "%Y-%m-%d %H:%M")
            heure = dt.hour
            h = stats_horaires[heure]
            h["n"] += 1
            h["pnl_total"] += t["gain_eur"]
            if t["gagnant"]:
                h["gagnants"] += 1
        except Exception:
            pass

        # Stats par crypto
        sym = t["symbole"]
        c = stats_par_crypto[sym]
        c["n"] += 1
        c["pnl_total"] += t["gain_eur"]
        if t["gagnant"]:
            c["gagnants"] += 1
            # Si le trade etait gagnant, le TP etait peut-etre trop bas
            if t["gain_pct"] > 0 and t["gain_pct"] < 3:
                c["meilleur_tp"] = max(c["meilleur_tp"], t["gain_pct"] + 1.0)
        else:
            # Si perdant, le SL etait peut-etre trop large
            if t["gain_pct"] < -2:
                c["meilleur_sl"] = min(c["meilleur_sl"], abs(t["gain_pct"]) * 0.8)

        # Stats par raison de fermeture
        r = stats_raison[t["raison_fermeture"][:20]]
        r["n"] += 1
        r["pnl_total"] += t["gain_eur"]
        if t["gagnant"]:
            r["gagnants"] += 1

    # Calculer win rates
    for s in stats_strategies.values():
        s["win_rate"] = (s["gagnants"] / s["n"] * 100) if s["n"] > 0 else 0
    for h in stats_horaires.values():
        h["win_rate"] = (h["gagnants"] / h["n"] * 100) if h["n"] > 0 else 0
    for c in stats_par_crypto.values():
        c["win_rate"] = (c["gagnants"] / c["n"] * 100) if c["n"] > 0 else 0
    for r in stats_raison.values():
        r["win_rate"] = (r["gagnants"] / r["n"] * 100) if r["n"] > 0 else 0

    # Identifier les patterns gagnants
    patterns_gagnants = {
        "meilleures_strategies": sorted(
            [(k, v) for k, v in stats_strategies.items() if v["n"] >= 2 and v["win_rate"] >= 50],
            key=lambda x: x[1]["pnl_total"], reverse=True
        )[:5],
        "meilleures_cryptos": sorted(
            [(k, v) for k, v in stats_par_crypto.items() if v["n"] >= 2 and v["win_rate"] >= 50],
            key=lambda x: x[1]["pnl_total"], reverse=True
        )[:5],
        "meilleures_heures": sorted(
            [(str(k), v) for k, v in stats_horaires.items() if v["n"] >= 2 and v["win_rate"] >= 50],
            key=lambda x: x[1]["pnl_total"], reverse=True
        )[:3],
        "pires_strategies": sorted(
            [(k, v) for k, v in stats_strategies.items() if v["n"] >= 2 and v["win_rate"] < 40],
            key=lambda x: x[1]["pnl_total"]
        )[:5],
        "pires_cryptos": sorted(
            [(k, v) for k, v in stats_par_crypto.items() if v["n"] >= 2 and v["win_rate"] < 40],
            key=lambda x: x[1]["pnl_total"]
        )[:5],
    }

    # Sauvegarder
    learning["trades_analyses"] = trades_analyses
    learning["patterns_gagnants"] = {k: [{**{"strategie": s[0]}, **s[1]} for s in v] if k.startswith("meilleures") or k.startswith("pires") else v for k, v in patterns_gagnants.items()}
    learning["stats_strategies"] = {k: v for k, v in stats_strategies.items()}
    learning["stats_horaires"] = {str(k): v for k, v in stats_horaires.items()}
    learning["stats_par_crypto"] = {k: v for k, v in stats_par_crypto.items()}
    learning["tp_optimal_par_crypto"] = {k: v["meilleur_tp"] for k, v in stats_par_crypto.items()}
    learning["sl_optimal_par_crypto"] = {k: v["meilleur_sl"] for k, v in stats_par_crypto.items()}
    learning["derniere_analyse"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    learning["total_trades"] = len(trades_analyses)
    learning["total_gagnants"] = sum(1 for t in trades_analyses if t["gagnant"])
    learning["total_perdants"] = sum(1 for t in trades_analyses if not t["gagnant"])
    learning["pnl_total"] = sum(t["gain_eur"] for t in trades_analyses)
    learning["win_rate_global"] = (learning["total_gagnants"] / len(trades_analyses) * 100) if trades_analyses else 0

    sauver_learning(learning)
    return learning


def get_recommandations():
    """Retourne les recommandations d'apprentissage pour le cycle actuel."""
    learning = charger_learning()
    recs = {
        "strategies_a_eviter": [],
        "strategies_a_privilegier": [],
        "cryptos_a_eviter": [],
        "cryptos_a_privilegier": [],
        "tp_optimal": {},
        "sl_optimal": {},
        "heures_favorables": [],
        "win_rate_global": learning.get("win_rate_global", 0),
        "total_trades": learning.get("total_trades", 0),
    }

    # Strategies a eviter (win rate < 30% avec au moins 5 trades)
    for strat, stats in learning.get("stats_strategies", {}).items():
        if stats.get("n", 0) >= 5 and stats.get("win_rate", 0) < 30:
            recs["strategies_a_eviter"].append(strat)
        elif stats.get("n", 0) >= 3 and stats.get("win_rate", 0) >= 60 and stats.get("pnl_total", 0) > 0:
            recs["strategies_a_privilegier"].append(strat)

    # Cryptos a eviter (win rate < 25% avec au moins 5 trades)
    for sym, stats in learning.get("stats_par_crypto", {}).items():
        if stats.get("n", 0) >= 5 and stats.get("win_rate", 0) < 25:
            recs["cryptos_a_eviter"].append(sym)
        elif stats.get("n", 0) >= 3 and stats.get("win_rate", 0) >= 60 and stats.get("pnl_total", 0) > 0:
            recs["cryptos_a_privilegier"].append(sym)

    # TP/SL optimaux par crypto (seulement si au moins 3 trades)
    for sym, stats in learning.get("stats_par_crypto", {}).items():
        if stats.get("n", 0) >= 3:
            recs["tp_optimal"][sym] = stats.get("meilleur_tp", 3.0)
            recs["sl_optimal"][sym] = stats.get("meilleur_sl", 1.5)

    # Heures favorables
    for heure, stats in learning.get("stats_horaires", {}).items():
        if stats.get("n", 0) >= 3 and stats.get("win_rate", 0) >= 60:
            recs["heures_favorables"].append(int(heure))

    return recs


def filtrer_signaux_avec_apprentissage(signaux):
    """Filtre les signaux en utilisant l'apprentissage: evite les cryptos et strategies perdantes."""
    recs = get_recommandations()
    signaux_filtres = []
    signaux_bloques = 0

    for signal in signaux:
        sym = signal.get("symbole", "")
        strat = signal.get("strategie", "")

        # Bloquer les cryptos qui perdent systematiquement
        if sym in recs["cryptos_a_eviter"]:
            signaux_bloques += 1
            print(f"  [LEARNING] SKIP {sym} — crypto perdante ({recs['win_rate_global']:.0f}% global)")
            continue

        # Bloquer les strategies qui perdent systematiquement
        if strat in recs["strategies_a_eviter"]:
            signaux_bloques += 1
            print(f"  [LEARNING] SKIP {strat} sur {sym} — strategie perdante")
            continue

        # Booster le score des cryptos et strategies gagnantes
        if sym in recs["cryptos_a_privilegier"]:
            signal["score"] = signal.get("score", 0) + 2
            signal["meta_confiance"] = signal.get("meta_confiance", 0.5) + 0.2
            print(f"  [LEARNING] BOOST {sym} — crypto gagnante (+2 score)")

        if strat in recs["strategies_a_privilegier"]:
            signal["score"] = signal.get("score", 0) + 1
            print(f"  [LEARNING] BOOST {strat} sur {sym} — strategie gagnante (+1 score)")

        # Ajuster le TP/SL selon l'apprentissage
        tp_opt = recs["tp_optimal"].get(sym)
        sl_opt = recs["sl_optimal"].get(sym)
        if tp_opt:
            signal["tp_optimal"] = tp_opt
        if sl_opt:
            signal["sl_optimal"] = sl_opt

        signaux_filtres.append(signal)

    if signaux_bloques > 0:
        print(f"  [LEARNING] {signaux_bloques} signaux bloques par apprentissage")

    return signaux_filtres


def rapport_learning():
    """Genere un rapport textuel de l'apprentissage."""
    learning = charger_learning()
    if not learning.get("trades_analyses"):
        return "Aucun trade analyse encore. L'apprentissage commence apres les premiers trades fermes."

    lignes = []
    lignes.append("=== APPRENTISSAGE TRADER ===\n")
    lignes.append(f"Trades analyses: {learning.get('total_trades', 0)}")
    lignes.append(f"Gagnants: {learning.get('total_gagnants', 0)} | Perdants: {learning.get('total_perdants', 0)}")
    lignes.append(f"Win rate global: {learning.get('win_rate_global', 0):.1f}%")
    lignes.append(f"PnL total: {learning.get('pnl_total', 0):+.2f}EUR")
    lignes.append(f"Derniere analyse: {learning.get('derniere_analyse', 'jamais')}\n")

    # Top strategies
    lignes.append("--- STRATEGIES ---")
    strats = sorted(learning.get("stats_strategies", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    for strat, s in strats[:10]:
        wr = s.get("win_rate", 0)
        n = s.get("n", 0)
        pnl = s.get("pnl_total", 0)
        emoji = "+" if pnl > 0 else "-"
        lignes.append(f"  {emoji} {strat:20s} | {n:3d} trades | WR {wr:5.1f}% | PnL {pnl:+.2f}EUR")

    # Top cryptos
    lignes.append("\n--- CRYPTOS ---")
    cryptos = sorted(learning.get("stats_par_crypto", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    for sym, s in cryptos[:10]:
        wr = s.get("win_rate", 0)
        n = s.get("n", 0)
        pnl = s.get("pnl_total", 0)
        tp_opt = s.get("meilleur_tp", 2.0)
        sl_opt = s.get("meilleur_sl", 1.5)
        emoji = "+" if pnl > 0 else "-"
        lignes.append(f"  {emoji} {sym:12s} | {n:3d} trades | WR {wr:5.1f}% | PnL {pnl:+.2f}EUR | TP {tp_opt:.1f}% SL {sl_opt:.1f}%")

    # Heures favorables
    lignes.append("\n--- HEURES FAVORABLES ---")
    heures = sorted(learning.get("stats_horaires", {}).items(), key=lambda x: x[1].get("pnl_total", 0), reverse=True)
    for heure, s in heures[:5]:
        wr = s.get("win_rate", 0)
        n = s.get("n", 0)
        pnl = s.get("pnl_total", 0)
        lignes.append(f"  {heure}h | {n:3d} trades | WR {wr:5.1f}% | PnL {pnl:+.2f}EUR")

    # Recommandations
    recs = get_recommandations()
    if recs["strategies_a_eviter"]:
        lignes.append(f"\n--- A EVITER ---")
        lignes.append(f"  Strategies: {', '.join(recs['strategies_a_eviter'])}")
        lignes.append(f"  Cryptos: {', '.join(recs['cryptos_a_eviter'])}")
    if recs["strategies_a_privilegier"]:
        lignes.append(f"\n--- A PRIVILEGIER ---")
        lignes.append(f"  Strategies: {', '.join(recs['strategies_a_privilegier'])}")
        lignes.append(f"  Cryptos: {', '.join(recs['cryptos_a_privilegier'])}")

    return "\n".join(lignes)


if __name__ == "__main__":
    # Analyser les trades fermes
    try:
        with open(FICHIER_PORTFOLIO) as f:
            pf = json.load(f)
        trades = pf.get("trades_fermes", [])
        if trades:
            print(f"Analyse de {len(trades)} trades fermes...")
            result = analyser_trades(trades)
            print(f"OK! {result.get('total_trades', 0)} trades analyses.")
            print(f"Win rate: {result.get('win_rate_global', 0):.1f}%")
            print(f"PnL total: {result.get('pnl_total', 0):+.2f}EUR")
            print()
            print(rapport_learning())
        else:
            print("Aucun trade ferme a analyser.")
    except Exception as e:
        print(f"Erreur: {e}")
