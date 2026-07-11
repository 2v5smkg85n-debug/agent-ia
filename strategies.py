#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moteur d'apprentissage de strategies de trading.
- Multi-marches: crypto (priorite), forex, actions, matieres premieres, indices
- APPREND: genere, enregistre, evalue et score les strategies
- Garde en memoire les meilleures strategies (base de connaissances qui grandit)

Usage:
    python strategies.py scan              # analyse tous les marches + genere des strategies
    python strategies.py marche crypto     # focus sur un marche precis
    python strategies.py evaluer           # evalue les strategies passees (win/loss)
    python strategies.py meilleures        # affiche les meilleures strategies apprises
    python strategies.py apprendre         # cycle complet: scan + eval + apprentissage
    python strategies.py journal           # historique complet
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta

from agent import (
    instruction_memoire, lecons_recentes,
    MODELS, disponible, meilleur_defaut, appeler_ia,
    notify_ifft, ajouter
)

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_STRATEGIES = os.path.join(DOSSIER, "strategies.json")
FICHIER_JOURNAL = os.path.join(DOSSIER, "journal_trades.json")

# ============================================
# MARCHES SUPPORTES (crypto en priorite)
# ============================================
MARCHES = {
    "crypto": {
        "symboles": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
        "noms": {"BTCUSDT":"Bitcoin","ETHUSDT":"Ethereum","SOLUSDT":"Solana","BNBUSDT":"BNB","XRPUSDT":"XRP"},
        "source": "binance",
        "description": "Crypto-monnaies (marche 24/7, haute volatilite)"
    },
    "forex": {
        "symboles": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        "noms": {"EUR/USD":"Euro/Dollar","GBP/USD":"Livre/Dollar","USD/JPY":"Dollar/Yen","XAU/USD":"Or"},
        "source": "perplexity",
        "description": "Forex + Or (devises majeures)"
    },
    "actions": {
        "symboles": ["AAPL", "TSLA", "NVDA", "MSFT"],
        "noms": {"AAPL":"Apple","TSLA":"Tesla","NVDA":"Nvidia","MSFT":"Microsoft"},
        "source": "perplexity",
        "description": "Actions US tech"
    },
    "matieres": {
        "symboles": ["PETROLE", "GAZ", "BLE", "CUIVRE"],
        "noms": {"PETROLE":"Petrole Brent","GAZ":"Gaz naturel","BLE":"Ble","CUIVRE":"Cuivre"},
        "source": "perplexity",
        "description": "Matières premieres"
    },
    "indices": {
        "symboles": ["SP500", "NASDAQ", "DAX", "CAC40"],
        "noms": {"SP500":"S&P 500","NASDAQ":"Nasdaq","DAX":"DAX 40","CAC40":"CAC 40"},
        "source": "perplexity",
        "description": "Indices boursiers mondiaux"
    }
}

# ============================================
# STOCKAGE
# ============================================
def charger(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r") as f:
                data = json.load(f)
                # Retourne toujours une liste (compat ancien format dict)
                if isinstance(data, list):
                    return data
                return []
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

def charger_journal():
    return charger(FICHIER_JOURNAL)

def ajouter_journal(entree):
    journal = charger_journal()
    # Si le journal existe dans un ancien format (dict), on convertit en liste
    if isinstance(journal, dict):
        journal = []
    journal.append(entree)
    journal = journal[-100:]  # garde les 100 derniers
    sauver(FICHIER_JOURNAL, journal)

# ============================================
# RECUPERATION PRIX CRYPTO (Binance, gratuit, sans cle)
# ============================================
def prix_binance(symbole):
    """Recupere le prix actuel d'une crypto via l'API publique Binance."""
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbole}", timeout=15)
        d = r.json()
        return {
            "prix": float(d["lastPrice"]),
            "variation24h": float(d["priceChangePercent"]),
            "volume24h": float(d["quoteVolume"]),
            "haut24h": float(d["highPrice"]),
            "bas24h": float(d["lowPrice"])
        }
    except Exception as e:
        return None

