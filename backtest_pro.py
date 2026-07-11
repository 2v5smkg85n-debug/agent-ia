#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BACKTEST PRO - PHASE 1 (couts reels + metriques pro).
Ameliore backtest_moteur.py avec un modele de couts realiste et des metriques
de niveau professionnel.

Ameliorations vs backtest_moteur.py:
  1. Slippage modelise par actif (3 a 50 bps selon la liquidite)
  2. Frais maker/taker SEPARES (pas un seul chiffre 0.1%)
  3. Maker share: fraction d'ordres qui reposent sur le carnet vs traversent le spread
  4. Reduction BNB (10%) pour la crypto
  5. Execution a l'OUVERTURE de la bougie suivante (anti look-ahead bias)
  6. Metriques pro: Sharpe, Sortino, Calmar, profit factor, CAGR, expectancy

Metriques pro:
  - Sharpe ratio: >1.0 acceptable, >1.5 bien, >2.0 suspect (overfit)
  - Sortino ratio (downside only)
  - Max drawdown: <30% tolerable, >50% trop risque
  - Profit factor: >1.5 = structurellement sain
  - Calmar ratio (CAGR / max drawdown)

Usage:
  python backtest_pro.py               # teste tout (4 strategies x 21 actifs = 84)
  python backtest_pro.py crypto         # focus sur un marche
  python backtest_pro.py compare        # compare couts naifs vs couts reels
  python backtest_pro.py resultats      # affiche les resultats pro
  python backtest_pro.py meilleurs      # top strategies gagnantes
