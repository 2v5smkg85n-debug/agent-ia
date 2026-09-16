#!/usr/bin/env python3
"""Restaure les stats d'apprentissage des 121 anciens trades + 6 nouveaux."""
import json
import os

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learning_trader.json")

# Anciennes stats (121 trades avant reset)
ANCIENNES_STRATEGIES = {
    "pattern_reversal": {"n": 43, "gagnants": 28, "pnl_total": 20.22, "win_rate": 65.1},
    "vwap_bounce": {"n": 22, "gagnants": 8, "pnl_total": -12.17, "win_rate": 36.4},
    "rsi_oversold": {"n": 8, "gagnants": 2, "pnl_total": -11.47, "win_rate": 25.0},
    "volume_spike": {"n": 26, "gagnants": 13, "pnl_total": -7.12, "win_rate": 50.0},
    "divergence_rsi": {"n": 13, "gagnants": 6, "pnl_total": -6.83, "win_rate": 46.2},
    "momentum": {"n": 4, "gagnants": 0, "pnl_total": -6.45, "win_rate": 0.0},
    "macd_cross": {"n": 2, "gagnants": 0, "pnl_total": -2.89, "win_rate": 0.0},
    "bollinger_bounce": {"n": 3, "gagnants": 2, "pnl_total": -1.77, "win_rate": 66.7},
}

# Nouvelles stats (6 trades apres reset)
NOUVELLES_STRATEGIES = {
    "EMA Crossover": {"n": 4, "gagnants": 1, "pnl_total": -5.15, "win_rate": 25.0},
    "vwap_bounce": {"n": 2, "gagnants": 1, "pnl_total": 0.04, "win_rate": 50.0},
}

try:
    with open(FICHIER) as f:
        learning = json.load(f)
except Exception:
    learning = {}

# Merger les strategies
stats_strat = learning.get("stats_strategies", {})
for strat, data in ANCIENNES_STRATEGIES.items():
    if strat in stats_strat:
        stats_strat[strat]["n"] += data["n"]
        stats_strat[strat]["gagnants"] += data["gagnants"]
        stats_strat[strat]["pnl_total"] += data["pnl_total"]
        n = stats_strat[strat]["n"]
        g = stats_strat[strat]["gagnants"]
        stats_strat[strat]["win_rate"] = (g / n * 100) if n > 0 else 0
    else:
        stats_strat[strat] = data.copy()

for strat, data in NOUVELLES_STRATEGIES.items():
    if strat in stats_strat:
        stats_strat[strat]["n"] += data["n"]
        stats_strat[strat]["gagnants"] += data["gagnants"]
        stats_strat[strat]["pnl_total"] += data["pnl_total"]
        n = stats_strat[strat]["n"]
        g = stats_strat[strat]["gagnants"]
        stats_strat[strat]["win_rate"] = (g / n * 100) if n > 0 else 0
    else:
        stats_strat[strat] = data.copy()

learning["stats_strategies"] = stats_strat
learning["total_trades"] = 127  # 121 + 6
learning["total_gagnants"] = 62  # 59 + 3
learning["total_perdants"] = 65  # 62 + 4 (correction: 59+3=62, 62+4=66... let me recalc)
# 121 trades: 59 gagnants, 62 perdants
# 6 trades: 2 gagnants, 4 perdants
# Total: 61 gagnants, 66 perdants = 127
learning["total_gagnants"] = 61
learning["total_perdants"] = 66
learning["pnl_total"] = -28.48 + (-5.11)  # ancien + nouveau
learning["win_rate_global"] = 61 / 127 * 100

with open(FICHIER, "w") as f:
    json.dump(learning, f, ensure_ascii=False, indent=2)

print("Apprentissage restaure:")
print(f"  Total trades: {learning['total_trades']}")
print(f"  WR global: {learning['win_rate_global']:.1f}%")
print(f"  PnL total: {learning['pnl_total']:+.2f}EUR")
print()
for s, d in sorted(stats_strat.items(), key=lambda x: x[1].get("pnl_total", 0)):
    print(f"  {s:22s} n={d['n']:3d} WR={d['win_rate']:5.1f}% PnL={d['pnl_total']:+.2f}")
