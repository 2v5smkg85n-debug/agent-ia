#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_trailing.py — Enregistre la lecon trailing stop + meta-pattern."""
import os, json
from datetime import datetime

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(os.path.join(os.getcwd(), "reflection_gemini.py")) else os.getcwd()
F = os.path.join(D, "lecons_apprises.jsonl")

entry = {
    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "hypothese": "Trailing stop (SL qui suit le pic de profit) pour laisser courir les gagnants",
    "source": "principe Seykota/Livermore 'let your profits run' (via sagesse)",
    "test": "backtest_trailing.py sur 5 cryptos (BTCUSDT,SOLUSDT,ETHUSDT,BNBUSDT,XRPUSDT), FIXE vs TRAIL",
    "resultat": "DEGRADE le PnL: TRAIL 4.09% vs FIXE 10.68% (-6.59%). Win 75%->58%, avgwin 1.80%->1.46%, maxwin 8.78%->8.54%",
    "raison": "Marche rangeant/QUIET: le trailing se fait whipsawer (ferme sur pullback mineur 0.8% avant le mouvement). Au lieu de laisser courir, il coupe les gagnants court.",
    "decision": "NE PAS activer le trailing stop en live. Garder le TP fixe.",
    "meta_pattern": "2eme hypothese trend-following rejetee apres ADX. Les principes trend (trailing, ADX gate, 'let profits run') BLESSENT en regime QUIET/range car pas de tendance a suivre. LA SAGESSE TREND DOIT ETRE CONDITIONNEE AU REGIME: appliquer seulement en TRENDING, pas en RANGING/QUIET.",
    "statut": "REJETEE par backtest",
}
with open(F, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("✅ lecon trailing stop enregistree dans lecons_apprises.jsonl")
print("✅ meta-pattern ajoute: sagesse trend a conditionner au regime")

# affiche le compte
n = sum(1 for _ in open(F, encoding="utf-8"))
print(f"   Total lecons: {n}")
