#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest des nouveaux paramètres:
- TP fixe 3% vs TP dynamique ATR
- Fermeture intelligente vs ancien système
- Boost temporel vs sans boost
- Filtre volume vs sans filtre
"""
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from indicateurs import historique_ohlcv

# Configs à comparer
CONFIGS = {
    "ancien": {"TP": 3.0, "SL": 1.0, "stale": 180, "trail_pct": 1.0, "cut_stagnation": False},
    "nouveau": {"TP": 4.0, "SL": 1.0, "stale": 120, "trail_pct": 2.0, "cut_stagnation": True},
    "atr": {"TP": "atr", "SL": 1.0, "stale": 120, "trail_pct": 2.0, "cut_stagnation": True},
}

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT", "ARBUSDT"]


def calculer_atr(bougies, lookback=14):
    if len(bougies) < lookback + 1:
        return None
    trs = []
    for i in range(1, len(bougies)):
        h, l = bougies[i]["haut"], bougies[i]["bas"]
        c_prev = bougies[i-1]["cloture"]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return sum(trs[-lookback:]) / lookback if trs else None


def backtest_config(symbol, config, capital=1000):
    bougies = historique_ohlcv(symbol, "1h", 200)
    if not bougies or len(bougies) < 50:
        return None

    trades = []
    position = None
    frais = 0.001  # 0.1% par côté

    for i in range(20, len(bougies)):
        b = bougies[i]
        prix = b["cloture"]
        heure = b.get("timestamp", i)

        # Calculer TP
        if config["TP"] == "atr":
            atr = calculer_atr(bougies[:i+1])
            if atr and prix > 0:
                tp_pct = max(3.0, min((atr / prix) * 100 * 2.0, 8.0))
            else:
                tp_pct = 4.0
        else:
            tp_pct = config["TP"]

        # Boost temporel (heures Europe + US)
        heure_utc = i % 24
        boost = 1 if (8 <= heure_utc < 11 or 13 <= heure_utc < 17) else 0

        # Signal simple: RSI < 35 + MACD > 0
        clotures = [bb["cloture"] for bb in bougies[max(0, i-15):i+1]]
        if len(clotures) < 15:
            continue
        # RSI
        gains = [max(0, clotures[j] - clotures[j-1]) for j in range(1, len(clotures))]
        pertes = [max(0, clotures[j-1] - clotures[j]) for j in range(1, len(clotures))]
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_perte = sum(pertes) / len(pertes) if pertes else 0
        rsi_val = 100 - (100 / (1 + (avg_gain / avg_perte if avg_perte > 0 else 99))) if avg_perte > 0 else 50

        # Filtre volume
        vols = [bb.get("volume", 0) for bb in bougies[max(0, i-20):i]]
        vol_actuel = b.get("volume", 0)
        vol_moyen = sum(vols) / len(vols) if vols else 0

        if position is None:
            # Entrée: RSI < 40 + volume OK + boost temporel
            if rsi_val < 40 and (vol_moyen == 0 or vol_actuel >= vol_moyen * 0.7):
                if boost or rsi_val < 30:
                    montant = capital * 0.20
                    quantite = montant / prix
                    frais_entry = montant * frais
                    position = {
                        "prix_entree": prix,
                        "quantite": quantite,
                        "montant": montant,
                        "frais_entry": frais_entry,
                        "timestamp_entree": i,
                        "tp": tp_pct,
                        "pic": prix,
                    }

        if position:
            variation = ((prix - position["prix_entree"]) / position["prix_entree"]) * 100
            age = i - position["timestamp_entree"]
            position["pic"] = max(position["pic"], prix)

            # TP
            if variation >= position["tp"]:
                gain = position["montant"] * variation / 100
                frais_exit = position["montant"] * frais
                net = gain - position["frais_entry"] - frais_exit
                capital += net
                trades.append({"gain": net, "raison": "TP", "var": variation})
                position = None

            # SL
            elif variation <= -config["SL"]:
                perte = position["montant"] * variation / 100
                frais_exit = position["montant"] * frais
                net = perte - position["frais_entry"] - frais_exit
                capital += net
                trades.append({"gain": net, "raison": "SL", "var": variation})
                position = None

            # Fermeture intelligente
            elif config["cut_stagnation"] and variation <= -0.5 and age >= 60:
                perte = position["montant"] * variation / 100
                frais_exit = position["montant"] * frais
                net = perte - position["frais_entry"] - frais_exit
                capital += net
                trades.append({"gain": net, "raison": "CUT-STAG", "var": variation})
                position = None

            # Stale
            elif age >= config["stale"] and variation < 0.8:
                gain = position["montant"] * variation / 100
                frais_exit = position["montant"] * frais
                net = gain - position["frais_entry"] - frais_exit
                capital += net
                trades.append({"gain": net, "raison": "STALE", "var": variation})
                position = None

            # Trailing stop
            elif variation >= 4.0:
                trail_var = ((prix - position["pic"]) / position["pic"]) * 100
                if prix <= position["pic"] * (1 - config["trail_pct"] / 100):
                    gain = position["montant"] * variation / 100
                    frais_exit = position["montant"] * frais
                    net = gain - position["frais_entry"] - frais_exit
                    capital += net
                    trades.append({"gain": net, "raison": "TRAIL", "var": variation})
                    position = None

    return {"capital": capital, "trades": trades, "nb_trades": len(trades)}


def main():
    print("=" * 60)
    print("BACKTEST NOUVEAUX PARAMETRES")
    print("=" * 60)
    print(f"Actifs testés: {', '.join(SYMBOLS)}")
    print(f"Capital initial: 1000 EUR")
    print()

    for config_name, config in CONFIGS.items():
        capital_total = 0
        trades_total = 0
        wins = 0
        losses = 0
        for sym in SYMBOLS:
            result = backtest_config(sym, config)
            if result:
                capital_total += result["capital"] - 1000
                trades_total += result["nb_trades"]
                for t in result["trades"]:
                    if t["gain"] > 0:
                        wins += 1
                    else:
                        losses += 1

        pnl_pct = (capital_total / (1000 * len(SYMBOLS))) * 100
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        print(f"  [{config_name:8s}] P&L: {capital_total:+.2f} EUR ({pnl_pct:+.1f}%) | "
              f"Trades: {trades_total} | WR: {wr:.0f}% | W/L: {wins}/{losses}")

    print()
    print("Comparaison ancien vs nouveau vs ATR:")
    print("  - Si nouveau > ancien: les changements sont validés")
    print("  - Si ATR > nouveau: le TP dynamique apporte un plus")


if __name__ == "__main__":
    main()
