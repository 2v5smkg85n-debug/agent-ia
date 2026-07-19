#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classement_strategies.py — Classement dynamique des strategies selon le moment.

Repond au besoin: trier et classer les meilleures strategies selon le moment
(regime + volatilite courants). Passe du pruning binaire (actif/desactive) a un
SCORE CONTINU conditionnel au regime.

Score(sym, strat) = backtest_edge × regime_fit × live_mult
  - backtest_edge: retour_pct historique (prior statique)
  - regime_fit: fit_multi_tf (1.0=neutre, >1=aide en regime courant, <1=nuit)
                -> C'EST la composante "selon le moment" (trend vs range)
  - live_mult: Bayesian-shrunk depuis perf live recente (0.7..1.3, pese peu
               avec peu de trades -> honnete sur petit echantillon)
  - desactivee -> score 0 (rang dernier)

MODE OBSERVATION: calcule + ecrit classement_strategies.json + log table.
N'change PAS encore le choix d'entree (argent reel via bridge) -> on valide
d'abord que le classement est sensé (strategies connues mauvaises en bas),
puis integration avec confirmation.
"""
import os, sys, json, logging

D = os.path.dirname(os.path.abspath(__file__)) if os.path.isdir(
    os.path.join(os.getcwd(), "paper_trading.py")) else os.getcwd()
os.chdir(D)
sys.path.insert(0, D)

OUT = os.path.join(D, "classement_strategies.json")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("classement")


def _imports():
    import backtest_trailing as bt
    import auto_pruning
    from regime import fit_multi_tf, regime_actif
    from indicateurs import historique_ohlcv
    return bt, auto_pruning, fit_multi_tf, regime_actif, historique_ohlcv


def _closes(actif, historique_ohlcv, n=500):
    bougies = historique_ohlcv(actif, "1h", n)
    if not bougies:
        return None
    return [b["cloture"] for b in bougies]


def calculer_classement():
    bt, auto_pruning, fit_multi_tf, regime_actif, historique_ohlcv = _imports()
    strats_par_actif = bt._load_strategies()
    stats = auto_pruning.stats_strategies()  # {cle: {strategie,actif,n,wins,win_rate,pnl_total}}
    result = {}
    for actif, strats in strats_par_actif.items():
        try:
            closes = _closes(actif, historique_ohlcv)
        except Exception:
            closes = None
        try:
            reg = regime_actif(actif)
            reg_label = str(reg.get("REGIME", reg.get("regime", "?"))).upper() if isinstance(reg, dict) else str(reg).upper()
        except Exception:
            reg_label = "?"
        rows = []
        for s in strats:
            nom = s.get("strategie", "")
            backtest = float(s.get("retour_pct", 0) or 0)
            disabled = False
            try:
                disabled = auto_pruning.est_desactivee(nom, actif)
            except Exception:
                pass
            # regime fit (composante "selon le moment")
            fit_avg = 1.0
            if closes and len(closes) > 60:
                try:
                    fit_avg, _, _ = fit_multi_tf(nom, closes)
                except Exception:
                    fit_avg = 1.0
            # live perf (Bayesian shrunk)
            try:
                cle = auto_pruning._cle(nom, actif)
            except Exception:
                cle = f"{nom}|{actif}"
            st = stats.get(cle, {})
            n = int(st.get("n", 0)); wins = int(st.get("wins", 0))
            live_wr = (wins + 1) / (n + 2)  # 0..1, shrink vers 0.5
            live_weight = min(n / 10.0, 1.0)  # plein a 10+ trades
            live_mult = 1.0 + live_weight * (live_wr - 0.5) * 0.6  # ~0.7..1.3
            if disabled:
                score = 0.0
            else:
                score = backtest * fit_avg * live_mult
            rows.append({
                "strategie": nom, "actif": actif, "rang": 0,
                "score": round(score, 3),
                "backtest": round(backtest, 2), "regime_fit": round(fit_avg, 2),
                "live_n": n, "live_wr": round(live_wr * 100, 1),
                "live_mult": round(live_mult, 2),
                "live_pnl": round(st.get("pnl_total", 0), 2),
                "disabled": disabled, "regime": reg_label,
            })
        # rang par score desc (disabled -> score 0 -> dernier)
        rows.sort(key=lambda r: r["score"], reverse=True)
        max_s = max((r["score"] for r in rows), default=0)
        for i, r in enumerate(rows):
            r["rang"] = i + 1
            r["score_norm"] = round(r["score"] / max_s, 3) if max_s > 0 else 0.0
        result[actif] = {"regime": reg_label, "strategies": rows}
    # ecrit JSON
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        log.warning("ecriture JSON: %s", ex)
    return result


def afficher(result, top=3):
    print("=" * 90)
    print(f"CLASSEMENT STRATEGIES (top {top} par actif, selon le moment)")
    print("=" * 90)
    for actif, d in result.items():
        reg = d.get("regime", "?")
        strats = d.get("strategies", [])
        print(f"\n[{actif}] regime={reg}  ({len(strats)} strategies)")
        print(f"  {'Rang':<5}{'Strategie':<28}{'Score':>7}{'BT':>6}{'Fit':>6}{'LiveN':>7}{'LiveWR':>8}{'Mult':>6}{'Dis':>5}")
        for r in strats[:top]:
            print(f"  {r['rang']:<5}{r['strategie'][:27]:<28}{r['score']:>7.2f}{r['backtest']:>6.1f}"
                  f"{r['regime_fit']:>6.2f}{r['live_n']:>7}{r['live_wr']:>7.0f}%{r['live_mult']:>6.2f}"
                  f"{'OFF' if r['disabled'] else '-':>5}")
        # dernier (le plus mauvais) pour observer
        if len(strats) > top:
            r = strats[-1]
            print(f"  ...")
            print(f"  {r['rang']:<5}{r['strategie'][:27]:<28}{r['score']:>7.2f}{r['backtest']:>6.1f}"
                  f"{r['regime_fit']:>6.2f}{r['live_n']:>7}{r['live_wr']:>7.0f}%{r['live_mult']:>6.2f}"
                  f"{'OFF' if r['disabled'] else '-':>5}  <- dernier")
    print("=" * 90)


def main():
    res = calculer_classement()
    afficher(res)
    log.info("classement ecrit dans %s", OUT)


if __name__ == "__main__":
    main()
