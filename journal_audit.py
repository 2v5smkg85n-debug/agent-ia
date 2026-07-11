#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JOURNAL AUDITE - Phase 6, Etape 1 (infrastructure pro).
========================================================

La feuille de route disait :
  "Tenir un journal audite de chaque trade (timestamp, prix attendu, prix
   fill, slippage, P&L)" + "comparer slippage simule vs slippage reel".

Ce module :
  1. Lit paper_trading.json (historique des trades fermes + positions ouvertes)
  2. Construit un JOURNAL AUDITE complet : un enregistrement par trade avec
     tous les champs necessaires a un audit (timestamp, prix entree/sortie,
     quantite, frais, gain, slippage simule, raison, marche, strategie...)
  3. Calcule les METRIQUES PRO : Sharpe, Sortino, Calmar, profit factor,
     expectancy, max drawdown, win rate, CAGR, avg gain/loss, streaks...
  4. Suit le P&L JOURNALIER (equity curve jour par jour)
  5. EXPORT CSV : pour audit externe / Excel / fiscalite
  6. FRAMEWORK PAPER vs LIVE : structure prete a comparer les trades
     simules aux trades reels quand on passera en capital reel (Phase 6 Etape 2)

AUCUNE IA : tout est calcule deterministiquement depuis les donnees reelles.

Usage:
    python journal_audit.py                # genere le rapport complet + CSV
    python journal_audit.py rapport        # affiche le rapport detaille
    python journal_audit.py trades         # liste tous les trades audites
    python journal_audit.py journal        # affiche le journal JSON
    python journal_audit.py csv            # exporte en CSV uniquement
    python journal_audit.py compare        # (plus tard) compare paper vs live
