#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_sagesse.py — Lecons des 10 maitres traders (3 tests)."""
import os, json
from datetime import datetime

D = os.path.dirname(os.path.abspath("paper_trading.py")) or os.getcwd()
F = os.path.join(D, "lecons_apprises.jsonl")

entries = [
    {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hypothese": "Sagesse Buffett/Rogers/Soros: acheter les creux profonds (RSI<20) = 'sang dans les rues'",
        "source": "sagesse_traders.py (base 10 maitres) + backtest_sagesse.py",
        "test": "deep_contrarian: RSI<20 (creux profond) vs RSI 20-30 (modere), 15 entrees RSI",
        "resultat": "REJETE. RSI<20 = 33.3% win / -0.18% avg (PERDANT). RSI 20-30 = 83.3% win / +1.07% avg (GAGNANT). Delta -50pt win.",
        "raison": "RSI<20 = couteau qui tombe (downtrend fort), pas un creux qui rebondit. Les creux moderes (20-30) rebondissent, les creux extremes continuent de chuter. 'Sang dans les rues' (Rogers) = piege en mean-reversion intraday.",
        "decision": "NE PAS chercher les creux extremes. Les strategies RSI<30 actuelles sont bonnes; eviter RSI<20 serait un raffinement (3 entrees, echantillon faible).",
        "statut": "REJETEE (creux profond = couteau tombant)",
        "meta_pattern": "Refinement du mean-reversion: acheter les creux MODERES (RSI 20-30), pas les extremes (<20). Le dip-buying gate actuel (bloquer bougies haussieres) reste valide; ne pas ajouter de preference pour les creux extremes.",
    },
    {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hypothese": "Sagesse Soros/PTJ: 'cut losers fast' (exit rapide des perdants), 'savoir quand on a tort'",
        "source": "sagesse_traders.py + backtest_sagesse.py test cut_losers",
        "test": "cut@12/18/24 bars vs patience (MAX_BARS normal), 29 entrees",
        "resultat": "REJETE. cut@12=4.90%, cut@18=7.35%, cut@24=7.19% vs normal 12.18%. Toutes les coupes rapides DEGRADENT le PnL (-5 a -7%).",
        "raison": "En mean-reversion, une position perdante est un creux plus profond qui finit par rebondir. Couper vite empeche la recuperation. Le risk management trend-style (Soros 'je sais quand j'ai tort', PTJ cut losers) ne s'applique PAS au mean-reversion: la patience paie.",
        "decision": "NE PAS ajouter d'exit rapide des perdants. Garder le time-stop MAX_BARS actuel (patience).",
        "statut": "REJETEE (la patience paie en mean-reversion, pas le cut rapide)",
        "meta_pattern": "5eme/6eme principe trend/contrarian rejete. Le mean-reversion veut de la PATIENCE (laisser les creux rebondir), l'inverse du 'cut losers fast'. Confirme: la sagesse classique du trading est souvent INVERSEE pour ce systeme.",
    },
    {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hypothese": "Sagesse Richard Dennis (Turtle Traders): breakout Donchian 20-bar (trend-following rules-based)",
        "source": "sagesse_traders.py + backtest_sagesse.py test turtle_breakout",
        "test": "Donchian 20-bar breakout sur 9 marches, 500 bars, 456 trades",
        "resultat": "NUANCE. 55.0% win, +49.98% PnL total, MAIS 0.11% avg/trade (vs 0.42% pour strategies actuelles). Volume eleve (456 vs 29).",
        "raison": "Le breakout a une expectancy positive tous regimes confondus (55% win > 50%) car les periodes TREND payent. MAIS qualite par trade 4x inferieure aux strategies mean-reversion, et le volume incompatible avec les caps (3 positions max). Sous caps, les strategies actuelles restent superieures.",
        "decision": "NE PAS deployer le breakout Donchian comme strategie principale. MAIS valeur regime-conditionnelle: a tester SEULEMENT sur entrees en regime TREND (ou le trend-following a ete valide theoriquement). Piste future.",
        "statut": "NUANCE (rejete en principal, piste regime TREND)",
        "meta_pattern": "Exception qui confirme: le trend-following (Turtle) a une expectancy positive sur la duree, mais le mean-reversion est superieur en qualité per-trade. Le systeme devrait conditionner le trend au regime TREND uniquement (deja theorise avec EXTEND/ADX/trailing).",
    },
]

with open(F, "a", encoding="utf-8") as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(f"OK {len(entries)} lecons sagesse enregistrees")
n = sum(1 for _ in open(F, encoding="utf-8"))
print(f"   Total lecons: {n}")
