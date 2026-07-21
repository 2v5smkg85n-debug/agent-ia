#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PAPER TRADING MULTI-MARCHES - Simulation en direct sur tous les marches.
Crypto + Forex + Actions + Matieres premieres + Indices.

Capital virtuel: 1000 EUR
Sources de prix:
  - Crypto: Binance (gratuit, temps reel)
  - Actions/Indices/Forex: Yahoo Finance (gratuit)
  - Fallback: Perplexity

Usage:
    python paper_trading.py init          # initialise le portefeuille (1000 EUR)
    python paper_trading.py tick          # 1 cycle: verifie prix + signaux
    python paper_trading.py solde         # portefeuille + performance
    python paper_trading.py positions     # positions ouvertes
    python paper_trading.py historique    # trades fermes
    python paper_trading.py boucle        # tourne en continu (30 min)
    python paper_trading.py reset         # reinitialise
"""
import os
import sys
import json
import time
import re
import signal
import requests
from datetime import datetime, timedelta

from agent import disponible, appeler_ia, notify_ifft, ajouter
from backtest import charger_backtests
try:
    from indicateurs import analyser_actif
    INDICATEURS_DISPONIBLES = True
except ImportError:
    INDICATEURS_DISPONIBLES = False

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")

# ============================================
# CONFIGURATION
# ============================================
CAPITAL_INITIAL = 1000.0
FRAIS_TRANSACTION = 0.001       # 0.1% par cote (aller = 0.1%, retour = 0.1% => 0.2% aller-retour)
MAX_POSITIONS = 5               # 5 positions (plus de diversification)
RISK_PAR_TRADE = 0.20           # 20% du capital par trade (200 EUR) [fallback]
INTERVALLE_BOUCLE = 1800       # 30 min (anti-churn : avant 15 min = trop de trades -> frais)
# Seuilles serres pour trading actif (prise de benefice frequente)
TAKE_PROFIT_PCT = 1.5           # +1.5% -> encaisse le benefice
STOP_LOSS_PCT = 1.5             # -1.5% -> coupe la perte
# EXTEND_TP (backtest +13.35% sur crypto): monte le TP quand la position crypto
# est en profit, pour laisser courir les gagnants. SL fixe (pas de breakeven).
# Idee utilisateur + valide par backtest elargi (9 marches, 30 trades, plateau a tp_ext=4).
EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"}
EXTEND_SEUIL = 0.5        # active l'extension a partir de +0.5% de gain
EXTEND_TP_PCT = 4.0       # TP monte (2.0% -> 4.0%) une fois en profit
EXTEND_DUREE_MAX = 480    # cap duree des positions extended (8h, vs 90min normal)
SORTIE_DUREE_MIN = 90           # ferme apres 90 min si en gain suffisant (avant 45 -> trop court)
# Seuil de gain minimum pour fermer par duree : doit couvrir les frais (0.2% AR) + une marge.
# Fermer a +0.05% = perte nette (frais 0.2%). Donc on n'accepte que gain >= 0.30%.
SEUIL_BENEFICE_MIN = 0.30       # 0.30% : couvre les 0.2% de frais + 0.1% de marge nette

# ============================================
# TOUS LES MARCHES (symboles pour Yahoo Finance / Binance)
# ============================================
MARCHES_PAPER = {
    # Crypto (Binance)
    "BTCUSDT": {"nom": "Bitcoin", "marche": "crypto", "source": "binance"},
    "ETHUSDT": {"nom": "Ethereum", "marche": "crypto", "source": "binance"},
    "SOLUSDT": {"nom": "Solana", "marche": "crypto", "source": "binance"},
    "BNBUSDT": {"nom": "BNB", "marche": "crypto", "source": "binance"},
    "XRPUSDT": {"nom": "XRP", "marche": "crypto", "source": "binance"},
    "LDOUSDT": {"nom": "Lido DAO", "marche": "crypto", "source": "binance"},
    "AAVEUSDT": {"nom": "Aave", "marche": "crypto", "source": "binance"},
    "UNIUSDT": {"nom": "Uniswap", "marche": "crypto", "source": "binance"},
    "PENDLEUSDT": {"nom": "Pendle", "marche": "crypto", "source": "binance"},
    "ARBUSDT": {"nom": "Arbitrum", "marche": "crypto", "source": "binance"},
    # Forex (Yahoo)
    "EURUSD=X": {"nom": "EUR/USD", "marche": "forex", "source": "yahoo"},
    "GBPUSD=X": {"nom": "GBP/USD", "marche": "forex", "source": "yahoo"},
    "JPY=X": {"nom": "USD/JPY", "marche": "forex", "source": "yahoo"},
    "GC=F": {"nom": "Or", "marche": "forex", "source": "yahoo"},
    # Actions (Yahoo)
    "AAPL": {"nom": "Apple", "marche": "actions", "source": "yahoo"},
    "TSLA": {"nom": "Tesla", "marche": "actions", "source": "yahoo"},
    "NVDA": {"nom": "Nvidia", "marche": "actions", "source": "yahoo"},
    "MSFT": {"nom": "Microsoft", "marche": "actions", "source": "yahoo"},
    # Matieres premieres (Yahoo)
    "BZ=F": {"nom": "Petrole Brent", "marche": "matieres", "source": "yahoo"},
    "NG=F": {"nom": "Gaz naturel", "marche": "matieres", "source": "yahoo"},
    "HG=F": {"nom": "Cuivre", "marche": "matieres", "source": "yahoo"},
    "ZW=F": {"nom": "Ble", "marche": "matieres", "source": "yahoo"},
    # Indices (Yahoo)
    "^GSPC": {"nom": "S&P 500", "marche": "indices", "source": "yahoo"},
    "^IXIC": {"nom": "Nasdaq", "marche": "indices", "source": "yahoo"},
    "^GDAXI": {"nom": "DAX", "marche": "indices", "source": "yahoo"},
    "^FCHI": {"nom": "CAC 40", "marche": "indices", "source": "yahoo"},
}

# ============================================
# STOCKAGE PORTEFEUILLE
# ============================================
def charger_portefeuille():
    if os.path.exists(FICHIER_PAPER):
        try:
            with open(FICHIER_PAPER, "r") as f:
                pf = json.load(f)
            # Migration Phase 2: ajoute les champs manquants sur les anciens portefeuilles
            if "pic_capital" not in pf:
                pf["pic_capital"] = pf.get("capital_initial", CAPITAL_INITIAL)
            if "trades_fermes" not in pf:
                pf["trades_fermes"] = []
            return pf
        except:
            pass
    return None

def sauver_portefeuille(pf):
    with open(FICHIER_PAPER, "w") as f:
        json.dump(pf, f, ensure_ascii=False, indent=2)

def initialiser():
    pf = {
        "capital_initial": CAPITAL_INITIAL,
        "liquidites": CAPITAL_INITIAL,
        "positions": [],
        "historique": [],
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dernier_tick": None,
        "total_frais": 0.0,
        "pic_capital": CAPITAL_INITIAL,
        "trades_fermes": []
    }
    sauver_portefeuille(pf)
    print(f"Portefeuille paper trading initialise.")
    print(f"  Capital initial: {CAPITAL_INITIAL} EUR (virtuel)")
    print(f"  Frais par transaction: {FRAIS_TRANSACTION*100}% (aller-retour 0.2%)")
    print(f"  Max positions: {MAX_POSITIONS}")
    print(f"  Intervalle boucle: {INTERVALLE_BOUCLE//60} min (anti-churn)")
    print(f"  Take-profit: +{TAKE_PROFIT_PCT}% | Stop-loss: -{STOP_LOSS_PCT}%")
    print(f"  Sortie par duree: {SORTIE_DUREE_MIN} min SEULEMENT si gain >= {SEUIL_BENEFICE_MIN}%")
    print(f"  Risk par trade: dynamique (Kelly fractionnaire, voir gestion_risque.py)")
    marches = set(m["marche"] for m in MARCHES_PAPER.values())
    print(f"  Marches: {', '.join(marches)}")
    print(f"  Symboles suivis: {len(MARCHES_PAPER)}")

# ============================================
# RECUPERATION PRIX MULTI-SOURCES
# ============================================
def prix_binance(symbole):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbole}", timeout=10)
        return float(r.json()["price"])
    except:
        return None

def prix_yahoo(symbole):
    """Recupere le prix via Yahoo Finance (gratuit, sans cle)."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbole}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        prix = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(prix)
    except:
        return None

