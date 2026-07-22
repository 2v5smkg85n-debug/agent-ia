#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_multi_strat.py — MULTI-STRATEGIES PARALLELES.
1. signaux_gagnants: collecte TOUS les ACHAT par actif (top-N par score) au lieu
   du seul meilleur. Avant: si la meilleure strat etait silencieuse, l'actif ne
   trade jamais, meme si une 2eme strat declenchait. Maintenant: top-N strats.
2. paper_trading: autorise jusqu'a MAX_POS_PAR_ACTIF positions par actif (differentes
   strategies) au lieu de 1. + MAX_POSITIONS 5->8 (slots pour les strats reparees).
Risk controle par caps existants: CAP_ACTIF 15%/actif, CAP_SECTEUR 40%/secteur, Kelly."""
import sys

MAX_N = 2  # top-N strategies par actif
MAX_POS = 8  # positions concurrentes (etait 5)

# ---------- 1. signaux_gagnants.py ----------
sf = "signaux_gagnants.py"
s = open(sf, encoding="utf-8").read()

# Constante MAX_SIGNAUX_PAR_ACTIF (pres de DIP_BUYING_GATE ou apres les imports)
if "MAX_SIGNAUX_PAR_ACTIF" in s:
    print("[signaux] constante deja presente - skip")
else:
    anchor = "STRATEGIES_TOUTES = STRATEGIES\n"
    if anchor in s:
        s = s.replace(anchor, anchor + "\n# MULTI-STRAT: nb max de signaux ACHAT retournes par actif (top-N par score)\n"
                        "MAX_SIGNAUX_PAR_ACTIF = %d\n" % MAX_N, 1)
        print("[signaux] constante MAX_SIGNAUX_PAR_ACTIF=%d ajoutee" % MAX_N)
    else:
        print("[signaux] ERREUR ancre STRATEGIES_TOUTES"); sys.exit(1)

# init candidats_achat apres meilleur_score
OLD_INIT = """        meilleur_signal = None
        meilleure_strat = None
        meilleur_retour = -999
        meilleur_score = -999  # REGIME-FIT-INSTALLE"""
NEW_INIT = """        meilleur_signal = None
        meilleure_strat = None
        meilleur_retour = -999
        meilleur_score = -999  # REGIME-FIT-INSTALLE
        candidats_achat = []  # MULTI-STRAT: collecte tous les ACHAT (score, retour, strat)"""
if "candidats_achat = []" in s:
    print("[signaux] candidats_achat init deja present - skip")
elif OLD_INIT in s:
    s = s.replace(OLD_INIT, NEW_INIT, 1)
    print("[signaux] init candidats_achat ajoute")
else:
    print("[signaux] ERREUR ancre meilleur_score"); sys.exit(1)

# collecter chaque ACHAT + garder le meilleur (pour log)
OLD_TRACK = """                    _score = strat.get("retour_pct", 0) * _fit_avg * _live_mult
                    if _score > meilleur_score:
                        meilleur_score = _score
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = {**strat, "intervalle_live": interv_live,
                                           "regime_1h": _r1h.get("regime"),
                                           "regime_4h": _r4h.get("regime"),
                                           "regime_fit": round(_fit_avg, 3),
                                           "live_mult": round(_live_mult, 3),
                                           "biais_bougies": round(_biais_bougies, 2)}"""
NEW_TRACK = """                    _score = strat.get("retour_pct", 0) * _fit_avg * _live_mult
                    _strat_full = {**strat, "intervalle_live": interv_live,
                                   "regime_1h": _r1h.get("regime"),
                                   "regime_4h": _r4h.get("regime"),
                                   "regime_fit": round(_fit_avg, 3),
                                   "live_mult": round(_live_mult, 3),
                                   "biais_bougies": round(_biais_bougies, 2)}
                    candidats_achat.append((_score, strat.get("retour_pct", 0), _strat_full))
                    if _score > meilleur_score:
                        meilleur_score = _score
                        meilleur_retour = strat.get("retour_pct", 0)
                        meilleur_signal = sig
                        meilleure_strat = _strat_full"""
if "candidats_achat.append" in s:
    print("[signaux] tracking candidats deja present - skip")
