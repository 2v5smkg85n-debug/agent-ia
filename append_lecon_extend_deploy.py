#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_extend_deploy.py — Lecon: EXTEND_TP deploye en live (version corrigee)."""
import os, json
from datetime import datetime

D = os.path.dirname(os.path.abspath("paper_trading.py")) or "."
F = os.path.join(D, "lecons_apprises.jsonl")

entry = {
    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "hypothese": "EXTEND_TP corrige: monter le TP en profit SANS breakeven (le breakeven etait le coupable du win rate bas). Idee utilisateur amelioree.",
    "source": "idee utilisateur + sweep backtest elargi (9 marches, 30 trades)",
    "test": "sweep_extend_full.py: tp_ext 2.5->8.0 sur 9 marches. Plateau a tp_ext=4.0 (30.35% vs FIXE 16.05%, +14.30%). Crypto-only: +13.35%, TOUS actifs non-negatifs.",
    "resultat": "AMELIORE le PnL: EXTEND_TP +14.30% vs FIXE. Win rate 66.7%->63.3% (-3.4pt seulement). Gain moyen 1.78%->2.71%. Courbe PLAFONNE a tp_ext=4 (edge reel, pas outlier). Diversifie (BTC+4.88, XRP+6.21, ETH+2.26, NG+1.22, HG+2.01).",
    "raison": "Sans breakeven, les gagnants courent plus loin (TP 2.0->4.0) sans etre whipsawes. Les perdants restent identiques (SL fixe). Forex/or mitiges (GC-0.86, ZW-1.41) donc crypto-only.",
    "decision": "DEPLOYE en live (commit 4dbf456). paper_trading.py: EXTEND_CRYPTOS, EXTEND_SEUIL=0.5%, EXTEND_TP_PCT=4.0%, EXTEND_DUREE_MAX=480min (8h). Cap duree etendu car live TEMPS=90min sinon couperait avant 4.0%.",
    "statut": "DEPLOYEE (crypto only)",
    "meta_pattern": "Le breakeven stop etait le coupable, pas l'idee. Retirer le breakeven a transforme un rejet (-3.61%) en succes (+14.30%). Lecon: quand une idee echoue, isoler le composant responsable avant de tout rejeter.",
    "a_surveiller": "Monitorer 'TAKE-PROFIT-EXTEND' dans trades fermes. Si perf live crypto > FIXE sur 2-4 semaines -> etendre EXTEND_TP au forex/or (avec TP 1.5->3.0). Si perf degrade -> revert.",
}
with open(F, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("✅ lecon EXTEND_TP deploye enregistree")
n = sum(1 for _ in open(F, encoding="utf-8"))
print(f"   Total lecons: {n}")
