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
MAX_POSITIONS = 8              # 8 positions max (concentration = meilleurs trades)
FENETRE_CORRELATION_MIN = 60    # anti-double-exposition: bloque 2e entree sur actif ouvert <60min
MAX_POS_PAR_ACTIF = 1          # 1 position par actif (pas de pyramiding risqué)
RISK_PAR_TRADE = 0.04          # 4% du capital par trade (8 positions, ~50EUR chacune)
INTERVALLE_BOUCLE = 600        # 10 min (plus réactif pour attraper les mouvements)
# RISK MANAGEMENT AVANCE
MAX_TRADES_PAR_JOUR = 10       # limite: max 10 trades par jour (qualité > quantité)
PERTE_JOUR_MAX_PCT = 2.0      # stop trading si -2% en une journee
CIRCUIT_BREAKER_CONSECUTIF = 2 # pause apres 2 pertes consecutives (plus prudent)
DRAWDOWN_REDUCTION_SEUIL = 0.95 # si capital < 95% du initial, reduit positions de 50%
COMPOUND_AUTOMATIQUE = True
HEURES_FAIBLE_LIQUIDITE = [(2, 6)] # pas de trades entre 2h-6h UTC
# Seuils pro: TP plus large pour laisser courir, SL serré pour couper vite
TAKE_PROFIT_PCT = 3.0          # +3% (laisse les gagnants courir)
STOP_LOSS_PCT = 1.5            # -1.5% (coupe les pertes vite)
# EXTEND_TP (backtest +13.35% sur crypto): monte le TP quand la position crypto
# est en profit, pour laisser courir les gagnants. SL fixe (pas de breakeven).
# Idee utilisateur + valide par backtest elargi (9 marches, 30 trades, plateau a tp_ext=4).
EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "OPUSDT", "INJUSDT", "NEARUSDT"}
EXTEND_SEUIL = 0.5        # active l'extension a partir de +0.5% de gain
EXTEND_TP_PCT = 4.0       # TP monte (2.0% -> 4.0%) une fois en profit
EXTEND_DUREE_MAX = 480    # cap duree des positions extended (8h, vs 90min normal)
SORTIE_DUREE_MIN = 720          # ferme apres 12h si en gain (laisse le TP dynamique travailler)
STALE_DUREE_MAX = 240           # position stale apres 4h (libere le capital plus vite)
# Seuil de gain minimum pour fermer par duree : doit couvrir les frais (0.2% AR) + une marge.
# Fermer a +0.05% = perte nette (frais 0.2%). Donc on n'accepte que gain >= 0.30%.
SEUIL_BENEFICE_MIN = 0.30       # 0.30% : couvre les 0.2% de frais + 0.1% de marge nette
DUREE_PETIT_GAIN = 180        # gain 0.30-0.45%: respire 2h (était 90min) pour viser partial TP
DUREE_GAIN_PROGRESS = 240    # gain 0.45-0.60%: respire 3h
DUREE_GAGNANT_MAX = 360         # gagnant protégé (breakeven armé): respire jusqu'à 4h pour atteindre partial/TP/trailing
DUREE_BONUS_STRATEGIE = 60    # stratégie prouvée (live_n>=3, wr>=60%, pnl>0): +1h de respiration
STALE_DUREE_MAX = 240           # position stale apres 4h (libere le capital plus vite)
BREAKEVEN_SEUIL = 2.0      # +2.0% -> SL monte au breakeven (un gagnant reste un gagnant)
TRAIL_ACTIF = 3.0          # +3.0% -> trailing stop derrière le pic
TRAIL_PCT = 1.0            # trail 1.0% sous le pic (lock profit, laisse respirer)
PARTIAL_TP_SEUIL = 0.8     # +1.0% -> encaisse une fraction du gain, garde le reste
PARTIAL_FRACTION = 0.5      # fraction clôturée au partial TP (50% lock, 50% runner)

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
    "SUIAUSDT": {"nom": "Sui Alpha", "marche": "crypto", "source": "binance"},
    # Meme coins (gains énormes possibles)
    "PEPEUSDT": {"nom": "Pepe", "marche": "crypto", "source": "binance"},
    "WIFUSDT": {"nom": "dogwifhat", "marche": "crypto", "source": "binance"},
    "FLOKIUSDT": {"nom": "Floki", "marche": "crypto", "source": "binance"},
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
    "MATICUSDT": {"nom": "Polygon", "marche": "crypto", "source": "binance"},
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
            # Signal d'achat uniquement si score >= 2 (ACHAT fort)
            # Les signaux faibles (score 1) sont ignores pour maximiser le win rate
            if score >= 2:
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
    if len(pf["positions"]) >= MAX_POSITIONS:
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
        # Montant ajuste par la meta-intelligence (confidence sizing)
        _meta_taille = signal.get("meta_taille")
        _meta_conf = signal.get("meta_confiance", 0.5)
        if _meta_taille == "grande":
            montant = pf["liquidites"] * min(RISK_PAR_TRADE * 1.5, 0.30)
        elif _meta_taille == "petite":
            montant = pf["liquidites"] * RISK_PAR_TRADE * 0.5
        else:
            montant = pf["liquidites"] * RISK_PAR_TRADE
    except Exception as e:
        print(f"  [SIZING erreur {e}] fallback 20% fixe")
        montant = pf["liquidites"] * RISK_PAR_TRADE
    # Plafonne au liquide dispo + plancher minimum 55EUR (15 positions x 60EUR)
    montant = max(55, min(montant, pf["liquidites"]))
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
    from gestion_risque import GROUPES_CORRELES
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
    capital_actuel = pf["liquidites"] + sum(p.get("montant", 0) for p in pf.get("positions", []))
    if capital_actuel < pf.get("capital_initial", 1000) * DRAWDOWN_REDUCTION_SEUIL:
        montant = montant * 0.5
        print(f"  [DRAWDOWN] Capital {capital_actuel:.0f}EUR < {DRAWDOWN_REDUCTION_SEUIL*100:.0f}% initial -> x0.5 ({montant:.0f}EUR)")
    # CONFLUENCE SIZING: si 2+ strategies signalent ACHAT, position plus grosse
    nb_conf = signal.get("confluence", 1)
    if nb_conf >= 2:
        montant = montant * min(nb_conf, 3)  # 2 strats=x2, 3 strats=x3, 4+=x3
        print(f"  [CONFLUENCE] {signal.get('nom',signal['symbole'])}: {nb_conf} strategies -> x{min(nb_conf,3)} sizing ({montant:.0f}EUR)")
    # BOOST STRATEGIE GAGNANTE: EMA Crossover = 50% WR live, +3.36EUR -> position 2x
    strat_name = signal.get("strategie", "")
    if strat_name == "EMA Crossover":
        montant = montant * 2.0
        print(f"  [BOOST] EMA Crossover: strategie gagnante -> x2 ({montant:.0f}EUR)")
    # CONVICTION SIZING: score plus eleve = position plus grosse
    score = signal.get("score", 2)
    if score >= 4:
        montant = montant * 1.5
        print(f"  [CONVICTION] Score {score} -> x1.5 ({montant:.0f}EUR)")
    # DETECTION REGIME: bull/bear/sideways
    try:
        sma50 = prix.get("sma50", None)
        if sma50 and prix_actuel:
            if prix_actuel > sma50 * 1.02:
                montant = montant * 1.2  # bull market: +20%
            elif prix_actuel < sma50 * 0.98:
                montant = montant * 0.5  # bear market: -50%
    except:
        pass
    # PYRAMIDING: si position deja ouverte ET en profit, on ajoute (acheter plus quand ca monte)
    _pos_existante = None
    for p in pf.get("positions", []):
        if p["symbole"] == signal["symbole"]:
            _pos_existante = p
            break
    if _pos_existante and prix_actuel > _pos_existante["prix_entree"]:
        _var = (prix_actuel - _pos_existante["prix_entree"]) / _pos_existante["prix_entree"] * 100
        if _var >= 1.0:  # position en profit de +1% minimum
            montant = montant * 1.5  # pyramiding: 50% plus
            print(f"  [PYRAMIDING] {signal.get('nom',signal['symbole'])}: ajout a position +{_var:.1f}% -> x1.5 ({montant:.0f}EUR)")
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
    # Clamp de securite: un plugin bugue ne peut pas depasser le liquide ni aller negatif
    # PLANCHER MINIMUM 80EUR applique APRES tous les filtres (regime, sentiment, plugins)
    montant = max(80, min(montant, pf["liquidites"]))
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
        "pattern_bougie": _pattern_info
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
        variation = (prix_actuel - prix_entree) / prix_entree * 100
        # Recupere le SL applicable (avant la detection de position piegee)
        if os.getenv('SCALPING', '0') == '1':
            _tp_check, _sl_check = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        else:
            try:
                from meta_tuning import tp_sl_actif
                _tp_check, _sl_check = tp_sl_actif(sym)
            except Exception:
                _tp_check, _sl_check = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        # DETECTION POSITION PIEGEE: si la perte depasse le SL, le SL aurait du etre touche
        # On ferme immediatement (le prix a chute trop, la position est morte)
        if variation <= -_sl_check:
            positions_a_fermer.append((pos, prix_actuel, f"SL-RETARD (perte {variation:+.1f}%, SL={-_sl_check}%%)", variation))
            continue
        # TP/SL: en mode scalping, les constantes globales priment sur meta_tuning
        if os.getenv('SCALPING', '0') == '1':
            _tp, _sl = TAKE_PROFIT_PCT, STOP_LOSS_PCT
        else:
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
        # === STOP SUIVEUR + TP DYNAMIQUE ===
        # SL fixe au debut (-1%), trailing commence seulement apres +2%
        # Avant +2%: SL fixe a -1% (laisse respirer)
        # Apres +2%: SL suit a 2% sous le pic (plus de marge = moins de faux signaux)
        _sl_regle = "fixe"
        _pic = pos.get("prix_peak", prix_entree)
        if prix_actuel > _pic:
            _pic = prix_actuel
            pos["prix_peak"] = _pic
        _var_pic = (_pic - prix_entree) / prix_entree * 100
        if _var_pic >= 2.0:
            # Trailing actif a 2% sous le pic (apres +2% seulement)
            _sl_price = _pic * (1 - 2.0 / 100.0)
            _sl_regle = "suiveur"
        else:
            # SL fixe a -1% au debut (laisse le trade respirer)
            _sl_price = prix_entree * (1 - _sl / 100.0)
        # TP DYNAMIQUE: quand le prix atteint le TP, on le monte de +1% au lieu de fermer
        # Le trade court tant que la tendance haussiere continue
        _tp_actuel = pos.get("tp_dynamique", _tp)
        if variation >= _tp_actuel:
            _tp_actuel = _tp_actuel + 1.0  # monte le TP de +1%
            pos["tp_dynamique"] = _tp_actuel
            print(f"  [TP-EXTEND] {sym}: TP monte a +{_tp_actuel:.1f}% (pic {_var_pic:+.1f}%)")
        # Partial take-profit: encaisse 50% a +2.5%, le reste court indéfiniment
        if variation >= PARTIAL_TP_SEUIL and not pos.get("partiellement_clote"):
            fermer_position_partielle(pf, pos, prix_actuel, PARTIAL_FRACTION, "PARTIAL-TP", variation)
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
                if age_min >= STALE_DUREE_MAX and variation < seuil_min:
                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS-stale ({variation:+.2f}%)", variation))
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
    trades_aujourdhui = [t for t in pf.get("trades_fermes", []) if t.get("date", "").startswith(datetime.now().strftime("%Y-%m-%d"))]
    pnl_jour = sum(t.get("gain_eur", 0) for t in trades_aujourdhui)
    capital_actuel = pf["liquidites"] + sum(p.get("montant", 0) for p in pf.get("positions", []))
    if capital_actuel > 0 and pnl_jour < -(capital_actuel * PERTE_JOUR_MAX_PCT / 100):
        print(f"  [RISK] Perte journaliere {pnl_jour:.2f}EUR > -{PERTE_JOUR_MAX_PCT}% -> STOP TRADING")
        return
    # 2. Circuit breaker 3 pertes consecutives
    pertes_consec = pf.get("circuit_breaker", {}).get("consecutive_losses", 0)
    if pertes_consec >= CIRCUIT_BREAKER_CONSECUTIF:
        print(f"  [RISK] Circuit breaker: {pertes_consec} pertes consecutives -> PAUSE")
        return
    # 3. Heures de faible liquidite
    heure_utc = datetime.utcnow().hour
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
                tous_signaux = ap.filtrer_signaux_avec_apprentissage(tous_signaux)
            except Exception as e:
                print(f"    Apprentissage indisponible: {e}")
            # === TRADER PRO: score multi-facteurs comme un pro ===
            try:
                import trader_pro as tp_module
                signaux_pro = []
                for sig in tous_signaux:
                    sym = sig.get("symbole", "")
                    prix = sig.get("prix_entree", 0)
                    if not sym or not prix:
                        signaux_pro.append(sig)
                        continue
                    score_pro, details_pro, reco_pro, params_pro = tp_module.score_opportunite(sym, prix)
                    sig["score_pro"] = score_pro
                    sig["score_pro_details"] = details_pro
                    sig["reco_pro"] = reco_pro
                    # Ajuster TP/SL selon volatilite
                    if params_pro.get("tp"):
                        sig["tp_optimal_pro"] = params_pro["tp"]
                    if params_pro.get("sl"):
                        sig["sl_optimal_pro"] = params_pro["sl"]
                    # Filtrer: laisse passer ACHAT, ACHAT_FORT et ATTENDRE (neutre)
                    # Bloque seulement NE_PAS_ACHETER et VENTE (score tres negatif)
                    if reco_pro in ["ACHAT", "ACHAT_FORT", "ATTENDRE"]:
                        if reco_pro == "ACHAT_FORT":
                            sig["score"] = sig.get("score", 0) + 3  # boost score
                            print(f"  [PRO] {sym}: ACHAT_FORT (score {score_pro:+.1f})")
                        elif reco_pro == "ACHAT":
                            sig["score"] = sig.get("score", 0) + 1  # petit boost
                            print(f"  [PRO] {sym}: ACHAT (score {score_pro:+.1f})")
                        else:
                            print(f"  [PRO] {sym}: NEUTRE - laisse passer (score {score_pro:+.1f})")
                        signaux_pro.append(sig)
                    else:
                        print(f"  [PRO] {sym}: SKIP - {reco_pro} (score {score_pro:+.1f})")
                tous_signaux = signaux_pro
            except Exception as e:
                print(f"    Trader pro indisponible: {e}")
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
    """Check crypto mi-boucle (15 min): rattrape les SL crypto 2x plus vite.
    Evite overshoot du SL sur mouvements rapides crypto (cf ETH -3.19% vs -1.5%).
    Ne fetch QUE les prix des positions crypto ouvertes -> pas de churn entree."""
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
    prix = {}
    for _s in _crypto_syms:
        _p = prix_binance(_s)
        if _p:
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
        print(f"\nProchaine verification: {prochaine.strftime('%H:%M')} (crypto SL check a +{INTERVALLE_BOUCLE//2//60}min)")
        _demi = INTERVALLE_BOUCLE // 2
        time.sleep(_demi)
        try:
            _check_crypto_sl_rapide()
        except Exception as _e:
            print(f"[crypto-check] erreur: {_e}")
        time.sleep(_demi)
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
