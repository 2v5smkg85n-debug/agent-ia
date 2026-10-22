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
import time
import os
from datetime import datetime, timedelta

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(DOSSIER, "registre_strategies.json")
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")

N_PROMO, WR_PROMO = 30, 55.0
N_RETRAIT, N_RETRAIT_RAPIDE, PERTE_RETRAIT_RAPIDE = 30, 15, -10.0
FRAIS_AR_PCT = 0.2  # frais aller-retour paper (0.1% x 2) deja inclus dans gain_eur

# Qui a le droit d'ouvrir des positions aujourd'hui (decision user: IA seulement)
DROIT_OUVERTURE = {"ia_autonome", "ouverture_ia_chat", "manuel", "ia_chat"}   # droits de base (jamais retires)
ARCHIVE_FILE = os.path.join(DOSSIER, "trades_archive.json")


def tous_les_trades(pf_trades=None):
    """Historique complet = archive (nouveaux departs) + trades du portefeuille courant. Jamais perdu."""
    trades = []
    try:
        trades += json.load(open(ARCHIVE_FILE)).get("trades", [])
    except Exception:
        pass
    if pf_trades is None:
        try:
            pf_trades = json.load(open(PT_FILE)).get("trades_fermes", [])
        except Exception:
            pf_trades = []
    return trades + list(pf_trades)


# ---------------------------------------------------------------- casier mesure (remplace les listes noires en dur)
CASIER_MIN_N = 15          # il faut au moins 15 trades sur une crypto / un jour pour la juger
CASIER_Z = 1.645           # intervalle de confiance 90 % sur le gain moyen par trade
_CASIER = {"t": 0.0, "d": {}}


def _ic_haut(gains):
    """Borne haute (90 %) du gain moyen par trade. Negative = perdant avec confiance."""
    n = len(gains)
    if n < 2:
        return None
    m = sum(gains) / n
    var = sum((g - m) ** 2 for g in gains) / (n - 1)
    return m + CASIER_Z * (var ** 0.5) / (n ** 0.5)


def casier(trades=None):
    """Cryptos et jours de semaine INTERDITS parce que mesures perdants avec confiance (>= CASIER_MIN_N trades et borne
    haute 90 % du gain moyen < 0). Revise automatiquement : une crypto qui redevient gagnante sort du casier.
    Remplace les anciennes listes noires fixes (LDO/ADA/DOT/PEPE/AVAX/BNB, lundi) qui dataient de 211 trades."""
    if time.time() - _CASIER["t"] < 600 and _CASIER["d"]:
        return _CASIER["d"]
    tr = trades if trades is not None else tous_les_trades()
    # Ne juger que les trades des strategies ENCORE EN SERVICE : les pertes de macd_cross / essai_bougies (retirees)
    # ne doivent pas condamner un jour ou une crypto pour ia_autonome et rsi_oversold.
    try:
        retirees = {k for k, s in _charger().get("strategies", {}).items() if s.get("statut") == "retiree"}
    except Exception:
        retirees = set()
    tr = [t for t in tr if _nom_strat(t) not in retirees and "_PARTIAL" not in str(t.get("source", ""))]
    par_sym, par_jour = {}, {}
    for t in tr:
        try:
            g = float(t.get("gain_eur", 0) or 0)
        except Exception:
            continue
        s = str(t.get("symbole", "")).upper()
        if s:
            par_sym.setdefault(s, []).append(g)
        try:
            j = datetime.strptime(str(t.get("date_ouverture", t.get("date", "")))[:16], "%Y-%m-%d %H:%M").weekday()
            par_jour.setdefault(j, []).append(g)
        except Exception:
            pass
    def _juge(groupes):
        out = {}
        for k, gs in groupes.items():
            if len(gs) >= CASIER_MIN_N:
                h = _ic_haut(gs)
                if h is not None and h < 0:
                    out[k] = {"n": len(gs), "net": round(sum(gs), 2), "ic_haut": round(h, 3)}
        return out
    d = {"cryptos": _juge(par_sym), "jours": _juge(par_jour), "maj": datetime.now().strftime("%Y-%m-%d %H:%M"),
         "n_trades_juges": len(tr), "strategies_exclues": sorted(retirees)}
    _CASIER["t"], _CASIER["d"] = time.time(), d
    return d


