#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test consensus_ia.py — mock des modèles (pas d'appel réseau)."""
import os
import sys
import types

# --- mock agent module avant import ---
mock_agent = types.ModuleType("agent")
KEYS = {"perplexity": "x", "gemini": "x", "claude": "x", "chatgpt": ""}
def disponible(m):
    return KEYS.get(m, "") != ""
# réponses par modèle (scénario: 3 modèles, 2 flaguent BTC, 1 seul ETH, 1 RIEN)
REPONSES = {
    "perplexity": "ACHAT: BTC | RAISON: momentum positif\nACHAT: ETH | RAISON: breakout\n",
    "gemini": "ACHAT: BTC | RAISON: RSI bas\nAUCUN SIGNAL\n",
    "claude": "AUCUN SIGNAL\n",
}
def appeler_ia(modele, prompt, tentative=1):
    return REPONSES.get(modele, "[Erreur mock]"), modele
mock_agent.disponible = disponible
mock_agent.appeler_ia = appeler_ia
sys.modules["agent"] = mock_agent

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consensus_ia as ci

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

print("=" * 60)
print("TEST 1: _extraire_achats parse correctement")
a = ci._extraire_achats("ACHAT: BTC | RAISON: momentum\nACHAT: ETH | RAISON: breakout\n")
check("extrait BTC", "BTC" in a, str(a))
check("extrait ETH", "ETH" in a, str(a))
check("AUCUN SIGNAL -> vide", ci._extraire_achats("AUCUN SIGNAL") == set())
check("pas d'ACHAT -> vide", ci._extraire_achats("VENTE: BTC") == set())

print("\nTEST 2: consensus_achats — quorum 2 atteint, BTC consensus (2/3), ETH non (1/3)")
os.environ["CONSENSUS_QUORUM"] = "2"
achats, meta = ci.consensus_achats("prompt test")
check("BTC dans consensus (2 modèles)", "BTC" in achats, str(achats))
check("ETH PAS dans consensus (1 seul)", "ETH" not in achats, str(achats))
check("quorum_atteint True", meta.get("quorum_atteint"), str(meta))
check("3 modèles ont répondu", meta.get("n_ok") == 3, str(meta.get("n_ok")))
check("par_modele présent", "perplexity" in meta.get("par_modele", {}))
check("votes BTC = 2 modèles", len(meta["votes"].get("BTC", [])) == 2, str(meta.get("votes")))

print("\nTEST 3: quorum 3 — aucun actif consensus (BTC n'a que 2/3)")
os.environ["CONSENSUS_QUORUM"] = "3"
achats, meta = ci.consensus_achats("prompt test")
check("aucun actif (quorum 3 non atteint par BTC)", "BTC" not in achats, str(achats))

print("\nTEST 4: fail-open — < quorum modèles répondent")
os.environ["CONSENSUS_QUORUM"] = "2"
# simuler 1 seul modèle dispo
ci.KEYS_BACKUP = dict(KEYS)
KEYS["gemini"] = ""; KEYS["claude"] = ""
achats, meta = ci.consensus_achats("prompt test")
check("fail-open retourne None (1 seul modèle < quorum 2)", achats is None, str(achats))
check("meta quorum_atteint False", meta.get("quorum_atteint") == False)
# restaure
KEYS["gemini"] = "x"; KEYS["claude"] = "x"

print("\nTEST 5: 0 modèle dispo -> fail-open None")
KEYS["perplexity"] = ""; KEYS["gemini"] = ""; KEYS["claude"] = ""
achats, meta = ci.consensus_achats("prompt test")
check("0 modele -> None", achats is None)
check("meta raison = aucun modele", "aucun" in meta.get("raison", "").lower(), str(meta))
KEYS["perplexity"] = "x"; KEYS["gemini"] = "x"; KEYS["claude"] = "x"

print("\nTEST 6: consensus() générique retourne toutes les réponses valides")
os.environ["CONSENSUS_QUORUM"] = "2"
reps, meta = ci.consensus("prompt")
check("3 réponses", len(reps) == 3, str(len(reps)))
check("tous modèles présents", set(m for m, _ in reps) == {"perplexity", "gemini", "claude"})

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
