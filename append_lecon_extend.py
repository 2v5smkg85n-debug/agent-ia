#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_extend.py — Lecon EXTEND (nuancee, regime-conditionnelle)."""
import os, json
from datetime import datetime

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(os.path.join(os.getcwd(), "reflection_gemini.py")) else os.getcwd()
F = os.path.join(D, "lecons_apprises.jsonl")

entry = {
    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "hypothese": "EXTEND: stop breakeven (+0.5%) + TP dynamique monte a +3% quand en profit (idee utilisateur: stop positif -> TP augmente)",
    "source": "idee utilisateur (laisser courir les gagnants + verrouiller)",
    "test": "backtest_trailing.py mode EXTEND sur 5 cryptos vs FIXE",
    "resultat": "DEGRADE le PnL global: EXTEND 6.92% vs FIXE 10.53% (-3.61%). MAIS gain moyen PLUS ELEVE (2.62% vs 1.78%) et gain max plus haut (9.13% vs 8.70%). Win rate chute 75%->41.7%.",
    "raison": "EXTEND produit de plus gros gagnants mais le breakeven stop se fait whipsawer en marche rangeant (sortie a 0% sur pullback au lieu de capturer le rebond). Mecanisme TREND-FRIENDLY, mal adapte au regime range actuel.",
    "decision": "NE PAS activer EXTEND en live maintenant (marche rangeant). MAIS c'est regime-conditionnel: a retester sur les entrees en regime TRENDING uniquement.",
    "opportunite_future": "TP/SL conditionnel au regime: FIXE en RANGING/QUIET, EXTEND en TRENDING. regime.py peut detecter le regime. Backtest future: mesurer EXTEND seulement sur entrees trendantes.",
    "meta_pattern": "3eme mecanisme trend-friendly rejete en range (apres ADX, trailing). Confirme: la gestion dynamique des gagnants DOIT etre conditionnee au regime. EXTEND est le moins pire des 3 (-3.61% vs -6.62% trailing, -2556€ ADX).",
    "statut": "REJETEE en range (regime-conditionnel)",
}
with open(F, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("✅ lecon EXTEND enregistree (nuancee: regime-conditionnelle)")
n = sum(1 for _ in open(F, encoding="utf-8"))
print(f"   Total lecons: {n}")
