#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""registre_strategies.py — Le casier judiciaire des strategies. JAMAIS remis a zero.

Chaque strategie a une fiche a vie (tous les trades fermes depuis le debut) et un statut:
  - active     : >= 30 trades, net > 0, WR >= 55%  -> peut ouvrir normalement
  - probation  : pas assez de recul                  -> 1 position max a la fois
  - retiree    : >= 30 trades et net < 0, ou >= 15 trades et net < -10 EUR -> n'ouvre plus
  - candidate  : aucun trade

Le statut peut etre force a la main (forcer()). Les changements de statut sont journalises.
Le droit d'ouverture reste separe (droit_ouverture): aujourd'hui seule ia_autonome ouvre,
les professeurs nourrissent l'IA sans ouvrir (decision user). Le registre indique quand
une strategie bloquee meriterait d'etre reactivee — la decision reste humaine.
"""
import json
import os
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "registre_strategies.json")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")

N_PROMO, WR_PROMO = 30, 55.0
N_RETRAIT, N_RETRAIT_RAPIDE, PERTE_RETRAIT_RAPIDE = 30, 15, -10.0
FRAIS_AR_PCT = 0.2  # frais aller-retour paper (0.1% x 2) deja inclus dans gain_eur

# Qui a le droit d'ouvrir des positions aujourd'hui (decision user: IA seulement)
DROIT_OUVERTURE = {"ia_autonome", "ouverture_ia_chat", "manuel", "ia_chat"}


def _charger():
    try:
        with open(FICHIER) as f:
            return json.load(f)
    except Exception:
        return {"cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"), "strategies": {},
                "historique_statuts": [], "forces": {}}


def _sauver(d):
    tmp = FICHIER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FICHIER)


def _nom_strat(t):
    return str(t.get("strategie") or t.get("source") or "inconnu")


def _statut_auto(s):
    n, net, wr = s["n"], s["net"], s["wr"]
    if n == 0:
        return "candidate"
    if (n >= N_RETRAIT and net < 0) or (n >= N_RETRAIT_RAPIDE and net <= PERTE_RETRAIT_RAPIDE):
        return "retiree"
    if n >= N_PROMO and net > 0 and wr >= WR_PROMO:
        return "active"
    return "probation"


def calculer(trades):
    """Stats a vie + 30 derniers jours par strategie."""
    stats = {}
    seuil_30j = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    for t in trades or []:
        k = _nom_strat(t)
        s = stats.setdefault(k, {"n": 0, "g": 0, "net": 0.0, "brut_gains": 0.0, "brut_pertes": 0.0,
                                 "n_30j": 0, "net_30j": 0.0, "premier": None, "dernier": None,
                                 "pire_serie": 0, "_serie": 0, "stops": 0})
        gain = float(t.get("gain_eur", 0) or 0)
        s["n"] += 1
        s["net"] += gain
        if gain > 0:
            s["g"] += 1; s["brut_gains"] += gain; s["_serie"] = 0
        else:
            s["brut_pertes"] += gain; s["_serie"] += 1; s["pire_serie"] = max(s["pire_serie"], s["_serie"])
        if str(t.get("raison", "")).upper().startswith("SL"):
            s["stops"] += 1
        d = str(t.get("date_fermeture") or t.get("date_ouverture") or "")[:16]
        if d:
            s["premier"] = min(s["premier"], d) if s["premier"] else d
            s["dernier"] = max(s["dernier"], d) if s["dernier"] else d
            if d >= seuil_30j:
                s["n_30j"] += 1; s["net_30j"] += gain
    for k, s in stats.items():
        s.pop("_serie", None)
        s["wr"] = round(100 * s["g"] / s["n"], 1) if s["n"] else 0.0
        s["esperance"] = round(s["net"] / s["n"], 3) if s["n"] else 0.0   # EUR par trade, frais inclus
        s["gain_moyen"] = round(s["brut_gains"] / s["g"], 2) if s["g"] else 0.0
        s["perte_moyenne"] = round(s["brut_pertes"] / (s["n"] - s["g"]), 2) if s["n"] - s["g"] else 0.0
        s["taux_stops"] = round(100 * s["stops"] / s["n"]) if s["n"] else 0
        s["net"] = round(s["net"], 2); s["net_30j"] = round(s["net_30j"], 2)
        s["statut_auto"] = _statut_auto(s)
    return stats


def mettre_a_jour(trades=None, verbose=False):
    """Recalcule le registre depuis paper_trading.json et journalise les changements de statut."""
    d = _charger()
    if trades is None:
        try:
            trades = json.load(open(PT_FILE)).get("trades_fermes", [])
        except Exception:
            trades = []
    stats = calculer(trades)
    forces = d.get("forces", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, s in stats.items():
        ancien = d["strategies"].get(k, {})
        statut = forces.get(k, {}).get("statut") or s["statut_auto"]
        s["statut"] = statut
        s["force"] = k in forces
        s["droit_ouverture"] = any(x in k.lower() for x in DROIT_OUVERTURE)
        s["recommandation"] = ""
        if statut == "active" and not s["droit_ouverture"]:
            s["recommandation"] = "merite une reactivation (active mais sans droit d'ouverture)"
        elif statut == "retiree" and s["droit_ouverture"]:
            s["recommandation"] = "ATTENTION: a le droit d'ouvrir mais statistiquement perdante"
        elif statut == "probation" and s["n"] >= 15 and s["wr"] >= 60 and s["net"] > 0:
            s["recommandation"] = f"prometteuse ({s['n']}/{N_PROMO} trades vers la promotion)"
        if ancien and ancien.get("statut") != statut:
            d["historique_statuts"].append({"date": now, "strategie": k, "de": ancien.get("statut"), "vers": statut,
                                            "n": s["n"], "net": s["net"], "wr": s["wr"]})
            if verbose:
                print(f"  [REGISTRE] {k}: {ancien.get('statut')} -> {statut} ({s['n']} trades, net {s['net']:+.2f})")
        elif not ancien:
            d["historique_statuts"].append({"date": now, "strategie": k, "de": None, "vers": statut,
                                            "n": s["n"], "net": s["net"], "wr": s["wr"]})
        s["mis_a_jour"] = now
        d["strategies"][k] = s
    d["derniere_maj"] = now
    d["total_trades"] = len(trades)
    _sauver(d)
    return d


def statut(strat):
    d = _charger()
    s = d["strategies"].get(str(strat))
    return s["statut"] if s else "candidate"


def autorisee(strat, pf=None):
    """(ok, raison). retiree -> non. probation -> 1 position max de cette strategie."""
    st = statut(strat)
    if st == "retiree":
        return False, f"strategie '{strat}' retiree du registre (perdante a vie)"
    if st in ("probation", "candidate") and pf is not None:
        n_ouv = sum(1 for p in pf.get("positions", []) if _nom_strat(p) == str(strat))
        if n_ouv >= 1:
            return False, f"strategie '{strat}' en probation: 1 position max (deja {n_ouv})"
    return True, st


def forcer(strat, nouveau_statut, motif=""):
    assert nouveau_statut in ("active", "probation", "retiree", "auto")
    d = _charger()
    if nouveau_statut == "auto":
        d["forces"].pop(strat, None)
    else:
        d["forces"][strat] = {"statut": nouveau_statut, "motif": motif, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
    _sauver(d)
    return mettre_a_jour()


def resume_pour_ia():
    """Texte court pour le prompt de l'IA."""
    d = _charger()
    lignes = []
    for k, s in sorted(d["strategies"].items(), key=lambda x: -x[1]["n"]):
        lignes.append(f"  {k}: {s['statut'].upper()} — {s['n']} trades, WR {s['wr']:.0f}%, net {s['net']:+.1f}EUR, esperance {s['esperance']:+.2f}EUR/trade")
    return "\n".join(lignes)


