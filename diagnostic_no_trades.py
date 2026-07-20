#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnostic_no_trades.py — Pourquoi l'IA ne trade pas?
Verifie: signaux recents, conditions d'entree, regime, gates."""
import os, sys, json
os.chdir(os.path.dirname(os.path.abspath("paper_trading.py")) or ".")
sys.path.insert(0, ".")

print("=" * 70)
print("DIAGNOSTIC: pourquoi aucun trade?")
print("=" * 70)

# 1) Signaux recents dans paper_trading.log
print("\n--- 1. SIGNAUX RECENTS (paper_trading.log, dernieres 200 lignes) ---")
lp = "paper_trading.log"
if os.path.exists(lp):
    lines = open(lp, encoding="utf-8", errors="ignore").read().splitlines()[-200:]
    achat = [l for l in lines if "ACHAT" in l]
    neutre = [l for l in lines if "neutre" in l.lower() or "NEUTRE" in l]
    ventes = [l for l in lines if "VENTE" in l or "ferm" in l.lower()]
    print(f"  ACHAT: {len(achat)} | NEUTRE: {len(neutre)} | VENTES/fermetures: {len(ventes)}")
    if achat:
        print("  derniers ACHAT:")
        for l in achat[-5:]:
            print(f"    {l.strip()[-90:]}")
    if neutre:
        print(f"  exemple NEUTRE: {neutre[-1].strip()[-90:]}")

# 2) Etat actuel: signaux sur les 10 cryptos maintenant
print("\n--- 2. SIGNAUX LIVE MAINTENANT (10 cryptos) ---")
try:
    from signaux_gagnants import generer_signaux_gagnants
    from indicateurs import historique_ohlcv, prix_binance
    import paper_trading as pt
    marches = {k: v for k, v in pt.MARCHES_PAPER.items() if v.get("marche") == "crypto"}
    # prix actuels
    prix = {}
    for sym in marches:
        try:
            b = historique_ohlcv(sym, "1h", 5)
            if b:
                prix[sym] = b[-1]["cloture"]
        except Exception:
            pass
    pf = pt.charger_portefeuille()
    signaux = generer_signaux_gagnants(prix, marches)
    n_achat = sum(1 for s in signaux.values() if isinstance(s, dict) and s.get("signal") == "ACHAT")
    n_neutre = sum(1 for s in signaux.values() if isinstance(s, dict) and s.get("signal") != "ACHAT")
    print(f"  {n_achat} ACHAT / {n_neutre} NEUTRE sur {len(signaux)} cryptos")
    for sym, s in signaux.items():
        if isinstance(s, dict):
            sig = s.get("signal", "?")
            strat = s.get("strategie", "")
            dip = s.get("dip", s.get("biais", "?"))
            score = s.get("score", 0)
            print(f"    {sym:<12} {sig:<8} strat={strat:<22} dip={dip} score={score}")
except Exception as e:
    import traceback
    print(f"  erreur: {e}")
    traceback.print_exc()

# 3) Regime actuel + RSI des cryptos
print("\n--- 3. REGIME + RSI (pourquoi pas d'entree) ---")
try:
    from regime import regime_actif
    from indicateurs import historique_ohlcv
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LDOUSDT", "AAVEUSDT"]:
        try:
            r = regime_actif(sym)
            b = historique_ohlcv(sym, "1h", 20)
            closes = [x["cloture"] for x in b]
            # RSI 14
            gains, losses = [], []
            for j in range(1, min(15, len(closes))):
                d = closes[j] - closes[j-1]
                (gains if d > 0 else losses).append(abs(d))
            ag = sum(gains)/14 if gains else 0
            al = sum(losses)/14 if losses else 0
            rsi = 100 if al == 0 else (100 - 100/(1 + ag/al))
            reg = r.get("REGIME", "?") if isinstance(r, dict) else "?"
            print(f"  {sym:<12} regime={reg:<6} RSI={rsi:.0f} (achat mean-reversion needs RSI 20-30)")
        except Exception as e:
            print(f"  {sym}: {e}")
except Exception as e:
    print(f"  erreur regime: {e}")

# 4) Gates actifs
print("\n--- 4. GATES D'ENTREE ACTIFS (stack de filtres) ---")
try:
    import signaux_gagnants as sg
    print(f"  DIP_BUYING_GATE = {getattr(sg, 'DIP_BUYING_GATE', '?')}")
    print(f"  (bloque entrees sur bougie haussiere, biais > 0)")
except Exception:
    pass
print("  + regime_fit doit etre suffisant (strategie adaptee au regime)")
print("  + classement: strategie doit etre dans le top par score")
print("  + sagesse_mult applique au score")
print("  + capital disponible pour ouvrir position")

print("\n" + "=" * 70)
print("CAUSES PROBABLES:")
print("1. Marche QUIET + lentement haussier -> pas de creux a acheter (RSI pas a 20-30)")
print("2. Dip-buying gate bloque les entrees sur bougie haussiere (marche qui monte)")
print("3. Mean-reversion a besoin d'oversold -> absent en marche calme haussier")
print("4. Systeme selectif par design (l'utilisateur a demande de couper les perdantes)")
print("=" * 70)
