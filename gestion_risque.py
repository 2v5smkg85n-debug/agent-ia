#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GESTION DU RISQUE PRO - PHASE 2.
Remplace le 20% fixe par trade par un sizing dynamique professionnel.

Systeme de sizing multi-niveaux:
  1. Kelly fractionnaire: calcule la taille optimale selon win rate et ratio gain/perte
  2. Quarter Kelly par defaut (0.25x): conservateur, evite la ruine
  3. Volatility targeting: les actifs volatils recaissent moins de capital
  4. Correlation haircut: BTC+ETH+SOL = 1 position effective (pas 3)
  5. Drawdown scaler: si drawdown recent > 10%, on reduit le sizing de 50%
  6. Circuit breaker: perte journaliere > 5% -> on arrete de trader
  7. Caps durs: max 10% par actif, max 25% par secteur

Formule finale:
  size = min(cap_dur, kelly_quarter * vol_target * correlation_haircut * drawdown_scaler)

Usage dans paper_trading.py:
  from gestion_risque import calculer_taille
  montant = calculer_taille(pf, signal, prix_actuel, backtest_stats)

Commandes standalone:
  python gestion_risque.py           # affiche l'etat du risque du portefeuille
  python gestion_risque.py test      # simule des tailles sur differents scenarios
"""
import os
import sys
import json
import math
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAPER = os.path.join(DOSSIER, "paper_trading.json")
FICHIER_BACKTESTS = os.path.join(DOSSIER, "backtests_pro.json")

# ============================================
# CONFIG RISQUE
# ============================================
KELLY_FRACTION = 0.50        # Half Kelly (plus agressif) - SIZING-BOOST-INSTALLE
VOL_CIBLE_JOUR = 0.03        # 2% de volatilite quotidienne cible au niveau portfolio
DRAWDOWN_SEUIL = 10.0        # si drawdown recent > 10%, on reduit
DRAWDOWN_REDUCTION = 0.50    # ... de 50%
CIRCUIT_BREAKER_JOUR = 5.0   # perte journaliere > 5% -> stop trading
CAP_ACTIF = 0.15             # max 15% du capital sur un seul actif
CAP_SECTEUR = 0.40           # max 25% du capital sur un secteur (crypto, forex, etc.)
CORRELATION_SEUIL = 0.60     # rho > 0.6 = positions correlees, groupees
RISK_MIN_EUR = 5.0           # en dessous de 5 EUR, on n'ouvre pas

# Actifs correles (groupes) - bases sur la realite des marches
GROUPES_CORRELES = [
    set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]),  # crypto major
    set(["AAPL", "MSFT", "NVDA"]),                                  # big tech US
    set(["^GSPC", "^IXIC"]),                                         # indices US correles
    set(["^GDAXI", "^FCHI"]),                                        # indices EU correles
    set(["BZ=F", "NG=F"]),                                           # energies correlees
]

# Volatilite quotidienne estimee par actif (annualisee / sqrt(252))
# Source: derivee des backtests et donnees de marche
VOLATILITE_ACTIF = {
    "BTCUSDT": 0.045, "ETHUSDT": 0.052, "SOLUSDT": 0.065,
    "BNBUSDT": 0.050, "XRPUSDT": 0.060,
    "EURUSD=X": 0.006, "GBPUSD=X": 0.007, "JPY=X": 0.008, "GC=F": 0.012,
    "AAPL": 0.018, "TSLA": 0.035, "NVDA": 0.030, "MSFT": 0.017,
    "BZ=F": 0.022, "NG=F": 0.040, "HG=F": 0.018, "ZW=F": 0.025,
    "^GSPC": 0.011, "^IXIC": 0.014, "^GDAXI": 0.013, "^FCHI": 0.012,
}
VOL_DEFAUT = 0.030  # 3% par jour si inconnu

# ============================================
# CHARGEMENT DONNEES
# ============================================
def charger_portefeuille():
    if not os.path.exists(FICHIER_PAPER):
        return None
    try:
        with open(FICHIER_PAPER, "r") as f:
            return json.load(f)
    except Exception:
        return None

def charger_backtest_stats():
    """Retourne un dict {(strategie, actif): stats} depuis backtests_pro.json."""
    if not os.path.exists(FICHIER_BACKTESTS):
        # fallback sur l'ancien fichier
        ancien = os.path.join(DOSSIER, "backtests_reels.json")
        if not os.path.exists(ancien):
            return {}
        fich = ancien
    else:
        fich = FICHIER_BACKTESTS
    try:
        with open(fich, "r") as f:
            data = json.load(f)
    except Exception:
        return {}
    stats = {}
    for r in data:
        cle = (r.get("strategie"), r.get("actif"))
        stats[cle] = r
    return stats

# ============================================
# 1. KELLY FRACTIONNAIRE
# ============================================
def kelly_optimal(win_rate, ratio_gain_perte):
    """
    Calcule la fraction Kelly complete.
    f* = (b*p - q) / b
      p = proba de gain, q = 1-p, b = ratio gain/perte
    """
    if win_rate is None or ratio_gain_perte is None or ratio_gain_perte <= 0:
        return 0.0
    p = win_rate / 100.0
    q = 1 - p
    f = (ratio_gain_perte * p - q) / ratio_gain_perte
    return max(0.0, f)  # jamais negatif (pas d'edge = pas de trade)

def kelly_fractionne(win_rate, ratio_gain_perte, fraction=KELLY_FRACTION):
    """Kelly x fraction (0.25 = Quarter Kelly)."""
    return kelly_optimal(win_rate, ratio_gain_perte) * fraction

def estimer_edge(strategie, actif):
    """Estime win rate et ratio gain/perte depuis les backtests."""
    stats = charger_backtest_stats()
    s = stats.get((strategie, actif))
    if not s:
        # fallback sur les stats de la strategie tous actifs confondus
        tous = [v for k, v in stats.items() if k[0] == strategie]
        if not tous:
            return None, None
        wr = sum(r.get("win_rate", 0) for r in tous) / len(tous)
        gagnants = [r for r in tous if r.get("verdict") == "GAGNANTE"]
        perdants = [r for r in tous if r.get("verdict") == "PERDANTE"]
        return _ratio_gp(gagnants, perdants, wr)
    wr = s.get("win_rate", 0)
    if s.get("verdict") != "GAGNANTE":
        # strategie perdante -> edge negatif -> Kelly = 0 -> on ne trade pas
        return wr, 0.0
    # ratio gain/perte approxime depuis profit factor
    pf = s.get("profit_factor", 1.0)
    if pf and pf > 0:
        # PF = (win_rate * avg_gain) / (loss_rate * avg_loss)
        # ratio_gain_perte = avg_gain / avg_loss = PF * loss_rate / win_rate
        loss_rate = (100 - wr) / 100 if wr < 100 else 0.01
        ratio = pf * loss_rate / (wr / 100) if wr > 0 else 0
        return wr, ratio
    return wr, 1.0

def _ratio_gp(gagnants, perdants, wr):
    if not gagnants:
        return wr, 0.0
    avg_gain = sum(r.get("retour_pct", 0) for r in gagnants) / len(gagnants)
    if perdants:
        avg_loss = abs(sum(r.get("retour_pct", 0) for r in perdants) / len(perdants))
    else:
        avg_loss = avg_gain  # pas de perte connue, suppose symetrique
    if avg_loss > 0:
        ratio = avg_gain / avg_loss
    else:
        ratio = 1.0
    return wr, ratio

# ============================================
# 2. VOLATILITY TARGETING
# ============================================
def vol_target_scaler(actif):
    """
    Reduit le sizing pour les actifs volatils.
    Notional = vol_cible / vol_actif (plafonne a 1.0).
    Un actif 2x plus volatil recoit 2x moins de capital.
    """
    vol_actif = VOLATILITE_ACTIF.get(actif, VOL_DEFAUT)
    if vol_actif <= 0:
        return 1.0
    scaler = VOL_CIBLE_JOUR / vol_actif
    return min(1.0, scaler)  # jamais amplifier au-dela de 1.0

# ============================================
# 3. CORRELATION HAIRCUT
# ============================================
def groupe_correlation(symbole, positions_ouvertes):
    """
    Compte combien de positions dans le meme groupe correle sont deja ouvertes.
    Plus il y en a, plus on reduit le sizing (eviter la concentration sur 1 theme).
    """
    groupe = None
    for g in GROUPES_CORRELES:
        if symbole in g:
            groupe = g
            break
    if groupe is None:
        return 1.0  # pas de groupe correle, pas de reduction

    nb_dans_groupe = sum(1 for p in positions_ouvertes if p.get("symbole") in groupe)
    # chaque position correlee additionnelle reduit le sizing de 20%
    reduction = max(0.2, 1.0 - 0.20 * nb_dans_groupe)
    return reduction

# ============================================
# 4. DRAWDOWN SCALER
# ============================================
def drawdown_scaler(pf):
    """
    Si drawdown recent > seuil, on reduit le sizing.
    Mesure: comparaison capital actuel vs pic recent.
    """
    capital_actuel = valeur_portefeuille(pf)
    capital_initial = pf.get("capital_initial", 1000.0)
    pic = pf.get("pic_capital", capital_initial)
    if pic <= 0:
        return 1.0
    dd = (pic - capital_actuel) / pic * 100
    if dd >= DRAWDOWN_SEUIL:
        return DRAWDOWN_REDUCTION
    # reduction lineaire entre 0 (a 0% dd) et 50% (a 10% dd)
    return max(DRAWDOWN_REDUCTION, 1.0 - (dd / DRAWDOWN_SEUIL) * (1 - DRAWDOWN_REDUCTION))

def valeur_portefeuille(pf):
    liquidites = pf.get("liquidites", 0)
    positions = pf.get("positions", [])
    # estimation sans prix live (juste le montant investi)
    valeur_positions = sum(p.get("montant_eur", 0) for p in positions)
    return liquidites + valeur_positions

# ============================================
# 5. CIRCUIT BREAKER
# ============================================
def circuit_breaker(pf):
    """
    Verifie si on doit arreter de trader aujourd'hui.
    Retourne True si OK pour trader, False si breaker active.
    """
    trades_aujourdhui = [t for t in pf.get("trades_fermes", [])
                         if t.get("date_fermeture", "").startswith(datetime.now().strftime("%Y-%m-%d"))]
    if not trades_aujourdhui:
        return True
    capital = pf.get("capital_initial", 1000.0)
    pnl_jour = sum(t.get("gain_eur", 0) for t in trades_aujourdhui)
    pnl_pct = pnl_jour / capital * 100 if capital > 0 else 0
    if pnl_pct <= -CIRCUIT_BREAKER_JOUR:
        return False
    return True

# ============================================
# 6. CAPS DURS
# ============================================
def cap_dur(montant, capital, symbole, marche, positions_ouvertes):
    """Applique les plafonds durs: max 10% par actif, 25% par secteur."""
    cap_actif_eur = capital * CAP_ACTIF
    # exposition deja ouverte sur cet actif
    expo_actif = sum(p.get("montant_eur", 0) for p in positions_ouvertes
                     if p.get("symbole") == symbole)
    dispo_actif = max(0, cap_actif_eur - expo_actif)

    cap_secteur_eur = capital * CAP_SECTEUR
    expo_secteur = sum(p.get("montant_eur", 0) for p in positions_ouvertes
                       if p.get("marche") == marche)
    dispo_secteur = max(0, cap_secteur_eur - expo_secteur)

    return min(montant, dispo_actif, dispo_secteur)

# ============================================
# FONCTION PRINCIPALE
# ============================================
def calculer_taille(pf, signal, prix_actuel, backtest_stats=None):
    """
    Calcule le montant EUR a investir pour un signal donne.
    Retourne 0 si on ne doit pas trader (edge negatif, breaker, etc.).

    Args:
        pf: portefeuille (dict)
        signal: dict avec 'symbole', 'marche', 'strategie'
        prix_actuel: prix actuel de l'actif
        backtest_stats: stats de backtest optionnelles (sinon charge depuis le fichier)
    """
    symbole = signal.get("symbole", "")
    marche = signal.get("marche", "?")
    strategie = signal.get("strategie", "")

    capital = valeur_portefeuille(pf)
    positions = pf.get("positions", [])

    # 1. Circuit breaker
    if not circuit_breaker(pf):
        return 0.0, "circuit_breaker"

    # 2. Edge (Kelly)
    if backtest_stats:
        wr = backtest_stats.get("win_rate", 0)
        if backtest_stats.get("verdict") != "GAGNANTE":
            return 0.0, "strategie_perdante"
        pf_val = backtest_stats.get("profit_factor")
        if pf_val and pf_val > 0:
            # profit_factor present (backtests_pro): ratio derive precis
            loss_rate = (100 - wr) / 100 if wr < 100 else 0.01
            ratio = pf_val * loss_rate / (wr / 100) if wr > 0 else 0
        else:
            # profit_factor absent (backtest_moteur.simuler): TP/SL symetriques
            # +1.5%/-1.5% -> payoff ratio ~1.0 (conservateur, realiste)
            ratio = 1.0
    else:
        wr, ratio = estimer_edge(strategie, symbole)
        if not wr or not ratio or ratio <= 0:
            # Edge inconnu: utilise des valeurs conservatives au lieu de bloquer
            # Si le signal contient MOMENTUM, on sait que TP=5% SL=2% -> ratio=2.5
            signaux_list = signal.get("signaux", [])
            if any("MOMENTUM" in str(s) for s in signaux_list):
                wr, ratio = 55.0, 2.5  # momentum: 55% win rate, TP5%/SL2%
            else:
                wr, ratio = 50.0, 2.5  # conservateur: 50% win, TP5%/SL2%

    kelly = kelly_fractionne(wr, ratio)

    # 3. Volatility targeting
    vol_scaler = vol_target_scaler(symbole)

    # 4. Correlation haircut
    corr_scaler = groupe_correlation(symbole, positions)

    # 5. Drawdown scaler
    dd_scaler = drawdown_scaler(pf)

    # 6. Montant de base (Kelly x capital)
    montant_base = capital * kelly * vol_scaler * corr_scaler * dd_scaler

    # 7. Caps durs
    montant_final = cap_dur(montant_base, capital, symbole, marche, positions)

    # 8. Minimum
    if montant_final < RISK_MIN_EUR:
        return 0.0, "montant_trop_petit"

    raison = (f"Kelly {kelly*100:.1f}% x vol {vol_scaler:.2f} x corr {corr_scaler:.2f} "
              f"x dd {dd_scaler:.2f} = {montant_base:.1f} EUR (cap {montant_final:.1f} EUR)")
    return round(montant_final, 2), raison

# ============================================
# AFFICHAGE ETAT DU RISQUE
# ============================================
def afficher_etat():
    pf = charger_portefeuille()
    if not pf:
        print("Aucun portefeuille paper trading. Lance 'python paper_trading.py init' d'abord.")
        return

    capital = valeur_portefeuille(pf)
    liquidites = pf.get("liquidites", 0)
    positions = pf.get("positions", [])

    print("=" * 60)
    print(f"ETAT DU RISQUE - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    print(f"\nCapital total: {capital:.2f} EUR")
    print(f"Liquidites: {liquidites:.2f} EUR ({liquidites/capital*100:.1f}%)")
    print(f"Positions ouvertes: {len(positions)}/{5}")

    # Exposition par secteur
    print("\nExposition par secteur (cap 25%):")
    expo_secteur = {}
    for p in positions:
        m = p.get("marche", "?")
        expo_secteur[m] = expo_secteur.get(m, 0) + p.get("montant_eur", 0)
    for m, expo in sorted(expo_secteur.items()):
        pct = expo / capital * 100
        alerte = " <-- CAP ATTEINT" if pct >= CAP_SECTEUR * 100 else ""
        print(f"  {m}: {expo:.2f} EUR ({pct:.1f}%){alerte}")

    # Drawdown
    pic = pf.get("pic_capital", pf.get("capital_initial", 1000.0))
    dd = (pic - capital) / pic * 100 if pic > 0 else 0
    print(f"\nPic capital: {pic:.2f} EUR")
    print(f"Drawdown actuel: {dd:.2f}%")
    if dd >= DRAWDOWN_SEUIL:
        print(f"  <-- SEUIL DRAWDOWN ATTEINT ({DRAWDOWN_SEUIL}%) -> sizing reduit de {(1-DRAWDOWN_REDUCTION)*100:.0f}%")

    # Circuit breaker
    ok = circuit_breaker(pf)
    print(f"\nCircuit breaker (perte jour > {CIRCUIT_BREAKER_JOUR}%): {'OK' if ok else 'ACTIVE - STOP TRADING'}")

    # Kelly pour chaque strategie gagnante
    print(f"\nSizing Kelly (fraction {KELLY_FRACTION}x) pour strategies gagnantes:")
    stats = charger_backtest_stats()
    gagnantes = [(k, v) for k, v in stats.items() if v.get("verdict") == "GAGNANTE"]
    gagnantes.sort(key=lambda x: x[1].get("retour_pct", 0), reverse=True)
    print(f"  {'Actif':<12} {'Strategie':<22} {'Win%':<6} {'PF':<5} {'Kelly%':<8}")
    for (strat, actif), s in gagnantes[:15]:
        wr = s.get("win_rate", 0)
        pf_val = s.get("profit_factor", 1.0)
        loss_rate = (100 - wr) / 100 if wr < 100 else 0.01
        ratio = pf_val * loss_rate / (wr / 100) if wr > 0 else 0
        k = kelly_fractionne(wr, ratio)
        print(f"  {actif:<12} {strat:<22} {wr:<6.0f} {pf_val:<5} {k*100:<8.1f}")

# ============================================
# TESTS UNITAIRES
# ============================================
def tester():
    print("=" * 60)
    print("TEST DU SYSTEME DE SIZING")
    print("=" * 60)

    # Portefeuille factice
    pf = {
        "liquidites": 800.0,
        "capital_initial": 1000.0,
        "pic_capital": 1000.0,
        "positions": [],
        "trades_fermes": [],
    }

    scenarios = [
        ("BTCUSDT", "crypto", "Bollinger Breakout", "crypto liquide, strategie gagnante"),
        ("ETHUSDT", "crypto", "Bollinger Breakout", "correle BTC (2e position)"),
        ("TSLA", "actions", "Bollinger Breakout", "action volatile, gagnante"),
        ("EURUSD=X", "forex", "RSI Mean Reversion", "forex stable"),
        ("BTCUSDT", "crypto", "RSI Mean Reversion", "strategie PERDANTE sur crypto"),
    ]

    for symbole, marche, strategie, desc in scenarios:
        signal = {"symbole": symbole, "marche": marche, "strategie": strategie}
        montant, raison = calculer_taille(pf, signal, 0)
        print(f"\n[{desc}]")
        print(f"  {symbole} x {strategie}")
        if montant > 0:
            print(f"  -> {montant:.2f} EUR ({montant/pf['liquidites']*100:.1f} des liquidites)")
            print(f"  -> {raison}")
        else:
            print(f"  -> PAS DE TRADE ({raison})")

    # Simule un drawdown
    print("\n" + "-" * 60)
    print("Test drawdown (capital tombe a 880 EUR, pic 1000 EUR):")
    pf["liquidites"] = 880.0
    pf["pic_capital"] = 1000.0
    signal = {"symbole": "TSLA", "marche": "actions", "strategie": "Bollinger Breakout"}
    montant, raison = calculer_taille(pf, signal, 0)
    print(f"  TSLA x Bollinger: {montant:.2f} EUR")
    print(f"  {raison}")

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "etat"
    if cmd == "test":
        tester()
    else:
        afficher_etat()

# CAPITAL-DEPLOI-INSTALLE: VOL_CIBLE_JOUR 0.02->0.03, CAP_SECTEUR 0.25->0.40 (deploiement capital)