def crypto_interdite(sym):
    """(interdite ?, motif) d'apres le casier mesure."""
    s = str(sym or "").upper()
    k = casier().get("cryptos", {}).get(s)
    if k:
        return True, f"{s}: {k['n']} trades, net {k['net']:+.2f} EUR, borne haute 90% {k['ic_haut']:+.3f} < 0"
    return False, ""


def jour_interdit(dt=None):
    j = (dt or datetime.now()).weekday()
    k = casier().get("jours", {}).get(j)
    noms = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    if k:
        return True, f"{noms[j]}: {k['n']} trades, net {k['net']:+.2f} EUR, borne haute 90% {k['ic_haut']:+.3f} < 0"
    return False, ""


def droits_supplementaires():
    try:
        return set(_charger().get("droits", []))
    except Exception:
        return set()


def a_le_droit(strat):
    """La strategie a-t-elle le droit d'OUVRIR des positions ? (base + droits accordes par l'utilisateur)"""
    s = str(strat or "").lower()
    return any(x in s for x in DROIT_OUVERTURE) or s in {x.lower() for x in droits_supplementaires()}


def donner_droit(strat, actif=True, motif=""):
    d = _charger()
    droits = set(d.get("droits", []))
    if actif:
        droits.add(strat)
    else:
        droits.discard(strat)
    d["droits"] = sorted(droits)
    d.setdefault("historique_statuts", []).append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "strategie": strat,
                                                   "de": "sans droit" if actif else "avec droit", "vers": "DROIT D'OUVERTURE" if actif else "RETRAIT DU DROIT", "motif": motif})
    _sauver(d)
    return mettre_a_jour()


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
    """Regles historiques + lecture bayesienne (Beta(5,5), intervalle de credibilite 90 %) :
       - retiree si le HAUT de l'intervalle reste sous le point mort apres >= 15 trades (perdante meme en etant optimiste)
       - active si le BAS de l'intervalle depasse le point mort de 5 points apres >= 20 trades et net > 0"""
    n, net, wr = s["n"], s["net"], s["wr"]
    if n == 0:
        return "candidate"
    ic_bas, ic_haut, pmort = s.get("wr_ic_bas"), s.get("wr_ic_haut"), s.get("point_mort")
    if (n >= N_RETRAIT and net < 0) or (n >= N_RETRAIT_RAPIDE and net <= PERTE_RETRAIT_RAPIDE):
        return "retiree"
    if n >= 15 and ic_haut is not None and pmort is not None and ic_haut < pmort and net < 0:
        return "retiree"
    if n >= N_PROMO and net > 0 and wr >= WR_PROMO:
        return "active"
    if n >= 20 and net > 0 and ic_bas is not None and pmort is not None and ic_bas > pmort + 5:
        return "active"
    return "probation"