"""
import os
import sys
import json
import math
import time
from datetime import datetime

# Reutilise les strategies et indicateurs du moteur existant (pas de duplication)
from backtest_moteur import (
    ACTIFS, STRATEGIES, CAPITAL_DEPART,
    sma_series, rsi_series, bollinger_series, _macd_full,
)
from indicateurs import historique_ohlcv

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_RESULTATS = os.path.join(DOSSIER, "backtests_pro.json")
FICHIER_ANCIEN = os.path.join(DOSSIER, "backtests_reels.json")

# ============================================
# CONFIG - COUTS REALISTES
# ============================================
TAKE_PROFIT_PCT = 0.015    # +1.5% (identique au paper trading)
STOP_LOSS_PCT = 0.015      # -1.5%

# Frais maker/taker par marche (fraction du notionnel)
# Source: Binance spot (crypto), brokers typiques (autres marches)
COUTS_PAR_MARCHE = {
    "crypto":   {"maker": 0.00100, "taker": 0.00100},  # spot Binance 0.1%/0.1%
    "forex":    {"maker": 0.00020, "taker": 0.00050},  # broker forex
    "actions":  {"maker": 0.00050, "taker": 0.00100},  # broker actions
    "matieres": {"maker": 0.00050, "taker": 0.00100},  # CFD matieres
    "indices":  {"maker": 0.00050, "taker": 0.00100},  # CFD indices
}

# Slippage par actif en bps (1 bp = 0.01%). Plus l'actif est liquide, moins de slippage.
SLIPPAGE_BPS = {
    # crypto majors tres liquides
    "BTCUSDT": 3,
    "ETHUSDT": 4,
    "BNBUSDT": 5,
    "SOLUSDT": 8,
    "XRPUSDT": 10,
    # forex tres liquide
    "EURUSD=X": 1,
    "GBPUSD=X": 2,
    "JPY=X": 2,
    "GC=F": 3,        # or, assez liquide
    # actions mega-cap liquides
    "AAPL": 2,
    "MSFT": 2,
    "NVDA": 3,
    "TSLA": 4,
    # matieres premieres - liquidite moyenne
    "BZ=F": 5,        # brent
    "NG=F": 8,        # gaz naturel, plus volatil
    "HG=F": 4,        # cuivre
    "ZW=F": 6,        # ble
    # indices tres liquides
    "^GSPC": 2,
    "^IXIC": 2,
    "^GDAXI": 3,
    "^FCHI": 3,
}
SLIPPAGE_DEFAUT_BPS = 10  # par marche si actif inconnu

# Fraction d'ordres maker (reposent sur le carnet) vs taker (traversent le spread)
# Une strategie momentum execute au marche -> majorite taker
MAKER_SHARE = 0.20

# Reduction BNB sur la crypto (paiement des frais en BNB = -10%)
REDUCTION_BNB = 0.10

# ============================================
# CALCUL DES COUTS EFFECTIFS
# ============================================
def frais_effectif(marche):
    """Frais blends: maker * share + taker * (1 - share), avec reduction BNB."""
    c = COUTS_PAR_MARCHE.get(marche, COUTS_PAR_MARCHE["actions"])
    blended = c["maker"] * MAKER_SHARE + c["taker"] * (1 - MAKER_SHARE)
    if marche == "crypto":
        blended *= (1 - REDUCTION_BNB)
    return blended

def slippage_effectif(marche, actif):
    """Slippage en fraction du prix (ex: 0.0003 = 3 bps)."""
    bps = SLIPPAGE_BPS.get(actif, COUTS_PAR_MARCHE.get(marche, {}).get("taker", 0.001) * 10000)
    if actif not in SLIPPAGE_BPS:
        bps = SLIPPAGE_DEFAUT_BPS
    return bps / 10000.0

# ============================================
# STOCKAGE
# ============================================
def charger_resultats():
    if os.path.exists(FICHIER_RESULTATS):
        try:
            with open(FICHIER_RESULTATS, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def sauver_resultats(resultats):
    with open(FICHIER_RESULTATS, "w") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

# ============================================
# SIMULATION REALISTE
# ============================================
def simuler_pro(bougies, fonction_strat, marche, actif, capital=CAPITAL_DEPART):
    """
    Execute une strategie bougie par bougie avec couts reels.
    Signal calcule sur cloture[i], execute a ouverture[i+1] (anti look-ahead).
    """
    if not bougies or len(bougies) < 60:
        return None

    clotures = [b["cloture"] for b in bougies]
    ouvertures = [b["ouverture"] for b in bougies]

    # Pre-calcule les indicateurs sur toute la serie
    donnees = {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": None, "bb_bas": None,
        "macd_line": None, "macd_signal": None,
    }
    donnees["bb_haut"], donnees["bb_bas"] = bollinger_series(clotures, 20, 2)
    donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)

    frais = frais_effectif(marche)
    slip = slippage_effectif(marche, actif)

    capital_dispo = capital
    quantite = 0.0
    prix_entree = 0.0
    trades = 0
    gagnes = 0
    perdus = 0
    somme_gains = 0.0
    somme_pertes = 0.0
    valeur_max = capital
    drawdown_max = 0.0
    courbe_capital = [capital]  # pour Sharpe/Sortino
    signal_en_attente = None   # signal genere au close de la veille, execute a l'ouverture

    for i in range(len(clotures)):
        prix_close = clotures[i]

        # 1. Execute le signal en attente a l'ouverture de CETTE bougie (anti look-ahead)
        if i > 0 and signal_en_attente is not None:
            prix_open = ouvertures[i]
            # Slippage: on paie plus a l'achat, on recoit moins a la vente
            if signal_en_attente == "ACHAT" and quantite == 0 and capital_dispo > 10:
                prix_fill = prix_open * (1 + slip)
                montant = capital_dispo
                quantite = (montant * (1 - frais)) / prix_fill
                capital_dispo = 0.0
                prix_entree = prix_fill
            elif signal_en_attente == "VENTE" and quantite > 0:
                prix_fill = prix_open * (1 - slip)
                produit = quantite * prix_fill * (1 - frais)
                pnl = produit - (prix_entree * quantite)
                capital_dispo += produit
                trades += 1
                if pnl > 0:
                    gagnes += 1
                    somme_gains += pnl
                else:
                    perdus += 1
                    somme_pertes += abs(pnl)
                quantite = 0.0
            signal_en_attente = None

        # 2. Verifie stop-loss / take-profit sur le prix de cloture (si en position)
        if quantite > 0:
            var = (prix_close - prix_entree) / prix_entree
            if var >= TAKE_PROFIT_PCT or var <= -STOP_LOSS_PCT:
                # Ferme au prix de cloture avec slippage
                prix_fill = prix_close * (1 - slip)
                produit = quantite * prix_fill * (1 - frais)
                pnl = produit - (prix_entree * quantite)
                capital_dispo += produit
                trades += 1
                if pnl > 0:
                    gagnes += 1
                    somme_gains += pnl
                else:
                    perdus += 1
                    somme_pertes += abs(pnl)
                quantite = 0.0

        # 3. Genere le signal pour execution a la bougie suivante
        if quantite == 0:
            signal = fonction_strat(i, donnees)
            if signal == "ACHAT":
                signal_en_attente = "ACHAT"
        else:
            signal = fonction_strat(i, donnees)
            if signal == "VENTE":
                signal_en_attente = "VENTE"

        # 4. Suivi drawdown + courbe de capital
        valeur = capital_dispo + quantite * prix_close
        courbe_capital.append(valeur)
        if valeur > valeur_max:
            valeur_max = valeur
        dd = (valeur_max - valeur) / valeur_max * 100 if valeur_max > 0 else 0
        drawdown_max = max(drawdown_max, dd)

    # Ferme la position a la fin si encore ouverte
    if quantite > 0:
        prix = clotures[-1]
        prix_fill = prix * (1 - slip)
        produit = quantite * prix_fill * (1 - frais)
        pnl = produit - (prix_entree * quantite)
        capital_dispo += produit
        trades += 1
        if pnl > 0:
            gagnes += 1
            somme_gains += pnl
        else:
            perdus += 1
            somme_pertes += abs(pnl)
        courbe_capital[-1] = capital_dispo

    # ============================================
    # METRIQUES PRO
    # ============================================
    retour_pct = (capital_dispo - capital) / capital * 100
    win_rate = gagnes / trades * 100 if trades > 0 else 0
    profit_factor = somme_gains / somme_pertes if somme_pertes > 0 else (float("inf") if somme_gains > 0 else 0)
    expectancy = (somme_gains - somme_pertes) / trades if trades > 0 else 0

    # Rendements journaliers pour Sharpe/Sortino
    rendements = []
    for k in range(1, len(courbe_capital)):
        if courbe_capital[k - 1] > 0:
            rendements.append((courbe_capital[k] - courbe_capital[k - 1]) / courbe_capital[k - 1])

    sharpe = 0.0
    sortino = 0.0
    if rendements:
        n = len(rendements)
        moy = sum(rendements) / n
        var = sum((r - moy) ** 2 for r in rendements) / n
        ecart_type = math.sqrt(var)
        # Annualisation: ~252 jours de trading
        if ecart_type > 0:
            sharpe = (moy / ecart_type) * math.sqrt(252)
        # Sortino: ecart-type downside seulement
        downside = [r for r in rendements if r < 0]
        if downside:
            var_down = sum(r ** 2 for r in downside) / n
            ecart_down = math.sqrt(var_down)
            if ecart_down > 0:
                sortino = (moy / ecart_down) * math.sqrt(252)

    # CAGR (annualise)
    nb_jours = len(clotures)
    if nb_jours > 0 and capital_dispo > 0:
        cagr = ((capital_dispo / capital) ** (365.0 / nb_jours) - 1) * 100
    else:
        cagr = 0.0

    # Calmar (CAGR / max drawdown)
    calmar = (cagr / drawdown_max) if drawdown_max > 0 else 0.0

    return {
        "capital_final": round(capital_dispo, 2),
        "retour_pct": round(retour_pct, 2),
        "trades": trades,
        "gagnes": gagnes,
        "perdus": perdus,
        "win_rate": round(win_rate, 1),
        "drawdown_max": round(drawdown_max, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "cagr": round(cagr, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        "expectancy": round(expectancy, 2),
        "frais_effectif_pct": round(frais * 100, 3),
        "slippage_bps": round(slip * 10000, 1),
        "verdict": "GAGNANTE" if retour_pct > 0 else ("PERDANTE" if retour_pct < 0 else "NEUTRE"),
    }

# ============================================
# EXECUTION COMPLETE
# ============================================
def tester_tout(categorie=None):
    resultats = charger_resultats()
    deja_fait = {(r.get("strategie"), r.get("actif")) for r in resultats}

    cats = [categorie] if categorie else list(ACTIFS.keys())
    nb_nouveau = 0

    for cat in cats:
        for actif in ACTIFS.get(cat, []):
            for nom_strat, fonc in STRATEGIES.items():
                if (nom_strat, actif) in deja_fait:
                    continue
                print(f"[{cat}] {actif} x {nom_strat}... ", end="", flush=True)
                bougies = historique_ohlcv(actif, "1d", 365)
                if not bougies or len(bougies) < 60:
                    print("pas assez de donnees")
                    continue
                stats = simuler_pro(bougies, fonc, cat, actif)
                if not stats:
                    print("echec simulation")
                    continue
                entree = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "marche": cat,
                    "actif": actif,
                    "strategie": nom_strat,
                    "bougies": len(bougies),
                    **stats,
                }
                resultats.append(entree)
                sauver_resultats(resultats)
                nb_nouveau += 1
                print(f"{stats['verdict']} | {stats['retour_pct']:+.2f}% | "
                      f"Sh {stats['sharpe']} | PF {stats['profit_factor']} | "
                      f"DD {stats['drawdown_max']:.1f}%")
                time.sleep(0.4)

    print("\n" + "=" * 60)
    print(f"Backtest pro termine. {nb_nouveau} nouveau(x), {len(resultats)} total en base.")
    print("=" * 60)

# ============================================
# COMPARAISON: couts naifs vs couts reels
# ============================================
def comparer():
    """Montre quelles strategies ont change de verdict avec les couts reels."""
    if not os.path.exists(FICHIER_ANCIEN):
        print("Aucun backtest ancien (backtests_reels.json). Lance backtest_moteur.py d'abord.")
        return
    with open(FICHIER_ANCIEN, "r") as f:
        anciens = json.load(f)
    nouveaux = charger_resultats()

    ancien_map = {(r["strategie"], r["actif"]): r for r in anciens}
    nouveau_map = {(r["strategie"], r["actif"]): r for r in nouveaux}

    print("=" * 70)
    print("COMPARAISON: COUTS NAIFS (0.1% fixe) vs COUTS REELS (slippage + maker/taker)")
    print("=" * 70)

    retournements = []  # gagnante -> perdante
    ameliorations = []  # perdante -> gagnante (rare)
    identiques = 0

    for cle, nouveau in nouveau_map.items():
        ancien = ancien_map.get(cle)
        if not ancien:
            continue
        v_ancien = ancien.get("verdict")
        v_nouveau = nouveau["verdict"]
        r_ancien = ancien.get("retour_pct", 0)
        r_nouveau = nouveau["retour_pct"]

        if v_ancien == "GAGNANTE" and v_nouveau == "PERDANTE":
            retournements.append((cle, r_ancien, r_nouveau))
        elif v_ancien == "PERDANTE" and v_nouveau == "GAGNANTE":
            ameliorations.append((cle, r_ancien, r_nouveau))
        elif v_ancien == v_nouveau:
            identiques += 1

    print(f"\nStrategies identiques: {identiques}")
    print(f"Retournements GAGNANTE -> PERDANTE: {len(retournements)}")
    print(f"Ameliorations PERDANTE -> GAGNANTE: {len(ameliorations)}")

    if retournements:
        print("\n--- STRATEGIES QUI NE RESISTENT PAS AUX COUTS REELS ---")
        for (strat, actif), r_old, r_new in sorted(retournements, key=lambda x: x[2] - x[1]):
            print(f"  [{actif}] {strat}: {r_old:+.2f}% -> {r_new:+.2f}% "
                  f"(perte de {r_new - r_old:+.2f} pts)")

    if ameliorations:
        print("\n--- STRATEGIES AMELIOREES PAR COUTS REELS (rare) ---")
        for (strat, actif), r_old, r_new in ameliorations:
            print(f"  [{actif}] {strat}: {r_old:+.2f}% -> {r_new:+.2f}%")

    # Stats globales comparees
    g_ancien = sum(1 for r in anciens if r.get("verdict") == "GAGNANTE")
    g_nouveau = sum(1 for r in nouveaux if r.get("verdict") == "GAGNANTE")
    print("\n" + "-" * 50)
    print(f"Gagnantes (naif):    {g_ancien}/{len(anciens)}")
    print(f"Gagnantes (reel):    {g_nouveau}/{len(nouveaux)}")
    if g_ancien > 0:
        print(f"Chute: {g_ancien - g_nouveau} strat\u00e9gies ne survivent pas aux couts reels")

# ============================================
# AFFICHAGE
# ============================================
def afficher_resultats(meilleurs_seulement=False):
    resultats = charger_resultats()
    if not resultats:
        print("Aucun backtest pro. Lance 'python backtest_pro.py' pour commencer.")
        return

    tries = sorted(resultats, key=lambda r: r.get("retour_pct", 0), reverse=True)
    if meilleurs_seulement:
        tries = [r for r in tries if r.get("verdict") == "GAGNANTE"]

    print("=" * 70)
    titre = "TOP STRATEGIES GAGNANTES (PRO)" if meilleurs_seulement else "RESULTATS BACKTEST PRO"
    print(f"{titre} ({len(tries)} strategies)")
    print("=" * 70)
    for i, r in enumerate(tries[:20], 1):
        print(f"\n{i}. [{r['marche']}] {r['actif']} x {r['strategie']} -> {r['verdict']}")
        print(f"   Retour: {r['retour_pct']:+.2f}% | CAGR: {r['cagr']:.2f}% | Capital: {r['capital_final']} EUR")
        print(f"   Sharpe: {r['sharpe']} | Sortino: {r['sortino']} | Calmar: {r['calmar']}")
        print(f"   Profit factor: {r['profit_factor']} | Expectancy: {r['expectancy']} EUR")
        print(f"   Trades: {r['trades']} ({r['gagnes']}G/{r['perdus']}P, win {r['win_rate']}%) | DD max: {r['drawdown_max']}%")
        print(f"   Cout: frais {r['frais_effectif_pct']}% | slippage {r['slippage_bps']} bps")

    total = len(resultats)
    gagnantes = sum(1 for r in resultats if r.get("verdict") == "GAGNANTE")
    perdantes = sum(1 for r in resultats if r.get("verdict") == "PERDANTE")
    neutres = total - gagnantes - perdantes
    print("\n" + "=" * 70)
    print(f"Stats: {total} tests | {gagnantes} gagnantes | {perdantes} perdantes | {neutres} neutres")
    if total:
        print(f"Win rate global: {gagnantes/total*100:.1f}%")
        # Sharpe moyen des gagnantes
        sharpes = [r["sharpe"] for r in resultats if r.get("verdict") == "GAGNANTE"]
        if sharpes:
            print(f"Sharpe moyen (gagnantes): {sum(sharpes)/len(sharpes):.2f}")

def aide():
    print("""