elif OLD_TRACK in s:
    s = s.replace(OLD_TRACK, NEW_TRACK, 1)
    print("[signaux] tracking candidats_achat ajoute")
else:
    print("[signaux] ERREUR ancre _score/meilleur_score"); sys.exit(1)

# remplace l'append unique par top-N appends
OLD_APPEND = """        if meilleur_signal == "ACHAT":
            interv_aff = meilleure_strat.get("intervalle", "?")
            _lm = meilleure_strat.get("live_mult", 1.0)
            _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""
            _bb_s = meilleure_strat.get("biais_bougies", 0.0)
            _bb_str = f", dip {_bb_s:+.2f}" if _bb_s != 0 else ""
            print(f"ACHAT ({meilleure_strat['strategie']} [{interv_aff}], "
                  f"backtest {meilleur_retour:+.1f}%{_lm_str}{_bb_str})")
            signaux.append({
                "symbole": symbole,
                "prix_entree": prix_actuels[symbole],
                "nom": config["nom"],
                "marche": config["marche"],
                "source": "backtest-gagnant",
                "score": 2,
                "strategie": meilleure_strat.get("strategie", ""),
                "backtest_stats": meilleure_strat,
                "raison": (f"strategie gagnante backtest "
                           f"({meilleure_strat['strategie']} [{interv_aff}], "
                           f"retour {meilleur_retour:+.1f}%, "
                           f"win rate {meilleure_strat.get('win_rate',0)}%)"),
            })
        else:
            print("neutre")
        time.sleep(0.3)"""
NEW_APPEND = """        if meilleur_signal == "ACHAT" and candidats_achat:
            # MULTI-STRAT: top-N strategies ACHAT par score (pas juste la meilleure)
            candidats_achat.sort(key=lambda c: c[0], reverse=True)
            for _sc, _retour, _strat in candidats_achat[:MAX_SIGNAUX_PAR_ACTIF]:
                interv_aff = _strat.get("intervalle", "?")
                _lm = _strat.get("live_mult", 1.0)
                _lm_str = f", live x{_lm:.2f}" if abs(_lm - 1.0) > 0.01 else ""
                _bb_s = _strat.get("biais_bougies", 0.0)
                _bb_str = f", dip {_bb_s:+.2f}" if _bb_s != 0 else ""
                print(f"ACHAT ({_strat['strategie']} [{interv_aff}], "
                      f"backtest {_retour:+.1f}%{_lm_str}{_bb_str})")
                signaux.append({
                    "symbole": symbole,
                    "prix_entree": prix_actuels[symbole],
                    "nom": config["nom"],
                    "marche": config["marche"],
                    "source": "backtest-gagnant",
                    "score": 2,
                    "strategie": _strat.get("strategie", ""),
                    "backtest_stats": _strat,
                    "raison": (f"strategie gagnante backtest "
                               f"({_strat['strategie']} [{interv_aff}], "
                               f"retour {_retour:+.1f}%, "
                               f"win rate {_strat.get('win_rate',0)}%)"),
                })
        else:
            print("neutre")
        time.sleep(0.3)"""
if "top-N strategies ACHAT" in s:
    print("[signaux] append top-N deja present - skip")
elif OLD_APPEND in s:
    s = s.replace(OLD_APPEND, NEW_APPEND, 1)
    print("[signaux] append top-N applique")
else:
    print("[signaux] ERREUR ancre append"); sys.exit(1)

open(sf, "w", encoding="utf-8").write(s)

# ---------- 2. paper_trading.py ----------
pf = "paper_trading.py"
p = open(pf, encoding="utf-8").read()

# MAX_POSITIONS 5 -> 8 + ajout MAX_POS_PAR_ACTIF
OLD_MP = "MAX_POSITIONS = 5               # 5 positions (plus de diversification)"
NEW_MP = "MAX_POSITIONS = %d              # positions concurrentes (multi-strat)\nMAX_POS_PAR_ACTIF = %d           # max positions par actif (differentes strategies)" % (MAX_POS, MAX_N)
if "MAX_POS_PAR_ACTIF" in p:
    print("[paper] MAX_POS_PAR_ACTIF deja present - skip")
