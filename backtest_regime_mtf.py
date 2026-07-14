#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_regime_mtf.py — Test du regime MULTI-TIMEFRAME (1h + 4h en confluence).

Hypothese: un regime 1h seul est bruite (backtest precedent: gating nuit au PnL).
En ajoutant la confluence 4h, le filtrage devient-il predictif ?

Variantes comparees:
  A  baseline      : pas de regime (selection par retour)
  D  MTf avg-gate  : entre si mean(fit_1h, fit_4h) >= 1.0
  E  MTf strict    : entre si fit_1h >= 1.0 ET fit_4h >= 1.0 (confluence totale)

Si D ou E > A en PnL, le multi-timeframe rend le regime predictif.
"""
import os
import json
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(DOSSIER, "backtest_regime_mtf_resultats.json")

TP, SL = 1.5, 1.5
MAX_BARS = 48
GATE = 1.0
LIMITE_BARS = 500
DEBUT = 60
FACTOR_4H = 4
ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bt_mtf")


def _downsample(closes_1h, factor):
    """Regroupe les bougies 1h en bougies de timeframe superieur (close = dernier du groupe)."""
    return [closes_1h[i] for i in range(factor - 1, len(closes_1h), factor)]


def _load_strategies():
    try:
        from signaux_gagnants import strategies_gagnantes_par_actif
        par_actif = strategies_gagnantes_par_actif() or {}
    except Exception as e:
        log.warning("strategies indispo: %s", e)
        return {}
    out = {}
    for actif, par_interv in par_actif.items():
        strats = []
        if isinstance(par_interv, dict):
            strats = par_interv.get("1h", []) or par_interv.get("15m", [])
        elif isinstance(par_interv, list):
            strats = par_interv
        if strats:
            out[actif] = [{"strategie": s.get("strategie"),
                           "retour_pct": float(s.get("retour_pct", 0) or 0)}
                          for s in strats if s.get("strategie")]
    return out


def backtester_actif(actif, strats):
    try:
        from indicateurs import historique_ohlcv
        from signaux_gagnants import signal_strategie, calculer_donnees
        from regime import regime_depuis_clotures, strategie_regime_fit
    except Exception as e:
        log.warning("imports indispo: %s", e)
        return None
    bougies = historique_ohlcv(actif, "1h", LIMITE_BARS)
    if not bougies or len(bougies) < DEBUT + 10:
        return None
    closes_1h = [b["cloture"] for b in bougies]
    closes_4h = _downsample(closes_1h, FACTOR_4H)
    res = {v: {"pnl": 0.0, "n": 0, "wins": 0, "ouvert": None,
               "entrees": 0, "skipped": 0} for v in ("A", "D", "E")}

    def _fermer(v, px):
        tr = res[v]["ouvert"]
        var = (px - tr["px"]) / tr["px"] * 100
        res[v]["pnl"] += var
        res[v]["n"] += 1
        if var > 0:
            res[v]["wins"] += 1
        res[v]["ouvert"] = None

    for i in range(DEBUT, len(closes_1h)):
        px = closes_1h[i]
        for v in res:
            if not res[v]["ouvert"]:
                continue
            tr = res[v]["ouvert"]
            var = (px - tr["px"]) / tr["px"] * 100
            age = i - tr["bar"]
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                _fermer(v, px)
        # regimes 1h et 4h a la barre i
        clotures_1h_i = closes_1h[: i + 1]
        nb_4h = (i + 1) // FACTOR_4H
        clotures_4h_i = closes_4h[:nb_4h] if nb_4h >= 50 else []
        try:
            donnees = calculer_donnees(clotures_1h_i)
        except Exception:
            continue
        reg_1h = regime_depuis_clotures(clotures_1h_i)
        reg_4h = regime_depuis_clotures(clotures_4h_i) if clotures_4h_i else {"regime": "INCONNU"}
        # signaux ACHAT
        achats = []
        for s in strats:
            nom = s["strategie"]
            try:
                sig = signal_strategie(nom, donnees)
            except Exception:
                sig = None
            if sig == "ACHAT":
                achats.append((nom, s["retour_pct"]))
        if not achats:
            continue
        # fit multi-timeframe par strategie
        for v in res:
            if res[v]["ouvert"]:
                continue
            res[v]["entrees"] += 1
            if v == "A":
                nom, _ = max(achats, key=lambda x: x[1])
                res[v]["ouvert"] = {"px": px, "bar": i, "strat": nom}
            else:
                scored = []
                for nom, r in achats:
                    f1 = strategie_regime_fit(nom, reg_1h["regime"])
                    f4 = strategie_regime_fit(nom, reg_4h["regime"])
                    if v == "D":
                        fit = (f1 + f4) / 2.0
                        skip = fit < GATE
                    else:  # E: confluence stricte
                        fit = (f1 + f4) / 2.0
                        skip = not (f1 >= GATE and f4 >= GATE)
                    scored.append((nom, r * fit, fit))
                nom, _, fit = max(scored, key=lambda x: x[1])
                if skip:
                    res[v]["skipped"] += 1
                    continue
                res[v]["ouvert"] = {"px": px, "bar": i, "strat": nom}
    for v in res:
        if res[v]["ouvert"]:
            _fermer(v, closes_1h[-1])
    for v in res:
        res[v]["win_rate"] = round(100 * res[v]["wins"] / res[v]["n"], 1) if res[v]["n"] else 0.0
        res[v]["pnl"] = round(res[v]["pnl"], 2)
    return res


def main():
    strats_par_actif = _load_strategies()
    if not strats_par_actif:
        log.error("Aucune stratégie chargée. Abandon.")
        return
    actifs = [a for a in ACTIFS_TEST if a in strats_par_actif] or list(strats_par_actif.keys())[:5]
    log.info("Backtest MTF sur: %s", actifs)
    totaux = {v: {"pnl": 0.0, "n": 0, "wins": 0, "entrees": 0, "skipped": 0}
              for v in ("A", "D", "E")}
    par_actif = {}
    for actif in actifs:
        log.info("  -> %s ...", actif)
        r = backtester_actif(actif, strats_par_actif[actif])
        if not r:
            continue
        par_actif[actif] = r
        for v in totaux:
            for k in totaux[v]:
                totaux[v][k] += r[v][k]
    print("\n" + "=" * 72)
    print("BACKTEST RÉGIME MULTI-TIMEFRAME (1h+4h) — PnL en %")
    print("=" * 72)
    print(f"{'Variante':<22} {'PnL%':>8} {'Trades':>7} {'Win%':>7} {'Entrées':>8} {'Skipped':>8}")
    print("-" * 72)
    labels = {"A": "A baseline", "D": "D MTF avg-gate", "E": "E MTF strict"}
    for v in ("A", "D", "E"):
        t = totaux[v]
        wr = round(100 * t["wins"] / t["n"], 1) if t["n"] else 0.0
        print(f"{labels[v]:<22} {t['pnl']:>8.2f} {t['n']:>7} {wr:>6.1f}% {t['entrees']:>8} {t['skipped']:>8}")
    print("=" * 72)
    pa, pd, pe = totaux["A"]["pnl"], totaux["D"]["pnl"], totaux["E"]["pnl"]
    print("\nVERDICT MTF:")
    print(f"  D (avg-gate) vs A: {pd-pa:+.2f}% — {'MTF aide ✅' if pd > pa + 0.5 else 'MTF neutre' if abs(pd-pa)<=0.5 else 'MTF nuit ❌'}")
    print(f"  E (strict)   vs A: {pe-pa:+.2f}% — {'MTF aide ✅' if pe > pa + 0.5 else 'MTF neutre' if abs(pe-pa)<=0.5 else 'MTF nuit ❌'}")
    if max(pd, pe) > pa + 0.5:
        print("  → Le multi-timeframe REND le régime prédictif: l'implémenter en live.")
    else:
        print("  → Le multi-timeframe n'aide pas non plus: le régime n'est pas exploitable tel quel.")
    json.dump({"totaux": totaux, "par_actif": par_actif,
               "config": {"TP": TP, "SL": SL, "LIMITE_BARS": LIMITE_BARS, "GATE": GATE}},
              open(RESULT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nRésultats: {RESULT_FILE}")


if __name__ == "__main__":
    main()
