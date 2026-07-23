#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_temps_adaptatif.py — time exit adaptatif selon le gain + la stratégie.

Problème: à 90 min, un trade entre +0.30% et +0.60% se fait couper (TEMPS+benefice)
alors qu'il pourrait encore monter vers partial TP (+1%) / trailing / TP.
Seuls les gagnants "protégés" (>= +0.60% breakeven) respiraient jusqu'à 4h.

Solution: respiration adaptative par palier de gain + bonus stratégie prouvée.
  gain >= 0.60% (breakeven)  -> respire 4h   (DUREE_GAGNANT_MAX, existant)
  gain >= 0.45% (progress)   -> respire 3h   (DUREE_GAIN_PROGRESS, nouveau)
  gain >= 0.30% (petit gain)  -> respire 2h   (DUREE_PETIT_GAIN, nouveau; était 90min)
  + stratégie prouvée         -> +1h bonus   (DUREE_BONUS_STRATEGIE, nouveau)

Les gagnants restent plus longtemps en market pour atteindre les zones de profit
supérieur (partial TP, trailing, TP). Les perdants (sous 0.30%) restent libérés à 3h
(STALE). Le SL fixe (-1.5%) borne la perte max inchangée.

Idempotent: skip si DUREE_PETIT_GAIN déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: nouvelles constantes ---
ancien_c = "DUREE_GAGNANT_MAX = 240         # gagnant protégé (breakeven armé): respire jusqu'à 4h pour atteindre partial/TP/trailing"
nouveau_c = (
    "DUREE_PETIT_GAIN = 120        # gain 0.30-0.45%: respire 2h (était 90min) pour viser partial TP\n"
    "DUREE_GAIN_PROGRESS = 180    # gain 0.45-0.60%: respire 3h\n"
    "DUREE_GAGNANT_MAX = 240         # gagnant protégé (breakeven armé): respire jusqu'à 4h pour atteindre partial/TP/trailing\n"
    "DUREE_BONUS_STRATEGIE = 60    # stratégie prouvée (live_n>=3, wr>=60%, pnl>0): +1h de respiration"
)
if ancien_c in src and "DUREE_PETIT_GAIN" not in src:
    src = src.replace(ancien_c, nouveau_c)
    edits += 1
    print("[paper] edit1: constantes respiration adaptative")

# --- Edit 2: charger les stratégies prouvées en début de verifier_sorties ---
ancien_load = "    positions_a_fermer = []\n    maintenant = datetime.now()\n    for pos in pf[\"positions\"]:"
nouveau_load = (
    "    positions_a_fermer = []\n"
    "    maintenant = datetime.now()\n"
    "    # Stratégies prouvées (pour bonus de durée): chargé une fois par cycle\n"
    "    _strats_prouvees = set()\n"
    "    try:\n"
    "        _cs = json.load(open(\"classement_strategies.json\"))\n"
    "        for _symc, _datac in _cs.items():\n"
    "            for _sc in _datac.get(\"strategies\", []):\n"
    "                if _sc.get(\"live_n\", 0) >= 3 and _sc.get(\"live_wr\", 0) >= 60 and _sc.get(\"live_pnl\", 0) > 0:\n"
    "                    _strats_prouvees.add((_symc, _sc.get(\"strategie\", \"\")))\n"
    "    except Exception:\n"
    "        pass\n"
    "    for pos in pf[\"positions\"]:"
)
if ancien_load in src and "_strats_prouvees" not in src:
    src = src.replace(ancien_load, nouveau_load)
    edits += 1
    print("[paper] edit2: chargement stratégies prouvées")

# --- Edit 3: logique de durée adaptative ---
ancien_log = (
    "                # Gagnant protégé (breakeven armé): respire jusqu à DUREE_GAGNANT_MAX\n"
    "                # pour atteindre partial TP / TP / trailing. Le SL est au breakeven -> pas de risque.\n"
    "                if os.getenv(\"EXIT_AVANCE\", \"1\") != \"0\" and variation >= BREAKEVEN_SEUIL:\n"
    "                    duree_min = max(duree_min, DUREE_GAGNANT_MAX)"
)
nouveau_log = (
    "                # RESPIRATION ADAPTATIVE: plus c'est gagnant, plus ça respire\n"
    "                # (pour laisser le temps d'atteindre partial TP +1% / trailing / TP)\n"
    "                if os.getenv(\"EXIT_AVANCE\", \"1\") != \"0\":\n"
    "                    if variation >= BREAKEVEN_SEUIL:        # >= 0.60% : protégé, respire 4h\n"
    "                        duree_min = max(duree_min, DUREE_GAGNANT_MAX)\n"
    "                    elif variation >= 0.45:                 # bon gain non protégé: respire 3h\n"
    "                        duree_min = max(duree_min, DUREE_GAIN_PROGRESS)\n"
    "                    elif variation >= SEUIL_BENEFICE_MIN:   # petit gain: respire 2h\n"
    "                        duree_min = max(duree_min, DUREE_PETIT_GAIN)\n"
    "                    # Bonus stratégie prouvée: +1h (laisse plus de temps aux stratégies qui gagnent)\n"
    "                    if (sym, pos.get(\"strategie\", \"\")) in _strats_prouvees:\n"
    "                        duree_min += DUREE_BONUS_STRATEGIE"
)
if ancien_log in src and "RESPIRATION ADAPTATIVE" not in src:
    src = src.replace(ancien_log, nouveau_log)
    edits += 1
    print("[paper] edit3: logique durée adaptative (3 paliers + bonus stratégie)")

open(P, "w").write(src)
print(f"\n=== TEMPS ADAPTATIF APPLIQUÉ ===  ({edits} edits)")
print("gain 0.30-0.45% -> 2h | 0.45-0.60% -> 3h | >=0.60% -> 4h | +1h si stratégie prouvée")
