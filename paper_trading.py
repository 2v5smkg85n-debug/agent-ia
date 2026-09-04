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
from datetime import datetime, timedelta, timezone

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
MAX_POSITIONS = 8              # 8 positions max (plus de trades)
LIQUIDITE_MIN = 200.0          # garde au moins 200 EUR de liquidites
FENETRE_CORRELATION_MIN = 30    # anti-double-exposition: 30min entre entrees meme actif (assoupli)
MAX_POS_PAR_ACTIF = 1          # 1 position par actif (pas de pyramiding risqué)
RISK_PAR_TRADE = 0.10         # 10% fixe (~100 EUR par position)
RISK_MAX_TRADE = 0.10         # 10% fixe (~100 EUR) - 8 positions x 100 EUR = 800 EUR + 200 liquidite
INTERVALLE_BOUCLE = 300        # 5 min (plus reactif pour plus de trades)
# RISK MANAGEMENT AVANCE
MAX_TRADES_PAR_JOUR = 40       # limite: 40 trades/jour (plus de trades)
PERTE_JOUR_MAX_PCT = 2.0      # stop trading si -2% en une journee
CIRCUIT_BREAKER_CONSECUTIF = 3 # pause apres 3 pertes consecutives (plus de room)
DRAWDOWN_REDUCTION_SEUIL = 0.95 # si capital < 95% du initial, reduit positions de 50%
COMPOUND_AUTOMATIQUE = True
HEURES_FAIBLE_LIQUIDITE = [(2, 6)] # pas de trades entre 2h-6h UTC
# DIVERSIFICATION TEMPORELLE: boost le score pendant les heures a fort volume
# Ouverture Europe (8h-11h UTC) et ouverture US (13h-17h UTC) = plus de liquidité
HEURES_FORT_VOLUME = [(8, 11), (13, 17)]  # UTC
HEURES_FORT_BOOST = 1  # +1 au score pendant ces heures
# Seuils pro: TP plus large pour laisser courir, SL serré pour couper vite
TAKE_PROFIT_PCT = 3.5          # +3.5% (compromis: plus de gains que 3% sans trop attendre)
STOP_LOSS_PCT = 1.0            # -1.0% ( coupe vite)
# EXTEND_TP (backtest +13.35% sur crypto): monte le TP quand la position crypto
# est en profit, pour laisser courir les gagnants. SL fixe (pas de breakeven).
# Idee utilisateur + valide par backtest elargi (9 marches, 30 trades, plateau a tp_ext=4).
EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "OPUSDT", "INJUSDT", "NEARUSDT"}
EXTEND_SEUIL = 0.5        # active l'extension a partir de +0.5% de gain
EXTEND_TP_PCT = 4.0       # TP monte a 4% une fois en profit (avant 5% trop greedy)
EXTEND_DUREE_MAX = 480    # cap duree des positions extended (8h, vs 90min normal)
SORTIE_DUREE_MIN = 720          # ferme apres 12h si en gain (laisse le TP dynamique travailler)
STALE_DUREE_MAX = 120           # position stale apres 2h (libere le capital plus vite)
# Seuil de gain minimum pour fermer par duree : doit couvrir les frais (0.2% AR) + une marge.
# Fermer a +0.05% = perte nette (frais 0.2%). Donc on n'accepte que gain >= 0.30%.
SEUIL_BENEFICE_MIN = 0.80       # 0.80% : couvre les 0.2% de frais + 0.6% de marge nette
DUREE_PETIT_GAIN = 180        # gain 0.30-0.45%: respire 2h (était 90min) pour viser partial TP
DUREE_GAIN_PROGRESS = 240    # gain 0.45-0.60%: respire 3h
DUREE_GAGNANT_MAX = 360         # gagnant protégé (breakeven armé): respire jusqu'à 4h pour atteindre partial/TP/trailing
DUREE_BONUS_STRATEGIE = 60    # stratégie prouvée (live_n>=3, wr>=60%, pnl>0): +1h de respiration
BREAKEVEN_SEUIL = 2.0      # +2.0% -> SL monte au breakeven (laisse respirer)
TRAIL_ACTIF = 4.0          # +4.0% -> trailing stop (apres un vrai move)
TRAIL_PCT = 1.5            # trail 1.5% sous le pic (compromis bruit/protection)
PARTIAL_TP_SEUIL = 2.5     # +2.5% -> encaisse 50% (pas trop tot)
PARTIAL_FRACTION = 0.5      # fraction clôturée au partial TP (50% lock, 50% runner)
# FERMETURE INTELLIGENTE: ferme les positions perdantes qui stagnent
STAGNATION_PERTE_SEUIL = -0.7   # si position a -0.7% ou pire (avant -0.5% trop agressif)
STAGNATION_PERTE_DUREE = 60     # pendant plus de 60 min -> ferme
# TP DYNAMIQUE ATR: adapte le TP selon la volatilité
ATR_LOOKBACK = 14               # périodes pour le calcul ATR
ATR_TP_MULT = 2.0               # TP = prix_entree + ATR * mult
ATR_TP_MIN = 3.0                # TP minimum 3%
ATR_TP_MAX = 8.0                # TP maximum 8%

# ============================================
# MODE SCALPING (SCALPING=1): boucle 5 min, TP 3%, SL 1%, timeframe 1h
# Utilise les strategies backtestees (72% WR) au lieu d'indicateurs generiques (12% WR)
if os.getenv('SCALPING', '0') == '1':
    INTERVALLE_BOUCLE = 300      # 5 min — evite le spam Telegram de signaux dupliques
    TAKE_PROFIT_PCT = 4.0      # +4% — gains plus gros pour 100EUR/jour
    STOP_LOSS_PCT = 1.0        # -1.0% — perte limitee
    FENETRE_CORRELATION_MIN = 10
    EXTEND_SEUIL = 999
    BREAKEVEN_SEUIL = 3.0      # +3.0% -> SL monte au breakeven (laisse les gagnants courir)
    TRAIL_ACTIF = 3.5          # +3.5% -> trailing (plus tard = plus de gains)
    TRAIL_PCT = 0.7            # trail 0.7% sous le pic (plus de marge)
    PARTIAL_TP_SEUIL = 2.5     # +2.5% -> prend 50% du benefice, le reste court vers TP
    SCALPING_TIMEFRAME = '1h'  # 1h au lieu de 15m — matche les backtests