BACKTEST PRO - PHASE 1 (couts reels + metriques pro)
====================================================
Commandes:
  python backtest_pro.py            Teste toutes les strategies (4 x 21 = 84)
  python backtest_pro.py crypto     Focus sur un marche
  python backtest_pro.py compare     Compare couts naifs vs couts reels
  python backtest_pro.py resultats   Affiche tous les resultats
  python backtest_pro.py meilleurs   Top strategies gagnantes

Ameliorations vs backtest_moteur.py:
  1. Slippage modelise par actif (3 a 50 bps selon liquidite)
  2. Frais maker/taker SEPARES (pas un seul 0.1%)
  3. Maker share 20% + reduction BNB 10% sur crypto
  4. Execution a l'ouverture de la bougie suivante (anti look-ahead)
  5. Metriques pro: Sharpe, Sortino, Calmar, profit factor, CAGR, expectancy

Interpretation des metriques:
  Sharpe > 1.0 = acceptable, > 1.5 = bien, > 2.0 = suspect (overfit)
  Max drawdown < 30% = tol\u00e9rable, > 50% = trop risqu\u00e9
  Profit factor > 1.5 = strategie saine
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "tous"

    print("=" * 60)
    print(f"BACKTEST PRO (Phase 1) - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    resultats = charger_resultats()
    print(f"Backtests pro en base: {len(resultats)}")

    if cmd == "resultats":
        afficher_resultats()
    elif cmd == "meilleurs":
        afficher_resultats(meilleurs_seulement=True)
    elif cmd == "compare":
        comparer()
    elif cmd == "aide":
        aide()
    elif cmd in ACTIFS.keys():
        tester_tout(categorie=cmd)
    else:
        tester_tout()