def prix_perplexity_fallback(symboles_noms):
    """Fallback: demande les prix a Perplexity."""
    if not disponible("perplexity"):
        return {}
    liste = ", ".join(symboles_noms.values())
    prompt = (f"Donne les prix actuels pour: {liste}. "
              f"Format: NOM: prix. Sois precis et concis.")
    try:
        rep, _ = appeler_ia("perplexity", prompt)
        resultats = {}
        for sym, nom in symboles_noms.items():
            # Cherche le prix dans la reponse
            for ligne in rep.split("\n"):
                if nom.lower() in ligne.lower() or sym.lower() in ligne.lower():
                    nombres = re.findall(r"\d+[.,]?\d*", ligne.replace(",", "."))
                    for n in nombres:
                        try:
                            val = float(n)
                            if val > 0:
                                resultats[sym] = val
                                break
                        except:
                            pass
                    if sym in resultats:
                        break
        return resultats
    except:
        return {}

def tous_les_prix():
    """Recupere tous les prix depuis toutes les sources."""
    prix = {}
    prix_par_source = {"binance": [], "yahoo": []}
    # Groupe par source
    for sym, config in MARCHES_PAPER.items():
        prix_par_source[config["source"]].append(sym)

    # Crypto via Binance
    for sym in prix_par_source["binance"]:
        p = prix_binance(sym)
        if p:
            prix[sym] = p
        time.sleep(0.2)

    # Actions/Forex/Indices/Matieres via Yahoo
    for sym in prix_par_source["yahoo"]:
        p = prix_yahoo(sym)
        if p:
            prix[sym] = p
        time.sleep(0.3)  # Yahoo peut bloquer si trop rapide

    # Fallback pour les manquants
    manquants = {s: MARCHES_PAPER[s]["nom"] for s in MARCHES_PAPER if s not in prix}
    if manquants and disponible("perplexity"):
        print(f"  [Fallback Perplexity pour {len(manquants)} symboles...]")
        prix_fallback = prix_perplexity_fallback(manquants)
        prix.update(prix_fallback)

    return prix

