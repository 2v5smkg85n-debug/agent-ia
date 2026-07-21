#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTEUR DE BACKTEST DETERMINISTE.
Execute reellement les strategies bougie par bougie sur l'historique reel.
AUCUNE IA: chaque trade est simule avec de vrais prix, de vrais indicateurs,
et un suivi euro par euro du capital.

Pourquoi ce module existe:
- backtest.py utilisait l'IA pour "simuler" -> resultats non fiables (l'IA devine)
- Ce moteur execute reellement: il parcourt chaque bougie, calcule les indicateurs
  a chaque pas, declenche les entrees/sorties selon des regles codees, et suit le P&L.

Strategies implementees (codees, pas texte):
  1. SMA Crossover        (SMA20 croise SMA50)
  2. RSI Mean Reversion   (RSI<30 achat, RSI>70 vente)
  3. Bollinger Breakout   (prix touche bande basse -> achat, bande haute -> vente)
  4. MACD Momentum        (MACD croise signal haussier -> achat)

Pour chaque strategie sur chaque actif:
  - 365 jours de donnees reelles (Binance crypto, Yahoo pour les autres)
  - Capital virtuel 1000 EUR par test
  - Stop-loss / take-profit / frais 0.1% appliques
  - Win rate, retour %, drawdown max, nombre de trades -> REELS

Usage:
    python backtest_moteur.py               # teste toutes les strategies sur tous les actifs
    python backtest_moteur.py crypto        # focus crypto
    python backtest_moteur.py resultats     # affiche les resultats
    python backtest_moteur.py meilleurs     # top strategies gagnantes
"""
import os
import sys
import json
import math
import time
from datetime import datetime

from indicateurs import historique_ohlcv, _est_symbole_yahoo

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_RESULTATS = os.path.join(DOSSIER, "backtests_reels.json")

# ============================================
# CONFIG
# ============================================
CAPITAL_DEPART = 1000.0
FRAIS_PCT = 0.001          # 0.1% par trade (aller + retour)
TAKE_PROFIT_PCT = 0.015    # +1.5%
STOP_LOSS_PCT = 0.015      # -1.5% (symetrique au paper trading)

# Actifs a tester (symboles Yahoo/Binance)
ACTIFS = {
    "crypto":   ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                  "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"],
    "forex":    ["EURUSD=X", "GBPUSD=X", "JPY=X", "GC=F"],
    "actions":  ["AAPL", "TSLA", "NVDA", "MSFT"],
    "matieres": ["BZ=F", "NG=F", "HG=F", "ZW=F"],
    "indices":  ["^GSPC", "^IXIC", "^GDAXI", "^FCHI"],
}

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
# INDICATEURS SERIE (calcules sur toute la serie, index i)
# ============================================
def sma_series(clotures, periode):
    """Retourne la liste des SMA pour chaque index (None si pas assez de donnees)."""
    out = [None] * len(clotures)
    for i in range(periode - 1, len(clotures)):
        out[i] = sum(clotures[i-periode+1:i+1]) / periode
    return out

def rsi_series(clotures, periode=14):
    """Retourne la liste des RSI pour chaque index."""
    out = [None] * len(clotures)
    if len(clotures) < periode + 1:
        return out
    # RSI avec lissage de Wilder
    gains = []
    pertes = []
    for i in range(1, periode + 1):
        diff = clotures[i] - clotures[i-1]
        gains.append(diff if diff > 0 else 0)
        pertes.append(-diff if diff < 0 else 0)
    gain_moyen = sum(gains) / periode
    perte_moyenne = sum(pertes) / periode
    if perte_moyenne == 0:
        out[periode] = 100.0
    else:
        rs = gain_moyen / perte_moyenne
        out[periode] = 100 - (100 / (1 + rs))
    for i in range(periode + 1, len(clotures)):
        diff = clotures[i] - clotures[i-1]
        gain = diff if diff > 0 else 0
        perte = -diff if diff < 0 else 0
        gain_moyen = (gain_moyen * (periode - 1) + gain) / periode
        perte_moyenne = (perte_moyenne * (periode - 1) + perte) / periode
        if perte_moyenne == 0:
            out[i] = 100.0
        else:
            rs = gain_moyen / perte_moyenne
            out[i] = 100 - (100 / (1 + rs))
    return out

def bollinger_series(clotures, periode=20, ecart=2):
    """Retourne (haut, bas) listes pour chaque index."""
    hauts = [None] * len(clotures)
    bas = [None] * len(clotures)
    for i in range(periode - 1, len(clotures)):
        fenetre = clotures[i-periode+1:i+1]
        moyenne = sum(fenetre) / periode
        variance = sum((x - moyenne) ** 2 for x in fenetre) / periode
        e = math.sqrt(variance)
        hauts[i] = moyenne + ecart * e
        bas[i] = moyenne - ecart * e
    return hauts, bas

def donchian_series(clotures, periode=20):
    """Retourne (haut, bas) rolling max/min sur periode, decales d'une bougie (breakout)."""
    hauts = [None] * len(clotures)
    bas = [None] * len(clotures)
    for i in range(periode, len(clotures)):
        fen = clotures[i-periode:i]  # exclut la bougie courante
        hauts[i] = max(fen)
        bas[i] = min(fen)
    return hauts, bas