else:
    SCALPING_TIMEFRAME = '1h'

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
    "DOGEUSDT": {"nom": "Dogecoin", "marche": "crypto", "source": "binance"},
    "AVAXUSDT": {"nom": "Avalanche", "marche": "crypto", "source": "binance"},
    "LINKUSDT": {"nom": "Chainlink", "marche": "crypto", "source": "binance"},
    "OPUSDT": {"nom": "Optimism", "marche": "crypto", "source": "binance"},
    "INJUSDT": {"nom": "Injective", "marche": "crypto", "source": "binance"},
    "NEARUSDT": {"nom": "NEAR Protocol", "marche": "crypto", "source": "binance"},
    # === Nouvelles cryptos haute volatilité (bénéfices énormes) ===
    # AI tokens
    "FETUSDT": {"nom": "Fetch.ai", "marche": "crypto", "source": "binance"},
    "RNDRUSDT": {"nom": "Render", "marche": "crypto", "source": "binance"},
    "OCEANUSDT": {"nom": "Ocean Protocol", "marche": "crypto", "source": "binance"},
    # Layer 1 haute volatilité
    "SUIUSDT": {"nom": "Sui", "marche": "crypto", "source": "binance"},
    "APTUSDT": {"nom": "Aptos", "marche": "crypto", "source": "binance"},
    "SEIUSDT": {"nom": "Sei", "marche": "crypto", "source": "binance"},
    "TIAUSDT": {"nom": "Celestia", "marche": "crypto", "source": "binance"},
    # SUIAUSDT retire (faux symbole, n'existe pas sur Binance)
    # Meme coins (gains énormes possibles)
    # PEPEUSDT retire (prix trop petit 0.000003€, spread 16% sur Revolut X)
    # FLOKIUSDT retire (prix = 0.0000 sur Revolut X)
    "WIFUSDT": {"nom": "dogwifhat", "marche": "crypto", "source": "binance"},
    # DeFi tokens
    "CRVUSDT": {"nom": "Curve DAO", "marche": "crypto", "source": "binance"},
    "COMPUSDT": {"nom": "Compound", "marche": "crypto", "source": "binance"},
    "CAKEUSDT": {"nom": "PancakeSwap", "marche": "crypto", "source": "binance"},
    # Gaming / Metaverse
    "IMXUSDT": {"nom": "Immutable X", "marche": "crypto", "source": "binance"},
    "SANDUSDT": {"nom": "The Sandbox", "marche": "crypto", "source": "binance"},
    "AXSUSDT": {"nom": "Axie Infinity", "marche": "crypto", "source": "binance"},
    # Autres haute volatilité
    "FILUSDT": {"nom": "Filecoin", "marche": "crypto", "source": "binance"},
    "ATOMUSDT": {"nom": "Cosmos", "marche": "crypto", "source": "binance"},
    "DOTUSDT": {"nom": "Polkadot", "marche": "crypto", "source": "binance"},
    # === Nouvelles cryptos haute liquidite (plus de trades possibles) ===
    "ADAUSDT": {"nom": "Cardano", "marche": "crypto", "source": "binance"},
    "TRXUSDT": {"nom": "TRON", "marche": "crypto", "source": "binance"},
    "LTCUSDT": {"nom": "Litecoin", "marche": "crypto", "source": "binance"},
    "SHIBUSDT": {"nom": "Shiba Inu", "marche": "crypto", "source": "binance"},
    "ALGOUSDT": {"nom": "Algorand", "marche": "crypto", "source": "binance"},
    "GRTUSDT": {"nom": "The Graph", "marche": "crypto", "source": "binance"},
    "ICPUSDT": {"nom": "Internet Computer", "marche": "crypto", "source": "binance"},
    "ETCUSDT": {"nom": "Ethereum Classic", "marche": "crypto", "source": "binance"},
    "XLMUSDT": {"nom": "Stellar", "marche": "crypto", "source": "binance"},
    "RUNEUSDT": {"nom": "THORChain", "marche": "crypto", "source": "binance"},
    # MATICUSDT retire (HTTP 400 sur Revolut X, renomme POL sur Revolut)
    # CRYPTO UNIQUEMENT — actions/forex/matieres/indices desactives
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
    """Prix via Revolut X (API publique, EUR). Remplace Binance."""
    try:
        import prix_revolut as pr
        p = pr.get_prix_revolut(symbole)
        return p if p > 0 else None
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
    """Recupere tous les prix depuis toutes les sources.
    Utilise Binance batch (1 appel pour TOUTES les cryptos) + Revolut X pour les top assets."""
    prix = {}
    prix_par_source = {"binance": [], "yahoo": []}
    for sym, config in MARCHES_PAPER.items():
        prix_par_source[config["source"]].append(sym)

    syms_crypto = prix_par_source["binance"]

    # 1. BATCH COINGECKO: toutes les cryptos en un seul appel (pas de geo-blocage)
    try:
        import prix_revolut as pr
        prix_batch = pr.get_prix_coingecko_batch(syms_crypto)
        if prix_batch:
            prix.update(prix_batch)
            print(f"  [COINGECKO-BATCH] {len(prix_batch)}/{len(syms_crypto)} cryptos recuperees")
        else:
            print(f"  [COINGECKO-BATCH] 0 prix - fallback Binance")
            # Fallback Binance si CoinGecko echoue
            prix_batch = pr.get_prix_binance_batch(syms_crypto)
            if prix_batch:
                prix.update(prix_batch)
                print(f"  [BINANCE-BATCH] {len(prix_batch)} cryptos (fallback)")
    except Exception as e:
        print(f"  [BATCH] Erreur: {e}")

    # 2. REVOLUT X pour les top assets non blacklistes (prix d'entree plus precis)
    top_revolut = ["BTCUSDT", "ETHUSDT"]
    for sym in top_revolut:
        try:
            p = prix_binance(sym)  # = Revolut X
            if p and p > 0:
                prix[sym] = p  # ecrase le prix Binance avec le prix Revolut X
        except Exception:
            pass
        time.sleep(1.0)

    # 3. Yahoo pour les non-crypto (si activé)
    for sym in prix_par_source["yahoo"]:
        p = prix_yahoo(sym)
        if p:
            prix[sym] = p
        time.sleep(0.3)

    manquants = [s for s in MARCHES_PAPER if s not in prix]
    if manquants:
        print(f"  [Info] {len(manquants)} symboles sans prix")

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
    # Top cryptos: ne trader que les 10 meilleurs selon l'apprentissage
    _top_cryptos = None
    try:
        _tc = json.load(open(os.path.join(DOSSIER, "top_cryptos.json")))
        _top_cryptos = set(_tc.get("top", []))
    except Exception:
        pass  # pas de fichier -> trade tous les actifs
    # Analyse tous les marches disposes dans MARCHES_PAPER (crypto ET non-crypto)
    for sym, config in MARCHES_PAPER.items():
        if sym not in prix_actuels:
            continue
        # Filtre top cryptos: skip les cryptos hors top 10
        if _top_cryptos and config.get("marche") == "crypto" and sym not in _top_cryptos:
            continue
        print(f"    Indicateurs {config['nom']}...", end=" ", flush=True)
        try:
            analyse = analyser_actif(sym, SCALPING_TIMEFRAME)
            if not analyse:
                print("echec")
                continue
            verdict = analyse["verdict"]
            score = analyse["score"]
            print(f"{verdict} (score {score:+d})")
            # Signal d'achat si score >= 1 (seuil bas pour plus de trades)
            # Les 14 couches d'intelligence filtrent ensuite la qualite
            if score >= 1:
                signaux.append({
                    "symbole": sym,
                    "prix_entree": prix_actuels[sym],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "indicateurs",
                    "strategie": "momentum" if any("MOMENTUM" in s for s in analyse.get("signaux", [])) else ("breakout" if any("BREAKOUT" in s for s in analyse.get("signaux", [])) else ("macd_cross" if any("MACD" in s for s in analyse.get("signaux", [])) else "technique")),
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
    # mots-cles communs aux 2 chemins (mono-modele et consensus)
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

    def _vers_signaux(achat_names, raison="signal IA (consensus)"):
        signaux = []
        for nom in achat_names:
            nom_lower = (nom or "").lower()
            symbole_trouve = None
            for sym, mots in mots_cles.items():
                if any(mot in nom_lower for mot in mots):
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
                "strategie": "ia",
                "score": 0,
                "raison": raison
            })
        return signaux

    def _mono():
        # Chemin mono-modele d'origine (CONSENSUS_IA=0) — inchangé
        ia = "claude" if disponible("claude") else ("gemini" if disponible("gemini") else None)
        if not ia:
            return []
        rep, _ = appeler_ia(ia, prompt)
        if rep.startswith("[Erreur") or "AUCUN SIGNAL" in rep.upper()[:30]:
            return []
        signaux = []
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
                "strategie": "ia",
                "score": 0,
                "raison": "signal IA"
            })
        return signaux

    try:
        if os.getenv("CONSENSUS_IA", "0") == "1":
            # Consensus multi-modeles: actif retenu si >= quorum modeles l'ont flague ACHAT.
            # Fail-open: si < quorum modeles repondent (achats is None) -> chemin mono.
            try:
                from consensus_ia import consensus_achats
                achats, _meta = consensus_achats(prompt)
                signaux = _vers_signaux(achats) if achats is not None else _mono()
            except Exception:
                signaux = _mono()
        else:
            signaux = _mono()
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
# ============================================
# PLUGINS (méta-évolution autonome): modules auto-chargés depuis plugins/
# L'agent dépose des modules validés -> intégration automatique sans toucher
# au code core. Hooks: hook_entree (veto) + hook_sizing (ajuste taille).
# Toggle: PLUGINS_ACTIVE=0. Hooks wrappés try/except (safe).
_plugins_charges = []
_plugins_sig = None
def _charger_plugins():
    """Charge les modules de plugins/. Recharge si le set change (actif SANS restart)."""
    global _plugins_charges, _plugins_sig
    if os.getenv("PLUGINS_ACTIVE", "1") == "0":  # désactivé
        return
    pdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
    if not os.path.isdir(pdir):
        return
    import importlib.util
    _parent = os.path.dirname(pdir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    try:
        fichiers = sorted(f for f in os.listdir(pdir) if f.endswith(".py") and not f.startswith("_"))
        sig = tuple((f, os.path.getmtime(os.path.join(pdir, f))) for f in fichiers)
    except Exception:
        return
    if _plugins_sig == sig and _plugins_charges:
        return  # inchangé
    _plugins_sig = sig
    _plugins_charges = []
    for fn in fichiers:
        try:
            spec = importlib.util.spec_from_file_location("plugin_" + fn[:-3],
                                                          os.path.join(pdir, fn))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _plugins_charges.append((fn, mod))
            print(f"  [PLUGIN] {fn} chargé")
        except Exception as _e:
            print(f"  [PLUGIN] {fn} erreur chargement: {_e}")


def _niveau_performance(pf):
    """Niveau de confiance global basé sur la performance RÉALISÉE du portefeuille.
    Chaque palier de +5% de PnL ajoute +0.5 aux multiplicateurs de conviction.
    Auto-protectif: si le PnL redescend sous un palier, le bonus est retiré."""
    try:
        cap = pf.get("capital_initial", 1000)
        liq = pf.get("liquidites", 0)
        pos = pf.get("positions", [])
        val = liq + sum(p.get("quantite", 0) * p.get("prix_actuel", p.get("prix_entree", 0)) for p in pos)
        pnl_pct = (val / cap - 1) * 100 if cap else 0
        niveau = max(0, int(round(pnl_pct, 4) // 5))   # 0-4.99%->0, 5-9.99%->1, 10-14.99%->2...
        bonus = niveau * 0.5
        return niveau, bonus, pnl_pct
    except Exception:
        return 0, 0.0, 0.0


def _conviction_mult(signal, cs):
    """Multiplicateur de conviction basé sur la performance LIVE de la stratégie.
    x1.5 éprouvé (>=5t, >=70% win, pnl>0) | x1.25 solide (>=3t, >=60%, pnl>0)
    x0.5 faible (>=3t, pnl<0) | x1.0 neuf/neutre."""
    _sym = signal.get("symbole", "")
    _nom = signal.get("nom", signal.get("strategie", ""))
    _entry = cs.get(_sym) or cs.get(_sym.upper()) or cs.get(_sym.lower()) or {}
    for _s in _entry.get("strategies", []):
        if _s.get("strategie", "") == _nom:
            _n = _s.get("live_n", 0); _wr = _s.get("live_wr", 0); _pnl = _s.get("live_pnl", 0)
            if _n >= 8 and _wr >= 75 and _pnl > 0:
                return 3.0, f"élite ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"
            if _n >= 5 and _wr >= 70 and _pnl > 0:
                return 2.5, f"éprouvé ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"
            if _n >= 3 and _wr >= 60 and _pnl > 0:
                return 1.75, f"solide ({_n}t {_wr:.0f}% +{_pnl:.2f}€)"
            if _n >= 3 and _pnl < 0:
                return 0.5, f"faible ({_n}t {_wr:.0f}% {_pnl:+.2f}€)"
            return 1.0, f"neutre (n={_n})"
    return 1.0, "nouveau"


def _entree_bloquee_weekend(signal, maintenant=None):
    """True si lentree est bloquee pour eviter le gap week-end (non-crypto, ven->week-end).
    Le forex/indices/matieres ferment le week-end -> gap possible a la reouverture
    qui peut overshooter le SL (cf. Or tenu 68h, -1.92EUR). Crypto 24/7 = non concerne."""
    if signal.get("marche") == "crypto":
        return False
    maintenant = maintenant or datetime.now()
    _jour = maintenant.weekday()  # 0=lun ... 4=ven, 5=sam, 6=dim
    return _jour == 4 or _jour >= 5

def ouvrir_position(pf, signal, prix_actuel):
    # PROTECTION: bloquer si prix invalide (0 ou None)
    if not prix_actuel or prix_actuel <= 0:
        print(f"  [BLOCAGE] Prix invalide ({prix_actuel}) pour {signal.get('symbole','?')} - trade bloque")
        return False
    # ANTI FLASH-CRASH: bloquer les nouveaux trades si circuit breaker actif
    try:
        import flash_crash as fc
        if fc.circuit_breaker_actif():
            _niveau = fc.get_niveau_protection()
            print(f"  [FLASH] Circuit breaker actif (niveau {_niveau}) - trade bloque")
            return False
    except Exception:
        pass
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False
    # PLANCHER LIQUIDITE: garde au moins 200 EUR de liquidites
    if pf["liquidites"] < LIQUIDITE_MIN:
        print(f"  [LIQUIDITE] {pf['liquidites']:.2f} EUR < {LIQUIDITE_MIN} EUR minimum -> skip nouveau trade")
        return False
    # BLACKLIST STRATEGIES PERDANTES: momentum bloque (33% WR, pertes repetees)
    _strat_blacklist = ["momentum"]
    _strat_signal = (signal.get("strategie", "") or "").lower()
    for _bl in _strat_blacklist:
        if _bl in _strat_signal:
            print(f"  [BLACKLIST] {signal.get('nom', signal.get('symbole','?'))}: strategie '{_bl}' bloquee")
            return False
    # ANTI-DOUBLE-EXPOSITION: bloque une 2e entrée sur un actif déjà ouvert récemment
    # (2 stratégies sur le même actif au même moment = perte corrélée doublée quand ça chute)
    if os.getenv("ANTI_CORR", "1") != "0":
        try:
            _sym = signal["symbole"]
            _sig_strat = signal.get("strategie") or signal.get("source") or ""
            _maint = datetime.now()
            _FEN_MEME_STRAT = 120  # meme strategie sur meme actif: bloque 2h (anti-pyramiding correle)
            for _p in pf["positions"]:
                if _p["symbole"] != _sym:
                    continue
                try:
                    _dt = datetime.strptime(_p.get("date_ouverture",""), "%Y-%m-%d %H:%M")
                    _age = (_maint - _dt).total_seconds() / 60
                    _meme_strat = bool(_sig_strat) and _p.get("strategie","") == _sig_strat
                    _fen = _FEN_MEME_STRAT if _meme_strat else FENETRE_CORRELATION_MIN
                    if _age <= _fen:
                        print("  [ANTI-CORR] " + str(signal.get("nom",_sym)) + ": actif deja ouvert (" + str(int(_age)) + "min<=" + str(_fen) + "min) -> entree bloquee (evite double-exposition)")
                        return False
                except Exception:
                    pass
        except Exception:
            pass
    # ANTI-GAP WEEK-END: bloque les entrees non-crypto le vendredi + week-end.
    # Ces marches ferment le week-end -> un gap a la reouverture peut overshooter
    # le SL (cf. Or tenu 68h, -1.92EUR). L exit stack (stale 3h) ferme les positions
    # lun-jeudi avant le week-end, mais une entree vendredi n a pas le temps.
    if os.getenv("ANTI_GAP_WEEKEND", "1") != "0":
        try:
            if _entree_bloquee_weekend(signal):
                print(f"  [ANTI-GAP] {signal.get('nom',signal.get('symbole','?'))} ({signal.get('marche','?')}): entree bloquee (week-end, risque de gap)")
                return False
        except Exception:
            pass
    # CIRCUIT BREAKER (protection capital): suspend les entrées en cas de drawdown
    # profond (>=12%) ou de pertes consecutives (>=5). Leçon #1: "survis aux bears".
    # Toggle: PROTECTION_CAPITAL=0 pour désactiver (en paper par défaut actif).
    if os.getenv("PROTECTION_CAPITAL", "1") != "0":
        try:
            from protection_capital import verifier_pause
            _pause, _raison = verifier_pause(pf)
            if _pause:
                print(f"  [CIRCUIT BREAKER] entrées suspendues — {_raison}")
                return False
        except ImportError:
            pass  # module absent -> pas de protection (paper)
        except Exception:
            pass
    # FILTRE POIDS STRATEGIES (anti-surapprentissage): bloque les stratégies
    # qui ont été ajustées à 0 (perdantes) par l'auto-ajustement. Le moteur de
    # trading ne peut pas ouvrir de position avec une stratégie qui a échoué
    # en backtest walk-forward. Toggle: POIDS_STRAT_FILTER=0.
    if os.getenv("POIDS_STRAT_FILTER", "1") != "0":
        try:
            _strat_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poids_strategies.json")
            if os.path.exists(_strat_file):
                with open(_strat_file, 'r') as _f:
                    _poids = json.load(_f)
                _strats = _poids.get("strategies", {})
                _sym_key = signal["symbole"]
                _strat_name = signal.get("strategie", "") or signal.get("source", "")
                # Normaliser le nom de stratégie (momentum, mean_reversion, breakout, rsi_extreme, macd)
                _strat_lower = _strat_name.lower()
                _strat_key = None
                for _s in ["momentum", "mean_reversion", "breakout", "rsi_extreme", "macd"]:
                    if _s in _strat_lower or _s.replace("_", "") in _strat_lower.replace(" ", ""):
                        _strat_key = _s
                        break
                if _strat_key:
                    _poids_val = _strats.get(f"{_sym_key}_{_strat_key}", 0.20)
                    if _poids_val <= 0.06:  # MIN_POIDS = 0.05, donc 0.06 = strat perdante
                        print(f"  [POIDS STRAT] {signal.get('nom', _sym_key)}: stratégie '{_strat_key}' poids={_poids_val:.2f} (perdante) -> entrée bloquée")
                        return False
                    # Ajuster la taille selon le poids (stratégie faible = position réduite)
                    if _poids_val < 0.20:
                        signal["poids_strat"] = _poids_val
                        print(f"  [POIDS STRAT] {signal.get('nom', _sym_key)}: stratégie '{_strat_key}' poids={_poids_val:.2f} (position réduite)")
                    elif _poids_val > 0.40:
                        signal["poids_strat"] = _poids_val
                        print(f"  [POIDS STRAT] {signal.get('nom', _sym_key)}: stratégie '{_strat_key}' poids={_poids_val:.2f} (stratégie forte)")
        except Exception as _e:
            print(f"  [POIDS STRAT erreur {_e}] entrée autorisée (fail-open)")
    # FILTRE SENTIMENT (gate d'entrée — Feature 2): bloque les achats en euphorie
    # (Extreme Greed F&G >= 80) ou quand l'actu crypto est fortement baissière.
    # Crypto uniquement (le F&G est le Crypto Fear & Greed Index). Complète le sizing
    # contrarian (plus bas dans cette fonction) par un VETO d'entrée. Off par défaut.
    if os.getenv("SENTIMENT_GATE", "0") == "1" and signal.get("marche") == "crypto":
        try:
            from sentiment_gate import gate_achat
            _allow, _raison = gate_achat(signal["symbole"])
            if not _allow:
                print(f"  [SENTIMENT GATE] {signal.get('nom', signal['symbole'])}: entrée bloquée — {_raison}")
                return False
        except ImportError:
            pass  # module absent -> pas de gate
        except Exception as _e:
            print(f"  [SENTIMENT GATE erreur {_e}] entrée autorisée (fail-open)")
    # FILTRE MACRO CALENDAR (gate d'entrée): bloque les achats avant un event High impact
    # (CPI, NFP, FOMC, ECB...) dans les 2 prochaines heures. Off par défaut.
    if os.getenv("MACRO_GATE", "0") == "1":
        try:
            from macro_calendar import gate_achat as _macro_gate
            _allow, _raison = _macro_gate(signal["symbole"])
            if not _allow:
                print(f"  [MACRO GATE] {signal.get('nom', signal['symbole'])}: entrée bloquée — {_raison}")
                return False
        except ImportError:
            pass  # module absent -> pas de gate
        except Exception as _e:
            print(f"  [MACRO GATE erreur {_e}] entrée autorisée (fail-open)")
    # FILTRE SOCIAL CONSENSUS (gate d'entrée): bloque les achats si les 8 traders
    # X/Twitter sont majoritairement bearish sur l'actif. Off par défaut.
    if os.getenv("SOCIAL_GATE", "0") == "1":
        try:
            from social_consensus import gate_achat as _social_gate
            _allow, _raison = _social_gate(signal["symbole"])
            if not _allow:
                print(f"  [SOCIAL GATE] {signal.get('nom', signal['symbole'])}: entrée bloquée — {_raison}")
                return False
        except ImportError:
            pass  # module absent -> pas de gate
        except Exception as _e:
            print(f"  [SOCIAL GATE erreur {_e}] entrée autorisée (fail-open)")
    # FILTRE BOUGIES (apprentissage): détecte les patterns de bougies japonaises
    # et bloque l'entrée si le pattern a un win rate < 40% sur cet actif (après 5+ trades).
    # L'agent apprend quels patterns marchent sur quelles cryptos. Toggle: BOUGIE_GATE=1.
    _pattern_info = None
    if os.getenv("BOUGIE_GATE", "1") == "1" and signal.get("marche") == "crypto":
        try:
            from candlestick_learning import analyser_avec_apprentissage
            _pa = analyser_avec_apprentissage(signal["symbole"])
            _pattern_info = _pa
            if _pa["score_apprentissage"] <= -0.5:
                _pats = ", ".join(p["pattern"] for p in _pa.get("patterns", [])) or "aucun"
                print(f"  [BOUGIES] {signal.get('nom', signal['symbole'])}: {_pats} score={_pa['score_apprentissage']:.2f} — entrée bloquée (pattern perdant)")
                return False
            if _pa["patterns"]:
                _pats = ", ".join(p["pattern"] for p in _pa["patterns"])
                print(f"  [BOUGIES] {signal.get('nom', signal['symbole'])}: {_pats} score={_pa['score_apprentissage']:.2f}")
        except ImportError:
            pass
        except Exception as _e:
            print(f"  [BOUGIES erreur {_e}] entrée autorisée (fail-open)")
    # META-INTELLIGENCE: backtest instantane + correlation + confidence sizing
    # L'agent verifie si ce signal a gagne historiquement avant d'ouvrir.
    if os.getenv("META_IA", "1") == "1" and signal.get("marche") == "crypto":
        try:
            from meta_intelligence import meta_analyse, positions_correlees, taille_position_optimale
            _ma = meta_analyse(signal["symbole"])
            if _ma["recommendation"] == "SKIP":
                print(f"  [META-IA] {signal.get('nom', signal['symbole'])}: SKIP (confiance {_ma['confiance']:.2f}, backtest win {_ma.get('backtest_win_rate',0)*100:.0f}%)")
                return False
            if _ma.get("correlation_bloquee"):
                print(f"  [META-IA] {signal.get('nom', signal['symbole'])}: bloque (correlation avec position existante)")
                return False
            # Ajuster la taille de position selon la confiance
            _tp = taille_position_optimale(_ma["confiance"], pf["liquidites"], risk_base=RISK_PAR_TRADE)
            if _tp["montant"] < 10:
                print(f"  [META-IA] {signal.get('nom', signal['symbole'])}: skip (confiance trop basse)")
                return False
            signal["meta_confiance"] = _ma["confiance"]
            signal["meta_taille"] = _tp["taille"]
            print(f"  [META-IA] {signal.get('nom', signal['symbole'])}: {_ma['recommendation']} confiance={_ma['confiance']:.2f} taille={_tp['taille']} ({_tp['montant']:.0f}€)")
        except ImportError:
            pass
        except Exception as _e:
            print(f"  [META-IA erreur {_e}] entree autorisee (fail-open)")
    # PLUGINS (méta-évolution): hooks d'entrée (veto). Toggle: PLUGINS_ACTIVE=0.
    if os.getenv("PLUGINS_ACTIVE", "1") != "0":
        try:
            _charger_plugins()
            for _fn, _mod in _plugins_charges:
                if hasattr(_mod, "hook_entree"):
                    try:
                        _allow, _raison = _mod.hook_entree(pf, signal)
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "veto" if not _allow else "allow")
                        except Exception:
                            pass
                        if not _allow:
                            print(f"  [PLUGIN {_fn}] entrée bloquée: {_raison}")
                            return False
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_entree erreur: {_e}")
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "error")
                        except Exception:
                            pass
        except Exception:
            pass
    # FILTRE CONFLUENCE MULTI-TF: bloque les entrees contre-tendance (HTF opposee).
    # Ameliore le win rate en n acceptant que les trades alignes avec la tendance
    # de la timeframe superieure. Fail-open sur erreur API. Toggle: CONF_MULTI_TF=0.
    if os.getenv("CONF_MULTI_TF", "1") != "0":
        try:
            from filtre_confluence_htf import _entree_bloquee_confluence
            _blk_conf, _raison_conf = _entree_bloquee_confluence(signal)
            if _blk_conf:
                print("  [CONFLUENCE] " + str(signal.get("nom", signal.get("strategie", signal.get("symbole", "?")))) + ": entree bloquee (" + str(_raison_conf) + ")")
                return False
        except Exception:
            pass
    # FILTRE SPREAD ANORMAL: bloque les entrees sur les actifs avec spread Revolut X anormal
    try:
        from prix_revolut import SPREAD_BLACKLIST
        if signal["symbole"] in SPREAD_BLACKLIST:
            print(f"  [SPREAD] {signal.get('nom',signal['symbole'])}: spread Revolut X anormal -> SKIP nouvelle entree")
            return False
    except Exception:
        pass
    # FILTRE VOLUME: verifie que le volume confirme le signal d'achat
    try:
        from indicateurs import historique_ohlcv, detecter_support_resistance
        # Filtre volume: le volume actuel doit etre >= 70% de la moyenne
        # Skip le filtre si Revolut X ne fournit pas le volume (volume=0 = indisponible)
        _vol_bougies = historique_ohlcv(signal["symbole"], "1h", 20)
        if _vol_bougies and len(_vol_bougies) >= 10:
            # Utilise l'avant-derniere bougie (derniere COMPLETE) comme volume actuel
            _vols = [b.get("volume", 0) for b in _vol_bougies[:-2]]
            _vol_actuel = _vol_bougies[-2].get("volume", 0) if len(_vol_bougies) >= 2 else 0
            _vol_moyen = sum(_vols) / len(_vols) if _vols else 0
            # Volume faible = penalite score (pas blocage dur)
            if _vol_moyen > 10 and _vol_actuel > 0:
                _ratio_vol = _vol_actuel / _vol_moyen
                if _ratio_vol < 0.3:
                    # Volume tres faible: -1 score (forte penalite)
                    signal["score"] = signal.get("score", 5) - 1
                    print(f"  [VOLUME] {signal.get('nom',signal['symbole'])}: volume tres faible ({_vol_actuel:.0f} vs moy {_vol_moyen:.0f}) -> -1 score")
                elif _ratio_vol < 0.5:
                    # Volume faible: -0.5 score
                    signal["score"] = signal.get("score", 5) - 0.5
                    print(f"  [VOLUME] {signal.get('nom',signal['symbole'])}: volume faible ({_vol_actuel:.0f} vs moy {_vol_moyen:.0f}) -> -0.5 score")
        # Filtre support/resistance: n'achete pas juste sous une resistance
        _sup, _res = detecter_support_resistance(signal["symbole"], "1h")
        if _res and prix_actuel > 0:
            _dist_res = ((_res - prix_actuel) / prix_actuel) * 100
            if _dist_res > 0 and _dist_res < 0.5:
                print(f"  [S/R] {signal.get('nom',signal['symbole'])}: prix trop proche resistance ({_dist_res:.1f}%) -> SKIP")
                return False
            _dist_sup = ((prix_actuel - _sup) / prix_actuel) * 100 if _sup and _sup < prix_actuel else 999
            if _dist_sup >= 0 and _dist_sup < 1.0:
                print(f"  [S/R] {signal.get('nom',signal['symbole'])}: proche support {_dist_sup:.1f}% -> BONUS (+1 score)")
                signal["score"] = signal.get("score", 0) + 1
    except Exception:
        pass
    # === AMELIORATION WIN RATE: 3 FILTRES SUPPLEMENTAIRES ===
    # FILTRE 1: CONFIRMATION MULTI-TIMEFRAME STRICTE (1h + 4h + 1d alignes)
    # Bloque les entrees si la tendance 4h ou 1d contredit le signal 1h
    try:
        from indicateurs import historique_ohlcv, rsi as _calc_rsi
        _sym = signal["symbole"]
        _conf_htf = 0
        _htf_details = []
        _data_ok = True  # detecte si les donnees HTF sont fiables
        for _tf, _label in [("4h", "4h"), ("1d", "1j")]:
            try:
                _bougies = historique_ohlcv(_sym, _tf, 20)
                if _bougies and len(_bougies) >= 5:
                    _closes = [b.get("close", 0) for b in _bougies]
                    # Detecte donnees defectueuses: tous les prix identiques ou quasi
                    _unique = len(set([round(c, 6) for c in _closes]))
                    if _unique <= 2:
                        _data_ok = False
                        _htf_details.append(f"{_label} donnees indisponibles")
                        continue
                    _sma20 = sum(_closes[-20:]) / len(_closes[-20:]) if len(_closes) >= 20 else sum(_closes) / len(_closes)
                    _prix_now = _closes[-1]
                    _rsi_tf = _calc_rsi(_closes) if len(_closes) >= 16 else 50
                    if _rsi_tf is None:
                        _rsi_tf = 50
                    if _prix_now > _sma20 and _rsi_tf > 45:
                        _conf_htf += 1
                        _htf_details.append(f"{_label} haussier (RSI {_rsi_tf:.0f})")
                    else:
                        _htf_details.append(f"{_label} baissier/neutre (RSI {_rsi_tf:.0f})")
            except Exception:
                _htf_details.append(f"{_label} indisponible")
        if not _data_ok:
            # Fallback: utilise l'historique stocke des prix batch
            try:
                import historique_prix as hp
                _conf_htf2 = 0
                _htf2_ok = True
                for _tf, _label in [("4h", "4h"), ("1d", "1j")]:
                    _closes_hist = hp.get_historique(_sym, _tf)
                    if len(_closes_hist) >= 16:
                        _sma_h = hp.sma_simple(_closes_hist, 20) or sum(_closes_hist) / len(_closes_hist)
                        _rsi_h = hp.rsi_simple(_closes_hist)
                        if _rsi_h is None:
                            _rsi_h = 50
                        _prix_h = _closes_hist[-1]
                        if _prix_h > _sma_h and _rsi_h > 45:
                            _conf_htf2 += 1
                            _htf_details.append(f"{_label} haussier (hist RSI {_rsi_h:.0f})")
                        else:
                            _htf_details.append(f"{_label} baissier (hist RSI {_rsi_h:.0f})")
                    else:
                        _htf2_ok = False
                        _htf_details.append(f"{_label} hist insuffisant ({len(_closes_hist)})")
                if _htf2_ok and _conf_htf2 == 2:
                    signal["score"] = signal.get("score", 0) + 1
                    print(f"  [MTF-65] {signal.get('nom',_sym)}: 2/2 HTF confirment (historique) -> +1 score")
                elif _htf2_ok and _conf_htf2 == 1:
                    signal["score"] = signal.get("score", 0) - 0.5
                    print(f"  [MTF-65] {signal.get('nom',_sym)}: 1/2 HTF confirme (historique) -> -0.5 score")
                elif _htf2_ok and _conf_htf2 == 0:
                    signal["score"] = signal.get("score", 0) - 2
                    print(f"  [MTF-65] {signal.get('nom',_sym)}: 0/2 HTF confirme (historique) -> -2 score")
                else:
                    print(f"  [MTF-65] {signal.get('nom',_sym)}: donnees HTF indisponibles ({', '.join(_htf_details)}) -> neutre (0)")
            except Exception:
                print(f"  [MTF-65] {signal.get('nom',_sym)}: donnees HTF indisponibles ({', '.join(_htf_details)}) -> neutre (0)")
        elif _conf_htf == 0:
            # Aucune HTF confirme -> forte penalite mais pas SKIP (assoupli)
            signal["score"] = signal.get("score", 0) - 2
            print(f"  [MTF-65] {signal.get('nom',_sym)}: 0/2 HTF confirme ({', '.join(_htf_details)}) -> -2 score")
        elif _conf_htf == 1:
            # 1 seule HTF confirme -> petite penalite
            signal["score"] = signal.get("score", 0) - 0.5
            print(f"  [MTF-65] {signal.get('nom',_sym)}: 1/2 HTF confirme ({', '.join(_htf_details)}) -> -0.5 score")
        else:
            # 2/2 HTF confirment -> bonus score
            signal["score"] = signal.get("score", 0) + 1
            print(f"  [MTF-65] {signal.get('nom',_sym)}: 2/2 HTF confirment -> +1 score")
    except Exception as _e:
        print(f"  [MTF-65] indisponible: {_e}")
    # FILTRE 2: ATTENDRE UN PULLBACK (pas acheter au sommet)
    # Si le prix est trop etendu au-dessus de la SMA20 ou RSI > 65, penalite
    try:
        from indicateurs import historique_ohlcv as _hist_1h, rsi as _rsi_fn
        _bougies_1h = _hist_1h(signal["symbole"], "1h", 20)
        if _bougies_1h and len(_bougies_1h) >= 14:
            _closes_1h = [b.get("close", 0) for b in _bougies_1h]
            # Detecte donnees defectueuses (prix identiques = rate limit)
            _unique_1h = len(set([round(c, 6) for c in _closes_1h]))
            if _unique_1h <= 2:
                # Fallback: utilise l'historique stocke
                try:
                    import historique_prix as hp
                    _closes_hist = hp.get_historique(signal["symbole"], "1h")
                    if len(_closes_hist) >= 16:
                        _sma20_1h = hp.sma_simple(_closes_hist, 20) or sum(_closes_hist) / len(_closes_hist)
                        _ecart_sma = ((prix_actuel - _sma20_1h) / _sma20_1h) * 100 if _sma20_1h > 0 else 0
                        _rsi_1h = hp.rsi_simple(_closes_hist) or 50
                        if _ecart_sma > 3.5:
                            signal["score"] = signal.get("score", 0) - 1
                            print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: prix +{_ecart_sma:.1f}% au-dessus SMA20 (hist) -> -1 score")
                        if _rsi_1h > 72:
                            signal["score"] = signal.get("score", 0) - 1
                            print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: RSI {_rsi_1h:.0f} > 72 (hist) -> -1 score")
                        if abs(_ecart_sma) <= 1.5:
                            signal["score"] = signal.get("score", 0) + 1
                            print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: prix proche SMA20 ({_ecart_sma:+.1f}%) (hist) -> +1 score")
                    else:
                        print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: donnees 1h indisponibles -> skip filtre")
                except Exception:
                    print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: donnees 1h indisponibles -> skip filtre")
            else:
                _sma20_1h = sum(_closes_1h[-20:]) / len(_closes_1h[-20:]) if len(_closes_1h) >= 20 else sum(_closes_1h) / len(_closes_1h)
                _ecart_sma = ((prix_actuel - _sma20_1h) / _sma20_1h) * 100 if _sma20_1h > 0 else 0
                _rsi_1h = _rsi_fn(_closes_1h) if len(_closes_1h) >= 16 else 50
                if _rsi_1h is None:
                    _rsi_1h = 50
                # Prix trop etendu au-dessus de la SMA20 (> 3.5%) = risque de pullback
                if _ecart_sma > 3.5:
                    signal["score"] = signal.get("score", 0) - 1
                    print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: prix +{_ecart_sma:.1f}% au-dessus SMA20 -> -1 score (risque pullback)")
                # RSI en surachat extreme (> 72) = attendre un repli
                if _rsi_1h > 72:
                    signal["score"] = signal.get("score", 0) - 1
                    print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: RSI {_rsi_1h:.0f} > 72 (surachat) -> -1 score (attendre repli)")
                # Prix proche de la SMA20 (dans +/- 1.5%) = bon point d'entree
                if abs(_ecart_sma) <= 1.5:
                    signal["score"] = signal.get("score", 0) + 1
                    print(f"  [PULLBACK] {signal.get('nom',signal['symbole'])}: prix proche SMA20 ({_ecart_sma:+.1f}%) -> +1 score (bon entree)")
    except Exception:
        pass
    # FILTRE 3: HEURES DE FAIBLE LIQUIDITE ETENDU (weekend + heures creuses)
    # Penalise les trades en dehors des heures de fort volume (pas de bonus)
    try:
        _heure_utc = datetime.now(timezone.utc).hour
        _jour = datetime.now(timezone.utc).weekday()  # 0=Lundi, 6=Dimanche
        _est_weekend = _jour >= 5  # Samedi=5, Dimanche=6
        _est_heure_faible = True
        for _h_deb, _h_fin in HEURES_FORT_VOLUME:
            if _h_deb <= _heure_utc < _h_fin:
                _est_heure_faible = False
                break
        if _est_weekend:
            signal["score"] = signal.get("score", 0) - 0.5
            print(f"  [LIQUIDITE] Weekend -> -0.5 score (liquidite faible)")
        elif _est_heure_faible and not (HEURES_FAIBLE_LIQUIDITE and any(h <= _heure_utc < f for h, f in HEURES_FAIBLE_LIQUIDITE)):
            # Heure creuse mais pas bloque: petite penalite (assoupli)
            signal["score"] = signal.get("score", 0) - 0.3
            print(f"  [LIQUIDITE] Heure creuse ({_heure_utc}h UTC) -> -0.3 score")
    except Exception:
        pass
    # FILTRE SCORE MINIMUM: ne trade que les signaux avec score >= 4 (assoupli, avant 5)
    _score_min = signal.get("score", 0)
    if _score_min < 4:
        print(f"  [SKIP] {signal.get('nom',signal['symbole'])} -> score {_score_min} < 4 (trop faible)")
        return False
    # SIZING DYNAMIQUE BASE SUR LE SENTIMENT ET LE SCORE
    # Le bot ajuste la taille de position selon le sentiment du marche:
    # - Score eleve + sentiment haussier = grosse position (jusqu'a 50%)
    # - Score faible + sentiment baissier = petite position (minimum 8%)
    # - Toujours avec SL/TP/trailing stop actifs
    try:
        from gestion_risque import calculer_taille
        montant, raison = calculer_taille(pf, signal, prix_actuel, signal.get("backtest_stats"))
        if montant <= 0:
            print(f"  [SKIP] {signal.get('nom',signal['symbole'])} -> pas de trade ({raison})")
            return False
        print(f"  [SIZING] {signal.get('nom',signal['symbole'])}: {raison}")
    except ImportError:
        _meta_taille = signal.get("meta_taille")
        _meta_conf = signal.get("meta_confiance", 0.5)
        if _meta_taille == "grande":
            montant = pf["liquidites"] * min(RISK_PAR_TRADE * 1.5, 0.30)
        elif _meta_taille == "petite":
            montant = pf["liquidites"] * RISK_PAR_TRADE * 0.5
        else:
            montant = pf["liquidites"] * RISK_PAR_TRADE
    except Exception as e:
        print(f"  [SIZING erreur {e}] fallback 8% fixe")
        montant = pf["liquidites"] * RISK_PAR_TRADE
    # SIZING ADAPTATIF SENTIMENT + SCORE
    # Base: 8% minimum, jusqu'a 50% maximum selon sentiment et conviction
    _base_size = pf["liquidites"] * RISK_PAR_TRADE  # 8% plancher
    _max_size = pf["liquidites"] * RISK_MAX_TRADE   # 50% plafond
    # Recupere le score du signal (1-10)
    _score = signal.get("score", 5)
    # Recupere le sentiment Fear & Greed
    _fg = 50  # defaut neutre
    try:
        from sentiment_marche import get_fear_greed
        _fg = get_fear_greed()
    except Exception:
        pass
    # Calcul du multiplicateur sentiment (0.5x a 3.0x)
    # Extreme Fear (0-25): x0.5 (prudent)
    # Fear (25-45): x0.8
    # Neutral (45-55): x1.0
    # Greed (55-75): x1.5 (confiant)
    # Extreme Greed (75-100): x2.0 (tres confiant)
    if _fg < 25:
        _sent_mult = 0.5
        _sent_label = "Extreme Fear"
    elif _fg < 45:
        _sent_mult = 0.8
        _sent_label = "Fear"
    elif _fg < 55:
        _sent_mult = 1.0
        _sent_label = "Neutral"
    elif _fg < 75:
        _sent_mult = 1.5
        _sent_label = "Greed"
    else:
        _sent_mult = 2.0
        _sent_label = "Extreme Greed"
    # Multiplicateur score (0.5x a 2.0x)
    # Score 1-3: x0.5 (signal faible)
    # Score 4-6: x1.0 (signal moyen)
    # Score 7-8: x1.5 (signal fort)
    # Score 9-10: x2.0 (signal tres fort)
    if _score <= 3:
        _score_mult = 0.5
    elif _score <= 6:
        _score_mult = 1.0
    elif _score <= 8:
        _score_mult = 1.5
    else:
        _score_mult = 2.0
    # Montant dynamique = base x sentiment x score
    _montant_dyn = _base_size * _sent_mult * _score_mult
    _montant_dyn = min(_montant_dyn, _max_size)  # plafond 50%
    _montant_dyn = max(_montant_dyn, _base_size)  # plancher 8%
    print(f"  [DYN-SIZE] {signal.get('nom',signal['symbole'])}: sentiment={_sent_label}({_fg:.0f}) x{_sent_mult} | score={_score} x{_score_mult} | {montant:.0f} -> {_montant_dyn:.0f}EUR")
    montant = _montant_dyn
    # FLASH-CRASH: reduire la taille si niveau de protection eleve
    try:
        import flash_crash as fc
        _niveau_fc = fc.get_niveau_protection()
        if _niveau_fc == 1:
            montant = montant * 0.7  # Vigilance: -30%
            print(f"  [FLASH] Niveau vigilance - taille reduite 30%")
        elif _niveau_fc >= 2:
            montant = 0  # Circuit breaker: pas de trade
            print(f"  [FLASH] Circuit breaker niveau {_niveau_fc} - trade bloque")
            return False
    except Exception:
        pass
    # FILTRE RÉGIME (méta-évolution): ajuste la taille selon le régime de marché.
    # En contagion baissière (crash), réduit la taille (floor ×0.10). Désactivable: REGIME_FILTER=0.
    if os.getenv("REGIME_FILTER", "1") != "0":
        try:
            from filtre_regime_vol_corr import ajuster_exposition
            from indicateurs import historique_ohlcv
            _sym = signal["symbole"]
            _is_crypto = signal.get("marche") == "crypto"
            _peer = "BTCUSDT" if _is_crypto and _sym != "BTCUSDT" else None
            _prices = [b["cloture"] for b in historique_ohlcv(_sym, "1h", 30) if b.get("cloture")]
            _peer_prices = None
            if _peer:
                _peer_prices = [b["cloture"] for b in historique_ohlcv(_peer, "1h", 30) if b.get("cloture")]
            if len(_prices) >= 5:
                _avant = montant
                montant, _meta = ajuster_exposition(montant, _prices, prices_peer=_peer_prices, window=20)
                if montant < _avant:
                    print(f"  [RÉGIME] {signal.get('nom', _sym)}: {_meta['regime']} risk={_meta['risk_score']:.2f} -> x{_meta['multiplier']:.2f} ({_avant:.0f}->{montant:.0f}EUR)")
        except ImportError:
            pass  # module filtre_regime absent -> sizing inchangé
        except Exception as _e:
            print(f"  [RÉGIME erreur {_e}] taille inchangée")
    # FILTRE SENTIMENT (Fear & Greed): sizing contrarian, crypto uniquement.
    # Achète plein en Extreme Fear (zone achat), réduit en Greed (euphorie = risque).
    # Compose avec le filtre régime: montant = base × régime × sentiment.
    # Désactivable: SENTIMENT_FILTER=0.
    if os.getenv("SENTIMENT_FILTER", "1") != "0" and signal.get("marche") == "crypto":
        try:
            from sentiment_marche import sentiment_multiplier
            _smult, _sclass = sentiment_multiplier()
            if _smult < 1.0:
                _avant = montant
                montant = montant * _smult
                print(f"  [SENTIMENT] {_sclass} -> x{_smult:.2f} ({_avant:.0f}->{montant:.0f}EUR)")
        except ImportError:
            pass  # module sentiment absent -> sizing inchangé
        except Exception as _e:
            print(f"  [SENTIMENT erreur {_e}] taille inchangée")
    # CONVICTION SIZING: amplifie les stratégies gagnantes éprouvées en live
    # (plus de bénéfices/trade sur ce qui marche déjà). Désactivable: CONVICTION_SIZING=0.
    _mult = 1.0  # default
    if os.getenv("CONVICTION_SIZING", "1") != "0":
        try:
            _cs = json.load(open("classement_strategies.json"))
            _mult, _craison = _conviction_mult(signal, _cs)
            # PALIER PROGRESSIF: +0.5 par palier de +5% de PnL (auto-protectif, seulement sur gagnants prouvés)
            _niv, _bonus, _pnl_pct = _niveau_performance(pf)
            if _mult > 1.0 and _bonus > 0:
                _mult = _mult + _bonus
                _craison += f" +palier{_niv}(PnL {_pnl_pct:+.1f}%)"
            if _mult != 1.0:
                _avant = montant
                montant = montant * _mult
                print(f"  [CONVICTION] {signal.get('nom', signal['symbole'])}: x{_mult:.2f} {_craison} ({_avant:.0f}->{montant:.0f}EUR)")
        except FileNotFoundError:
            pass  # classement pas encore créé -> sizing par défaut
        except Exception as _e:
            print(f"  [CONVICTION erreur {_e}] taille inchangée")
    # PLUGINS (méta-évolution): hooks de sizing (ajustent la taille).
    if os.getenv("PLUGINS_ACTIVE", "1") != "0":
        try:
            for _fn, _mod in _plugins_charges:
                if hasattr(_mod, "hook_sizing"):
                    try:
                        _avant = montant
                        montant = _mod.hook_sizing(pf, signal, montant, prix_actuel)
                        if montant != _avant:
                            print(f"  [PLUGIN {_fn}] sizing {_avant:.0f}->{montant:.0f}EUR")
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_sizing erreur: {_e}")
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "error")
                        except Exception:
                            pass
        except Exception:
            pass
    # ANTI-CORRELATION: si on a deja une position sur un actif correle, on reduit
    try:
        from gestion_risque import GROUPES_CORRELES
    except ImportError:
        GROUPES_CORRELES = []
    sym = signal["symbole"]
    _nb_correl = 0
    for p in pf.get("positions", []):
        for groupe in GROUPES_CORRELES:
            if sym in groupe and p["symbole"] in groupe and sym != p["symbole"]:
                _nb_correl += 1
                break
    if _nb_correl >= 2:
        print(f"  [CORREL] {signal.get('nom',sym)}: deja {_nb_correl} positions correlees -> skip")
        return False
    elif _nb_correl == 1:
        montant = montant * 0.5  # reduit de 50% si 1 position correlee
        print(f"  [CORREL] {signal.get('nom',sym)}: 1 position correlee -> x0.5 ({montant:.0f}EUR)")
    # DRAWDOWN REDUCTION: si capital < 95% du initial, reduit les positions de 50%
    capital_actuel = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
    if capital_actuel < pf.get("capital_initial", 1000) * DRAWDOWN_REDUCTION_SEUIL:
        montant = montant * 0.5
        print(f"  [DRAWDOWN] Capital {capital_actuel:.0f}EUR < {DRAWDOWN_REDUCTION_SEUIL*100:.0f}% initial -> x0.5 ({montant:.0f}EUR)")
    # CONFLUENCE SIZING: si 2+ strategies signalent ACHAT, position plus grosse
    nb_conf = signal.get("confluence", 1)
    if nb_conf >= 2:
        montant = montant * min(nb_conf, 3)  # 2 strats=x2, 3 strats=x3, 4+=x3
        print(f"  [CONFLUENCE] {signal.get('nom',signal['symbole'])}: {nb_conf} strategies -> x{min(nb_conf,3)} sizing ({montant:.0f}EUR)")
    # (Sizing deja calcule ci-dessus via DYN-SIZE + filtres)
    # POIDS STRATEGIES (anti-surapprentissage): ajuste la taille selon le poids
    # de la stratégie. Une stratégie forte (poids > 0.40) obtient +50% de taille,
    # une stratégie faible (poids < 0.20) obtient -50% de taille.
    _poids_strat = signal.get("poids_strat", 0.20)
    if _poids_strat > 0.40:
        montant = montant * 1.5
        print(f"  [POIDS STRAT SIZE] stratégie forte (poids {_poids_strat:.2f}) -> x1.5 ({montant:.0f}EUR)")
    elif _poids_strat < 0.20:
        montant = montant * 0.5
        print(f"  [POIDS STRAT SIZE] stratégie faible (poids {_poids_strat:.2f}) -> x0.5 ({montant:.0f}EUR)")
    # SIZING ADAPTATIF SELON LE SPREAD Revolut X
    # Plus le spread est large, plus la position est reduite (liquidite faible = SL-RETARD)
    # Le bot apprend: ATOM (spread 200%) = position x0.1, BTC (spread 0.2%) = position x1.0
    if montant > 0 and signal.get("marche") == "crypto":
        try:
            import prix_revolut as pr
            _spread = pr.get_spread_pct(signal["symbole"])
            if _spread >= 100:
                # Spread absurde (>100%) = ne pas trader
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> trade bloque (illiquide)")
                return False
            elif _spread >= 50:
                _facteur = 0.1  # position reduite a 10%
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> position x{_facteur} ({montant*_facteur:.0f}EUR)")
                montant = montant * _facteur
            elif _spread >= 20:
                _facteur = 0.25  # position reduite a 25%
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> position x{_facteur} ({montant*_facteur:.0f}EUR)")
                montant = montant * _facteur
            elif _spread >= 10:
                _facteur = 0.5  # position reduite a 50%
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> position x{_facteur} ({montant*_facteur:.0f}EUR)")
                montant = montant * _facteur
            elif _spread >= 5:
                _facteur = 0.75  # position reduite a 75%
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> position x{_facteur} ({montant*_facteur:.0f}EUR)")
                montant = montant * _facteur
            else:
                print(f"  [SPREAD] {signal['symbole']}: spread {_spread:.1f}% -> position pleine ({montant:.0f}EUR)")
        except Exception:
            pass
    # Clamp de securite: ne pas depasser le liquide dispo, ne pas aller negatif
    # Pas de plancher fixe - le sizing dynamique decide (sentiment + score)
    # Mais on garde un minimum de 5% pour eviter les micro-positions inutiles
    if montant > 0 and pf["liquidites"] >= 80:
        _min_absolu = pf["liquidites"] * 0.05  # 5% minimum absolu
        montant = max(_min_absolu, min(montant, pf["liquidites"]))
    if montant <= 0:
        return False
    if pf["liquidites"] < 80:
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
        "strategie": signal.get("strategie") or signal.get("source") or "inconnu",
        "pattern_bougie": _pattern_info,
        # Intelligence pro
        "tp_adaptatif": signal.get("tp_adaptatif"),
        "sl_adaptatif": signal.get("sl_adaptatif"),
        "intel_score": signal.get("intel_score"),
        "intel_fg": signal.get("intel_fg"),
        "intel_regime": signal.get("intel_regime"),
        "mtf_confirmation": signal.get("mtf_confirmation"),
    }
    pf["positions"].append(position)
    print(f"  [ACHAT] {signal.get('nom',signal['symbole'])} ({signal.get('marche','?')}) @ {prix_actuel:.2f} | {montant:.2f} EUR | qty {quantite:.6f}")
    # Notif Telegram: prévient qu'une stratégie a ouvert une position
    try:
        from telegram_alerte import envoyer as _tg_envoyer
        _conv = ""
        try:
            if _mult and _mult != 1.0:
                _conv = f" (conviction x{_mult:.2f})"
        except Exception:
            pass
        _tg_envoyer(f"📈 Position ouverte{_conv}\n"
                    f"Stratégie: {position.get('strategie', '?')}\n"
                    f"Actif: {position['nom']} ({position.get('marche','?')})\n"
                    f"Prix: {prix_actuel:.2f} | Montant: {montant:.2f} EUR\n"
                    f"Raison: {signal.get('raison', '')}")
    except Exception:
        pass
    notify_ifft("Paper Trade ACHAT", f"Achat {signal.get('nom','?')} @ {prix_actuel:.2f} EUR")
    return True