# ============================================
# STRATEGIES GAGNANTES (tous marches)
# ============================================
def strategies_gagnantes():
    backtests = charger_backtests()
    return [b for b in backtests if "GAGNANTE" in b.get("verdict","").upper()]

# ============================================
# ANALYSE DES SIGNAUX
# ============================================
def analyser_signaux_techniques(prix_actuels):
    """Analyse TOUS les marches avec les VRAIS indicateurs techniques (pas l'IA).
    Crypto (Binance) + Forex/Actions/Indices/Matieres (Yahoo Finance)."""
    if not INDICATEURS_DISPONIBLES:
        return []
    signaux = []
    # Analyse tous les marches disposes dans MARCHES_PAPER (crypto ET non-crypto)
    for sym, config in MARCHES_PAPER.items():
        if sym not in prix_actuels:
            continue
        print(f"    Indicateurs {config['nom']}...", end=" ", flush=True)
        try:
            analyse = analyser_actif(sym, "1h")
            if not analyse:
                print("echec")
                continue
            verdict = analyse["verdict"]
            score = analyse["score"]
            print(f"{verdict} (score {score:+d})")
            # Signal d'achat si score >= 1 (ACHAT) ou score == 1 (ACHAT FAIBLE)
            if score >= 1:
                signaux.append({
                    "symbole": sym,
                    "prix_entree": prix_actuels[sym],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "indicateurs",
                    "score": score,
                    "raison": "; ".join(analyse["signaux"][:2])
                })
        except Exception as e:
            print(f"erreur: {e}")
        time.sleep(0.3)
    return signaux

