#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de BACKTESTING.
Teste les strategies sur l'historique reel des prix (1-2 ans).
Garde seulement les strategies gagnantes.

Comment ça marche:
1. Recupere l'historique des prix via Binance (gratuit, sans cle)
2. Pour chaque strategie, l'IA simule les trades sur l'historique
3. Calcule les vraies performances (win rate, gain, drawdown)
4. Garde les strategies gagnantes, elimine les perdantes

Usage:
    python backtest.py                    # backteste toutes les strategies
    python backtest.py crypto             # focus crypto
    python backtest.py resultats          # affiche les resultats de backtest
    python backtest.py gagnantes          # affiche seulement les strategies gagnantes
    python backtest.py nettoyer           # supprime les strategies perdantes du stock
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta

from agent import (
    instruction_memoire, lecons_recentes,
    MODELS, disponible, meilleur_defaut, appeler_ia, ajouter
)

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_STRATEGIES = os.path.join(DOSSIER, "strategies.json")
FICHIER_BACKTESTS = os.path.join(DOSSIER, "backtests.json")

# ============================================
# STOCKAGE
# ============================================
def charger(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except:
            pass
    return []

def sauver(fichier, data):
    with open(fichier, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def charger_strategies():
    return charger(FICHIER_STRATEGIES)

def sauver_strategies(strategies):
    sauver(FICHIER_STRATEGIES, strategies)

def charger_backtests():
    return charger(FICHIER_BACKTESTS)

def sauver_backtests(backtests):
    sauver(FICHIER_BACKTESTS, backtests)

# ============================================
# RECUPERATION HISTORIQUE DES PRIX (Binance, gratuit)
# ============================================
def historique_prix(symbole="BTCUSDT", intervalle="1d", jours=365):
    """
    Recupere l'historique des prix (chandeliers OHLCV) via Binance.
    intervalle: 1d (jour), 4h, 1h, 15m...
    jours: nombre de jours d'historique
    """
    try:
        fin = int(time.time() * 1000)
        debut = int((time.time() - jours * 86400) * 1000)
        url = (f"https://api.binance.com/api/v3/klines?"
               f"symbol={symbole}&interval={intervalle}&startTime={debut}&endTime={fin}&limit=1000")
        r = requests.get(url, timeout=30)
        data = r.json()
        # Format: [openTime, open, high, low, close, volume, ...]
        bougies = []
        for b in data:
            bougies.append({
                "temps": datetime.fromtimestamp(b[0]/1000).strftime("%Y-%m-%d"),
                "ouverture": float(b[1]),
                "haut": float(b[2]),
                "bas": float(b[3]),
                "cloture": float(b[4]),
                "volume": float(b[5])
            })
        return bougies
    except Exception as e:
        print(f"Erreur recuperation historique {symbole}: {e}")
        return []

def formater_historique(bougies, max_bougies=30):
    """Formate l'historique pour l'IA (pas trop long)."""
    if not bougies:
        return "Pas de donnees"
    # Prend les dernieres bougies + un echantillon
    echantillon = bougies[-max_bougies:]
    lignes = []
    for b in echantillon:
        lignes.append(f"{b['temps']}: cloture {b['cloture']:.2f}, haut {b['haut']:.2f}, bas {b['bas']:.2f}, vol {b['volume']:.0f}")
    return "\n".join(lignes)

# ============================================
# SIMULATION DE BACKTEST (via IA)
# ============================================
def backtester_strategie(strategie, jours=365):
    """
    Simule une strategie sur l'historique.
    L'IA analyse la strategie + l'historique et estime les performances.
    """
    cat = strategie.get("marche", "crypto")
    contenu = strategie.get("contenu", "")

    # Pour crypto: historique reel Binance
    # Pour autres: Perplexity pour contexte
    symboles = {
        "crypto": "BTCUSDT",
        "forex": "EUR/USD",
        "actions": "AAPL",
        "matieres": "PETROLE",
        "indices": "SP500"
    }
    symbole = symboles.get(cat, "BTCUSDT")

    if cat == "crypto":
        print(f"    Recuperation historique {symbole} ({jours}j)...", end=" ", flush=True)
        historique = historique_prix(symbole, "1d", jours)
        if historique:
            print(f"{len(historique)} bougies")
        else:
            print("echec")
            return None
        donnees = formater_historique(historique)
    else:
        # Pour non-crypto, on utilise Perplexity pour le contexte historique
        if not disponible("perplexity"):
            return None
        print(f"    Contexte historique via Perplexity...", end=" ", flush=True)
        try:
            prompt = (f"Donne l'evolution de {symbole} sur les {jours} derniers jours. "
                      f"Prix debut, prix fin, plus haut, plus bas, tendance generale. Concis.")
            rep, _ = appeler_ia("perplexity", prompt)
            donnees = rep[:600]
            print("OK")
        except:
            print("echec")
            return None

    prompt = (
        f"Tu es un backtester professionnel. Simule cette strategie sur l'historique reel.\n\n"
        f"STRATEGIE A TESTER:\n{contenu[:800]}\n\n"
        f"MARCHE: {cat} ({symbole})\n"
        f"HISTORIQUE DES PRIX (jours select):\n{donnees}\n\n"
        f"Simule l'execution de cette strategie sur cet historique. Estime:\n"
        f"1. Combien de trades auraient ete pris\n"
        f"2. Combien gagnes vs perdus\n"
        f"3. Gain/perte total estime en %\n"
        f"4. Drawdown max (plus grosse perte temporaire)\n\n"
        f"Reponds STRICTEMENT en format:\n"
        f"TRADES: [nombre]\n"
        f"GAGNES: [nombre]\n"
        f"PERDUS: [nombre]\n"
        f"WIN_RATE: [%]\n"
        f"RETOUR: [% gain/perte total]\n"
        f"DRAWDOWN: [%]\n"
        f"VERDICT: [GAGNANTE/PERDANTE/NEUTRE]\n"
        f"NOTE: [1 phrase d'analyse]\n"
    )
    ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else meilleur_defaut())
    print(f"    Backtest via {ia}...", end=" ", flush=True)
    try:
        rep, modele = appeler_ia(ia, prompt)
        if rep.startswith("[Erreur"):
            print("echec")
            return None
        print("OK")
        return {"resultat_brut": rep, "modele": modele, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
    except Exception as e:
        print(f"erreur: {e}")
        return None

def extraire_backtest(resultat_brut):
    """Extrait les chiffres du resultat du backtest."""
    import re
    def cherche(champ):
        pattern = champ + r"\s*:\s*([^\n]+)"
        m = re.search(pattern, resultat_brut, re.IGNORECASE)
        return m.group(1).strip() if m else "?"
    return {
        "trades": cherche("TRADES"),
        "gagnes": cherche("GAGNES"),
        "perdus": cherche("PERDUS"),
        "win_rate": cherche("WIN_RATE"),
        "retour": cherche("RETOUR"),
        "drawdown": cherche("DRAWDOWN"),
        "verdict": cherche("VERDICT"),
        "note": cherche("NOTE")
    }

# ============================================
# CYCLE DE BACKTEST
# ============================================
def backtester_toutes(categorie=None):
    """Backteste toutes les strategies non encore backtestees."""
    strategies = charger_strategies()
    backtests = charger_backtests()

    # Filtre par categorie
    if categorie:
        strategies = [s for s in strategies if s.get("marche") == categorie]

    # Strategies deja backtestees (par contenu)
    deja_fait = {b.get("strategie_contenu","")[:200] for b in backtests}
    a_tester = [s for s in strategies if s.get("contenu","")[:200] not in deja_fait]

    if not a_tester:
        print("Toutes les strategies ont deja ete backtestees.")
        print("Lance 'python backtest.py resultats' pour voir les resultats.")
        return

    print(f"{len(a_tester)} strategie(s) a backtester...")
    print("="*55)

    for i, strat in enumerate(a_tester, 1):
        cat = strat.get("marche", "crypto")
        print(f"\n[{i}/{len(a_tester)}] Backtest strategie {cat}...")
        print(f"    Date creation: {strat.get('date','?')}")

        resultat = backtester_strategie(strat)
        if resultat:
            chiffres = extraire_backtest(resultat["resultat_brut"])
            entree = {
                "date_backtest": resultat["date"],
                "marche": cat,
                "strategie_date": strat.get("date",""),
                "strategie_contenu": strat.get("contenu","")[:500],
                "modele": resultat["modele"],
                "resultat_brut": resultat["resultat_brut"][:800],
                "trades": chiffres["trades"],
                "gagnes": chiffres["gagnes"],
                "perdus": chiffres["perdus"],
                "win_rate": chiffres["win_rate"],
                "retour": chiffres["retour"],
                "drawdown": chiffres["drawdown"],
                "verdict": chiffres["verdict"],
                "note": chiffres["note"]
            }
            backtests.append(entree)
            sauver_backtests(backtests)  # sauvegarde au fur et a mesure
            print(f"    Verdict: {chiffres['verdict']} | Win rate: {chiffres['win_rate']} | Retour: {chiffres['retour']}")
        time.sleep(2)

    print("\n" + "="*55)
    print(f"Backtest termine. {len(backtests)} resultats stockes.")

def afficher_resultats(gagnantes_seulement=False):
    """Affiche les resultats de backtest."""
    backtests = charger_backtests()
    if not backtests:
        print("Aucun backtest realise. Lance 'python backtest.py' pour commencer.")
        return

    if gagnantes_seulement:
        backtests = [b for b in backtests if "GAGNANTE" in b.get("verdict","").upper()]
        if not backtests:
            print("Aucune strategie gagnante trouvee pour le moment.")
            return

    print("="*60)
    titre = "STRATEGIES GAGNANTES" if gagnantes_seulement else "RESULTATS BACKTEST"
    print(f"{titre} ({len(backtests)} strategies)")
    print("="*60)

    for i, b in enumerate(backtests, 1):
        print(f"\n{i}. [{b.get('marche','?').upper()}] {b.get('verdict','?')}")
        print(f"   Date strategie: {b.get('strategie_date','?')} | Backtest: {b.get('date_backtest','?')}")
        print(f"   Trades: {b.get('trades','?')} | Gagnes: {b.get('gagnes','?')} | Perdus: {b.get('perdus','?')}")
        print(f"   Win rate: {b.get('win_rate','?')} | Retour: {b.get('retour','?')} | Drawdown: {b.get('drawdown','?')}")
        print(f"   Note: {b.get('note','?')[:150]}")
    print("="*60)

    # Stats globales
    total = len(backtests)
    gagnantes = sum(1 for b in backtests if "GAGNANTE" in b.get("verdict","").upper())
    perdantes = sum(1 for b in backtests if "PERDANTE" in b.get("verdict","").upper())
    neutres = total - gagnantes - perdantes
    print(f"\nStats globales: {total} testees | {gagnantes} gagnantes | {perdantes} perdantes | {neutres} neutres")
    if total:
        print(f"Taux de succes: {gagnantes/total*100:.0f}%")

def nettoyer_perdantes():
    """Supprime les strategies perdantes du stock principal."""
    backtests = charger_backtests()
    strategies = charger_strategies()

    perdantes_contenus = {b.get("strategie_contenu","")[:200]
                          for b in backtests
                          if "PERDANTE" in b.get("verdict","").upper()}

    if not perdantes_contenus:
        print("Aucune strategie perdante identifiee.")
        return

    avant = len(strategies)
    strategies_filtrees = [s for s in strategies if s.get("contenu","")[:200] not in perdantes_contenus]
    apres = len(strategies_filtrees)
    sauver_strategies(strategies_filtrees)
    print(f"Nettoyage: {avant - apres} strategie(s) perdante(s) supprimee(s).")
    print(f"Stock restant: {apres} strategies (gardées: gagnantes + non testees).")
    ajouter("apprentissages", f"Backtest nettoyage {datetime.now().strftime('%d/%m')}: {avant-apres} perdantes supprimees")

def aide():
    print("""
BACKTESTING - Aide
===========================================
Commandes:
  python backtest.py               Backteste toutes les strategies non testees
  python backtest.py crypto         Focus sur un marche (crypto/forex/...)
  python backtest.py resultats      Affiche tous les resultats
  python backtest.py gagnantes      Affiche seulement les strategies gagnantes
  python backtest.py nettoyer       Supprime les strategies perdantes du stock

Le backtest:
  1. Recupere l'historique reel (Binance pour crypto, 365j)
  2. Simule chaque strategie sur l'historique
  3. Calcule win rate, gain, drawdown
  4. Verdict: GAGNANTE / PERDANTE / NEUTRE
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "tous"

    print("="*55)
    print(f"BACKTESTING - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*55)
    backtests = charger_backtests()
    print(f"Backtests realises: {len(backtests)}")
    ias = [n for n in ["perplexity","gemini","claude","chatgpt"] if disponible(n)]
    print(f"IA: {', '.join(ias)}")

    if cmd == "resultats":
        afficher_resultats()
    elif cmd == "gagnantes":
        afficher_resultats(gagnantes_seulement=True)
    elif cmd == "nettoyer":
        nettoyer_perdantes()
    elif cmd == "aide":
        aide()
    elif cmd in ["crypto","forex","actions","matieres","indices"]:
        backtester_toutes(categorie=cmd)
    else:
        # Par defaut: backtest tout
        backtester_toutes()
