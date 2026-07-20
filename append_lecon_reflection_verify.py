#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_lecon_reflection_verify.py — Lecon 9: reflection = generateur d'hypotheses,
backtest obligatoire (LLM a hallucine Bollinger -1.58€ inexistant)."""
import json
from datetime import datetime

F = "lecons_apprises.jsonl"
entrees = [json.loads(l) for l in open(F, encoding="utf-8") if l.strip()]

# modeles des cles du dernier enregistrement
last = entrees[-1] if entrees else {}
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

nouvelle = dict(last)  # herite la structure
nouvelle.update({
    "ts": now,
    "hypothese": "Reflection Gemini: desactiver Bollinger Breakout + monter EXTEND_TP a 4.5%",
    "source": "reflection_gemini (fallback Perplexity)",
    "statut": "REJETEE (backtest)",
    "backtest": "Bollinger: backtest +22.03% (SOL 15.27%), live 1 trade +0.12€ (IA hallucine -1.58€/2trades inexistants). EXTEND_TP 4.5%: 31.40% vs 4.0%=35.65% (-4.25pt, plateau confirme a 4.0).",
    "verdict": "REJETEE. La reflection est un GENERATEUR D'HYPOTHESES: utile pour explorer, mais l'LLM peut halluciner les donnees de perf. TOUJOURS backtester avant deploy. Ne pas auto-executer les suggestions sans validation backtest.",
    "meta": "Discipline validee: reflection propose -> backtest valide/rejette -> lecon -> reflection lit la lecon et evite de re-proposer. Boucle d'auto-apprentissage correcte.",
})
with open(F, "a", encoding="utf-8") as f:
    f.write(json.dumps(nouvelle, ensure_ascii=False) + "\n")

print(f"OK lecon 9 ajoutee (total: {len(entrees)+1})")
print(f"  hypothese: {nouvelle['hypothese']}")
print(f"  statut: {nouvelle['statut']}")