def analyser_signaux_ia(prix_actuels):
    """Fallback: analyse via IA pour les marches non-crypto (actions, forex, etc.)."""
    gagnantes = strategies_gagnantes()
    if not gagnantes:
        return []
    # Garde seulement les marches non-crypto (crypto = indicateurs)
    prix_non_crypto = {s: p for s, p in prix_actuels.items()
                       if MARCHES_PAPER.get(s, {}).get("marche") != "crypto"}
    if not prix_non_crypto:
        return []
    prix_texte = "\n".join(f"- {MARCHES_PAPER.get(s,{}).get('nom',s)} ({s}): {p:.2f}"
                          for s,p in prix_non_crypto.items())
    strat_texte = "\n".join(f"--- Strategie {i+1} [{g.get('marche','?')}] ---\n{g.get('strategie_contenu','')[:300]}"
                            for i,g in enumerate(gagnantes[:4]))
    prompt = (
        f"Tu es un moteur de trading. Analyse les prix avec les strategies gagnantes.\n\n"
        f"PRIX ACTUELS:\n{prix_texte}\n\n"
        f"STRATEGIES GAGNANTES:\n{strat_texte}\n\n"
        f"Pour chaque actif, dis si un signal d'ACHAT se declenche maintenant.\n"
        f"Format: ACHAT: [nom] | RAISON: [10 mots]\n"
        f"Si aucun signal: AUCUN SIGNAL\n"
        f"Sois precis, ne force pas un trade."
    )
    ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else None)
    if not ia:
        return []
    try:
        rep, _ = appeler_ia(ia, prompt)
        if rep.startswith("[Erreur") or "AUCUN SIGNAL" in rep.upper()[:30]:
            return []
        signaux = []
        mots_cles = {}
        for sym, config in MARCHES_PAPER.items():
            mots = [config["nom"].lower()]
            if "Apple" in config["nom"]: mots += ["aapl", "apple"]
            if "Tesla" in config["nom"]: mots += ["tsla", "tesla"]
            if "Nvidia" in config["nom"]: mots += ["nvda", "nvidia"]
            if "Microsoft" in config["nom"]: mots += ["msft", "microsoft"]
            if "Or" in config["nom"]: mots += ["or", "gold", "xau"]
            if "Petrole" in config["nom"]: mots += ["petrole", "brent", "oil"]
            if "S&P" in config["nom"]: mots += ["s&p", "sp500"]
            if "Nasdaq" in config["nom"]: mots += ["nasdaq"]
            if "DAX" in config["nom"]: mots += ["dax"]
            if "CAC" in config["nom"]: mots += ["cac 40", "cac40"]
            mots_cles[sym] = mots
        for ligne in rep.split("\n"):
            if "ACHAT" not in ligne.upper():
                continue
            ligne_lower = ligne.lower()
            symbole_trouve = None
            for sym, mots in mots_cles.items():
                if any(mot in ligne_lower for mot in mots):
                    symbole_trouve = sym
                    break
            if not symbole_trouve or symbole_trouve not in prix_actuels:
                continue
            signaux.append({
                "symbole": symbole_trouve,
                "prix_entree": prix_actuels[symbole_trouve],
                "nom": MARCHES_PAPER[symbole_trouve]["nom"],
                "marche": MARCHES_PAPER[symbole_trouve]["marche"],
                "source": "ia",
                "score": 0,
                "raison": "signal IA"
            })
        # Dedoublonne
        vus = set()
        uniques = []
        for s in signaux:
            if s["symbole"] not in vus:
                uniques.append(s)
                vus.add(s["symbole"])
        return uniques
    except:
        return []

# ============================================
# EXECUTION DES TRADES
# ============================================
def ouvrir_position(pf, signal, prix_actuel):
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False
    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire
    # + vol targeting + correlation + drawdown + caps durs
    try:
        from gestion_risque import calculer_taille
        montant, raison = calculer_taille(pf, signal, prix_actuel, signal.get("backtest_stats"))
        if montant <= 0:
            print(f"  [SKIP] {signal.get('nom',signal['symbole'])} -> pas de trade ({raison})")
            return False
        print(f"  [SIZING] {signal.get('nom',signal['symbole'])}: {raison}")
    except ImportError:
        # Fallback si gestion_risque.py absent: ancien comportement 20% fixe
        montant = pf["liquidites"] * RISK_PAR_TRADE
    except Exception as e:
        print(f"  [SIZING erreur {e}] fallback 20% fixe")
        montant = pf["liquidites"] * RISK_PAR_TRADE
    # Plafonne au liquide dispo
    montant = min(montant, pf["liquidites"])
    if montant < 5:
        return False
    frais = montant * FRAIS_TRANSACTION
    quantite = (montant - frais) / prix_actuel
    pf["liquidites"] -= montant
    pf["total_frais"] += frais
    position = {
        "symbole": signal["symbole"],
        "nom": signal.get("nom", signal["symbole"]),
        "marche": signal.get("marche", "?"),
        "prix_entree": prix_actuel,
        "quantite": quantite,
        "montant_eur": montant,
        "frais_entree": frais,
        "date_ouverture": datetime.now().strftime("%Y-%m-%d %H:%M"),
        # Phase 6 (journal audite) : conserve la raison d'OUVERTURE (strategie)
        # separement de la raison de fermeture (TAKE-PROFIT, STOP-LOSS, TEMPS...)
        "signal_raison": signal.get("raison", ""),
        "source": signal.get("source", ""),
        "strategie": signal.get("strategie") or signal.get("source") or "inconnu"
    }
    pf["positions"].append(position)
    print(f"  [ACHAT] {signal.get('nom',signal['symbole'])} ({signal.get('marche','?')}) @ {prix_actuel:.2f} | {montant:.2f} EUR | qty {quantite:.6f}")
    notify_ifft("Paper Trade ACHAT", f"Achat {signal.get('nom','?')} @ {prix_actuel:.2f} EUR")
    return True