def stochastic_series(clotures, periode=14, smooth=3):
    """Retourne (k, d). %K = position dans le range; %D = SMA de %K."""
    k = [None] * len(clotures)
    for i in range(periode - 1, len(clotures)):
        fen = clotures[i-periode+1:i+1]
        hh = max(fen); ll = min(fen)
        k[i] = 100.0 * (clotures[i] - ll) / (hh - ll) if hh != ll else 50.0
    d = [None] * len(clotures)
    for i in range(periode - 1 + smooth - 1, len(clotures)):
        fen = [x for x in k[i-smooth+1:i+1] if x is not None]
        if len(fen) == smooth:
            d[i] = sum(fen) / smooth
    return k, d

def ema_simple_series(clotures, periode):
    """EMA simple sur la serie complete."""
    out = [None] * len(clotures)
    if len(clotures) < periode:
        return out
    mult = 2 / (periode + 1)
    out[periode-1] = sum(clotures[:periode]) / periode
    for i in range(periode, len(clotures)):
        out[i] = (clotures[i] - out[i-1]) * mult + out[i-1]
    return out

# ============================================
# STRATEGIES DETERMINISTES
# Chaque strategie est une fonction: (index, donnees) -> "ACHAT"/"VENTE"/None
# ============================================
def strat_sma_crossover(i, d):
    """Achat quand SMA20 croise au-dessus SMA50; vente quand croise en dessous."""
    if i < 1 or d["sma20"][i] is None or d["sma50"][i] is None:
        return None
    if d["sma20"][i-1] is None or d["sma50"][i-1] is None:
        return None
    croise_hausse = d["sma20"][i-1] <= d["sma50"][i-1] and d["sma20"][i] > d["sma50"][i]
    croise_baisse = d["sma20"][i-1] >= d["sma50"][i-1] and d["sma20"][i] < d["sma50"][i]
    if croise_hausse:
        return "ACHAT"
    if croise_baisse:
        return "VENTE"
    return None

