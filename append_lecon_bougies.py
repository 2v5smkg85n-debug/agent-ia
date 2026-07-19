#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_bougies.py — Lecon lecture chandeliers (rejetee + nuance mean-reversion)."""
import os, json
from datetime import datetime

D = os.path.dirname(os.path.abspath("paper_trading.py")) or os.getcwd()
F = os.path.join(D, "lecons_apprises.jsonl")

entry = {
    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "hypothese": "Lire les chandeliers japonais (engulfing, marteau, marubozu...) pour predire direction haussiere/baissiere et confirmer les entrees",
    "source": "idee utilisateur (IA doit lire les bougies)",
    "test": "backtest_bougies.py: biais chandeliers au moment de l'entree vs issue du trade, 29 entrees sur 9 marches",
    "resultat": "REJETE. Filtre biais haussier NUIT: win 50.0% vs 62.1% toutes (-12.1pt), avgPnL -0.23%. Contre-intuitif: entrees avec bougie BAISSIERE gagnent PLUS (68.4% win, 10.31% PnL).",
    "raison": "Les strategies du systeme sont majoritairement mean-reversion (RSI Mean Reversion #1 en QUIET). Le mean-reversion achete les creux -> la derniere bougie a l'entree est souvent baissiere (le creux achete), puis rebond. Donc bougie baissiere=bon (achat creux), bougie haussiere=mauvais (achat dans la force, en range). Le signal classique 'bougie haussiere=continuation haussiere' est FAUX pour un systeme mean-reversion.",
    "decision": "NE PAS integrer le biais haussier comme confirmation d'entree. Rejet documente.",
    "opportunite_future": "Hypothese inverse a tester: FILTRE 'dip-buying' = ne prendre QUE les entrees avec bougie baissiere (confirmer l'achat de creux). 19 trades baissiers=68.4% win vs 62.1% toutes -> prometteur mais echantillon faible. A retester separement.",
    "meta_pattern": "4eme test rejete. Lecon transverse: les signaux 'directionnels classiques' (trend-following, bougies haussieres) nuisent en regime range/mean-reversion. Le systeme est mean-reversion -> les confirmations doivent etre 'achat de creux' (biais baissier), pas 'continuation' (biais haussier).",
    "statut": "REJETEE (biais haussier). Piste inverse (biais baissier) a explorer.",
}
with open(F, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("✅ lecon bougies enregistree (rejetee + nuance mean-reversion)")
n = sum(1 for _ in open(F, encoding="utf-8"))
print(f"   Total lecons: {n}")