def prix_perplexity(symboles, type_marche):
    """Recupere les prix forex/actions/matieres via Perplexity."""
    if not disponible("perplexity"):
        return {}
    liste = ", ".join(symboles)
    prompt = (
        f"Donne les prix actuels en temps reel pour: {liste} ({type_marche}). "
        f"Pour chacun: prix actuel, variation 24h en %. "
        f"Format: SYMBOLE: prix | variation%. Sois precis et concis. Pas de bla-bla."
    )
    try:
        rep, _ = appeler_ia("perplexity", prompt)
        resultats = {}
        for sym in symboles:
            for ligne in rep.split("\n"):
                if sym in ligne and ":" in ligne:
                    resultats[sym] = ligne.strip()[:120]
                    break
        return resultats
    except:
        return {}

def recuperer_donnees_marche(categorie):
    """Recupere les donnees de prix pour une categorie de marche."""
    config = MARCHES[categorie]
    donnees = {}
    if config["source"] == "binance":
        for sym in config["symboles"]:
            print(f"    {sym}...", end=" ", flush=True)
            d = prix_binance(sym)
            if d:
                donnees[sym] = d
                print(f"{d['prix']:.2f} ({d['variation24h']:+.2f}%)")
            else:
                print("echec")
            time.sleep(0.3)
    else:
        print(f"    via Perplexity...", end=" ", flush=True)
        donnees = prix_perplexity(config["symboles"], config["description"])
        print("OK" if donnees else "echec")
    return donnees

# ============================================
# GENERATION DE STRATEGIES (avec IA)
# ============================================
def top_strategies_apprises(categorie=None, n=3):
    """Retourne les meilleures strategies apprises pour inspire de nouvelles."""
    strategies = charger_strategies()
    # Filtre par categorie si specifie
    if categorie:
        strategies = [s for s in strategies if s.get("marche") == categorie]
    # Trie par score (win rate)
    avec_score = [s for s in strategies if s.get("evaluations", 0) > 0]
    avec_score.sort(key=lambda x: x.get("win_rate", 0), reverse=True)
    return avec_score[:n]

def generer_strategie(categorie, donnees):
    """L'IA genere une strategie adaptee au marche actuel."""
    config = MARCHES[categorie]
    memoire = instruction_memoire()
    lecons = lecons_recentes()
    top = top_strategies_apprises(categorie, 2)

    # Formate les donnees de marche
    if config["source"] == "binance":
        marche_texte = "\n".join(
            f"- {config['noms'].get(s,s)} ({s}): {d['prix']:.2f}$, var 24h: {d['variation24h']:+.2f}%, haut: {d['haut24h']:.2f}, bas: {d['bas24h']:.2f}, vol: {d['volume24h']:.0f}$"
            for s,d in donnees.items()
        )
    else:
        marche_texte = "\n".join(f"- {k}: {v}" for k,v in donnees.items())

    top_texte = ""
    if top:
        top_texte = "\nSTRATEGIES QUI ONT BIEN MARCHE AVANT (inspire-t-en):\n" + "\n".join(
            f"- {s.get('type','?')}: {s.get('regles','?')[:100]} (win rate: {s.get('win_rate',0):.0%})"
            for s in top
        ) + "\n"

    prompt = (
        f"Tu es un trader algorithmique expert. Genere UNE strategie de trading concrete et actionnable.\n\n"
        f"MARCHE: {categorie.upper()} - {config['description']}\n"
        f"DONNEES ACTUELLES:\n{marche_texte}\n\n"
        f"{memoire}{lecons}{top_texte}"
        f"Format de reponse OBLIGATOIRE:\n"
        f"TYPE: [ex: grid trading, breakout, mean reversion, trend following, DCA, arbitrage]\n"
        f"ENTREE: [condition precise d'achat, avec seuils chiffrés]\n"
        f"SORTIE: [condition de vente + stop-loss]\n"
        f"GESTION RISQUE: [taille position, max loss]\n"
        f"RAISONNEMENT: [2-3 lignes pourquoi cette strategie maintenant]\n"
        f"CONFIANCE: [1-10]\n"
        f"Sois precis et realiste. Pas de conseil financier genérique."
    )
    ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else meilleur_defaut())
    print(f"    generation via {ia}...", end=" ", flush=True)
    try:
        rep, modele = appeler_ia(ia, prompt)
        if rep.startswith("[Erreur"):
            print("echec")
            return None
        print("OK")
        return {"contenu": rep, "modele": modele, "marche": categorie, "ia": ia}
    except Exception as e:
        print(f"erreur: {e}")
        return None

