#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""genetic_optimizer.py — Optimizer GENETIQUE pour apprentissage accelere.

Au lieu de tester 4 seuils RSI en grille (auto_sweep.py), fait EVOLUER une
population de configurations sur N generations:
  - genome: rsi_achat, rsi_vente, tp, sl, bb_ecart (5 genes)
  - selection elite + crossover + mutation
  - WALK-FORWARD: entraine sur 70% des bougies, valide sur 30% jamais vues
  - deploie seulement si OOS bat la baseline + marge (anti-overfitting)

Beaucoup plus rapide + plus sur que le grid sweep. Cron quotidien (03:30 UTC).

Fitness in-sample = moyenne sur 10 cryptos de la MEILLEURE strategie par crypto
(mimique le classement: l'agent choisit sa meilleure strategie par actif).
"""
import os, json, random, time
from datetime import datetime
import backtest_moteur as bm
from indicateurs import historique_ohlcv

DOSSIER = os.path.dirname(os.path.abspath(__file__))
SP_FILE = os.path.join(DOSSIER, "strat_params.json")
LECONS = os.path.join(DOSSIER, "lecons_apprises.jsonl")
LOGDIR = os.path.join(DOSSIER, "logs")
LOG = os.path.join(LOGDIR, "genetic_optimizer.log")

# --- Genome: 5 genes optimisables ---
BOUNDS = {
    "rsi_achat": (25, 45),
    "rsi_vente": (65, 85),
    "tp":        (0.008, 0.030),   # take-profit 0.8%-3%
    "sl":        (0.008, 0.030),   # stop-loss 0.8%-3%
    "bb_ecart":  (1.5, 3.0),      # ecart Bollinger
}
POP = 12          # taille population
GENS = 6          # generations
ELITE = 3         # elites conserves
MUT = 0.30        # proba mutation par gene
DEPLOI_MARGE = 1.0  # +3pp OOS requis pour deployer (anti-overfitting)

CRYPTOS = bm.ACTIFS["crypto"]
INTERVALLE = "1h"
N_BOUGIES = 500
SPLIT = 0.70      # 70% in-sample, 30% out-of-sample


def log(msg):
    line = f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def load_sp():
    try:
        return json.load(open(SP_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_sp(sp):
    json.dump(sp, open(SP_FILE, "w"), indent=2, ensure_ascii=False)


def apply_genome(g):
    """Applique un genome: ecrit rsi/bb_ecart dans strat_params + monkeypatch tp/sl."""
    sp = load_sp()
    sp["rsi_achat"] = g["rsi_achat"]
    sp["rsi_vente"] = g["rsi_vente"]
    sp["bb_ecart"] = g["bb_ecart"]
    save_sp(sp)
    bm._SP_CACHE["vals"] = None  # bust cache -> _strat_params/_bb_ecart rechargent
    bm.TAKE_PROFIT_PCT = g["tp"]
    bm.STOP_LOSS_PCT = g["sl"]


def rand_genome():
    return {k: round(random.uniform(lo, hi), 4) for k, (lo, hi) in BOUNDS.items()}


def crossover(a, b):
    return {k: (a[k] if random.random() < 0.5 else b[k]) for k in BOUNDS}


def mutate(g):
    for k, (lo, hi) in BOUNDS.items():
        if random.random() < MUT:
            g[k] = round(random.uniform(lo, hi), 4)
    return g


def eval_genome(g, bougies_map, sample_end):
    """Fitness in-sample = moyenne des meilleures strategie/crypto (0..sample_end)."""
    apply_genome(g)
    best_pnls = []
    for sym in CRYPTOS:
        bougies = bougies_map.get(sym, [])[:sample_end]
        if not bougies or len(bougies) < 60:
            continue
        best = None
        for _, fonc in bm.STRATEGIES.items():
            st = bm.simuler(bougies, fonc)
            if st and st["trades"] >= 3:
                if best is None or st["retour_pct"] > best:
                    best = st["retour_pct"]
        if best is not None:
            best_pnls.append(best)
    if len(best_pnls) < 3:
        return -999.0
    return sum(best_pnls) / len(best_pnls)


def eval_oos(g, bougies_map, sample_start):
    """Out-of-sample: moyenne meilleures strategie/crypto sur les 30% finales."""
    apply_genome(g)
    pnls = []
    for sym in CRYPTOS:
        bougies = bougies_map.get(sym, [])[sample_start:]
        if not bougies or len(bougies) < 60:
            continue
        best = None
        for _, fonc in bm.STRATEGIES.items():
            st = bm.simuler(bougies, fonc)
            if st and st["trades"] >= 3:
                if best is None or st["retour_pct"] > best:
                    best = st["retour_pct"]
        if best is not None:
            pnls.append(best)
    if len(pnls) < 3:
        return -999.0, 0
    return sum(pnls) / len(pnls), len(pnls)


def record_lecon(g, fit_is, fit_oos, base_oos, deployed):
    entry = {
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "source": "genetic_optimizer",
        "type": "optimisation_genetique",
        "generations": GENS,
        "population": POP,
        "genome": {k: round(v, 4) for k, v in g.items()},
        "fitness_in_sample": round(fit_is, 2),
        "fitness_out_of_sample": round(fit_oos, 2),
        "baseline_out_of_sample": round(base_oos, 2),
        "deployed": deployed,
    }
    try:
        with open(LECONS, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    log("=" * 50)
    log("GENETIC OPTIMIZER START")
    log(f"genome: {list(BOUNDS.keys())} | pop={POP} gens={GENS} walk-forward {int(SPLIT*100)}/{int((1-SPLIT)*100)}")
    random.seed(int(time.time()))

    # 1. Charge les bougies (une seule fois)
    bougies_map = {}
    for sym in CRYPTOS:
        try:
            b = historique_ohlcv(sym, INTERVALLE, N_BOUGIES)
            if b and len(b) >= 60:
                bougies_map[sym] = b
        except Exception as e:
            log(f"  bougies {sym} echec: {e}")
        time.sleep(0.15)
    log(f"Bougies chargees: {len(bougies_map)}/{len(CRYPTOS)} cryptos")
    if len(bougies_map) < 3:
        log("PAS ASSEZ DE BOUGIES - abandon")
        return

    n = min(len(b) for b in bougies_map.values())
    split_idx = int(n * SPLIT)
    log(f"Bougies: {n} | in-sample [0:{split_idx}] | OOS [{split_idx}:{n}]")

    # 2. Baseline (config actuelle) en OOS
    sp = load_sp()
    baseline = {
        "rsi_achat": sp.get("rsi_achat", 35),
        "rsi_vente": sp.get("rsi_vente", 70),
        "tp": 0.015,   # defaut simuler
        "sl": 0.015,
        "bb_ecart": sp.get("bb_ecart", 2.0),
    }
    # recupere tp/sl actuels du module (peuvent avoir ete modifies)
    baseline["tp"] = round(bm.TAKE_PROFIT_PCT, 4)
    baseline["sl"] = round(bm.STOP_LOSS_PCT, 4)
    base_oos, base_n = eval_oos(baseline, bougies_map, split_idx)
    log(f"Baseline actuelle OOS: {base_oos:+.2f}% (n={base_n}) | {baseline}")

    # 3. Evolution
    pop = [rand_genome() for _ in range(POP)]
    best_g = None
    best_fit = -999.0
    for gen in range(GENS):
        scored = [(eval_genome(g, bougies_map, split_idx), g) for g in pop]
        scored.sort(key=lambda x: x[0], reverse=True)
        gen_best_fit, gen_best_g = scored[0]
        if gen_best_fit > best_fit:
            best_fit = gen_best_fit
            best_g = dict(gen_best_g)
        g = gen_best_g
        log(f"Gen {gen+1}/{GENS}: best IS={gen_best_fit:+.2f}% | "
            f"rsi={g['rsi_achat']}/{g['rsi_vente']} tp={g['tp']} sl={g['sl']} bb={g['bb_ecart']}")
        # elite + reproduction
        elites = [x[1] for x in scored[:ELITE]]
        pool = [x[1] for x in scored[:max(ELITE*2, 4)]]
        new_pop = list(elites)
        while len(new_pop) < POP:
            new_pop.append(mutate(crossover(random.choice(elites), random.choice(pool))))
        pop = new_pop

    log(f"Meilleur genome IS: fitness={best_fit:+.2f}%")

    # 4. Walk-forward OOS validation du meilleur genome
    oos, oos_n = eval_oos(best_g, bougies_map, split_idx)
    log(f"Meilleur genome OOS: {oos:+.2f}% (n={oos_n}) vs baseline {base_oos:+.2f}%")

    # 5. Deploiement conditionnel (anti-overfitting)
    deployed = False
    if oos > base_oos + DEPLOI_MARGE and oos > 0:
        apply_genome(best_g)
        sp = load_sp()
        sp["dernier_genetic"] = {
            "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "oos": round(oos, 2),
            "baseline_oos": round(base_oos, 2),
            "gens": GENS,
        }
        save_sp(sp)
        deployed = True
        log(f"DEPLOIEMENT: genome evolue deploye (OOS {oos:+.2f}% > baseline {base_oos:+.2f}% + {DEPLOI_MARGE}pp)")
    else:
        apply_genome(baseline)  # restore config actuelle
        log(f"PAS DE DEPLOIEMENT: OOS {oos:+.2f}% <= baseline+marge {base_oos+DEPLOI_MARGE:+.2f}% (overfitting evite)")

    record_lecon(best_g, best_fit, oos, base_oos, deployed)
    log("GENETIC OPTIMIZER END")
    log("=" * 50)


if __name__ == "__main__":
    main()