# --- Auto-tunable params (auto_sweep.py met a jour strat_params.json) ---
import json as _sp_json, os as _sp_os, time as _sp_time
_SP_CACHE = {"vals": None, "mtime": 0.0}
def _strat_params():
    """Lit strat_params.json avec cache (recharge si mtime change). Fallback safe."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strat_params.json")
        mt = os.path.getmtime(p)
        if _SP_CACHE["vals"] is None or mt != _SP_CACHE["mtime"]:
            _SP_CACHE["vals"] = _sp_json.load(open(p, encoding="utf-8"))
            _SP_CACHE["mtime"] = mt
    except Exception:
        _SP_CACHE["vals"] = {}
    v = _SP_CACHE["vals"] or {}
    return v.get("rsi_achat", 35), v.get("rsi_vente", 70)

def _bb_ecart():
    """Lit bb_ecart de strat_params.json (cache partage). Fallback 2.0.
    Permet a genetic_optimizer.py d'optimiser l'ecart Bollinger."""
    if _SP_CACHE["vals"] is None:
        _strat_params()
    v = _SP_CACHE["vals"] or {}
    return v.get("bb_ecart", 2.0)

def strat_rsi_reversion(i, d):
    """Achat quand RSI < seuil (survente); vente quand RSI > seuil_haut.
    Seuil auto-ajuste par auto_sweep.py via strat_params.json."""
    r = d["rsi"][i]
    if r is None:
        return None
    achat, vente = _strat_params()
    if r < achat:
        return "ACHAT"
    if r > vente:
        return "VENTE"
    return None

def strat_bollinger_breakout(i, d):
    """Achat quand le prix touche/sous la bande basse; vente sur bande haute."""
    if d["bb_haut"][i] is None or d["bb_bas"][i] is None:
        return None
    prix = d["clotures"][i]
    if prix <= d["bb_bas"][i]:
        return "ACHAT"
    if prix >= d["bb_haut"][i]:
        return "VENTE"
    return None

def strat_macd_momentum(i, d):
    """Achat quand MACD croise signal haussier."""
    if i < 1:
        return None
    m, s = d["macd_line"], d["macd_signal"]
    if m[i] is None or s[i] is None or m[i-1] is None or s[i-1] is None:
        return None
    if m[i-1] <= s[i-1] and m[i] > s[i]:
        return "ACHAT"
    if m[i-1] >= s[i-1] and m[i] < s[i]:
        return "VENTE"
    return None

def strat_donchian_breakout(i, d):
    """Achat quand prix casse au-dessus du plus haut 20 (breakout); vente sous le plus bas."""
    if d["donchian_haut"][i] is None or d["donchian_bas"][i] is None:
        return None
    prix = d["clotures"][i]
    if prix > d["donchian_haut"][i]:
        return "ACHAT"
    if prix < d["donchian_bas"][i]:
        return "VENTE"
    return None

def strat_stochastic(i, d):
    """Achat quand %K croise au-dessus %D en zone oversold (<20); vente inverse en overbought (>80)."""
    if i < 1:
        return None
    k, kd = d["stoch_k"], d["stoch_d"]
    if k[i] is None or kd[i] is None or k[i-1] is None or kd[i-1] is None:
        return None
    if k[i-1] <= kd[i-1] and k[i] > kd[i] and k[i] < 20:
        return "ACHAT"
    if k[i-1] >= kd[i-1] and k[i] < kd[i] and k[i] > 80:
        return "VENTE"
    return None

def strat_ema_crossover(i, d):
    """Achat quand EMA12 croise au-dessus EMA26; vente inverse."""
    if i < 1:
        return None
    e12, e26 = d["ema12"], d["ema26"]
    if e12[i] is None or e26[i] is None or e12[i-1] is None or e26[i-1] is None:
        return None
    if e12[i-1] <= e26[i-1] and e12[i] > e26[i]:
        return "ACHAT"
    if e12[i-1] >= e26[i-1] and e12[i] < e26[i]:
        return "VENTE"
    return None

def _macd_full(clotures, courte=12, longue=26, signal=9):
    """Calcule les series MACD completes."""
    def ema_series(valeurs, periode):
        mult = 2 / (periode + 1)
        emas = [valeurs[0]]
        for v in valeurs[1:]:
            emas.append((v - emas[-1]) * mult + emas[-1])
        return emas
    if len(clotures) < longue + signal:
        return [None]*len(clotures), [None]*len(clotures)
    ema_c = ema_series(clotures, courte)
    ema_l = ema_series(clotures, longue)
    decalage = len(ema_c) - len(ema_l)
    macd_line = [None]*decalage + [ec - el for ec, el in zip(ema_c[decalage:], ema_l)]
    decalage2 = len(macd_line) - len(ema_l)
    # signal sur la partie valide de macd_line
    valide = [x for x in macd_line if x is not None]
    if len(valide) < signal:
        return [None]*len(clotures), [None]*len(clotures)
    sig = ema_series(valide, signal)
    signal_line = [None]*(len(macd_line) - len(sig)) + sig
    return macd_line, signal_line

STRATEGIES = {
    "SMA Crossover":      strat_sma_crossover,
    "RSI Mean Reversion": strat_rsi_reversion,
    "Bollinger Breakout": strat_bollinger_breakout,
    "MACD Momentum":      strat_macd_momentum,
    "Donchian Breakout":  strat_donchian_breakout,
    "Stochastic":         strat_stochastic,
    "EMA Crossover":      strat_ema_crossover,
}

# ============================================
# MOTEUR DE SIMULATION
# ============================================
def simuler(bougies, fonction_strat, capital=CAPITAL_DEPART):
    """Execute une strategie bougie par bougie. Retourne les stats REELLES."""
    if not bougies or len(bougies) < 60:
        return None
    clotures = [b["cloture"] for b in bougies]

    # Pre-calcule tous les indicateurs sur toute la serie
    donnees = {
        "clotures": clotures,
        "sma20": sma_series(clotures, 20),
        "sma50": sma_series(clotures, 50),
        "rsi": rsi_series(clotures, 14),
        "bb_haut": None,
        "bb_bas": None,
        "macd_line": None,
        "macd_signal": None,
    }
    donnees["bb_haut"], donnees["bb_bas"] = bollinger_series(clotures, 20, _bb_ecart())
    donnees["macd_line"], donnees["macd_signal"] = _macd_full(clotures)
    donnees["donchian_haut"], donnees["donchian_bas"] = donchian_series(clotures, 20)
    donnees["stoch_k"], donnees["stoch_d"] = stochastic_series(clotures, 14, 3)
    donnees["ema12"] = ema_simple_series(clotures, 12)
    donnees["ema26"] = ema_simple_series(clotures, 26)

    capital_dispo = capital
    quantite = 0.0
    prix_entree = 0.0
    trades = 0
    gagnes = 0
    perdus = 0
    pic_capital = capital
    drawdown_max = 0.0
    valeur_max = capital

    for i in range(len(clotures)):
        prix = clotures[i]
        signal = fonction_strat(i, donnees)

        # Verifie stop-loss / take-profit si en position
        if quantite > 0:
            var = (prix - prix_entree) / prix_entree
            fermer = False
            raison = ""
            if var >= TAKE_PROFIT_PCT:
                fermer = True
                raison = "take-profit"
            elif var <= -STOP_LOSS_PCT:
                fermer = True
                raison = "stop-loss"
            elif signal == "VENTE":
                fermer = True
                raison = "signal vente"
            if fermer:
                produit = quantite * prix * (1 - FRAIS_PCT)
                capital_dispo += produit
                if produit > prix_entree * quantite:
                    gagnes += 1
                else:
                    perdus += 1
                trades += 1
                quantite = 0.0
                pic_capital = max(pic_capital, capital_dispo)

        # Ouvre une position sur signal d'achat (si pas deja en position)
        if signal == "ACHAT" and quantite == 0 and capital_dispo > 10:
            montant = capital_dispo  # tout-in (simple, reproductible)
            quantite = (montant * (1 - FRAIS_PCT)) / prix
            capital_dispo = 0.0
            prix_entree = prix

        # Suivi drawdown
        valeur = capital_dispo + quantite * prix
        if valeur > valeur_max:
            valeur_max = valeur
        dd = (valeur_max - valeur) / valeur_max * 100 if valeur_max > 0 else 0
        drawdown_max = max(drawdown_max, dd)

    # Ferme la position a la fin si encore ouverte
    if quantite > 0:
        prix = clotures[-1]
        produit = quantite * prix * (1 - FRAIS_PCT)
        capital_dispo += produit
        if produit > prix_entree * quantite:
            gagnes += 1
        else:
            perdus += 1
        trades += 1

    retour_pct = (capital_dispo - capital) / capital * 100
    win_rate = gagnes / trades * 100 if trades > 0 else 0
    return {
        "capital_final": round(capital_dispo, 2),
        "retour_pct": round(retour_pct, 2),
        "trades": trades,
        "gagnes": gagnes,
        "perdus": perdus,
        "win_rate": round(win_rate, 1),
        "drawdown_max": round(drawdown_max, 2),
        "verdict": "GAGNANTE" if retour_pct > 0 else ("PERDANTE" if retour_pct < 0 else "NEUTRE"),
    }

# ============================================
# EXECUTION COMPLETE
# ============================================
def tester_tout(categorie=None):
    resultats = charger_resultats()
    # couples (strategie, actif) deja faits
    deja_fait = {(r.get("strategie"), r.get("actif")) for r in resultats}

    cats = [categorie] if categorie else list(ACTIFS.keys())
    nb_total = 0
    nb_nouveau = 0

    for cat in cats:
        for actif in ACTIFS.get(cat, []):
            for nom_strat, fonc in STRATEGIES.items():
                nb_total += 1
                if (nom_strat, actif) in deja_fait:
                    continue
                print(f"[{cat}] {actif} x {nom_strat}...", end=" ", flush=True)
                bougies = historique_ohlcv(actif, "1d", 365)
                if not bougies or len(bougies) < 60:
                    print("pas assez de donnees")
                    continue
                stats = simuler(bougies, fonc)
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
                print(f"{stats['verdict']} | {stats['retour_pct']:+.2f}% | {stats['gagnes']}G/{stats['perdus']}P | DD {stats['drawdown_max']:.1f}%")
                time.sleep(0.4)

    print("\n" + "=" * 60)
    print(f"Backtest termine. {nb_nouveau} nouveau(x) test(s), {len(resultats)} total en base.")
    print("=" * 60)

# ============================================
# AFFICHAGE
# ============================================
def afficher_resultats(meilleurs_seulement=False):
    resultats = charger_resultats()
    if not resultats:
        print("Aucun backtest reel. Lance 'python backtest_moteur.py' pour commencer.")
        return

    # Tri par retour decroissant
    tries = sorted(resultats, key=lambda r: r.get("retour_pct", 0), reverse=True)
    if meilleurs_seulement:
        tries = [r for r in tries if r.get("verdict") == "GAGNANTE"]

    print("=" * 65)
    titre = "TOP STRATEGIES GAGNANTES" if meilleurs_seulement else "RESULTATS BACKTEST REEL"
    print(f"{titre} ({len(tries)} strategies)")
    print("=" * 65)
    for i, r in enumerate(tries[:20], 1):
        print(f"\n{i}. [{r['marche']}] {r['actif']} x {r['strategie']} -> {r['verdict']}")
        print(f"   Retour: {r['retour_pct']:+.2f}% | Capital: {r['capital_final']} EUR (de 1000)")
        print(f"   Trades: {r['trades']} ({r['gagnes']}G/{r['perdus']}P, win rate {r['win_rate']}%) | Drawdown max: {r['drawdown_max']}%")

    # Stats globales
    total = len(resultats)
    gagnantes = sum(1 for r in resultats if r.get("verdict") == "GAGNANTE")
    perdantes = sum(1 for r in resultats if r.get("verdict") == "PERDANTE")
    neutres = total - gagnantes - perdantes
    print("\n" + "=" * 65)
    print(f"Stats globales: {total} tests | {gagnantes} gagnantes | {perdantes} perdantes | {neutres} neutres")
    if total:
        print(f"Taux de succes: {gagnantes/total*100:.1f}%")

    # Meilleure strategie par marche
    print("\nMeilleure strategie par marche:")
    for cat in ACTIFS.keys():
        cat_res = [r for r in resultats if r.get("marche") == cat]
        if cat_res:
            best = max(cat_res, key=lambda r: r.get("retour_pct", -9999))
            print(f"  {cat}: {best['actif']} x {best['strategie']} ({best['retour_pct']:+.2f}%)")

def aide():
    print("""
