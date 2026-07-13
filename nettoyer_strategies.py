#!/usr/bin/env python3
"""Nettoyage automatique des stratégies perdantes (Phase 3).
Coupe les stratégies dont le backtest moyen est perdant (retour < 0 OU profit factor < 1).
Sauvegarde strategies.json avant modification (reversible)."""
import json
import shutil
import datetime
from collections import defaultdict


def load(name, default):
    try:
        return json.load(open(name))
    except Exception:
        return default


def num(v, d=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return d


def main():
    bp = load("backtests_pro.json", [])
    strats = load("strategies.json", [])

    if not bp:
        print("ERREUR: backtests_pro.json vide ou absent. Abandon.")
        return
    if not strats:
        print("ERREUR: strategies.json vide ou absent. Abandon.")
        return

    print(f"Backtests: {len(bp)} | Stratégies: {len(strats)}")
    print(f"Structure strategies.json[0]: {json.dumps(strats[0], ensure_ascii=False)[:200]}")

    # 1. Agreger les backtests par nom de strategie
    agg = defaultdict(list)
    for b in bp:
        agg[b.get("strategie", "?")].append(b)

    verdicts = {}
    for name, lst in agg.items():
        rets = [num(x.get("retour_pct")) for x in lst]
        pfs = [num(x.get("profit_factor")) for x in lst if x.get("profit_factor") is not None]
        wrs = [num(x.get("win_rate")) for x in lst if x.get("win_rate") is not None]
        g = sum(1 for x in lst if x.get("verdict") == "GAGNANTE")
        avg_ret = sum(rets) / len(rets)
        avg_pf = sum(pfs) / len(pfs) if pfs else 0
        avg_wr = sum(wrs) / len(wrs) if wrs else 0
        pct_g = g / len(lst) * 100 if lst else 0
        if avg_ret > 0 and avg_pf >= 1.0 and pct_g >= 50:
            v = "GARDER"
        elif avg_ret < 0 or avg_pf < 1:
            v = "COUPER"
        else:
            v = "SURVEILLER"
        verdicts[name] = {"verdict": v, "retour": avg_ret, "pf": avg_pf,
                          "wr": avg_wr, "n": len(lst), "pct_g": pct_g}

    n_garder = sum(1 for x in verdicts.values() if x["verdict"] == "GARDER")
    n_couper = sum(1 for x in verdicts.values() if x["verdict"] == "COUPER")
    n_surv = sum(1 for x in verdicts.values() if x["verdict"] == "SURVEILLER")
    print(f"\nVerdicts (backtests): {n_garder} GARDER, {n_surv} SURVEILLER, {n_couper} COUPER")

    # 2. Sauvegarde timestampée
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"strategies_backup_{ts}.json"
    shutil.copy2("strategies.json", bak)
    print(f"Sauvegarde: {bak}")

    # 3. Trouver le nom de chaque strategie et son verdict
    def find_name(item):
        if isinstance(item, dict):
            for k in ("nom", "strategie", "nom_strategie", "name", "titre", "label"):
                if item.get(k):
                    return str(item[k])
            return str(item.get("contenu", ""))[:60]
        return str(item)[:60]

    def match_verdict(name):
        if name in verdicts:
            return name, verdicts[name]
        # match souple (substring)
        for bn, vd in verdicts.items():
            if bn and (bn in name or name in bn):
                return bn, vd
        return None, None

    kept = []
    cut = []
    unmatched = 0
    for s in strats:
        nm = find_name(s)
        bn, vd = match_verdict(nm)
        if vd is None:
            unmatched += 1
            kept.append(s)  # conserve si non verifiable (securite)
            continue
        if vd["verdict"] == "COUPER":
            cut.append((nm, bn, vd))
        else:
            kept.append(s)

    print(f"Stratégies: {len(strats)} -> {len(kept)} gardées, {len(cut)} coupées, {unmatched} non vérifiables (conservées)")

    # 4. Ecrire strategies.json nettoyé
    with open("strategies.json", "w") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    # 5. Rapport d'audit + blacklist
    audit = {
        "date": ts,
        "avant": len(strats),
        "apres": len(kept),
        "coupees": len(cut),
        "non_verifiables": unmatched,
        "verdicts_backtests": verdicts,
        "strategies_coupees": [{"nom": n, "match": b, "retour": v["retour"],
                                "pf": v["pf"], "wr": v["wr"], "n": v["n"]}
                               for n, b, v in cut],
    }
    with open("strategies_audit.json", "w") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    # 6. Blacklist (noms coupés) pour usage futur par l'agent
    blacklist = list({b for _, b, _ in cut})
    with open("strategies_blacklist.json", "w") as f:
        json.dump(blacklist, f, ensure_ascii=False, indent=2)

    print("\n=== Stratégies COUPÉES ===")
    if cut:
        print(f"{'Nom':<40} {'Retour':>8} {'PF':>6} {'WR':>6} {'N':>3}")
        for nm, bn, v in cut:
            print(f"{nm[:38]:<40} {v['retour']:>+7.2f}% {v['pf']:>6.2f} {v['wr']:>5.0f}% {v['n']:>3}")
    else:
        print("  (aucune coupée — vérifie le matching)")

    print(f"\nRapport: strategies_audit.json")
    print(f"Blacklist: strategies_blacklist.json")
    print(f"\nPour appliquer: sudo systemctl restart paper_trading.service")
    print(f"Pour annuler: cp {bak} strategies.json && sudo systemctl restart paper_trading.service")


if __name__ == "__main__":
    main()