def verifier_sorties(pf, prix_actuels):
    positions_a_fermer = []
    maintenant = datetime.now()
    for pos in pf["positions"]:
        sym = pos["symbole"]
        if sym not in prix_actuels:
            continue
        prix_actuel = prix_actuels[sym]
        prix_entree = pos["prix_entree"]
        variation = (prix_actuel - prix_entree) / prix_entree * 100
        # META-TUNING-INSTALLE : TP/SL par actif (fallback constantes globales)
        try:
            from meta_tuning import tp_sl_actif
            _tp, _sl = tp_sl_actif(sym)
        except Exception:
            _tp, _sl = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        # EXTEND_TP (valide backtest +13.35% crypto): si position crypto en profit
        # >= +0.5%, on monte le TP a 4.0% pour laisser courir les gagnants.
        # SL fixe (pas de breakeven). Forex/or/matieres: TP fixe (non valide).
        extend_actif = sym in EXTEND_CRYPTOS and variation >= EXTEND_SEUIL
        if extend_actif:
            _tp = EXTEND_TP_PCT
        # Take-profit: encaisse des que +_tp%
        if variation >= _tp:
            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"
            positions_a_fermer.append((pos, prix_actuel, raison, variation))
        # Stop-loss: coupe des que -_sl%
        elif variation <= -_sl:
            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))
        else:
            # Sortie par duree: UNIQUEMENT si la position est en gain SUFFISANT.
            # Anti-churn : on ne ferme pas a +0.05% car les frais (0.2% AR) =>
            # perte nette. On attend gain >= SEUIL_BENEFICE_MIN (0.30%).
            # Si en perte, on garde (elle attend TP/SL) -> evite de fermer a perte.
            try:
                dt_ouv = datetime.strptime(pos.get("date_ouverture", ""), "%Y-%m-%d %H:%M")
                age_min = (maintenant - dt_ouv).total_seconds() / 60
                # EXTEND: cap duree plus long (8h) pour laisser le TP etendu se realiser
                duree_min = EXTEND_DUREE_MAX if extend_actif else SORTIE_DUREE_MIN
                seuil_min = EXTEND_SEUIL if extend_actif else SEUIL_BENEFICE_MIN
                if age_min >= duree_min and variation >= seuil_min:
                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))
            except Exception:
                pass
    for pos, prix, raison, var in positions_a_fermer:
        fermer_position(pf, pos, prix, raison, var)
    return len(positions_a_fermer) > 0

