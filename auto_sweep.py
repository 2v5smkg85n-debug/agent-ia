#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_sweep.py — Auto-optimisation continue des parametres de strategies.

Tourne toutes les 6h (cron). Balaie le seuil RSI via backtest, deploie la
meilleure variante si elle bat l'actuel, et enregistre la lecon.

Boucle d'auto-apprentissage:
  1. Lit le seuil RSI actuel dans strat_params.json
  2. Backtest chaque candidat (30/35/40/45) sur 1h x 10 cryptos
  3. Compare PnL total + win%
  4. Si un candidat bat l'actuel (PnL +10% ET win% >= actuel-5pt): deploie
  5. Enregistre la lecon dans lecons_apprises.jsonl (DEPLOYEE/REJETEE)

Securite:
  - Bornes: seuil RSI dans [30, 45]
  - 1 changement max par cycle
  - Idempotent (re-teste l'actuel comme reference)
  - Backup implicite: strat_params.json + lecon enregistree
  - Jamais de seuil < 30 (trop rare) ni > 45 (trop bruite)
"""
import os, sys, json
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(DOSSIER)
sys.path.insert(0, DOSSIER)

PARAMS_FILE = os.path.join(DOSSIER, "strat_params.json")
LECONS_FILE = os.path.join(DOSSIER, "lecons_apprises.jsonl")

CRYPTOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"]
CANDIDATS = [30, 35, 40, 45]   # seuils RSI a tester
N_BOUGIES = 500               # 1h, ~21 jours
SEUIL_AMELIORATION = 1.10     # +10% PnL pour deployer
TOLERANCE_WIN = 5.0           # win% peut baisser de max 5pt

def _load_params():
    try:
        return json.load(open(PARAMS_FILE, encoding="utf-8"))
    except Exception:
        return {"rsi_achat": 35, "rsi_vente": 70}

def _save_params(p):
    json.dump(p, open(PARAMS_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

def _append_lecon(lecon):
    with open(LECONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(lecon, ensure_ascii=False) + "\n")

def make_rsi(seuil_achat, seuil_vente=70):
    """RSI Mean Reversion parametre (pour le sweep)."""
    def f(i, d):
        r = d["rsi"][i]
        if r is None:
            return None
        if r < seuil_achat:
            return "ACHAT"
        if r > seuil_vente:
            return "VENTE"
        return None
    return f

def backtester_seuil(seuil, bougies_par_crypto):
    """Backtest un seuil RSI sur tous les cryptos. Retourne (pnl_total, win_pct, trades)."""
    from backtest_moteur import simuler
    pnl, gagnes, perdus, trades = 0.0, 0, 0, 0
    for sym, bougies in bougies_par_crypto.items():
        try:
            stats = simuler(bougies, make_rsi(seuil))
            if stats:
                pnl += stats.get("retour_pct", 0)
                gagnes += stats.get("gagnes", 0)
                perdus += stats.get("perdus", 0)
                trades += stats.get("trades", 0)
        except Exception:
            pass
    win = (100 * gagnes / trades) if trades else 0
    return pnl, win, trades

def main():
    from indicateurs import historique_ohlcv
    print(f"=== AUTO-SWEEP {datetime.utcnow():%Y-%m-%d %H:%M} UTC ===")
    params = _load_params()
    seuil_actuel = params.get("rsi_achat", 35)
    print(f"Seuil RSI actuel: {seuil_actuel}")

    # Fetch bougies une fois (reutilise pour tous les candidats)
    print(f"Fetch {N_BOUGIES} bougies 1h x {len(CRYPTOS)} cryptos...")
    bougies_par_crypto = {}
    for sym in CRYPTOS:
        b = historique_ohlcv(sym, "1h", N_BOUGIES)
        if b and len(b) >= 60:
            bougies_par_crypto[sym] = b
    print(f"  {len(bougies_par_crypto)}/{len(CRYPTOS)} cryptos chargés")

    # Backtest chaque candidat
    resultats = {}
    for seuil in CANDIDATS:
        pnl, win, n = backtester_seuil(seuil, bougies_par_crypto)
        resultats[seuil] = {"pnl": pnl, "win": win, "trades": n}
        print(f"  RSI<{seuil:<2}: PnL {pnl:>+7.1f}%  win {win:>4.0f}%  {n} trades")

    # Reference = seuil actuel
    ref = resultats.get(seuil_actuel, {"pnl": 0, "win": 0, "trades": 0})
    print(f"\nReference (actuel RSI<{seuil_actuel}): PnL {ref['pnl']:+.1f}% win {ref['win']:.0f}%")

    # Cherche le meilleur candidat (max PnL, win% >= ref.win - tolerance)
    meilleurs = [(s, r) for s, r in resultats.items()
                 if r["win"] >= ref["win"] - TOLERANCE_WIN]
    if not meilleurs:
        print("Aucun candidat respecte la tolerance win% -> pas de changement")
        _append_lecon(_lecon(seuil_actuel, resultats, None, "REJETEE",
                             "aucun candidat respecte tolerance win%"))
        return
    best_seuil, best = max(meilleurs, key=lambda x: x[1]["pnl"])

    # Deploie seulement si amelioration significative
    if best_seuil != seuil_actuel and best["pnl"] > ref["pnl"] * SEUIL_AMELIORATION:
        avant = seuil_actuel
        params["rsi_achat"] = best_seuil
        params["dernier_sweep"] = f"{datetime.utcnow():%Y-%m-%d %H:%M} UTC"
        params["dernier_pnl_total"] = round(best["pnl"], 2)
        _save_params(params)
        print(f"\n*** DEPLOIE: RSI seuil {avant} -> {best_seuil} ***")
        print(f"  PnL {ref['pnl']:+.1f}% -> {best['pnl']:+.1f}%  win {ref['win']:.0f}% -> {best['win']:.0f}%")
        _append_lecon(_lecon(avant, resultats, best_seuil, "DEPLOYEE",
                             f"RSI {avant}->{best_seuil}: PnL {ref['pnl']:+.1f}%->{best['pnl']:+.1f}% win {ref['win']:.0f}%->{best['win']:.0f}%"))
    else:
        print(f"\nPas de deploiement (meilleur={best_seuil} non assez superieur ou = actuel)")
        _append_lecon(_lecon(seuil_actuel, resultats, best_seuil, "REJETEE",
                             f"meilleur RSI<{best_seuil} PnL {best['pnl']:+.1f}% vs actuel {ref['pnl']:+.1f}% (amelioration < {int((SEUIL_AMELIORATION-1)*100)}%)"))

def _lecon(seuil_actuel, resultats, best_seuil, statut, decision):
    return {
        "ts": f"{datetime.utcnow():%Y-%m-%d %H:%M:%S}",
        "source": "auto_sweep.py (auto-optimisation seuil RSI)",
        "hypothese": f"Seuil RSI optimal: tester {CANDIDATS} vs actuel {seuil_actuel}",
        "test": f"Backtest 1h {N_BOUGIES} bougies x {len(CRYPTOS)} cryptos, RSI Mean Reversion",
        "resultat": " | ".join(f"RSI<{s}: {r['pnl']:+.1f}% win{r['win']:.0f}% ({r['trades']}t)"
                               for s, r in resultats.items()),
        "decision": decision,
        "statut": statut,
        "meta": f"auto_sweep: seuil_actuel={seuil_actuel} best={best_seuil}",
    }

if __name__ == "__main__":
    main()
