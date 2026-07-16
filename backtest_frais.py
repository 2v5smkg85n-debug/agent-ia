#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_frais.py — Réduit l'impact des frais en optimisant la sortie.

Compare 3 modes de sortie (frais 0.2% aller-retour appliqués):
  A: actuel     — sortie TEMPS si var>0 apres MAX_BARS, + TP/SL
  B: min-gain   — sortie TEMPS seulement si var>=0.5%, sinon attend TP/SL
  C: hold       — jamais de sortie TEMPS, attend TP/SL uniquement (timeout dur MAX_BARS*2)

Celui avec le meilleur PnL NET (apres frais) est gagnant -> moins de churn = moins de frais.
"""
import os
import json
import logging

DOSSIER = os.path.dirname(os.path.abspath(__file__))

TP, SL = 2.0, 2.5          # crypto optimal (deja applique)
FRAIS_ALLER_RETOUR = 0.2  # 0.1% x 2 cotes
MAX_BARS = 48
MIN_GAIN_TEMPS = 0.5       # mode B: seuil min pour sortie temps
GATE = 1.0
LIMITE_BARS = 500
DEBUT = 60
ACTIFS_TEST = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bt_frais")


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


def collecter_entrees(actif, strats):
    try:
        from indicateurs import historique_ohlcv
        from signaux_gagnants import signal_strategie, calculer_donnees
        from regime import fit_multi_tf
    except Exception as e:
        log.warning("imports indispo: %s", e)
        return None, None
    bougies = historique_ohlcv(actif, "1h", LIMITE_BARS)
    if not bougies or len(bougies) < DEBUT + 10:
        return None, None
    closes = [b["cloture"] for b in bougies]
    entrees = []
    ouvert = None
    # entrees collectees avec logique A (identique pour tous les modes)
    for i in range(DEBUT, len(closes)):
        px = closes[i]
        if ouvert:
            var = (px - ouvert["px"]) / ouvert["px"] * 100
            age = i - ouvert["bar"]
            if var >= TP or var <= -SL or (age >= MAX_BARS and var > 0):
                entrees.append((ouvert["bar"], ouvert["px"]))
                ouvert = None
        if ouvert:
            continue
        clotures_i = closes[: i + 1]
        try:
            donnees = calculer_donnees(clotures_i)
        except Exception:
            continue
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
        passed = []
        for nom, r in achats:
            try:
                fit_avg, _, _ = fit_multi_tf(nom, clotures_i)
            except Exception:
                fit_avg = 1.0
            if fit_avg >= GATE:
                passed.append((nom, r * fit_avg))
        if not passed:
            continue
        ouvert = {"px": px, "bar": i}
    if ouvert:
        entrees.append((ouvert["bar"], ouvert["px"]))
    return closes, entrees


def simuler_mode(closes, entrees, mode):
    """mode in A/B/C. Retourne PnL net (apres frais), n, wins."""
    pnl_brut = 0.0
    pnl_net = 0.0
    n = 0
    wins = 0
    max_bars_c = MAX_BARS * 2
    for bar_e, px_e in entrees:
        fin = min(bar_e + max_bars_c + 20, len(closes) - 1)
        exit_var = None
        for j in range(bar_e + 1, fin + 1):
            var = (closes[j] - px_e) / px_e * 100
            age = j - bar_e
            # SL commun
            if var <= -SL:
                exit_var = var
                break
            # TP commun
            if var >= TP:
                exit_var = var
                break
            # sortie TEMPS selon mode
            if mode == "A":
                if age >= MAX_BARS and var > 0:
                    exit_var = var
                    break
            elif mode == "B":
                if age >= MAX_BARS and var >= MIN_GAIN_TEMPS:
                    exit_var = var
                    break
            elif mode == "C":
                if age >= max_bars_c:
                    exit_var = var  # timeout dur
                    break
        if exit_var is None:
            exit_var = (closes[fin] - px_e) / px_e * 100
        net = exit_var - FRAIS_ALLER_RETOUR
        pnl_brut += exit_var
        pnl_net += net
        n += 1
        if net > 0:
            wins += 1
    return {"pnl_brut": round(pnl_brut, 2), "pnl_net": round(pnl_net, 2),
            "n": n, "wins": wins,
            "win_rate": round(100 * wins / n, 1) if n else 0.0}


def main():
    strats_par_actif = _load_strategies()
    if not strats_par_actif:
        log.error("Aucune stratégie chargée. Abandon.")
        return
    actifs = [a for a in ACTIFS_TEST if a in strats_par_actif] or list(strats_par_actif.keys())[:5]
    log.info("Backtest frais sur: %s", actifs)
    actifs_data = {}
    for actif in actifs:
        log.info("  -> %s ...", actif)
        closes, entrees = collecter_entrees(actif, strats_par_actif[actif])
        if closes and entrees:
            actifs_data[actif] = (closes, entrees)
    if not actifs_data:
        log.error("Aucune entrée collectée. Abandon.")
        return
    tot = {m: {"pnl_brut": 0.0, "pnl_net": 0.0, "n": 0, "wins": 0}
           for m in ("A", "B", "C")}
    for actif, (closes, entrees) in actifs_data.items():
        for m in ("A", "B", "C"):
            r = simuler_mode(closes, entrees, m)
            for k in tot[m]:
                tot[m][k] += r[k]
    for m in tot:
        tot[m]["win_rate"] = round(100 * tot[m]["wins"] / tot[m]["n"], 1) if tot[m]["n"] else 0.0
        tot[m]["pnl_brut"] = round(tot[m]["pnl_brut"], 2)
        tot[m]["pnl_net"] = round(tot[m]["pnl_net"], 2)
    labels = {"A": "actuel (temps si var>0)", "B": "min-gain (temps si var>=0.5%)",
              "C": "hold (TP/SL seulement)"}
    print("\n" + "=" * 78)
    print("BACKTEST FRAIS — impact du churn sur le PnL NET (frais 0.2% A/R appliqués)")
    print("=" * 78)
    print(f"{'Mode':<6} {'Description':<28} {'PnL brut':>9} {'PnL net':>9} {'Frais':>7} {'N':>4} {'Win%':>6}")
    print("-" * 78)
    for m in ("A", "B", "C"):
        t = tot[m]
        frais = round(t["pnl_brut"] - t["pnl_net"], 2)
        print(f"{m:<6} {labels[m]:<28} {t['pnl_brut']:>+8.2f}% {t['pnl_net']:>+8.2f}% "
              f"{frais:>+6.2f}% {t['n']:>4} {t['win_rate']:>5.1f}%")
    print("=" * 78)
    best = max(tot, key=lambda x: tot[x]["pnl_net"])
    print(f"\nVERDICT:")
    print(f"  Meilleur PnL net: mode {best} ({labels[best]}) = {tot[best]['pnl_net']:+.2f}%")
    print(f"  Mode actuel A:    {tot['A']['pnl_net']:+.2f}% net ({tot['A']['frais']}% frais)")
    if best != "A":
        gain = tot[best]["pnl_net"] - tot["A"]["pnl_net"]
        print(f"  Gain potentiel: {gain:+.2f}% net en passant au mode {best}")
        if best == "B":
            print("  → Ne sortir sur TEMPS que si gain>=0.5% (sinon attend TP/SL).")
        elif best == "C":
            print("  → Supprimer la sortie TEMPS (laisser courir jusqu'a TP/SL).")
    else:
        print("  → Le mode actuel est déjà optimal: garder tel quel.")
    json.dump({"totaux": tot, "labels": labels, "actifs": list(actifs_data.keys())},
              open(os.path.join(DOSSIER, "backtest_frais_resultats.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\nRésultats: {os.path.join(DOSSIER, 'backtest_frais_resultats.json')}")


if __name__ == "__main__":
    main()