def fermer_position(pf, position, prix_actuel, raison, variation):
    montant_recu = position["quantite"] * prix_actuel
    frais = montant_recu * FRAIS_TRANSACTION
    pf["liquidites"] += montant_recu - frais
    pf["total_frais"] += frais
    gain = (montant_recu - frais) - position["montant_eur"]
    trade = {
        "symbole": position["symbole"],
        "nom": position.get("nom", position["symbole"]),
        "marche": position.get("marche", "?"),
        "prix_entree": position["prix_entree"],
        "prix_sortie": prix_actuel,
        "quantite": position["quantite"],
        "montant_eur": position["montant_eur"],
        "gain_eur": gain,
        "variation_pct": variation,
        "raison": raison,
        # Phase 6 (journal audite) : raison d'ouverture (strategie utilisee)
        "signal_raison": position.get("signal_raison", ""),
        "strategie": position.get("strategie", position.get("source", "")),
        "source": position.get("source", ""),
        "frais_total": position["frais_entree"] + frais,
        "date_ouverture": position["date_ouverture"],
        "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    pf["historique"].append(trade)
    # Phase 2: suit les trades fermes pour le circuit breaker (perte journaliere)
    pf.setdefault("trades_fermes", []).append(trade)
    pf["positions"].remove(position)
    # Phase 2: met a jour le pic de capital pour le drawdown scaler
    _cap_total = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
    pf["pic_capital"] = max(pf.get("pic_capital", pf.get("capital_initial", 1000.0)), _cap_total)
    print(f"  [{raison}] {position.get('nom',position['symbole'])} @ {prix_actuel:.2f} | var {variation:+.2f}% | gain {gain:+.2f} EUR")
    notify_ifft("Paper Trade fermeture", f"{raison} {position.get('nom','?')} var {variation:+.2f}%")

# ============================================
# CYCLE PRINCIPAL
# ============================================
def tick():
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise. Lance 'python paper_trading.py init' d'abord.")
        return
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Verification des prix...")
    prix = tous_les_prix()
    if not prix:
        print("Impossible de recuperer les prix.")
        return
    print(f"Prix recuperes ({len(prix)} actifs):")
    # Groupe par marche pour l'affichage
    par_marche = {}
    for s, p in prix.items():
        m = MARCHES_PAPER.get(s, {}).get("marche", "?")
        if m not in par_marche:
            par_marche[m] = []
        par_marche[m].append((s, p))
    for marche, items in par_marche.items():
        print(f"  [{marche}]")
        for s, p in items:
            nom = MARCHES_PAPER.get(s, {}).get("nom", s)
            print(f"    {nom}: {p:.2f}")

    print("\nVerification des positions ouvertes...")
    verifier_sorties(pf, prix)

    if len(pf["positions"]) < MAX_POSITIONS:
        symboles_ouverts = {p["symbole"] for p in pf["positions"]}
        print("\nAnalyse strategies gagnantes (backtest reel)...")
        signaux_gagnants = []
        try:
            import signaux_gagnants as sg
            signaux_gagnants = sg.generer_signaux_gagnants(prix, MARCHES_PAPER)
        except Exception as e:
            print(f"    Module signaux_gagnants indisponible: {e}")
        tous_signaux = list(signaux_gagnants)
        # Fallback: si aucune strategie gagnante ne signale, on utilise les indicateurs generiques
        if not tous_signaux:
            print("\nAucun signal gagnant -> indicateurs generiques...")
            signaux_techniques = analyser_signaux_techniques(prix)
            tous_signaux = signaux_techniques
        # En dernier recours: l'IA (rare)
        if not tous_signaux:
            print("\nAucun signal technique -> analyse IA (fallback)...")
            signaux_ia = analyser_signaux_ia(prix)
            tous_signaux = signaux_ia
        if tous_signaux:
            print(f"\n{len(tous_signaux)} signal(s) d'achat detecte(s)")
            # Phase 3: filtre ML - confirme les signaux via le modele predictif
            # Seuls les signaux confirmes par le ML (sur les actifs avec edge) sont gardes
            try:
                from ml_filtre import confirmer_signaux_ml
                signaux_avant = len(tous_signaux)
                tous_signaux = confirmer_signaux_ml(tous_signaux)
                if len(tous_signaux) < signaux_avant:
                    print(f"  -> filtre ML: {signaux_avant} -> {len(tous_signaux)} signaux confirmes")
            except Exception as e:
                print(f"  (filtre ML indisponible: {e})")
            for signal in tous_signaux:
                if signal["symbole"] not in symboles_ouverts:
                    ouvrir_position(pf, signal, prix[signal["symbole"]])
                    symboles_ouverts.add(signal["symbole"])
        else:
            print("\nAucun signal d'achat.")
    pf["dernier_tick"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    sauver_portefeuille(pf)
    afficher_solde(pf, prix)

# ============================================
# AFFICHAGE
# ============================================
def valeur_totale(pf, prix=None):
    if not prix:
        prix = tous_les_prix()
    valeur_positions = sum(p["quantite"] * prix.get(p["symbole"], p["prix_entree"]) for p in pf["positions"])
    return pf["liquidites"] + valeur_positions

def afficher_solde(pf=None, prix=None):
    if not pf:
        pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise.")
        return
    if not prix:
        prix = tous_les_prix()
    valeur = valeur_totale(pf, prix)
    gain = valeur - pf["capital_initial"]
    pct = gain / pf["capital_initial"] * 100
    print("\n" + "="*55)
    print("PORTEFEUILLE PAPER TRADING MULTI-MARCHES")
    print("="*55)
    print(f"Capital initial: {pf['capital_initial']:.2f} EUR")
    print(f" Liquidites:     {pf['liquidites']:.2f} EUR")
    print(f" Positions:      {len(pf['positions'])}")
    print(f" Valeur totale:  {valeur:.2f} EUR")
    print(f" Gain/perte:     {gain:+.2f} EUR ({pct:+.2f}%)")
    print(f" Frais payes:    {pf['total_frais']:.2f} EUR")
    print(f"Dernier tick: {pf.get('dernier_tick','jamais')}")
    if pf["positions"]:
        print(f"\nPositions ouvertes:")
        for p in pf["positions"]:
            prix_actuel = prix.get(p["symbole"], p["prix_entree"])
            var = (prix_actuel - p["prix_entree"]) / p["prix_entree"] * 100
            print(f"  [{p.get('marche','?')}] {p.get('nom','?')}: {p['quantite']:.6f} @ {p['prix_entree']:.2f} | actuel {prix_actuel:.2f} ({var:+.2f}%)")
    print("="*55)

def afficher_positions():
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise.")
        return
    if not pf["positions"]:
        print("Aucune position ouverte.")
        return
    prix = tous_les_prix()
    print(f"\nPositions ouvertes ({len(pf['positions'])}):")
    for p in pf["positions"]:
        prix_actuel = prix.get(p["symbole"], p["prix_entree"])
        var = (prix_actuel - p["prix_entree"]) / p["prix_entree"] * 100
        print(f"\n  [{p.get('marche','?')}] {p.get('nom','?')} ({p['symbole']})")
        print(f"    Quantite: {p['quantite']:.6f}")
        print(f"    Prix entree: {p['prix_entree']:.2f}")
        print(f"    Prix actuel: {prix_actuel:.2f} ({var:+.2f}%)")
        print(f"    Montant: {p['montant_eur']:.2f} EUR")
        print(f"    Ouvert le: {p['date_ouverture']}")

def afficher_historique():
    pf = charger_portefeuille()
    if not pf or not pf["historique"]:
        print("Aucun trade dans l'historique.")
        return
    print(f"\nHISTORIQUE DES TRADES ({len(pf['historique'])} fermes):")
    print("="*60)
    gains = 0
    gagnes = 0
    for t in pf["historique"]:
        print(f"\n[{t['date_fermeture']}] [{t.get('marche','?')}] {t.get('nom','?')} - {t['raison']}")
        print(f"  Entree: {t['prix_entree']:.2f} -> Sortie: {t['prix_sortie']:.2f} ({t['variation_pct']:+.2f}%)")
        print(f"  Gain: {t['gain_eur']:+.2f} EUR")
        gains += t["gain_eur"]
        if t["gain_eur"] > 0:
            gagnes += 1
    print("="*60)
    print(f"Total: {len(pf['historique'])} trades | {gagnes} gagnes | {len(pf['historique'])-gagnes} perdus")
    print(f"Gain/perte cumule: {gains:+.2f} EUR")
    if pf["historique"]:
        print(f"Win rate: {gagnes/len(pf['historique'])*100:.0f}%")

class TickTimeout(Exception):
    pass

def _timeout_handler(signum, frame):
    raise TickTimeout("Tick interrompu: depasse le temps maximum (un actif ne repondait pas)")

TEMPS_MAX_TICK = 120

def boucle():
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise. Lance 'python paper_trading.py init' d'abord.")
        return
    print(f"MODE PAPER TRADING MULTI-MARCHES CONTINU - toutes les {INTERVALLE_BOUCLE//60} min")
    print(f"Watchdog actif: un tick bloque au-dela de {TEMPS_MAX_TICK}s est interrompu.")
    print("Pour arreter: Ctrl+C")
    print("="*55)
    ancien_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    while True:
        try:
            signal.alarm(TEMPS_MAX_TICK)
            tick()
        except TickTimeout as e:
            print(f"\n[WATCHDOG] {e}")
            print("    Sauvegarde de l'etat et passage au prochain tick.")
            try:
                pf_courant = charger_portefeuille()
                if pf_courant:
                    pf_courant["dernier_tick"] = datetime.now().strftime("%Y-%m-%d %H:%M") + " (interrompu)"
                    sauver_portefeuille(pf_courant)
            except Exception:
                pass
        except Exception as e:
            print(f"Erreur: {e}")
        finally:
            signal.alarm(0)
        prochaine = datetime.now() + timedelta(seconds=INTERVALLE_BOUCLE)
        print(f"\nProchaine verification: {prochaine.strftime('%H:%M')}")
        time.sleep(INTERVALLE_BOUCLE)
    signal.signal(signal.SIGALRM, ancien_handler)

def acheter_manuel(symbole_requete):
    """Ouvre manuellement une position virtuelle sur un actif (Or, BTC, etc.).
    Accepte le symbole Yahoo/Binance (GC=F, AAPL, BTCUSDT) ou un nom (or, apple, bitcoin)."""
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise. Lance 'python paper_trading.py init' d'abord.")
        return
    # Normalise la requete utilisateur -> symbole officiel dans MARCHES_PAPER
    symbole = _resoudre_symbole(symbole_requete)
    if not symbole or symbole not in MARCHES_PAPER:
        print(f"Actif inconnu: {symbole_requete}")
        print(f"Actifs disponibles: {', '.join(MARCHES_PAPER.keys())}")
        print(f"Ou par nom: or, bitcoin, btc, ethereum, apple, tesla, petrole, cac 40, nasdaq...")
        return
    if len(pf["positions"]) >= MAX_POSITIONS:
        print(f"Nombre max de positions atteint ({MAX_POSITIONS}). Ferme-en une d'abord.")
        return
    symboles_ouverts = {p["symbole"] for p in pf["positions"]}
    if symbole in symboles_ouverts:
        print(f"Tu as deja une position ouverte sur {MARCHES_PAPER[symbole]['nom']}.")
        return
    config = MARCHES_PAPER[symbole]
    print(f"Recuperation du prix de {config['nom']} ({config['source']})...")
    if config["source"] == "binance":
        prix = prix_binance(symbole)
    else:
        prix = prix_yahoo(symbole)
    if not prix:
        print(f"Impossible de recuperer le prix de {config['nom']}. Reessaie.")
        return
    signal = {
        "symbole": symbole,
        "nom": config["nom"],
        "marche": config["marche"],
        "source": "manuel",
        "score": 0,
        "raison": "achat manuel utilisateur",
    }
    if ouvrir_position(pf, signal, prix):
        sauver_portefeuille(pf)
        print(f"Position virtuelle ouverte sur {config['nom']} @ {prix:.2f}")
    else:
        print("Echec de l'ouverture (capital insuffisant ?)")

# Correspondance nom -> symbole officiel (pour l'achat manuel)
_NOMS_VERS_SYMBOLE = {
    "or": "GC=F", "gold": "GC=F", "xauusd": "GC=F", "xau": "GC=F",
    "bitcoin": "BTCUSDT", "btc": "BTCUSDT",
    "ethereum": "ETHUSDT", "eth": "ETHUSDT", "ether": "ETHUSDT",
    "solana": "SOLUSDT", "sol": "SOLUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT", "ripple": "XRPUSDT",
    "eur/usd": "EURUSD=X", "eurusd": "EURUSD=X", "euro dollar": "EURUSD=X",
    "gbp/usd": "GBPUSD=X", "gbpusd": "GBPUSD=X",
    "usd/jpy": "JPY=X", "usdjpy": "JPY=X",
    "apple": "AAPL", "aapl": "AAPL",
    "tesla": "TSLA", "tsla": "TSLA",
    "nvidia": "NVDA", "nvda": "NVDA",
    "microsoft": "MSFT", "msft": "MSFT",
    "petrole": "BZ=F", "brent": "BZ=F", "baril": "BZ=F",
    "gaz": "NG=F",
    "cuivre": "HG=F",
    "ble": "ZW=F",
    "s&p 500": "^GSPC", "sp500": "^GSPC", "s&p500": "^GSPC",
    "nasdaq": "^IXIC",
    "dax": "^GDAXI",
    "cac 40": "^FCHI", "cac40": "^FCHI", "cac": "^FCHI",
}

def _resoudre_symbole(requete):
    q = requete.strip().lower()
    if q in MARCHES_PAPER:
        return q
    if q in _NOMS_VERS_SYMBOLE:
        return _NOMS_VERS_SYMBOLE[q]
    # Symbole officiel avec majuscules (GC=F, ^GSPC, AAPL...) tape tel quel
    if requete.strip() in MARCHES_PAPER:
        return requete.strip()
    return None

def aide():
    print("""
PAPER TRADING MULTI-MARCHES (1000 EUR virtuel)
===========================================
Marches: crypto, forex, actions, matieres, indices
Commandes:
  python paper_trading.py init          Initialise (1000 EUR)
  python paper_trading.py tick          1 cycle
  python paper_trading.py solde         Portefeuille + perf
  python paper_trading.py positions     Positions ouvertes
  python paper_trading.py historique    Trades fermes
  python paper_trading.py boucle        Continu (30 min)
  python paper_trading.py achat OR      Ouvre une position virtuelle (or, btc, apple...)
  python paper_trading.py reset         Reinitialise
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "solde"
    print("="*55)
    print(f"PAPER TRADING MULTI-MARCHES - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*55)
    if cmd == "init":
        initialiser()
    elif cmd == "tick":
        tick()
    elif cmd == "solde":
        afficher_solde()
    elif cmd == "positions":
        afficher_positions()
    elif cmd == "historique":
        afficher_historique()
    elif cmd == "boucle":
        boucle()
    elif cmd == "achat":
        if len(args) < 2:
            print("Usage: python paper_trading.py achat <actif>")
            print("Exemples: achat or | achat btc | achat apple | achat cac 40")
        else:
            acheter_manuel(" ".join(args[1:]))
    elif cmd == "reset":
        if os.path.exists(FICHIER_PAPER):
            os.remove(FICHIER_PAPER)
        print("Portefeuille reinitialise.")
    else:
        aide()