def rapport():
    d = mettre_a_jour()
    ordre = {"active": 0, "probation": 1, "candidate": 2, "retiree": 3}
    lignes = [f"=== REGISTRE DES STRATEGIES ({d.get('total_trades', 0)} trades a vie, maj {d.get('derniere_maj')}) ==="]
    for k, s in sorted(d["strategies"].items(), key=lambda x: (ordre.get(x[1]["statut"], 9), -x[1]["n"])):
        tag = " [FORCE]" if s.get("force") else ""
        ouvre = "ouvre" if s.get("droit_ouverture") else "n'ouvre pas"
        lignes.append(f"{s['statut'].upper():9s}{tag} {k:22s} {s['n']:4d} trades | WR {s['wr']:5.1f}% | net {s['net']:+7.2f} | /trade {s['esperance']:+.2f} | stops {s['taux_stops']}% | 30j {s['net_30j']:+.1f} | {ouvre}")
        if s.get("recommandation"):
            lignes.append(f"          -> {s['recommandation']}")
    if d.get("historique_statuts"):
        lignes.append("Derniers changements:")
        for h in d["historique_statuts"][-5:]:
            lignes.append(f"  {h['date']} {h['strategie']}: {h['de']} -> {h['vers']}")
    return "\n".join(lignes)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "forcer":
        print(rapport() if forcer(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "auto", " ".join(sys.argv[4:])) else "")
    else:
        print(rapport())