def verifier_sorties(pf, prix_actuels):
    positions_a_fermer = []
    maintenant = datetime.now()
    # Stratégies prouvées (pour bonus de durée): chargé une fois par cycle
    _strats_prouvees = set()
    try:
        _cs = json.load(open("classement_strategies.json"))
        for _symc, _datac in _cs.items():
            for _sc in _datac.get("strategies", []):
                if _sc.get("live_n", 0) >= 3 and _sc.get("live_wr", 0) >= 60 and _sc.get("live_pnl", 0) > 0:
                    _strats_prouvees.add((_symc, _sc.get("strategie", "")))
    except Exception:
        pass
    for pos in pf["positions"]:
        sym = pos["symbole"]
        if sym not in prix_actuels:
            continue
        prix_actuel = prix_actuels[sym]
        prix_entree = pos["prix_entree"]
        # Sanity check: si prix invalide (0 ou negative), skip pour éviter fermeture erronee
        # MAIS on ferme quand meme si la perte est enorme (> -SL% = le SL aurait du etre touche depuis longtemps)
        if not prix_actuel or prix_actuel <= 0:
            print(f"  [PRIX INVALIDE] {sym}: prix={prix_actuel} — position preservee")
            continue
        if prix_entree <= 0:
            print(f"  [PRIX ENTREE INVALIDE] {sym}: prix_entree={prix_entree} — skip")
            continue
        variation = (prix_actuel - prix_entree) / prix_entree * 100
        # Recupere le SL applicable (avant la detection de position piegee)
        # Priorite: TP/SL adaptatif intelligence_pro > meta_tuning > constantes globales
        _tp_adapt = pos.get("tp_adaptatif")
        _sl_adapt = pos.get("sl_adaptatif")
        if os.getenv('SCALPING', '0') == '1':
            _tp_check, _sl_check = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        elif _tp_adapt and _sl_adapt:
            _tp_check, _sl_check = _tp_adapt, _sl_adapt
        else:
            try:
                from meta_tuning import tp_sl_actif
                _tp_check, _sl_check = tp_sl_actif(sym)
            except Exception:
                _tp_check, _sl_check = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        # DETECTION POSITION PIEGEE: si la perte depasse le SL, le SL aurait du etre touche
        # On ferme immediatement (le prix a chute trop, la position est morte)
        if variation <= -_sl_check:
            positions_a_fermer.append((pos, prix_actuel, f"SL-RETARD (perte {variation:+.1f}%, SL={_sl_check}%)", variation))
            continue
        # TP/SL: en mode scalping, les constantes globales priment sur meta_tuning
        if os.getenv('SCALPING', '0') == '1':
            _tp, _sl = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        elif _tp_adapt and _sl_adapt:
            _tp, _sl = _tp_adapt, _sl_adapt
        else:
            try:
                from meta_tuning import tp_sl_actif
                _tp, _sl = tp_sl_actif(sym)
            except Exception:
                _tp, _sl = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        # TP DYNAMIQUE ATR: adapte le TP selon la volatilité de l'actif
        try:
            from indicateurs import historique_ohlcv
            _bougies = historique_ohlcv(sym, "1h", ATR_LOOKBACK + 1)
            if _bougies and len(_bougies) >= ATR_LOOKBACK:
                _trs = []
                for i in range(1, len(_bougies)):
                    h = _bougies[i]["haut"]
                    l = _bougies[i]["bas"]
                    c_prev = _bougies[i-1]["cloture"]
                    _tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
                    _trs.append(_tr)
                if _trs:
                    _atr = sum(_trs) / len(_trs)
                    _px = pos.get("prix_entree", prix_actuel)
                    if _px > 0:
                        _atr_pct = (_atr / _px) * 100
                        _tp_atr = _atr_pct * ATR_TP_MULT
                        _tp = max(ATR_TP_MIN, min(_tp_atr, ATR_TP_MAX))
        except Exception:
            pass
        # EXTEND_TP (valide backtest +13.35% crypto): si position crypto en profit
        # >= +0.5%, on monte le TP a 4.0% pour laisser courir les gagnants.
        # SL fixe (pas de breakeven). Forex/or/matieres: TP fixe (non valide).
        extend_actif = sym in EXTEND_CRYPTOS and variation >= EXTEND_SEUIL
        if extend_actif:
            _tp = EXTEND_TP_PCT
        # === STOP SUIVEUR PROGRESSIF + TP DYNAMIQUE ===
        # Le trailing se rapproche du pic au fur et a mesure que le gain augmente
        # Plus le trade gagne, plus le stop serre pour proteger les benefices
        _sl_regle = "fixe"
        _pic = pos.get("prix_peak", prix_entree)
        if prix_actuel > _pic:
            _pic = prix_actuel
            pos["prix_peak"] = _pic
        _var_pic = (_pic - prix_entree) / prix_entree * 100
        if _var_pic >= 6.0:
            # Tres en profit: trail serre a 0.5% sous le pic (protege fortement)
            _sl_price = _pic * (1 - 0.5 / 100.0)
            _sl_regle = "suiveur-serre"
        elif _var_pic >= 4.0:
            # Bien en profit: trail a 1.0% sous le pic
            _sl_price = _pic * (1 - 1.0 / 100.0)
            _sl_regle = "suiveur-proche"
        elif _var_pic >= 2.5:
            # En profit: trail a 1.5% sous le pic (laisse respirer vers le TP)
            _sl_price = _pic * (1 - 1.5 / 100.0)
            _sl_regle = "suiveur"
        else:
            # SL fixe au debut (laisse respirer vers le TP de +3%)
            _sl_price = prix_entree * (1 - _sl / 100.0)
        # TP DYNAMIQUE PROGRESSIF: quand le prix atteint le TP, on le monte de plus en plus
        # Le trade court tant que la tendance haussiere continue
        # Chaque palier monte le TP de plus en plus pour capturer les gros gains
        _tp_actuel = pos.get("tp_dynamique", _tp)
        if variation >= _tp_actuel:
            # Plus le gain est eleve, plus le TP monte loin
            if _tp_actuel >= 7.0:
                _tp_actuel = _tp_actuel + 2.0  # +2% par palier au-dela de +7%
            elif _tp_actuel >= 5.0:
                _tp_actuel = _tp_actuel + 1.5  # +1.5% par palier au-dela de +5%
            else:
                _tp_actuel = _tp_actuel + 1.0  # +1% par palier au debut
            pos["tp_dynamique"] = _tp_actuel
            print(f"  [TP-EXTEND] {sym}: TP monte a +{_tp_actuel:.1f}% (pic {_var_pic:+.1f}%, stop {_sl_regle})")
        # Partial take-profit: encaisse 50% a +2.5%, le reste court indéfiniment
        if variation >= PARTIAL_TP_SEUIL and not pos.get("partiellement_clote"):
            fermer_position_partielle(pf, pos, prix_actuel, PARTIAL_FRACTION, "PARTIAL-TP", variation)
        # HARD STOP D'URGENCE: si la perte dépasse 1.5x le SL, ferme immédiatement
        # Evite les SL-RETARD de -2% à -3% quand le prix gap entre deux checks
        if variation <= -(_sl * 1.5):
            positions_a_fermer.append((pos, prix_actuel, f"SL-URGENCE ({variation:+.2f}%, SL={_sl}%)", variation))
            continue
        # GESTION POSITION LIVE: analyse adaptative en temps réel
        try:
            from gestion_position_live import analyser_position_live
            _action, _raison = analyser_position_live(pos, prix_actuel)
            if _action == "FERMER":
                positions_a_fermer.append((pos, prix_actuel, f"LIVE-EXIT: {_raison}", variation))
                continue
            elif _action == "PARTIAL_TP" and not pos.get("partiellement_clote"):
                fermer_position_partielle(pf, pos, prix_actuel, 0.5, f"LIVE-PARTIAL: {_raison}", variation)
                print(f"  [LIVE] {sym}: {_raison}")
            elif _action == "TIGHTEN_SL":
                # Serrer le SL au breakeven ou plus proche du prix actuel
                _new_sl_pct = max(0.3, variation - 0.5)
                _new_sl_price = prix_actuel * (1 - _new_sl_pct / 100.0)
                if _new_sl_price > _sl_price:
                    _sl_price = _new_sl_price
                    _sl_regle = "live-tight"
                    print(f"  [LIVE] {sym}: SL resserré → {_new_sl_pct:.1f}% sous le prix actuel")
            elif _action == "HOLD":
                print(f"  [LIVE] {sym}: HOLD - {_raison}")
        except ImportError:
            pass
        except Exception as _e:
            print(f"  [LIVE] {sym}: erreur analyse ({_e})")
        # Fermeture au SL suiveur (1% sous le pic) — le seul point de sortie
        if prix_actuel <= _sl_price:
            positions_a_fermer.append((pos, prix_actuel, f"STOP-SUIVEUR (pic {_var_pic:+.1f}%, ferme a {variation:+.1f}%)", variation))
        # Sortie intelligente: fermer si pattern baissier detecte (en profit)
        elif variation > 0 and os.getenv("SMART_EXIT", "0") == "1":
            try:
                from candlestick_learning import analyser_avec_apprentissage
                _se = analyser_avec_apprentissage(sym)
                if _se["direction"] == "bearish" and _se["score_apprentissage"] <= -0.3:
                    _pats = ", ".join(p["pattern"] for p in _se.get("patterns", []))
                    positions_a_fermer.append((pos, prix_actuel, f"SMART-EXIT ({_pats})", variation))
            except Exception:
                pass
        else:
            # FERMETURE INTELLIGENTE: position perdante qui stagne
            try:
                dt_ouv = datetime.strptime(pos.get("date_ouverture", ""), "%Y-%m-%d %H:%M")
                age_min = (maintenant - dt_ouv).total_seconds() / 60
                if variation <= STAGNATION_PERTE_SEUIL and age_min >= STAGNATION_PERTE_DUREE:
                    positions_a_fermer.append((pos, prix_actuel, f"CUT-STAGNATION ({variation:+.2f}% après {age_min:.0f}min)", variation))
                    continue
            except Exception:
                pass
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
                # RESPIRATION ADAPTATIVE: plus c'est gagnant, plus ça respire
                # (pour laisser le temps d'atteindre partial TP +1% / trailing / TP)
                if os.getenv("EXIT_AVANCE", "1") != "0":
                    if variation >= BREAKEVEN_SEUIL:        # >= 0.60% : protégé, respire 4h
                        duree_min = max(duree_min, DUREE_GAGNANT_MAX)
                    elif variation >= 0.45:                 # bon gain non protégé: respire 3h
                        duree_min = max(duree_min, DUREE_GAIN_PROGRESS)
                    elif variation >= SEUIL_BENEFICE_MIN:   # petit gain: respire 2h
                        duree_min = max(duree_min, DUREE_PETIT_GAIN)
                    # Bonus stratégie prouvée: +1h (laisse plus de temps aux stratégies qui gagnent)
                    if (sym, pos.get("strategie", "")) in _strats_prouvees:
                        duree_min += DUREE_BONUS_STRATEGIE
                # TIME-STOP STALE: position sous seuil depuis trop longtemps -> libère le capital
                # (fixe les positions bloquées plates, ex EURUSD à 0% qui n atteint jamais +0.30%)
                # ANTI-FRAIS: ne ferme pas si le gain net apres frais est negatif
                # (frais 0.2% AR). Ferme seulement si variation > 0.2% ou perte > -1%
                if age_min >= STALE_DUREE_MAX and variation < seuil_min:
                    if variation >= 0.2 or variation <= -1.0:
                        positions_a_fermer.append((pos, prix_actuel, f"TEMPS-stale ({variation:+.2f}%)", variation))
                    else:
                        print(f"  [ANTI-FRAIS] {sym}: garde position ({variation:+.2f}%) - gain net apres frais negatif")
                elif age_min >= duree_min and variation >= seuil_min:
                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))
            except Exception:
                pass
    for pos, prix, raison, var in positions_a_fermer:
        fermer_position(pf, pos, prix, raison, var)
    return len(positions_a_fermer) > 0