# ============================================
# EVALUATION DES STRATEGIES PASSEES
# ============================================
def evaluer_strategies():
    """Re-evalue les strategies non encore evaluees (simulee sur donnees recentes)."""
    strategies = charger_strategies()
    non_evaluees = [s for s in strategies if not s.get("evaluee")]
    if not non_evaluees:
        print("Toutes les strategies ont deja ete evaluees.")
        return

    print(f"{len(non_evaluees)} strategie(s) a evaluer...")
    ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else meilleur_defaut())

    for strat in non_evaluees[-5:]:  # max 5 par cycle
        print(f"  -> Evaluation strategie {strat['marche']}...", end=" ", flush=True)
        # Recupere donnees recentes du marche
        cat = strat["marche"]
        if cat in MARCHES:
            donnees = recuperer_donnees_marche(cat)
        else:
            donnees = {}

        prompt = (
            f"Tu evalues une strategie de trading generee il y a quelques jours.\n\n"
            f"STRATEGIE:\n{strat.get('contenu','')[:600]}\n\n"
            f"DONNEES ACTUELLES DU MARCHE ({cat}):\n{json.dumps(donnees, ensure_ascii=False)[:400]}\n\n"
            f"Evalue: cette strategie aurait-elle ete gagnante ou perdante entre sa creation et maintenant? "
            f"Reponds en 2 lignes:\n"
            f"RESULTAT: [GAGNE/PERDU/NEUTRE]\n"
            f"POURQUOI: [1 phrase]\n"
        )
        try:
            rep, _ = appeler_ia(ia, prompt)
            if "GAGNE" in rep.upper():
                strat["resultat"] = "gagne"
                strat["evaluee"] = True
                strat["evaluations"] = strat.get("evaluations", 0) + 1
                strat["gagnes"] = strat.get("gagnes", 0) + 1
                print("GAGNE")
            elif "PERDU" in rep.upper():
                strat["resultat"] = "perdu"
                strat["evaluee"] = True
                strat["evaluations"] = strat.get("evaluations", 0) + 1
                print("PERDU")
            else:
                strat["resultat"] = "neutre"
                strat["evaluee"] = True
                strat["evaluations"] = strat.get("evaluations", 0) + 1
                print("NEUTRE")
            strat["raison_eval"] = rep[:300]
            # Recalcule win rate
            evals = strat.get("evaluations", 0)
            gains = strat.get("gagnes", 0)
            strat["win_rate"] = gains / evals if evals else 0
        except Exception as e:
            print(f"erreur: {e}")
        time.sleep(2)

    sauver_strategies(strategies)
    print("Evaluation terminee.")

