#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test intégration consensus_ia <-> paper_trading.analyser_signaux_ia."""
import os, sys, types

# --- mock agent (servira a paper_trading ET consensus_ia) ---
mock_agent = types.ModuleType("agent")
DISPO = {"perplexity": True, "gemini": True, "claude": True, "chatgpt": False}
REP = {
    "perplexity": "ACHAT: Apple | RAISON: momentum positif\n",
    "gemini": "ACHAT: Apple | RAISON: RSI bas\n",
    "claude": "ACHAT: Tesla | RAISON: breakout volume\n",
}
def disponible(m): return DISPO.get(m, False)
def appeler_ia(modele, prompt, tentative=1):
    return REP.get(modele, "[Erreur mock]"), modele
def notify_ifft(*a, **k): pass
def ajouter(*a, **k): pass
mock_agent.disponible = disponible
mock_agent.appeler_ia = appeler_ia
mock_agent.notify_ifft = notify_ifft
mock_agent.ajouter = ajouter
sys.modules["agent"] = mock_agent

# --- mock backtest ---
mock_bt = types.ModuleType("backtest")
mock_bt.charger_backtests = lambda: {}
sys.modules["backtest"] = mock_bt

sys.path.insert(0, "/tmp/agent-ia-inspect")
import paper_trading as pt
# strategies_gagnantes doit retourner non-vide pour passer le garde
pt.strategies_gagnantes = lambda: [{"marche": "actions", "strategie_contenu": "RSI<30 buy"}]

PRIX = {"AAPL": 190.0, "TSLA": 250.0, "BTCUSDT": 60000.0}

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

print("=" * 60)
print("INTÉGRATION: analyser_signaux_ia x consensus_ia")

print("\nTEST 1: CONSENSUS_IA=0 (mono) — claude flag Tesla")
os.environ["CONSENSUS_IA"] = "0"
os.environ.pop("CONSENSUS_QUORUM", None)
sig = pt.analyser_signaux_ia(PRIX)
syms = [s["symbole"] for s in sig]
check("mono retourne Tesla (claude)", "TSLA" in syms, str(syms))
check("mono raison='signal IA'", any(s["raison"] == "signal IA" for s in sig), str([s['raison'] for s in sig]))

print("\nTEST 2: CONSENSUS_IA=1 — Apple retenu (2/3 modèles), Tesla non (1/3)")
os.environ["CONSENSUS_IA"] = "1"
os.environ["CONSENSUS_QUORUM"] = "2"
sig = pt.analyser_signaux_ia(PRIX)
syms = [s["symbole"] for s in sig]
check("consensus retient Apple (majorité 2/3)", "AAPL" in syms, str(syms))
check("consensus exclut Tesla (1 seul)", "TSLA" not in syms, str(syms))
check("raison marque 'consensus'", any("consensus" in s["raison"] for s in sig), str([s['raison'] for s in sig]))

print("\nTEST 3: CONSENSUS_IA=1 fail-open — 1 seul modèle dispo -> mono")
DISPO["perplexity"] = False; DISPO["gemini"] = False
# seul claude dispo; consensus_achats retourne None (< quorum) -> _mono -> claude -> Tesla
sig = pt.analyser_signaux_ia(PRIX)
syms = [s["symbole"] for s in sig]
check("fail-open bascule mono -> Tesla", "TSLA" in syms, str(syms))
# restaure
DISPO["perplexity"] = True; DISPO["gemini"] = True

print("\nTEST 4: CONSENSUS_IA=1 quorum 3 — aucun actif (Apple n'a que 2/3)")
os.environ["CONSENSUS_QUORUM"] = "3"
sig = pt.analyser_signaux_ia(PRIX)
check("quorum 3 -> aucun signal (pas de majorité)", len(sig) == 0, str([s['symbole'] for s in sig]))

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
