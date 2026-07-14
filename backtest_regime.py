#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_regime.py — Backtest A/B/C de la ponderation par regime de marche.

Compare 3 variantes de selection de strategies sur l'historique:
  A) Baseline       : selection par retour backtest seul (fit=1.0)
  B) Reweighting   : retour * fit(strategie, regime)  [implémentation actuelle]
  C) Gating         : entre uniquement si fit regime favorable (>= GATE)

Verdict: le reweighting pur (B) est-il cosmétique (mêmes entrées que A) ?
Le gating regime (C) améliore-t-il le PnL ?

PnL exprimé en % par trade (TP/SL uniformes 1.5%).
"""
import os
import json
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(DOSSIER, "backtest_regime_resultats.json")

TP, SL = 1.5, 1.5            # seuils identiques au live
MAX_BARS = 48                # sortie temps (2j sur 1h) si en gain
GATE = 1.0                   # fit min pour variante C (1.0 = neutre ou mieux)
LIMITE_BARS = 400
DEBUT = 50                   # barre de depart (indicateurs)

# Actifs testes (crypto = regime le plus pertinent + assez de volatilite)
ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bt_regime")


def _load_strategies():
    """Charge les strategies gagnantes par actif (intervalle 1h)."""
    try:
        from signaux_gagnants import strategies_gagnantes_par_actif
        par_actif = strategies_gagnantes_par_actif() or {}
    except Exception as e:
        log.warning("strategies_gagnantes_par_actif indispo: %s", e)
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
    """Backtest A/B/C sur un actif. Retourne dict {variante: {pnl,n,wins}}."""
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
    closes = [b["cloture"] for b in bougies]
    res = {v: {"pnl": 0.0, "n": 0, "wins": 0, "ouvert": None,
               "entrees": 0, "skipped": 0} for v in ("A", "B", "C")}

    def _fermer(v, px, i):
        tr = res[v]["ouvert"]
        var = (px - tr["px"]) / tr["px"] * 100
        res[v]["pnl"] += var
        res[v]["n"] += 1
        if var > 0:
            res[v]["wins"] += 1
        res[v]["ouvert"] = None

    for i in range(DEBUT, len(closes)):
        px = closes[i]
        # 1. gerer sorties positions ouvertes
        for v in res:
            if not res[v]["ouvert"]:
                continue
            tr = res[v]["ouvert"]
            var = (px - tr["px"]) / tr["px"] * 100
            age = i - tr["bar"]
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                _fermer(v, px, i)
        # 2. signaux ACHAT si pas de position ouverte
        clotures_i = closes[: i + 1]
        try:
            donnees = calculer_donnees(clotures_i)
        except Exception:
            continue
        reg = regime_depuis_clotures(clotures_i)
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
        for v in res:
            if res[v]["ouvert"]:
                continue
            res[v]["entrees"] += 1
            if v == "A":
                nom, _ = max(achats, key=lambda x: x[1])
                res[v]["ouvert"] = {"px": px, "bar": i, "strat": nom}
            elif v == "B":
                scored = [(nom, r * strategie_regime_fit(nom, reg["regime"]))
                          for nom, r in achats]
                nom, _ = max(scored, key=lambda x: x[1])
                res[v]["ouvert"] = {"px": px, "bar": i, "strat": nom}
            elif v == "C":
                scored = [(nom, r * strategie_regime_fit(nom, reg["regime"]),
                           strategie_regime_fit(nom, reg["regime"]))
                          for nom, r in achats]
                nom, _, fit = max(scored, key=lambda x: x[1])
                if fit < GATE:  # regime defavorable -> skip
                    res[v]["skipped"] += 1
                    continue
                res[v]["ouvert"] = {"px": px, "bar": i, "strat": nom}
    # fermer positions restantes
    for v in res:
        if res[v]["ouvert"]:
            _fermer(v, closes[-1], len(closes) - 1)
    for v in res:
        res[v]["win_rate"] = round(100 * res[v]["wins"] / res[v]["n"], 1) \
            if res[v]["n"] else 0.0
        res[v]["pnl"] = round(res[v]["pnl"], 2)
    return res


def main():
    strats_par_actif = _load_strategies()
    if not strats_par_actif:
        log.error("Aucune stratégie gagnante chargée. Abandon.")
        return
    log.info("Stratégies chargées pour %d actif(s): %s",
             len(strats_par_actif), list(strats_par_actif.keys()))
    # limiter aux actifs test + disponibles
    actifs = [a for a in ACTIFS_TEST if a in strats_par_actif]
    if not actifs:
        actifs = list(strats_par_actif.keys())[:5]
    log.info("Backtest sur: %s", actifs)
    totaux = {v: {"pnl": 0.0, "n": 0, "wins": 0, "entrees": 0, "skipped": 0}
              for v in ("A", "B", "C")}
    par_actif = {}
    for actif in actifs:
        log.info("  -> %s ...", actif)
        r = backtester_actif(actif, strats_par_actif[actif])
        if not r:
            continue
        par_actif[actif] = r
        for v in totaux:
            totaux[v]["pnl"] += r[v]["pnl"]
            totaux[v]["n"] += r[v]["n"]
            totaux[v]["wins"] += r[v]["wins"]
            totaux[v]["entrees"] += r[v]["entrees"]
            totaux[v]["skipped"] += r[v]["skipped"]
    # affichage
    print("\n" + "=" * 70)
    print("BACKTEST RÉGIME — A/B/C (PnL en %)")
    print("=" * 70)
    print(f"{'Variante':<12} {'PnL%':>8} {'Trades':>7} {'Win%':>7} "
          f"{'Entrées':>8} {'Skipped':>8}")
    print("-" * 70)
    labels = {"A": "A baseline", "B": "B reweight", "C": "C gating"}
    for v in ("A", "B", "C"):
        t = totaux[v]
        wr = round(100 * t["wins"] / t["n"], 1) if t["n"] else 0.0
        print(f"{labels[v]:<12} {t['pnl']:>8.2f} {t['n']:>7} {wr:>6.1f}% "
              f"{t['entrees']:>8} {t['skipped']:>8}")
    print("=" * 70)
    # verdict
    pa, pb, pc = totaux["A"]["pnl"], totaux["B"]["pnl"], totaux["C"]["pnl"]
    print("\nVERDICT:")
    print(f"  B vs A (reweight): {pb-pa:+.2f}% — "
          f"{'cosmétique (entrées identiques)' if abs(pb-pa)<0.01 else 'impact réel'}")
    print(f"  C vs A (gating)  : {pc-pa:+.2f}% — "
          f"{'régime aide ✅' if pc > pa + 0.5 else 'régime neutre/aide pas ❌' if pc < pa - 0.5 else 'neutre'}")
    if pc > pa:
        print("  → Le GATING par régime améliore le PnL: activer la variante C.")
    elif pb == pa:
        print("  → Le reweighting seul est cosmétique: envisager le gating (C).")
    # sauvegarde
    json.dump({"totaux": totaux, "par_actif": par_actif,
               "config": {"TP": TP, "SL": SL, "MAX_BARS": MAX_BARS,
                          "GATE": GATE, "LIMITE_BARS": LIMITE_BARS}},
              open(RESULT_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nRésultats sauvegardés: {RESULT_FILE}")


if __name__ == "__main__":
    main()