# ============================================
# CYCLE D'APPRENTISSAGE
# ============================================
def scan_complet(categorie=None):
    """Scan tous les marches + genere des strategies."""
    categories = [categorie] if categorie else list(MARCHES.keys())
    strategies = charger_strategies()
    total_cats = len(categories)
    debut = time.time()

    for idx, cat in enumerate(categories, 1):
        elapsed = time.time() - debut
        if idx > 1:
            moy_par_marche = elapsed / (idx - 1)
            reste = moy_par_marche * (total_cats - idx + 1)
            print(f"\n[Progression {idx}/{total_cats}] Temps ecoule: {int(elapsed)}s | Reste estime: ~{int(reste)}s ({int(reste/60)}min{int(reste%60)}s)")
        else:
            print(f"\n[Progression {idx}/{total_cats}] Demarrage...")
        print(f"=== {cat.upper()} ===")
        config = MARCHES[cat]
        print(f"Recuperation des prix...")
        donnees = recuperer_donnees_marche(cat)
        if not donnees:
            print(f"Pas de donnees pour {cat}, skip.")
            continue
        print(f"Generation de strategie...")
        strat = generer_strategie(cat, donnees)
        if strat:
            strat["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            strat["evaluee"] = False
            strategies.append(strat)
            ajouter_journal({
                "date": strat["date"],
                "type": "generation",
                "marche": cat,
                "strategie": strat["contenu"][:200]
            })
            print(f"\n--- Strategie generee ({cat}) ---")
            print(strat["contenu"][:600])
            print("-"*50)
        # Sauvegarde au fur et a mesure (pour ne rien perdre si coupure)
        strategies = strategies[-50:]
        sauver_strategies(strategies)
        time.sleep(1)

    print(f"\nTotal strategies stockees: {len(strategies)}")

def afficher_meilleures():
    """Affiche les meilleures strategies apprises."""
    strategies = charger_strategies()
    evaluees = [s for s in strategies if s.get("evaluations", 0) > 0]
    if not evaluees:
        print("Aucune strategie evaluee pour le moment.")
        print("Lance 'python strategies.py evaluer' pour evaluer les strategies passees.")
        return
    evaluees.sort(key=lambda x: x.get("win_rate", 0), reverse=True)
    print("="*55)
    print("MEILLEURES STRATEGIES APPRISES")
    print("="*55)
    for i, s in enumerate(evaluees[:5], 1):
        print(f"\n{i}. [{s['marche'].upper()}] Win rate: {s.get('win_rate',0):.0%} ({s.get('gagnes',0)}/{s.get('evaluations',0)})")
        print(f"   Date: {s.get('date','?')}")
        print(f"   {s.get('contenu','')[:300]}")
    print("="*55)

def afficher_journal():
    journal = charger_journal()
    if not journal:
        print("Journal vide.")
        return
    print("="*55)
    print(f"JOURNAL DE TRADING ({len(journal)} entrees)")
    print("="*55)
    for e in journal[-15:]:
        print(f"\n[{e['date']}] {e.get('type','?').upper()} - {e.get('marche','?')}")
        print(f"  {e.get('strategie','')[:150]}")
    print("="*55)

# ============================================
# MENU PRINCIPAL
# ============================================
def aide():
    print("""
MOTEUR D'APPRENTISSAGE DE STRATEGIES - Aide
===========================================
Commandes:
  python strategies.py scan           Analyse tous les marches + genere des strategies
  python strategies.py marche crypto   Focus sur un marche (crypto/forex/actions/matieres/indices)
  python strategies.py evaluer         Evalue les strategies passees (gagne/perdu)
  python strategies.py meilleures      Affiche les meilleures strategies apprises
  python strategies.py apprendre       Cycle complet: scan + evaluer
  python strategies.py journal          Historique des actions
  python strategies.py aide            Cette aide

Marches supportes: crypto (priorite), forex, actions, matieres, indices
L'agent apprend: chaque strategie est evaluee, les meilleures sont reutilisees
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "aide"

    print("="*55)
    print(f"MOTEUR STRATEGIES - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*55)
    ias = [n for n in ["perplexity","gemini","claude","chatgpt"] if disponible(n)]
    print(f"IA: {', '.join(ias)}")
    print(f"Strategies stockees: {len(charger_strategies())}")

    if cmd == "scan":
        scan_complet()
    elif cmd == "marche" and len(args) > 1:
        cat = args[1].lower()
        if cat not in MARCHES:
            print(f"Marche inconnu. Choix: {', '.join(MARCHES.keys())}")
        else:
            scan_complet(cat)
    elif cmd == "evaluer":
        evaluer_strategies()
    elif cmd == "meilleures":
        afficher_meilleures()
    elif cmd == "apprendre":
        print("\n[1/2] Scan + generation de strategies...")
        scan_complet()
        print("\n[2/2] Evaluation des strategies passees...")
        evaluer_strategies()
        print("\n--- Synthese ---")
        afficher_meilleures()
        # Apprend le contexte
        ajouter("apprentissages", f"Cycle apprentissage trading {datetime.now().strftime('%d/%m')}")
    elif cmd == "journal":
        afficher_journal()
    else:
        aide()