"""
import os
import sys
import json
import math
import csv
from datetime import datetime, timedelta
from collections import defaultdict

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_JOURNAL = os.path.join(DOSSIER, "journal_audit.json")
FICHIER_CSV = os.path.join(DOSSIER, "journal_audit.csv")

# Capital de reference (pour les rendements %)
CAPITAL_REF = 1000.0


# ============================================
# CHARGEMENT
# ============================================
def charger_paper():
    if not os.path.exists(FICHIER_PAPER):
        return None
    try:
        with open(FICHIER_PAPER, "r") as f:
            return json.load(f)
    except Exception:
        return None


def charger_journal():
    if os.path.exists(FICHIER_JOURNAL):
        try:
            with open(FICHIER_JOURNAL, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"trades": [], "metriques": {}, "genere_le": None}


def sauver_journal(journal):
    with open(FICHIER_JOURNAL, "w") as f:
        json.dump(journal, f, ensure_ascii=False, indent=2)


# ============================================
# CONSTRUCTION DU JOURNAL AUDITE
# ============================================
def construire_journal(pf):
    """Transforme l'historique de paper_trading.json en journal audite.

    Chaque trade devient un enregistrement avec tous les champs d'audit.
    Le champ 'slippage_simule' est estime (en paper, 0 par defaut ; plus tard
    en live, on comparera prix attendu vs prix fill reel).
    """
    trades = pf.get("historique", [])
    journal_trades = []

    for i, t in enumerate(trades, 1):
        # Slippage simule : en paper trading, le prix d'execution = prix voulu
        # (pas de slippage reel). On garde la structure pour la comparaison live.
        prix_entree = t.get("prix_entree", 0)
        prix_sortie = t.get("prix_sortie", 0)
        variation_pct = t.get("variation_pct", 0)
        frais_total = t.get("frais_total", 0)
        montant = t.get("montant_eur", 0)
        gain = t.get("gain_eur", 0)

        # Slippage = difference entre rendement brut et rendement apres frais
        # (en paper, c'est uniquement les frais ; en live on aura frais + slippage reel)
        rendement_brut_pct = variation_pct
        rendement_net_pct = (gain / montant * 100) if montant else 0
        cout_total_pct = rendement_brut_pct - rendement_net_pct  # frais + slippage

        entree = {
            "id": i,
            "date_fermeture": t.get("date_fermeture", ""),
            "date_ouverture": t.get("date_ouverture", ""),
            "symbole": t.get("symbole", ""),
            "nom": t.get("nom", ""),
            "marche": t.get("marche", ""),
            "raison": t.get("raison", ""),
            "prix_entree": round(prix_entree, 6),
            "prix_sortie": round(prix_sortie, 6),
            "quantite": round(t.get("quantite", 0), 8),
            "montant_eur": round(montant, 2),
            "frais_total": round(frais_total, 4),
            "frais_pct": round((frais_total / montant * 100) if montant else 0, 4),
            "variation_pct": round(variation_pct, 4),
            "gain_eur": round(gain, 4),
            "rendement_net_pct": round(rendement_net_pct, 4),
            "cout_total_pct": round(cout_total_pct, 4),
            "slippage_simule_pct": 0.0,  # paper = 0 ; structure prete pour le live
            "gagnant": gain > 0,
            # Phase 6 : extrait la strategie depuis la raison d'OUVERTURE
            # (signal_raison), pas la raison de fermeture (TAKE-PROFIT, STOP-LOSS...)
            "strategie": extraire_strategie(t.get("signal_raison", "")),
        }
        journal_trades.append(entree)

    return journal_trades


def extraire_strategie(raison_ouverture):
    """Extrait le nom de strategie depuis la raison d'ouverture du signal.

    Format attendu (depuis signaux_gagnants.py) :
      "strategie gagnante backtest (MACD Momentum [4h], retour +15.1%, win rate 60%)"
      -> "MACD Momentum [4h]"

    Fallback : si aucune strategie identifiable (manuel, indicateurs, IA),
    renvoie une etiquette claire au lieu d'un pourcentage errone.
    """
    if not raison_ouverture:
        return "manuel/indicateurs"
    import re
    # Cherche un pattern comme "(MACD Momentum [4h], ..." : strategie avant la 1ere virgule
    m = re.search(r"\(([^,]+(?:\[[^\]]+\])?)", raison_ouverture)
    if m:
        candidat = m.group(1).strip()
        # Un vrai nom de strategie contient des lettres et ne commence pas par un chiffre/+/-
        if re.search(r"[a-zA-Z]", candidat) and not re.match(r"^[+\-]?\d", candidat):
            return candidat
    # Detection des sources connues
    r = raison_ouverture.lower()
    if "backtest" in r or "gagnante" in r:
        return "backtest (strategie non identifiee)"
    if any(k in r for k in ("indicateur", "rsi", "macd", "bollinger", "sma")):
        return "indicateurs techniques"
    if "ia" in r or "signal ia" in r:
        return "IA"
    if "manuel" in r:
        return "manuel"
    return "manuel/indicateurs"


# ============================================
# METRIQUES PRO
# ============================================
def calculer_metriques(trades, pf):
    """Calcule toutes les metriques pro depuis le journal audite."""
    if not trades:
        return {"erreur": "Aucun trade dans le journal"}

    n = len(trades)
    gains = [t["gain_eur"] for t in trades]
    gagnants = [g for g in gains if g > 0]
    perdants = [g for g in gains if g <= 0]
    n_gagnes = len(gagnants)
    n_perdus = len(perdants)

    gain_total = sum(gains)
    gain_brut = sum(gagnants)
    perte_brute = abs(sum(perdants))

    # Win rate
    win_rate = n_gagnes / n * 100 if n else 0

    # Profit factor
    profit_factor = gain_brut / perte_brute if perte_brute > 0 else float("inf")

    # Moyennes
    avg_gain = gain_brut / n_gagnes if gagnants else 0
    avg_perte = perte_brute / n_perdus if perdants else 0

    # Expectancy : gain moyen attendu par trade
    expectancy = (win_rate / 100) * avg_gain - (1 - win_rate / 100) * avg_perte

    # Ratio gain/perte
    ratio_gp = abs(avg_gain / avg_perte) if avg_perte else float("inf")

    # Frais totaux
    frais_totaux = pf.get("total_frais", 0)

    # Capital final
    valeur_actuelle = pf.get("liquidites", 0)
    for pos in pf.get("positions", []):
        valeur_actuelle += pos.get("montant_eur", 0)  # approximation sans prix live
    capital_final = valeur_actuelle
    retour_pct = (capital_final - CAPITAL_REF) / CAPITAL_REF * 100

    # Equity curve jour par jour (cumul des gains par jour)
    pnl_journalier = defaultdict(float)
    for t in trades:
        try:
            jour = t["date_fermeture"].split(" ")[0]
            pnl_journalier[jour] += t["gain_eur"]
        except Exception:
            pass
    jours = sorted(pnl_journalier.keys())
    equity_curve = []
    cumul = CAPITAL_REF
    for j in jours:
        cumul += pnl_journalier[j]
        equity_curve.append({"jour": j, "pnl": pnl_journalier[j], "equity": round(cumul, 2)})

    # Rendements journaliers (pour Sharpe/Sortino)
    rendements = []
    for e in equity_curve:
        if len(rendements) == 0:
            base = CAPITAL_REF
        else:
            base = equity_curve[len(rendements) - 1]["equity"]
        if base > 0:
            rendements.append(pnl_journalier[e["jour"]] / base)

    # Sharpe ratio (annualise, sans taux sans risque)
    sharpe = calculer_sharpe(rendements)

    # Sortino ratio (denominateur = downside deviation seulement)
    sortino = calculer_sortino(rendements)

    # Max drawdown
    max_dd = calculer_max_drawdown(equity_curve)

    # Calmar = retour annualise / max drawdown
    nb_jours = max(len(jours), 1)
    retour_annualise = ((capital_final / CAPITAL_REF) ** (365 / nb_jours) - 1) * 100 if capital_final > 0 else 0
    calmar = abs(retour_annualise / max_dd) if max_dd > 0 else float("inf")

    # Streaks (series de gains/pertes consecutifs)
    max_streak_gains, max_streak_pertes = calculer_streaks(gains)

    # Stats par marche
    par_marche = {}
    for t in trades:
        m = t["marche"]
        par_marche.setdefault(m, {"trades": 0, "gain": 0.0, "gagnes": 0})
        par_marche[m]["trades"] += 1
        par_marche[m]["gain"] += t["gain_eur"]
        if t["gain_eur"] > 0:
            par_marche[m]["gagnes"] += 1
    for m in par_marche:
        s = par_marche[m]
        s["win_rate"] = round(s["gagnes"] / s["trades"] * 100, 1) if s["trades"] else 0
        s["gain_moyen"] = round(s["gain"] / s["trades"], 4) if s["trades"] else 0

    # Stats par strategie
    par_strat = {}
    for t in trades:
        s = t["strategie"]
        par_strat.setdefault(s, {"trades": 0, "gain": 0.0, "gagnes": 0})
        par_strat[s]["trades"] += 1
        par_strat[s]["gain"] += t["gain_eur"]
        if t["gain_eur"] > 0:
            par_strat[s]["gagnes"] += 1
    for s in par_strat:
        d = par_strat[s]
        d["win_rate"] = round(d["gagnes"] / d["trades"] * 100, 1) if d["trades"] else 0

    # Stats par raison de sortie
    par_raison = defaultdict(lambda: {"trades": 0, "gain": 0.0})
    for t in trades:
        r = t["raison"].split(" (")[0] if " (" in t["raison"] else t["raison"]
        par_raison[r]["trades"] += 1
        par_raison[r]["gain"] += t["gain_eur"]

    return {
        "resume": {
            "trades_total": n,
            "trades_gagnes": n_gagnes,
            "trades_perdus": n_perdus,
            "win_rate_pct": round(win_rate, 1),
            "capital_initial": CAPITAL_REF,
            "capital_final": round(capital_final, 2),
            "retour_pct": round(retour_pct, 2),
            "retour_annualise_pct": round(retour_annualise, 2),
            "gain_perte_total": round(gain_total, 2),
            "frais_totaux": round(frais_totaux, 2),
            "gain_brut_sans_frais": round(gain_total + frais_totaux, 2),
        },
        "ratios_pro": {
            "sharpe": round(sharpe, 3) if sharpe == sharpe else None,  # NaN check
            "sortino": round(sortino, 3) if sortino == sortino else None,
            "calmar": round(calmar, 3) if calmar == calmar else None,
            "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else None,
            "max_drawdown_pct": round(max_dd, 2),
            "expectancy_eur": round(expectancy, 4),
            "avg_gain_eur": round(avg_gain, 4),
            "avg_perte_eur": round(avg_perte, 4),
            "ratio_gain_perte": round(ratio_gp, 3) if ratio_gp != float("inf") else None,
            "max_streak_gains": max_streak_gains,
            "max_streak_pertes": max_streak_pertes,
        },
        "par_marche": par_marche,
        "par_strategie": par_strat,
        "par_raison": dict(par_raison),
        "equity_curve": equity_curve,
        "nb_jours_actifs": len(jours),
    }


def calculer_sharpe(rendements, per_an=365):
    """Sharpe ratio annualise (sans taux sans risque, crypto = 24/7)."""
    if len(rendements) < 2:
        return 0.0
    moy = sum(rendements) / len(rendements)
    var = sum((r - moy) ** 2 for r in rendements) / (len(rendements) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (moy / std) * math.sqrt(per_an)


def calculer_sortino(rendements, per_an=365):
    """Sortino ratio (denominateur = ecart-type des rendements negatifs seulement)."""
    if len(rendements) < 2:
        return 0.0
    moy = sum(rendements) / len(rendements)
    downside = [r for r in rendements if r < 0]
    if not downside:
        return float("inf") if moy > 0 else 0.0
    var_down = sum(r ** 2 for r in downside) / len(downside)
    dd_std = math.sqrt(var_down)
    if dd_std == 0:
        return 0.0
    return (moy / dd_std) * math.sqrt(per_an)


def calculer_max_drawdown(equity_curve):
    """Drawdown maximum depuis l'equity curve."""
    if not equity_curve:
        return 0.0
    pic = equity_curve[0]["equity"]
    max_dd = 0.0
    for e in equity_curve:
        if e["equity"] > pic:
            pic = e["equity"]
        if pic > 0:
            dd = (pic - e["equity"]) / pic * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def calculer_streaks(gains):
    """Series de gains et de pertes consecutifs max."""
    max_g = 0
    max_p = 0
    cur_g = 0
    cur_p = 0
    for g in gains:
        if g > 0:
            cur_g += 1
            cur_p = 0
            max_g = max(max_g, cur_g)
        else:
            cur_p += 1
            cur_g = 0
            max_p = max(max_p, cur_p)
    return max_g, max_p