MOTEUR DE BACKTEST DETERMINISTE (sans IA)
===========================================
Commandes:
  python backtest_moteur.py            Teste toutes les strategies x actifs
  python backtest_moteur.py crypto     Focus sur un marche
  python backtest_moteur.py resultats  Affiche tous les resultats
  python backtest_moteur.py meilleurs  Affiche les strategies gagnantes

Le moteur:
  1. Recupere 365 jours de donnees reelles (Binance/Yahoo)
  2. Calcule les indicateurs a chaque bougie (SMA, RSI, Bollinger, MACD)
  3. Execute les trades bougie par bougie (entree/sortie reelles)
  4. Suit le capital euro par euro (frais 0.1%, TP +1.5%, SL -1.5%)
  5. Stats REELLES: win rate, retour %, drawdown max

5 strategies x 21 actifs = 105 tests possibles.
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "tous"

    print("=" * 60)
    print(f"BACKTEST MOTEUR DETERMINISTE - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    resultats = charger_resultats()
    print(f"Backtests reels en base: {len(resultats)}")

    if cmd == "resultats":
        afficher_resultats()
    elif cmd == "meilleurs":
        afficher_resultats(meilleurs_seulement=True)
    elif cmd == "aide":
        aide()
    elif cmd in ACTIFS.keys():
        tester_tout(categorie=cmd)
    else:
        tester_tout()
