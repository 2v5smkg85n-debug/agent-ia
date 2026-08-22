#!/usr/bin/env python3
"""Analyse detaillee de la performance pour identifier comment atteindre 3%/jour."""
import json
from datetime import datetime, timedelta

pf = json.load(open("paper_trading.json"))
trades = pf.get("trades_fermes", [])

# 4 derniers jours
stats = {}
for i in range(4):
    jour = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    trades_jour = [t for t in trades if t.get("date_fermeture", "").startswith(jour)]
    if not trades_jour:
        continue
    gagnes = [t for t in trades_jour if t.get("gain_eur", 0) >= 0]
    perdus = [t for t in trades_jour if t.get("gain_eur", 0) < 0]
    
    avg_win = sum(t.get("gain_eur", 0) for t in gagnes) / len(gagnes) if gagnes else 0
    avg_loss = sum(t.get("gain_eur", 0) for t in perdus) / len(perdus) if perdus else 0
    total_g = sum(t.get("gain_eur", 0) for t in gagnes)
    total_p = sum(t.get("gain_eur", 0) for t in perdus)
    net = total_g + total_p
    
    # Calculer le montant moyen par trade
    montants = [t.get("montant_eur", 80) for t in trades_jour]
    avg_montant = sum(montants) / len(montants) if montants else 80
    
    print(f"--- {jour} ---")
    print(f"  Trades: {len(trades_jour)} ({len(gagnes)}G / {len(perdus)}P) | Win rate: {len(gagnes)/len(trades_jour)*100:.0f}%")
    print(f"  Gagnes: +{total_g:.2f}EUR (avg +{avg_win:.2f}EUR = +{avg_win/avg_montant*100:.2f}%)")
    print(f"  Pertes: {total_p:.2f}EUR (avg {avg_loss:.2f}EUR = {avg_loss/avg_montant*100:.2f}%)")
    print(f"  Net: {net:+.2f}EUR | Montant avg/trade: {avg_montant:.0f}EUR")
    
    # Expected value per trade
    wr = len(gagnes)/len(trades_jour)
    ev = wr * avg_win + (1-wr) * avg_loss
    print(f"  EV/trade: {ev:+.3f}EUR | EV/jour ({len(trades_jour)} trades): {ev*len(trades_jour):+.2f}EUR")
    print(f"  RSI win%: {avg_win/avg_montant*100:.2f}% | RSI loss%: {avg_loss/avg_montant*100:.2f}%")
    print()

# Ce qu'il faut pour 3%/jour
print("=== OBJECTIF 3%/JOUR ===")
print(f"Capital: ~1000EUR")
print(f"Objectif: +30EUR/jour = +3%")
print()
print("Chemin:")
print("  Fix SL-RETARD: pertes de -1.4% a -1.0% = +0.4% gagne/trade perdant")
print("  Augmenter TP capture: gains de +1.5% a +2.5% = +1.0% gagne/trade gagnant")
print("  Si 50 trades/jour, 65% win rate:")
print(f"    EV actuelle: 0.65*1.22 + 0.35*(-1.15) = {0.65*1.22 + 0.35*(-1.15):.3f}EUR/trade")
print(f"    EV fixe SL: 0.65*1.22 + 0.35*(-0.80) = {0.65*1.22 + 0.35*(-0.80):.3f}EUR/trade")
print(f"    EV fixe SL + better TP: 0.65*2.00 + 0.35*(-0.80) = {0.65*2.00 + 0.35*(-0.80):.3f}EUR/trade")
print(f"    50 trades * {0.65*2.00 + 0.35*(-0.80):.3f}EUR = {(0.65*2.00 + 0.35*(-0.80))*50:.1f}EUR/jour = {(0.65*2.00 + 0.35*(-0.80))*50/1000*100:.1f}%/jour")