elif OLD_MP in p:
    p = p.replace(OLD_MP, NEW_MP, 1)
    print("[paper] MAX_POSITIONS->%d, MAX_POS_PAR_ACTIF=%d ajoute" % (MAX_POS, MAX_N))
else:
    print("[paper] ERREUR ancre MAX_POSITIONS"); sys.exit(1)

# boucle d'ouverture: 1-par-actif -> N-par-actif (compteur)
OLD_LOOP = """    if len(pf["positions"]) < MAX_POSITIONS:
        symboles_ouverts = {p["symbole"] for p in pf["positions"]}
        print("\\nAnalyse strategies gagnantes (backtest reel)...")"""
NEW_LOOP = """    if len(pf["positions"]) < MAX_POSITIONS:
        from collections import Counter
        nb_par_actif = Counter(pos["symbole"] for pos in pf["positions"])
        print("\\nAnalyse strategies gagnantes (backtest reel)...")"""
if "nb_par_actif = Counter" in p:
    print("[paper] loop counter deja present - skip")
elif OLD_LOOP in p:
    p = p.replace(OLD_LOOP, NEW_LOOP, 1)
    print("[paper] loop init counter applique")
else:
    print("[paper] ERREUR ancre loop init"); sys.exit(1)

OLD_OPEN = """        if tous_signaux:
            print(f"\\n{len(tous_signaux)} signal(s) d'achat detecte(s)")
            # Phase 3: filtre ML - confirme les signaux via le modele predictif
            # Seuls les signaux confirmes par le ML (sur les actifs avec edge) sont gardes
            try:
                from ml_filtre import confirmer_signaux_ml
                signaux_avant = len(tous_signaux)
                tous_signaux = confirmer_signaux_ml(tous_signaux)
                if len(tous_signaux) < signaux_avant:
                    print(f"  -> filtre ML: {signaux_avant} -> {len(tous_signaux)} signaux confirmes")
            except Exception as e:
                print(f"  (filtre ML indisponible: {e})")
            for signal in tous_signaux:
                if signal["symbole"] not in symboles_ouverts:
                    ouvrir_position(pf, signal, prix[signal["symbole"]])
                    symboles_ouverts.add(signal["symbole"])"""
NEW_OPEN = """        if tous_signaux:
            print(f"\\n{len(tous_signaux)} signal(s) d'achat detecte(s)")
            # Phase 3: filtre ML - confirme les signaux via le modele predictif
            # Seuls les signaux confirmes par le ML (sur les actifs avec edge) sont gardes
            try:
                from ml_filtre import confirmer_signaux_ml
                signaux_avant = len(tous_signaux)
                tous_signaux = confirmer_signaux_ml(tous_signaux)
                if len(tous_signaux) < signaux_avant:
                    print(f"  -> filtre ML: {signaux_avant} -> {len(tous_signaux)} signaux confirmes")
            except Exception as e:
                print(f"  (filtre ML indisponible: {e})")
            for signal in tous_signaux:
                if len(pf["positions"]) >= MAX_POSITIONS:
                    break  # plus de slots disponibles
                if nb_par_actif[signal["symbole"]] < MAX_POS_PAR_ACTIF:
                    if ouvrir_position(pf, signal, prix[signal["symbole"]]):
                        nb_par_actif[signal["symbole"]] += 1"""
if "nb_par_actif[signal[\"symbole\"]] < MAX_POS_PAR_ACTIF" in p:
    print("[paper] loop open deja patche - skip")
elif OLD_OPEN in p:
    p = p.replace(OLD_OPEN, NEW_OPEN, 1)
    print("[paper] loop open N-par-actif applique")
else:
    print("[paper] ERREUR ancre loop open"); sys.exit(1)

open(pf, "w", encoding="utf-8").write(p)

print("\n=== PATCH MULTI-STRAT APPLIQUE ===")
print("signaux_gagnants: top-%d strategies par actif" % MAX_N)
print("paper_trading: MAX_POSITIONS=%d, MAX_POS_PAR_ACTIF=%d" % (MAX_POS, MAX_N))
