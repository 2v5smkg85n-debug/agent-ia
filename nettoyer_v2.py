#!/usr/bin/env python3
"""Nettoyage v2 — coupe les stratégies 'perdues' (resultat == 'perdu').
Basé sur les champs d'evaluation propres de strategies.json.
Sauvegarde automatique (reversible)."""
import json
import shutil
import datetime
from collections import Counter


def load(n, d):
    try:
        return json.load(open(n))
    except Exception:
        return d


def main():
    strats = load("strategies.json", [])
    if not strats:
        print("ERREUR: strategies.json vide/absent.")
        return

    # Sauvegarde
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"strategies_backup_{ts}.json"
    shutil.copy2("strategies.json", bak)

    dist = Counter(s.get("resultat", "?") for s in strats if isinstance(s, dict))
    print(f"AVANT: {len(strats)} stratégies — {dict(dist)}")
    print(f"Sauvegarde: {bak}\n")

    # Coupe les 'perdu', garde 'gagne' + 'neutre'
    kept, cut = [], []
    for s in strats:
        res = str(s.get("resultat", "")).lower().strip("[] ")
        if res == "perdu":
            cut.append(s)
        else:
            kept.append(s)

    # Distribution après, par marché
    kept_dist = Counter(s.get("resultat", "?") for s in kept if isinstance(s, dict))
    cut_by_marche = Counter(s.get("marche", "?") for s in cut if isinstance(s, dict))
    print(f"COUPÉES: {len(cut)} (resultat=perdu)")
    print(f"  par marché: {dict(cut_by_marche)}")
    print(f"GARDÉES: {len(kept)} — {dict(kept_dist)}\n")

    # Ecrire strategies.json nettoyé
    with open("strategies.json", "w") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    # Audit + blacklist
    audit = {
        "date": ts,
        "avant": len(strats), "apres": len(kept), "coupees": len(cut),
        "critere": "resultat == perdu (évaluation AI unique par stratégie)",
        "distribution_avant": dict(dist),
        "coupees_par_marche": dict(cut_by_marche),
        "indices_coupees": [i for i, s in enumerate(strats)
                            if isinstance(s, dict) and str(s.get("resultat", "")).lower().strip("[] ") == "perdu"],
    }
    with open("strategies_audit.json", "w") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    print("=== Stratégies conservées (gagnantes + neutres) ===")
    for s in kept:
        if not isinstance(s, dict):
            continue
        res = s.get("resultat", "?")
        m = s.get("marche", "?")
        c = str(s.get("contenu", ""))[:55].replace("\n", " ")
        print(f"  [{res:<6}] {m:<9} {c}")

    print(f"\nstrategies.json: {len(strats)} -> {len(kept)} stratégies")
    print(f"Rapport: strategies_audit.json")
    print(f"\nAppliquer: sudo systemctl restart paper_trading.service")
    print(f"Annuler:   cp {bak} strategies.json && sudo systemctl restart paper_trading.service")
    print(f"\nNOTE: {dict(kept_dist).get('neutre', 0)} stratégies 'neutres' conservées (n'ont pas")
    print(f"donné de signal). Dis-moi si tu veux aussi les couper pour être plus agressif.")


if __name__ == "__main__":
    main()