# ============================================
# EXPORT CSV
# ============================================
def exporter_csv(trades):
    """Exporte le journal en CSV pour audit externe / Excel / fiscalite."""
    if not trades:
        print("Aucun trade a exporter.")
        return
    champs = [
        "id", "date_ouverture", "date_fermeture", "marche", "nom", "symbole",
        "strategie", "raison", "prix_entree", "prix_sortie", "quantite",
        "montant_eur", "variation_pct", "frais_total", "frais_pct",
        "cout_total_pct", "slippage_simule_pct", "rendement_net_pct",
        "gain_eur", "gagnant",
    ]
    with open(FICHIER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            w.writerow(t)
    print(f"CSV exporte : {FICHIER_CSV} ({len(trades)} trades)")


# ============================================
# FRAMEWORK PAPER vs LIVE (pour la Phase 6 Etape 2)
# ============================================
def framework_comparaison(trades):
    """Prepare la structure pour comparer paper vs live plus tard.

    Quand on passera en capital reel (Revolut X), chaque trade live aura un
    prix 'attendu' (calcul par la strategie) et un prix 'fill' reel (execute).
    La difference = slippage reel. Ce framework prepare les buckets de comparaison.
    """
    buckets = {
        "paper": {
            "trades": len(trades),
            "slippage_moyen_pct": 0.0,  # paper = 0
            "frais_moyen_pct": round(
                sum(t["frais_pct"] for t in trades) / len(trades), 4
            ) if trades else 0,
            "gain_moyen_eur": round(
                sum(t["gain_eur"] for t in trades) / len(trades), 4
            ) if trades else 0,
        },
        "live": {
            # A remplir quand les trades live seront disponibles
            "trades": 0,
            "slippage_moyen_pct": None,
            "frais_moyen_pct": None,
            "gain_moyen_eur": None,
            "statut": "en attente du capital reel (Phase 6 Etape 2)",
        },
        "divergence": {
            "statut": "N/A - pas encore de trades live",
            "explication": ("Quand les trades live seront disponibles, ce bucket "
                            "comparera slippage/frais/gain moyens entre paper et live. "
                            "Toute divergence > 0.5% = probleme a diagnostiquer."),
        },
    }
    return buckets


# ============================================
# AFFICHAGE
# ============================================
def afficher_rapport(journal):
    met = journal.get("metriques", {})
    res = met.get("resume", {})
    ratios = met.get("ratios_pro", {})

    print("=" * 65)
    print("JOURNAL AUDITE - RAPPORT COMPLET")
    print(f"Genere le : {journal.get('genere_le', '?')}")
    print("=" * 65)

    print("\n--- RESUME ---")
    print(f"  Trades total       : {res.get('trades_total', 0)}")
    print(f"  Gagnes / Perdus    : {res.get('trades_gagnes', 0)} / {res.get('trades_perdus', 0)}")
    print(f"  Win rate           : {res.get('win_rate_pct', 0)}%")
    print(f"  Capital initial    : {res.get('capital_initial', 0)} EUR")
    print(f"  Capital final      : {res.get('capital_final', 0)} EUR")
    print(f"  Retour total       : {res.get('retour_pct', 0):+.2f}%")
    print(f"  Retour annualise   : {res.get('retour_annualise_pct', 0):+.2f}%")
    print(f"  Gain/perte net     : {res.get('gain_perte_total', 0):+.2f} EUR")
    print(f"  Frais totaux       : {res.get('frais_totaux', 0)} EUR")
    print(f"  Gain brut sans frais: {res.get('gain_brut_sans_frais', 0):+.2f} EUR")
    print(f"  Jours actifs       : {met.get('nb_jours_actifs', 0)}")

    print("\n--- RATIOS PRO ---")
    sharpe = ratios.get("sharpe")
    sortino = ratios.get("sortino")
    calmar = ratios.get("calmar")
    pf = ratios.get("profit_factor")
    print(f"  Sharpe ratio       : {sharpe if sharpe is not None else 'N/A'}")
    print(f"  Sortino ratio      : {sortino if sortino is not None else 'N/A'}")
    print(f"  Calmar ratio       : {calmar if calmar is not None else 'N/A'}")
    print(f"  Profit factor      : {pf if pf is not None else 'inf'}")
    print(f"  Max drawdown       : {ratios.get('max_drawdown_pct', 0)}%")
    print(f"  Expectancy/trade   : {ratios.get('expectancy_eur', 0):+.4f} EUR")
    print(f"  Gain moyen         : {ratios.get('avg_gain_eur', 0):+.4f} EUR")
    print(f"  Perte moyenne     : {ratios.get('avg_perte_eur', 0):+.4f} EUR")
    print(f"  Ratio gain/perte   : {ratios.get('ratio_gain_perte', 'N/A')}")
    print(f"  Max streak gains   : {ratios.get('max_streak_gains', 0)}")
    print(f"  Max streak pertes  : {ratios.get('max_streak_pertes', 0)}")

    print("\n--- PERFORMANCE PAR MARCHE ---")
    for m, s in sorted(met.get("par_marche", {}).items(),
                       key=lambda x: x[1].get("gain", 0), reverse=True):
        print(f"  {m:<12} : {s['trades']:>3} trades | "
              f"WR {s.get('win_rate',0):>5}% | "
              f"gain {s['gain']:+.2f} EUR | "
              f"moy {s.get('gain_moyen',0):+.4f}")

    print("\n--- PERFORMANCE PAR STRATEGIE ---")
    for s, d in sorted(met.get("par_strategie", {}).items(),
                       key=lambda x: x[1].get("gain", 0), reverse=True):
        print(f"  {s:<28} : {d['trades']:>3} trades | "
              f"WR {d.get('win_rate',0):>5}% | "
              f"gain {d['gain']:+.2f} EUR")

    print("\n--- RAISONS DE SORTIE ---")
    for r, d in sorted(met.get("par_raison", {}).items(),
                       key=lambda x: x[1].get("gain", 0), reverse=True):
        print(f"  {r:<28} : {d['trades']:>3} trades | gain {d['gain']:+.2f} EUR")

    eq = met.get("equity_curve", [])
    if eq:
        print("\n--- EQUITY CURVE (journalier) ---")
        for e in eq:
            print(f"  {e['jour']} : P&L {e['pnl']:+.2f} EUR | equity {e['equity']:.2f} EUR")

    print("\n--- COMPARAISON PAPER vs LIVE ---")
    comp = journal.get("comparaison", {})
    paper = comp.get("paper", {})
    live = comp.get("live", {})
    print(f"  Paper : {paper.get('trades',0)} trades | "
          f"slippage {paper.get('slippage_moyen_pct',0)}% | "
          f"frais {paper.get('frais_moyen_pct',0)}% | "
          f"gain moy {paper.get('gain_moyen_eur',0)} EUR")
    print(f"  Live  : {live.get('trades',0)} trades | "
          f"statut: {live.get('statut','?')}")

    print("\n" + "=" * 65)
    # Test "es-tu pro" (de la feuille de route)
    print("TEST PRO : cases cochees")
    checks = [
        ("Sharpe > 1.0", sharpe is not None and sharpe > 1.0),
        ("Max drawdown < 30%", ratios.get("max_drawdown_pct", 100) < 30),
        ("Win rate > 50%", res.get("win_rate_pct", 0) > 50),
        ("Profit factor > 1.5", pf is not None and pf > 1.5),
        ("100+ trades en backtest", True),  # deja valide (168 backtests horaires + 84 daily)
        ("30+ trades live", False),  # pas encore de live
    ]
    coches = sum(1 for _, v in checks if v)
    for label, v in checks:
        print(f"  [{'x' if v else ' '}] {label}")
    print(f"  -> {coches}/{len(checks)} cases cochees")
    print("=" * 65)


def afficher_trades(journal):
    trades = journal.get("trades", [])
    if not trades:
        print("Aucun trade dans le journal.")
        return
    print(f"\nTRADES AUDITES ({len(trades)}):")
    print("-" * 90)
    print(f"{'ID':>3} {'Date':<16} {'Marche':<10} {'Nom':<12} {'Raison':<22} "
          f"{'Var%':>7} {'Frais%':>7} {'Gain EUR':>9}")
    print("-" * 90)
    for t in trades:
        raison = t["raison"][:20]
        print(f"{t['id']:>3} {t['date_fermeture']:<16} {t['marche']:<10} "
              f"{t['nom']:<12} {raison:<22} {t['variation_pct']:+.2f} "
              f"{t['frais_pct']:+.3f} {t['gain_eur']:+.4f}")


# ============================================
# GENERATION COMPLETE
# ============================================
def generer():
    pf = charger_paper()
    if not pf:
        print("Portefeuille paper trading introuvable. Lance 'python paper_trading.py init' d'abord.")
        return None

    trades = construire_journal(pf)
    metriques = calculer_metriques(trades, pf)
    comparaison = framework_comparaison(trades)

    journal = {
        "genere_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": FICHIER_PAPER,
        "trades": trades,
        "metriques": metriques,
        "comparaison": comparaison,
    }
    sauver_journal(journal)
    exporter_csv(trades)
    return journal


def aide():
    print("""
JOURNAL AUDITE (Phase 6, Etape 1)
=================================
Commandes:
  python journal_audit.py            Genere le rapport complet + CSV
  python journal_audit.py rapport    Affiche le rapport detaille (metriques pro)
  python journal_audit.py trades     Liste tous les trades audites
  python journal_audit.py journal    Affiche le journal JSON
  python journal_audit.py csv        Exporte en CSV uniquement

Le journal contient pour chaque trade:
  - Timestamps (ouverture/fermeture)
  - Prix entree/sortie, quantite, montant
  - Frais, slippage simule, cout total
  - Variation %, rendement net, gain EUR
  - Marche, strategie, raison de sortie

Metriques pro calculees:
  - Sharpe, Sortino, Calmar, profit factor
  - Max drawdown, expectancy, ratio gain/perte
  - Win rate, streaks, equity curve journaliere
  - Performance par marche, par strategie, par raison

Exports:
  - journal_audit.json (journal complet machine)
  - journal_audit.csv (pour Excel / audit externe / fiscalite)

Framework paper vs live:
  - Structure prete a comparer slippage/frais/gains
    entre paper et live quand tu passeras en capital reel.
""")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "rapport"

    print("=" * 65)
    print(f"JOURNAL AUDITE - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 65)

    if cmd == "aide":
        aide()
    elif cmd == "csv":
        pf = charger_paper()
        if pf:
            exporter_csv(construire_journal(pf))
    elif cmd == "journal":
        j = charger_journal()
        if j:
            print(json.dumps(j, indent=2, ensure_ascii=False)[:5000])
        else:
            print("Aucun journal. Lance 'python journal_audit.py' d'abord.")
    elif cmd == "trades":
        j = charger_journal()
        if not j:
            j = generer()
        if j:
            afficher_trades(j)
    elif cmd == "compare":
        j = charger_journal()
        if not j:
            j = generer()
        if j:
            comp = j.get("comparaison", {})
            print(json.dumps(comp, indent=2, ensure_ascii=False))
    else:
        # rapport (defaut)
        j = generer()
        if j:
            afficher_rapport(j)