def facteur_taille(strat, regime=None, mini=0.5, maxi=1.25):
    """Echantillonnage de Thompson : tire un WR plausible dans la loi a posteriori de la strategie et le compare
    a son point mort. Retourne un multiplicateur de taille [mini, maxi] (1.0 si inconnu). Ne touche pas au risque max."""
    try:
        import validation_stats as vs
        d = _charger()
        s = d["strategies"].get(str(strat))
        if not s or s.get("n", 0) < 5:
            return 1.0
        a, b = 5.0 + s.get("g", 0), 5.0 + s.get("n", 0) - s.get("g", 0)
        if regime and isinstance(s.get("par_regime"), dict) and s["par_regime"].get(regime, {}).get("n", 0) >= 5:
            r = s["par_regime"][regime]
            a, b = 5.0 + r["g"], 5.0 + r["n"] - r["g"]
        tirage = vs.echantillon_beta(a, b) * 100
        pmort = s.get("point_mort") or 50.0
        # +10 points au-dessus du point mort -> x1.25 ; -10 points -> x0.5
        f = 1.0 + (tirage - pmort) / 40.0
        return round(max(mini, min(maxi, f)), 2)
    except Exception:
        return 1.0


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
        s.setdefault("_gains", []).append(gain)
        # ventilation par regime (si le contexte d'entree l'a enregistre)
        _reg = (t.get("contexte") or {}).get("regime") if isinstance(t.get("contexte"), dict) else None
        if _reg:
            r = s.setdefault("par_regime", {}).setdefault(_reg, {"n": 0, "g": 0, "net": 0.0})
            r["n"] += 1; r["g"] += 1 if gain > 0 else 0; r["net"] = round(r["net"] + gain, 2)
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
        # Lecture bayesienne : WR a posteriori Beta(5,5) + intervalle 90 % + point mort + Sharpe deflate
        try:
            import validation_stats as vs
            post = vs.beta_posterior(s["g"], s["n"])
            s["wr_bayes"], s["wr_ic_bas"], s["wr_ic_haut"] = post["moyenne"], post["ic_bas"], post["ic_haut"]
            s["point_mort"] = vs.point_mort(s["gain_moyen"], s["perte_moyenne"])
            gains = s.pop("_gains", [])
            mo = vs.moments(gains)
            s["dsr"] = vs.sharpe_deflate(mo["sharpe"], s["n"], 1, mo["skew"], mo["kurt"]) if mo else None
            for r in s.get("par_regime", {}).values():
                r["wr"] = round(100 * r["g"] / r["n"], 1) if r["n"] else 0.0
        except Exception:
            s.pop("_gains", None)
        s["statut_auto"] = _statut_auto(s)
    return stats


def mettre_a_jour(trades=None, verbose=False):
    """Recalcule le registre depuis paper_trading.json et journalise les changements de statut."""
    d = _charger()
    trades = tous_les_trades(trades)   # archive + courant
    stats = calculer(trades)
    forces = d.get("forces", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, s in stats.items():
        ancien = d["strategies"].get(k, {})
        statut = forces.get(k, {}).get("statut") or s["statut_auto"]
        s["statut"] = statut
        s["force"] = k in forces
        s["droit_ouverture"] = a_le_droit(k)
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
        bayes = f", WR bayesien {s['wr_bayes']:.0f}% [{s['wr_ic_bas']:.0f}-{s['wr_ic_haut']:.0f}] vs point mort {s['point_mort']:.0f}%" if s.get("wr_bayes") is not None else ""
        lignes.append(f"  {k}: {s['statut'].upper()} — {s['n']} trades, WR {s['wr']:.0f}%, net {s['net']:+.1f}EUR, esperance {s['esperance']:+.2f}EUR/trade{bayes}")
    return "\n".join(lignes)


def rapport_casier():
    k = casier()
    noms = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    l = [f"=== CASIER MESURE (>= {CASIER_MIN_N} trades, borne haute 90% du gain moyen < 0 ; maj {k.get('maj')}) ===",
         f"  juge sur {k.get('n_trades_juges', '?')} trades des strategies en service (exclues : {', '.join(k.get('strategies_exclues', [])) or 'aucune'})"]
    for s, v in sorted(k.get("cryptos", {}).items(), key=lambda kv: kv[1]["net"]):
        l.append(f"  crypto {s:10s} {v['n']:3d} trades  net {v['net']:+7.2f}  ic_haut {v['ic_haut']:+.3f}  -> interdite")
    for j, v in sorted(k.get("jours", {}).items()):
        l.append(f"  jour   {noms[j]:10s} {v['n']:3d} trades  net {v['net']:+7.2f}  ic_haut {v['ic_haut']:+.3f}  -> interdit")
    if len(l) == 2:
        l.append("  rien d'interdit : aucune crypto ni aucun jour n'est perdant avec confiance")
    return "\n".join(l)


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
    elif len(sys.argv) >= 4 and sys.argv[1] == "droit":
        donner_droit(sys.argv[2], sys.argv[3].lower() in ("on", "oui", "1", "true"), " ".join(sys.argv[4:]))
        print(rapport())
    elif len(sys.argv) >= 2 and sys.argv[1] == "casier":
        print(rapport_casier())
    else:
        print(rapport())
        print(rapport_casier())