def fermer_position_partielle(pf, position, prix_actuel, fraction, raison, variation):
    """Clôture une FRACTION de la position (partial take-profit).
    Réalise le gain sur la partie vendue, réduit quantité + cost-basis,
    garde la position OUVERTE (le reste ride le trailing stop)."""
    if fraction <= 0 or fraction >= 1.0:
        return
    quantite_vendue = position["quantite"] * fraction
    if quantite_vendue <= 0:
        return
    montant_recu = quantite_vendue * prix_actuel
    frais = montant_recu * FRAIS_TRANSACTION
    pf["liquidites"] += montant_recu - frais
    pf["total_frais"] += frais
    cout_partie = position["montant_eur"] * fraction   # cost-basis de la partie vendue
    gain = (montant_recu - frais) - cout_partie
    # réduit la position (le reste reste ouvert)
    position["quantite"] -= quantite_vendue
    position["montant_eur"] -= cout_partie
    position["partiellement_clote"] = True
    trade = {
        "symbole": position["symbole"],
        "nom": position.get("nom", position["symbole"]),
        "marche": position.get("marche", "?"),
        "prix_entree": position["prix_entree"],
        "prix_sortie": prix_actuel,
        "quantite": quantite_vendue,
        "montant_eur": cout_partie,
        "gain_eur": gain,
        "variation_pct": variation,
        "raison": raison,
        "signal_raison": position.get("signal_raison", ""),
        "strategie": position.get("strategie", position.get("source", "")),
        "source": position.get("source", "") + "_PARTIAL",
        "frais_total": position["frais_entree"] * fraction + frais,
        "date_ouverture": position["date_ouverture"],
        "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    pf["trades_fermes"].append(trade)
    print(f"  [PARTIAL-TP] {position['symbole']}: {fraction*100:.0f}% @ {variation:+.2f}% (gain {gain:+.2f}€) | reste {position['quantite']:.6f} en position")


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
    # Circuit breaker: track pertes consecutives
    if gain < 0:
        pf["pertes_consecutives"] = pf.get("pertes_consecutives", 0) + 1
    else:
        pf["pertes_consecutives"] = 0
    # Phase 2: met a jour le pic de capital pour le drawdown scaler
    _cap_total = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
    pf["pic_capital"] = max(pf.get("pic_capital", pf.get("capital_initial", 1000.0)), _cap_total)
    print(f"  [{raison}] {position.get('nom',position['symbole'])} @ {prix_actuel:.2f} | var {variation:+.2f}% | gain {gain:+.2f} EUR")
    notify_ifft("Paper Trade fermeture", f"{raison} {position.get('nom','?')} var {variation:+.2f}%")
    # Apprentissage bougies: enregistre le résultat du pattern pour apprendre
    try:
        _pi = position.get("pattern_bougie")
        if _pi and _pi.get("patterns"):
            from candlestick_learning import enregistrer_resultat
            for _pat in _pi["patterns"]:
                enregistrer_resultat(_pat["pattern"], position["symbole"], variation, _pat["direction"])
            print(f"  [BOUGIES] Apprentissage enregistré pour {position['symbole']}")
    except Exception:
        pass
    # === APPRENTISSAGE TRADER: analyser le trade ferme pour apprendre ===
    try:
        import apprentissage_trader as ap
        trades = pf.get("trades_fermes", [])
        if trades and len(trades) % 3 == 0:
            ap.analyser_trades(trades)
            print(f"  [LEARNING] Apprentissage mis a jour ({len(trades)} trades analyses)")
    except Exception as e:
        print(f"  [LEARNING] Erreur: {e}")
    # === TRADER PRO: apprendre du resultat du trade ===
    try:
        import trader_pro as tp_module
        score_pro = position.get("score_pro", 0)
        if score_pro != 0:
            tp_module.apprendre_erreur(position["symbole"], score_pro, gain, position.get("facteurs_pro", {}))
            print(f"  [PRO] Apprentissage: {position['symbole']} resultat={gain:+.2f}€ (score initial {score_pro:+.1f})")
    except Exception as e:
        print(f"  [PRO] Erreur apprentissage: {e}")
    # === MASTER TRADERS: apprendre du resultat du trade ===
    try:
        import master_traders as mt
        score_mt = position.get("score_maitres", 0)
        if score_mt != 0:
            votes = {k: v for k, v in position.items() if k.startswith("vote_")}
            mt.apprendre_trade(position["symbole"], score_mt, gain, votes or None)
            print(f"  [MAITRES] Apprentissage: {position['symbole']} resultat={gain:+.2f}€ (consensus {score_mt:+.2f})")
    except Exception as e:
        print(f"  [MAITRES] Erreur apprentissage: {e}")
    # === MASTER TRADERS: ameliorer les parametres des strategies ===
    try:
        import master_traders as mt
        _, ameliorations = mt.ameliorer_strategies()
        if ameliorations and ameliorations != "Aucune amelioration necessaire":
            print(f"  [MAITRES] Strategies ameliorees: {ameliorations}")
    except Exception as e:
        print(f"  [MAITRES] Erreur amelioration: {e}")
    # === AUTO-EVOLUTION: memoriser le trade dans la memoire profonde ===
    try:
        import auto_evolution as ae
        conditions = {
            "score_maitres": position.get("score_maitres", 0),
            "intel_score": position.get("intel_score", 0),
            "mtf_confirmation": 1 if position.get("mtf_confirmation") == "CONFIRME_ACHAT" else 0,
            "fear_greed": position.get("intel_fg", 50),
        }
        ae.memoriser_trade(
            symbole=position["symbole"],
            strategie=position.get("strategie", ""),
            gain=gain,
            gain_pct=variation,
            conditions=conditions,
            pattern_bougie=position.get("pattern_bougie", ""),
            regime=position.get("intel_regime", ""),
            fear_greed=position.get("intel_fg", 50),
        )
        # Mettre a jour le fitness de la strategie dans le genome
        genome = ae.charger_genome()
        strat_nom = position.get("strategie", "")
        for s in genome.get("strategies", []):
            if s.get("nom", "") in strat_nom or strat_nom in s.get("nom", ""):
                s["trades"] += 1
                if gain > 0:
                    s["gagnants"] += 1
                s["pnl"] += gain
                break
        ae.sauver_genome(genome)
    except Exception as e:
        print(f"  [EVOL] Erreur memoire: {e}")

# ============================================
# CYCLE PRINCIPAL
# ============================================
def tick():
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise. Lance 'python paper_trading.py init' d'abord.")
        return
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Verification des prix...")
    # === RISK MANAGEMENT AVANCE ===
    # 1. Perte journaliere max
    trades_aujourdhui = [t for t in pf.get("trades_fermes", []) if t.get("date_fermeture", "").startswith(datetime.now().strftime("%Y-%m-%d"))]
    pnl_jour = sum(t.get("gain_eur", 0) for t in trades_aujourdhui)
    capital_actuel = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))
    if capital_actuel > 0 and pnl_jour < -(capital_actuel * PERTE_JOUR_MAX_PCT / 100):
        print(f"  [RISK] Perte journaliere {pnl_jour:.2f}EUR > -{PERTE_JOUR_MAX_PCT}% -> STOP TRADING")
        return
    # 2. Circuit breaker 3 pertes consecutives
    _cb = pf.get("circuit_breaker", {})
    if not isinstance(_cb, dict):
        _cb = {}
    pertes_consec = _cb.get("consecutive_losses", pf.get("pertes_consecutives", 0))
    if pertes_consec >= CIRCUIT_BREAKER_CONSECUTIF:
        print(f"  [RISK] Circuit breaker: {pertes_consec} pertes consecutives -> PAUSE")
        return
    # 3. Heures de faible liquidite
    heure_utc = datetime.now(timezone.utc).hour
    for h_debut, h_fin in HEURES_FAIBLE_LIQUIDITE:
        if h_debut <= heure_utc < h_fin:
            print(f"  [RISK] Heure de faible liquidite ({h_debut}h-{h_fin}h UTC) -> skip nouveaux trades")
            break
    else:
        # 4. Limite trades par jour
        if len(trades_aujourdhui) >= MAX_TRADES_PAR_JOUR:
            print(f"  [RISK] Max {MAX_TRADES_PAR_JOUR} trades/jour atteint -> skip")
            return
    prix = tous_les_prix()
    if not prix:
        print("Impossible de recuperer les prix.")
        return
    # Stocke l'historique des prix pour les filtres MTF/PULLBACK
    try:
        import historique_prix as hp
        hp.stocker_prix(prix)
    except Exception:
        pass
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
        from collections import Counter
        nb_par_actif = Counter(pos["symbole"] for pos in pf["positions"])
        print("\nAnalyse strategies gagnantes (backtest reel)...")
        signaux_gagnants = []
        try:
            import signaux_gagnants as sg
            signaux_gagnants = sg.generer_signaux_gagnants(prix, MARCHES_PAPER)
        except Exception as e:
            print(f"    Module signaux_gagnants indisponible: {e}")
        tous_signaux = list(signaux_gagnants)
        # Fallback: si aucune strategie gagnante ne signale, on utilise les indicateurs techniques
        if not tous_signaux:
            print("\nAucun signal gagnant -> indicateurs techniques...")
            signaux_techniques = analyser_signaux_techniques(prix)
            tous_signaux = signaux_techniques
        # En dernier recours: l'IA (rare)
        if not tous_signaux:
            print("\nAucun signal technique -> analyse IA (fallback)...")
            signaux_ia = analyser_signaux_ia(prix)
            tous_signaux = signaux_ia
        if tous_signaux:
            # === APPRENTISSAGE: filtrer les signaux avec l'apprentissage ===
            try:
                import apprentissage_trader as ap
                signaux_avant_app = len(tous_signaux)
                tous_signaux = ap.filtrer_signaux_avec_apprentissage(tous_signaux)
                if len(tous_signaux) < signaux_avant_app:
                    # Restaurer les signaux bloques mais avec score reduit
                    print(f"  [APPRENTISSAGE] {signaux_avant_app - len(tous_signaux)} signaux filtres")
            except Exception as e:
                print(f"    Apprentissage indisponible: {e}")
            # === TRADER PRO: score multi-facteurs comme un pro ===
            try:
                import trader_pro as tp_module
                signaux_pro = []
                for sig in tous_signaux:
                    sym = sig.get("symbole", "")
                    prix_sig = sig.get("prix_entree", 0)
                    if not sym or not prix_sig:
                        signaux_pro.append(sig)
                        continue
                    score_pro, details_pro, reco_pro, params_pro = tp_module.score_opportunite(sym, prix_sig)
                    sig["score_pro"] = score_pro
                    sig["score_pro_details"] = details_pro
                    sig["reco_pro"] = reco_pro
                    if params_pro.get("tp"):
                        sig["tp_optimal_pro"] = params_pro["tp"]
                    if params_pro.get("sl"):
                        sig["sl_optimal_pro"] = params_pro["sl"]
                    if reco_pro in ["ACHAT", "ACHAT_FORT", "ATTENDRE"]:
                        if reco_pro == "ACHAT_FORT":
                            sig["score"] = sig.get("score", 0) + 3
                            print(f"  [PRO] {sym}: ACHAT_FORT (score {score_pro:+.1f})")
                        elif reco_pro == "ACHAT":
                            sig["score"] = sig.get("score", 0) + 1
                            print(f"  [PRO] {sym}: ACHAT (score {score_pro:+.1f})")
                        else:
                            print(f"  [PRO] {sym}: NEUTRE - laisse passer (score {score_pro:+.1f})")
                        signaux_pro.append(sig)
                    else:
                        print(f"  [PRO] {sym}: SKIP - {reco_pro} (score {score_pro:+.1f})")
                tous_signaux = signaux_pro
            except Exception as e:
                print(f"    Trader pro indisponible: {e}")
            # === MULTI-AGENTS IA: 4 agents débattent et ajustent le score ===
            try:
                import agents_consensus as ac
                signaux_avant_agents = len(tous_signaux)
                tous_signaux = ac.enrichir_signaux(tous_signaux, prix, pf.get("positions", []))
                if len(tous_signaux) < signaux_avant_agents:
                    print(f"  [AGENTS] {signaux_avant_agents - len(tous_signaux)} signal(aux) filtré(s) par le consensus IA")
            except Exception as e:
                print(f"    Multi-agents indisponible: {e}")
            # === MASTER TRADERS: consensus des 10 plus grands traders ===
            try:
                import master_traders as mt
                signaux_maitres = []
                for sig in tous_signaux:
                    sym = sig.get("symbole", "")
                    if not sym:
                        signaux_maitres.append(sig)
                        continue
                    score_mt, details_mt, reco_mt, extra_mt = mt.consensus_maitres(sym)
                    sig["score_maitres"] = score_mt
                    sig["reco_maitres"] = reco_mt
                    sig["patterns_bougies"] = extra_mt.get("patterns", "")
                    # Le consensus des maitres ajuste le score
                    if reco_mt == "ACHAT_FORT":
                        sig["score"] = sig.get("score", 0) + 4
                        print(f"  [MAITRES] {sym}: ACHAT_FORT (consensus {score_mt:+.2f}) - {extra_mt.get('patterns','')}")
                    elif reco_mt == "ACHAT":
                        sig["score"] = sig.get("score", 0) + 2
                        print(f"  [MAITRES] {sym}: ACHAT (consensus {score_mt:+.2f})")
                    elif reco_mt == "ATTENDRE":
                        print(f"  [MAITRES] {sym}: NEUTRE (consensus {score_mt:+.2f})")
                    elif reco_mt == "NE_PAS_ACHETER":
                        print(f"  [MAITRES] {sym}: SKIP - {reco_mt} (consensus {score_mt:+.2f})")
                        continue
                    elif reco_mt == "VENTE":
                        print(f"  [MAITRES] {sym}: SKIP - VENTE (consensus {score_mt:+.2f})")
                        continue
                    else:  # Donnees insuffisantes ou erreur API - laisser passer
                        print(f"  [MAITRES] {sym}: passe-temps (donnees insuffisantes)")
                    signaux_maitres.append(sig)
                tous_signaux = signaux_maitres
            except Exception as e:
                print(f"    Master traders indisponible: {e}")
            # === INTELLIGENCE PRO: Fear&Greed, regime, multi-timeframe, correlation, TP/SL adaptatifs ===
            try:
                import intelligence_pro as ip
                signaux_intel = []
                fg = ip.get_fear_greed()
                regime, regime_detail, regime_score = ip.regime_global()
                ajustements_regime = ip.strategie_par_regime(regime)
                print(f"  [INTEL] Fear&Greed: {fg.get('value',50)} ({fg.get('classification','')}) | Regime: {regime}")
                for sig in tous_signaux:
                    sym = sig.get("symbole", "")
                    if not sym:
                        signaux_intel.append(sig)
                        continue
                    # Multi-timeframe
                    mtf_score, mtf_conf, mtf_scores, mtf_details = ip.analyse_multi_timeframe(sym)
                    sig["mtf_score"] = mtf_score
                    sig["mtf_confirmation"] = mtf_conf
                    # Fear & Greed
                    fg_score, fg_detail = ip.fear_greed_score()
                    # TP/SL adaptatifs
                    tp_adapt, sl_adapt = ip.tp_sl_adaptatifs(sig.get("score_maitres", 0), regime, fg.get("value", 50))
                    sig["tp_adaptatif"] = tp_adapt
                    sig["sl_adaptatif"] = sl_adapt
                    # Diversification (correlation)
                    div_ok, div_detail = ip.verifier_diversification(sym, pf.get("positions", []))
                    if not div_ok:
                        print(f"  [INTEL] {sym}: SKIP - {div_detail}")
                        continue
                    # Score intelligence
                    bonus_intel = fg_score * 0.5 + regime_score * 1.0 + mtf_score * 1.5
                    sig["score"] = sig.get("score", 0) + bonus_intel
                    sig["intel_score"] = bonus_intel
                    sig["intel_fg"] = fg.get("value", 50)
                    sig["intel_regime"] = regime
                    if mtf_conf == "CONFIRME_ACHAT":
                        print(f"  [INTEL] {sym}: MTF confirme achat ({mtf_score:+.1f}), TP={tp_adapt}% SL={sl_adapt}%")
                    elif mtf_conf == "CONFIRME_VENTE":
                        print(f"  [INTEL] {sym}: MTF contredit (vente) - score reduit")
                    signaux_intel.append(sig)
                tous_signaux = signaux_intel
            except Exception as e:
                print(f"    Intelligence pro indisponible: {e}")
            # === SUPER INTELLIGENCE: DESACTIVE (erreurs 429/401/403 sur toutes les sources API) ===
            # TODO: reactiver quand API keys validees
            # === WEB GLOBAL: DESACTIVE (meme problemes d'API) ===
            # === CONSENSUS MULTI-IA: DESACTIVE (429 sur Gemini + Perplexity) ===
            # === SENTIMENT SOCIAL: DESACTIVE (Reddit 403, Fear&Greed OK mais pas critique) ===
            # === MULTI-TIMEFRAME: DESACTIVE (429 sur OHLC Revolut X) ===
            # === DIVERSIFICATION TEMPORELLE: boost le score pendant les heures a fort volume ===
            _heure_utc_now = datetime.now(timezone.utc).hour
            _boost_heure = False
            for _h_deb, _h_fin in HEURES_FORT_VOLUME:
                if _h_deb <= _heure_utc_now < _h_fin:
                    _boost_heure = True
                    break
            if _boost_heure:
                for sig in tous_signaux:
                    sig["score"] = sig.get("score", 0) + HEURES_FORT_BOOST
                print(f"  [TEMPS] Heure fort volume ({_heure_utc_now}h UTC) -> +{HEURES_FORT_BOOST} score")
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
                if len(pf["positions"]) >= MAX_POSITIONS:
                    break  # plus de slots disponibles
                if nb_par_actif[signal["symbole"]] < MAX_POS_PAR_ACTIF:
                    if ouvrir_position(pf, signal, prix[signal["symbole"]]):
                        nb_par_actif[signal["symbole"]] += 1
        else:
            print("\nAucun signal d'achat.")
    pf["dernier_tick"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    sauver_portefeuille(pf)
    afficher_solde(pf, prix)
    # === AUTO-EVOLUTION: toutes les 6h, lancer l'evolution complete ===
    try:
        evol_data = json.load(open(os.path.join(DOSSIER, "auto_evolution.json")))
        derniere = evol_data.get("derniere_evolution", "")
        if derniere:
            dt_derniere = datetime.strptime(derniere, "%Y-%m-%d %H:%M")
            if (datetime.now() - dt_derniere).total_seconds() >= 6 * 3600:  # 6h
                import auto_evolution as ae
                rapport = ae.evolution_complete()
                print(f"\n  [EVOL] Evolution complete lancee:")
                for line in rapport.split("\n")[:5]:
                    print(f"    {line}")
        else:
            # Premiere evolution
            import auto_evolution as ae
            ae.evolution_complete()
            print("\n  [EVOL] Premiere evolution lancee")
    except FileNotFoundError:
        try:
            import auto_evolution as ae
            ae.evolution_complete()
            print("\n  [EVOL] Premiere evolution lancee")
        except Exception as e:
            print(f"\n  [EVOL] Erreur: {e}")
    except Exception as e:
        print(f"\n  [EVOL] Erreur evolution: {e}")

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

def _check_crypto_sl_rapide():
    """Check crypto mi-boucle (20s): rattrape les SL crypto instantanement.
    Utilise Binance batch (1 seul appel pour tous les symboles) au lieu de
    Revolut X (1 appel par symbole + rate limit = SL-RETARD)."""
    pf = charger_portefeuille()
    if not pf or not pf.get("positions"):
        return
    _crypto_syms = []
    _seen = set()
    for _p in pf["positions"]:
        _s = _p["symbole"]
        if _s in _seen:
            continue
        if MARCHES_PAPER.get(_s, {}).get("source") == "binance":
            _crypto_syms.append(_s)
            _seen.add(_s)
    if not _crypto_syms:
        return
    import prix_revolut as pr
    # 1. Binance batch (1 appel, instantane)
    prix = pr.get_prix_binance_batch(_crypto_syms)
    # 2. Fallback CoinGecko batch si Binance geo-bloque
    _missing = [s for s in _crypto_syms if s not in prix or prix[s] <= 0]
    if _missing:
        _cg = pr.get_prix_coingecko_batch(_missing)
        for _s, _p in _cg.items():
            if _p > 0:
                prix[_s] = _p
        _missing = [s for s in _crypto_syms if s not in prix or prix[s] <= 0]
    # 3. Fallback Revolut X pour les restants
    for _s in _missing:
        _p = pr.get_prix_revolut(_s)
        if _p and _p > 0:
            prix[_s] = _p
    if not prix:
        return
    verifier_sorties(pf, prix)
    sauver_portefeuille(pf)
    print(f"[crypto-check] {len(prix)} actif(s) crypto verifie(s) (mi-boucle SL rapide)")

def boucle():
    pf = charger_portefeuille()
    if not pf:
        print("Portefeuille non initialise. Lance 'python paper_trading.py init' d'abord.")
        return
    # Rotation automatique des logs au démarrage
    try:
        from rotation_logs import rotation
        rotation()
    except Exception:
        pass
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
        print(f"\nProchaine verification: {prochaine.strftime('%H:%M')} (crypto SL check toutes les 10s)")
        # SL check toutes les 10s (Binance batch = instantane, pas de rate limit)
        _nb_checks = INTERVALLE_BOUCLE // 10
        _check_interval = 10
        for _ in range(_nb_checks):
            time.sleep(_check_interval)
            try:
                _check_crypto_sl_rapide()
            except Exception as _e:
                print(f"[crypto-check] erreur: {_e}")
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
