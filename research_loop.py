#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research_loop.py — Moteur de recherche continu 24/7 (boucle ~1h).

Apprentissage accelere: tourne en PERMANENCE (pas seulement nocturne).
Chaque cycle (~1h) fait 4 choses:

  1. REGIME WATCH: detecte le regime de chaque marche + detecte les SHIFTS.
     Si le regime change (ex QUIET->TREND), re-teste EXTEND_TP dans le nouveau
     regime. Une idee validee/Rejetee en range peut se comporter autrement en trend.
     C'est LE levier: l'IA ne peut apprendre les strategies trend que quand le
     marche trende — il faut le detecter en temps reel.

  2. PARAMETER SWEEP: grille deterministe (tp_ext 2->5, tp/sl base) sur crypto.
     Suit la STABILITE des optima dans le temps (optimum qui bouge beaucoup =
     overfitting; optimum stable = edge reel).

  3. LIVE DIVERGENCE: compare la perf live des strategies deployees (EXTEND_TP)
     vs l'attendu backtest (~63% win, +2.71% avg). Alerte si sous-perf.
     EXTEND_TP est en argent reel -> surveillance prioritaire.

  4. AUTO-LECON: enregistre les findings significatifs dans lecons_apprises.jsonl.

IMPORTANT: CHERCHE + APPREND, ne DEPLOIE PAS. Le deploiement reste gate par
actions_executor (quotidien, confiance 0.70) pour eviter l'overfitting.
"""
import os, sys, json, time, logging, traceback
from datetime import datetime

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(
    os.path.join(os.getcwd(), "paper_trading.py")) else os.getcwd()
os.chdir(D)
sys.path.insert(0, D)

# ---- Config ----
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVAL_SEC = 3600          # 1h
LIMITE_BARS = 500
DEBUT = 60
MAX_BARS = 48
GATE = 1.0
TP_BASE = 2.0
SL_BASE = 2.5
EXTEND_SEUIL = 0.5
# Attendu backtest EXTEND_TP (pour divergence live)
EXTEND_EXPECTED_WIN = 63.0
EXTEND_EXPECTED_AVG = 2.71
EXTEND_MIN_TRADES = 5        # besoin de 5+ trades EXTEND live pour juger

PT_FILE = os.path.join(D, "paper_trading.json")
LECONS_FILE = os.path.join(D, "lecons_apprises.jsonl")
REGIME_HIST = os.path.join(D, "regime_history.json")
RECHERCHE_LOG = os.path.join(D, "recherche_log.jsonl")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("recherche")


# ---- Imports defensifs (chainage) ----
def _imports():
    from indicateurs import historique_ohlcv
    from signaux_gagnants import signal_strategie, calculer_donnees
    from regime import fit_multi_tf, regime_actif
    import backtest_trailing as bt
    return historique_ohlcv, signal_strategie, calculer_donnees, fit_multi_tf, regime_actif, bt


# ---- Entrees (reutilise la logique validee du sweep) ----
def entrees_actif(actif, strats, historique_ohlcv, signal_strategie, calculer_donnees, fit_multi_tf):
    bougies = historique_ohlcv(actif, "1h", LIMITE_BARS)
    if not bougies or len(bougies) < DEBUT + 10:
        return None, None
    closes = [b["cloture"] for b in bougies]
    entrees = []
    ouvert = None
    for i in range(DEBUT, len(closes)):
        px = closes[i]
        if ouvert:
            var = (px - ouvert["px"]) / ouvert["px"] * 100
            age = i - ouvert["bar"]
            if var >= TP_BASE or var <= -SL_BASE or (age >= MAX_BARS and var > 0):
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
        nom, _ = max(passed, key=lambda x: x[1])
        ouvert = {"px": px, "bar": i, "strat": nom}
    if ouvert:
        entrees.append((ouvert["bar"], ouvert["px"]))
    return closes, entrees


def simule_mode(closes, entrees, activate, tp_ext, tp=TP_BASE, sl=SL_BASE):
    res = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
    for bar_e, px_e in entrees:
        fin = min(bar_e + MAX_BARS + 20, len(closes) - 1)
        peak = 0.0
        ex = None
        for j in range(bar_e + 1, fin + 1):
            var = (closes[j] - px_e) / px_e * 100
            peak = max(peak, var)
            age = j - bar_e
            in_profit = peak >= activate
            tp_niv = tp_ext if in_profit else tp
            if var >= tp_niv:
                ex = var; break
            if var <= -sl:
                ex = var; break
            if age >= MAX_BARS and var > 0:
                ex = var; break
        if ex is None:
            ex = (closes[fin] - px_e) / px_e * 100
        res["pnl"] += ex; res["n"] += 1
        if ex > 0:
            res["wins"] += 1; res["sum_win"] += ex
            res["max_win"] = max(res["max_win"], ex)
    res["win_rate"] = round(100 * res["wins"] / res["n"], 1) if res["n"] else 0
    res["avg_win"] = round(res["sum_win"] / res["wins"], 2) if res["wins"] else 0
    res["pnl"] = round(res["pnl"], 2)
    return res


# ---- 1. REGIME WATCH ----
def regime_watch(regime_actif, historique_ohlcv, fit_multi_tf):
    """Retourne {sym: regime_str} et detecte les shifts vs historique."""
    regimes = {}
    for sym in CRYPTO:
        try:
            r = regime_actif(sym)
            # regime_actif retourne un dict avec TREND_STRENGTH/SMA qui changent
            # chaque heure -> extraire juste le label REGIME pour eviter les faux
            # shifts (QUIET/TREND/RANGE/VOL change rarement = vrai signal).
            if isinstance(r, dict):
                regimes[sym] = str(r.get("REGIME", r.get("regime", "?"))).upper()
            else:
                regimes[sym] = str(r).upper()
        except Exception:
            regimes[sym] = "?"
    # historique
    try:
        hist = json.load(open(REGIME_HIST, encoding="utf-8"))
    except Exception:
        hist = {}
    shifts = []
    for sym, r in regimes.items():
        avant = hist.get(sym)
        if avant and avant != r:
            shifts.append((sym, avant, r))
    # sauvegarde
    hist_out = {**hist, **regimes, "_dernier": datetime.now().strftime("%Y-%m-%d %H:%M")}
    try:
        json.dump(hist_out, open(REGIME_HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    return regimes, shifts


# ---- 2. PARAMETER SWEEP ----
def sweep_params(cache):
    """Grille deterministe sur tp_ext. Retourne resultat FIXE vs meilleur EXTEND."""
    base = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
    for a, (c, e) in cache.items():
        r = simule_mode(c, e, 999.0, TP_BASE)
        for k in base:
            base[k] += r[k]
    base["win_rate"] = round(100 * base["wins"] / base["n"], 1) if base["n"] else 0
    base["avg_win"] = round(base["sum_win"] / base["wins"], 2) if base["wins"] else 0
    base["pnl"] = round(base["pnl"], 2)
    best = None
    rows = []
    for tp_ext in [2.5, 3.0, 3.5, 4.0, 5.0]:
        tot = {"pnl": 0.0, "n": 0, "wins": 0, "sum_win": 0.0, "max_win": 0.0}
        for a, (c, e) in cache.items():
            r = simule_mode(c, e, EXTEND_SEUIL, tp_ext)
            for k in tot:
                tot[k] += r[k]
        tot["win_rate"] = round(100 * tot["wins"] / tot["n"], 1) if tot["n"] else 0
        tot["avg_win"] = round(tot["sum_win"] / tot["wins"], 2) if tot["wins"] else 0
        tot["pnl"] = round(tot["pnl"], 2)
        rows.append((tp_ext, tot["pnl"], tot["win_rate"], tot["avg_win"]))
        if best is None or tot["pnl"] > best[1]:
            best = (tp_ext, tot["pnl"], tot["win_rate"], tot["avg_win"])
    return base, rows, best


# ---- 3. LIVE DIVERGENCE ----
def divergence_extend():
    """Compare la perf live d'EXTEND_TP vs l'attendu backtest."""
    try:
        pt = json.load(open(PT_FILE, encoding="utf-8"))
    except Exception:
        return None
    # cherche les trades fermes (plusieurs schemas possibles)
    trades = []
    for key in ("trades", "historique", "trades_fermes", "fermes"):
        if isinstance(pt.get(key), list):
            trades = pt[key]; break
    if not trades:
        return {"n_extend": 0, "msg": "aucun trade ferme a analyser"}
    ext = []
    for t in trades:
        raison = str(t.get("raison", t.get("raison_sortie", t.get("type", ""))))
        if "EXTEND" in raison.upper():
            var = t.get("variation", t.get("pct", t.get("pnl_pct", None)))
            if var is not None:
                try:
                    ext.append(float(var))
                except Exception:
                    pass
    if len(ext) < EXTEND_MIN_TRADES:
        return {"n_extend": len(ext), "msg": f"trop peu de trades EXTEND live ({len(ext)}/{EXTEND_MIN_TRADES})"}
    wins = sum(1 for v in ext if v > 0)
    win_rate = round(100 * wins / len(ext), 1)
    avg = round(sum(ext) / len(ext), 2)
    ecart_win = round(win_rate - EXTEND_EXPECTED_WIN, 1)
    ecart_avg = round(avg - EXTEND_EXPECTED_AVG, 2)
    alerte = (ecart_win < -15) or (ecart_avg < -1.0)  # sous-perf significative
    return {
        "n_extend": len(ext), "win_rate_live": win_rate, "avg_win_live": avg,
        "win_rate_attendu": EXTEND_EXPECTED_WIN, "avg_win_attendu": EXTEND_EXPECTED_AVG,
        "ecart_win": ecart_win, "ecart_avg": ecart_avg, "alerte": alerte,
    }


# ---- 4. AUTO-LECON ----
def enregistrer_lecon(entry):
    try:
        with open(LECONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def log_recherche(record):
    try:
        with open(RECHERCHE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---- CYCLE ----
def cycle(mods):
    historique_ohlcv, signal_strategie, calculer_donnees, fit_multi_tf, regime_actif, bt = mods
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.info("=== CYCLE RECHERCHE %s ===", ts)

    # 1. regime watch
    regimes, shifts = regime_watch(regime_actif, historique_ohlcv, fit_multi_tf)
    log.info("Regimes: %s", {k: regimes[k] for k in CRYPTO})
    if shifts:
        log.info("⚠️ SHIFTS REGIME: %s", shifts)

    # 2. parameter sweep (calcule entrees pour crypto)
    try:
        strats_par_actif = bt._load_strategies()
    except Exception:
        strats_par_actif = {}
    cache = {}
    for a in CRYPTO:
        if a not in strats_par_actif:
            continue
        try:
            c, e = entrees_actif(a, strats_par_actif[a], historique_ohlcv, signal_strategie, calculer_donnees, fit_multi_tf)
            if c and e is not None:
                cache[a] = (c, e)
        except Exception as ex:
            log.warning("%s indispo: %s", a, ex)
    base, rows, best = sweep_params(cache) if cache else (None, [], None)
    if best:
        log.info("Sweep: FIXE=%s%% | best EXTEND tp_ext=%s -> %s%% (win %s%%, avg %s%%)",
                 base["pnl"], best[0], best[1], best[2], best[3])

    # 3. divergence live
    div = divergence_extend()
    if div:
        if div.get("alerte"):
            log.warning("⚠️ DIVERGENCE LIVE EXTEND: %s", div)
        elif "win_rate_live" in div:
            log.info("Divergence EXTEND: live win=%s%% (attendu %s%%), avg=%s%%",
                     div["win_rate_live"], div["win_rate_attendu"], div["avg_win_live"])
        else:
            log.info("Divergence EXTEND: %s", div.get("msg"))

    # 4. classement strategies selon le moment (regime + perf live)
    try:
        import classement_strategies as cs
        cl = cs.calculer_classement()
        tops = []
        for actif, d in cl.items():
            s = d.get("strategies", [])
            if s and s[0].get("score", 0) > 0:
                tops.append(f"{actif}:{s[0]['strategie']}")
        if tops:
            log.info("Top strat (moment): %s", ", ".join(tops))
    except Exception:
        log.warning("classement: echec (non bloquant)")

    # 5. lecons auto (uniquement sur evenements significatifs)
    # a) shift de regime -> re-evaluer EXTEND dans le nouveau regime
    for sym, avant, apres in shifts:
        if best and base:
            delta = round(best[1] - base["pnl"], 2)
            verdict = "AIDE" if delta > 0.5 else ("NUIT" if delta < -0.5 else "neutre")
            entry = {
                "ts": ts, "source": "research_loop (24/7)",
                "type": "regime_shift",
                "hypothese": f"Regime {sym} shifted {avant}->{apres}: re-evaluation EXTEND_TP",
                "resultat": f"EXTEND tp_ext={best[0]} PnL={best[1]}% vs FIXE={base['pnl']}% (Δ{delta:+.2f}%)",
                "decision": f"EXTEND_TP {verdict} dans le regime {apres}. Surveiller.",
                "statut": "OBSERVATION",
            }
            if enregistrer_lecon(entry):
                log.info("Lecon regime_shift enregistree: %s %s->%s", sym, avant, apres)

    # b) divergence live -> lecon d'alerte
    if div and div.get("alerte"):
        entry = {
            "ts": ts, "source": "research_loop (24/7)",
            "type": "divergence_live",
            "hypothese": "EXTEND_TP sous-performe en live vs backtest",
            "resultat": f"live win={div['win_rate_live']}% (attendu {div['win_rate_attendu']}%), avg={div['avg_win_live']}% (attendu {div['avg_win_attendu']}%)",
            "decision": "ALERTE: envisager revert EXTEND_TP si sous-perf persiste",
            "statut": "ALERTES",
        }
        if enregistrer_lecon(entry):
            log.warning("⚠️ Lecon divergence_live ENREGISTREE (alerte)")

    # log complet du cycle
    log_recherche({
        "ts": ts, "regimes": {k: regimes[k] for k in CRYPTO}, "shifts": shifts,
        "sweep": {"fixe": base["pnl"] if base else None, "rows": rows,
                  "best": list(best) if best else None},
        "divergence": div,
    })
    log.info("Cycle complete. Prochain dans %ds.", INTERVAL_SEC)


def main():
    log.info("research_loop demarre (24/7, intervalle %ds)", INTERVAL_SEC)
    # mode one-shot si arg "once"
    once = len(sys.argv) > 1 and sys.argv[1] == "once"
    while True:
        try:
            mods = _imports()
            cycle(mods)
        except Exception:
            log.error("Erreur cycle:\n%s", traceback.format_exc())
        if once:
            break
        try:
            time.sleep(INTERVAL_SEC)
        except KeyboardInterrupt:
            log.info("Arret."); break


if __name__ == "__main__":
    main()
