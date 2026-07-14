#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regime.py — Detection du regime de marche (trend/range/volatilite).

Classifie le regime actuel d'un actif pour adapter la selection de strategies:
  - TRENDING_UP / TRENDING_DOWN : tendance nette (SMA20 eloignee de SMA50)
  - VOLATILE : forte volatilite recente
  - QUIET    : faible volatilite
  - RANGING  : range sans tendance (cas par defaut)

Fit strategie -> regime:
  - MACD Momentum, SMA Crossover -> preferent TRENDING
  - RSI Mean Reversion           -> preferent RANGING/QUIET
  - Bollinger Breakout           -> preferent VOLATILE/TRENDING

Integration: signaux_gagnants pondere retour_pct par le fit de regime
(strategies adaptees au regime actuel privilegiees).

CLI:
  python regime.py                 # regimes actuels de tous les marches paper
  python regime.py BTCUSDT 1h     # regime d'un actif precis
"""
import os
import json
import math
import logging
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
REGIME_LOG = os.path.join(DOSSIER, "regime_history.jsonl")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("regime")


def _sma(values, periode):
    if len(values) < periode:
        return None
    return sum(values[-periode:]) / periode


def _stdev(values):
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def regime_depuis_clotures(clotures):
    """Classifie le regime a partir d'une liste de prix de cloture.
    Retourne dict {regime, direction, trend_strength, vol, sma20, sma50}."""
    if not clotures or len(clotures) < 50:
        return {"regime": "INCONNU", "direction": "?",
                "trend_strength": 0.0, "vol": 0.0,
                "sma20": None, "sma50": None}
    sma20 = _sma(clotures, 20)
    sma50 = _sma(clotures, 50)
    # force de tendance: ecart normalise SMA20 vs SMA50 (en %)
    trend_strength = abs(sma20 - sma50) / sma50 * 100.0 if sma50 else 0.0
    direction = "up" if sma20 >= sma50 else "down"
    # volatilite: ecart-type des rendements % sur 20 dernieres bougies
    rends = []
    for i in range(max(1, len(clotures) - 20), len(clotures)):
        if clotures[i - 1] > 0:
            rends.append((clotures[i] / clotures[i - 1] - 1) * 100.0)
    vol = _stdev(rends)
    # seuils empiriques
    if trend_strength > 1.5:
        regime = f"TRENDING_{direction.upper()}"
    elif vol > 2.5:
        regime = "VOLATILE"
    elif vol < 0.8:
        regime = "QUIET"
    else:
        regime = "RANGING"
    return {"regime": regime, "direction": direction,
            "trend_strength": round(trend_strength, 3),
            "vol": round(vol, 3),
            "sma20": round(sma20, 6), "sma50": round(sma50, 6)}


def regime_actif(symbole, intervalle="1h", limite=100):
    """Recupere l'historique et classifie le regime d'un actif."""
    try:
        from indicateurs import historique_ohlcv
        bougies = historique_ohlcv(symbole, intervalle, limite)
        clotures = [b["cloture"] for b in bougies] if bougies else []
        r = regime_depuis_clotures(clotures)
        r["symbole"] = symbole
        r["intervalle"] = intervalle
        return r
    except Exception as e:
        log.warning("regime_actif %s indispo: %s", symbole, e)
        return {"regime": "INCONNU", "symbole": symbole, "intervalle": intervalle}


# --- Fit strategie -> regime ---
FIT_REGIME = {
    # strategie: {regime_cible: multiplicateur}
    "MACD Momentum":      {"TRENDING_UP": 1.3, "TRENDING_DOWN": 1.3,
                           "RANGING": 0.7, "QUIET": 0.6, "VOLATILE": 1.1},
    "SMA Crossover":      {"TRENDING_UP": 1.3, "TRENDING_DOWN": 1.3,
                           "RANGING": 0.6, "QUIET": 0.8, "VOLATILE": 1.0},
    "RSI Mean Reversion": {"RANGING": 1.3, "QUIET": 1.3,
                           "TRENDING_UP": 0.6, "TRENDING_DOWN": 0.6,
                           "VOLATILE": 0.9},
    "Bollinger Breakout": {"VOLATILE": 1.3, "TRENDING_UP": 1.2,
                           "TRENDING_DOWN": 1.2, "RANGING": 0.8, "QUIET": 0.7},
}


def strategie_regime_fit(nom_strat, regime):
    """Multiplicateur de fit [0.5..1.5]. 1.0 = neutre/inconnu."""
    if not regime or regime == "INCONNU":
        return 1.0
    fits = FIT_REGIME.get(nom_strat, {})
    return fits.get(regime, 1.0)


def regimes_actuels(marches=None):
    """Regime actuel de tous les marches paper (pour dashboard/reflection)."""
    pf = {}
    try:
        pf = json.load(open(PT_FILE, encoding="utf-8"))
    except Exception:
        pass
    if marches is None:
        marches = pf.get("marches_config", {}) or {}
        if not marches:
            # fallback: positions + quelques actifs connus
            marches = {p["symbole"]: {} for p in pf.get("positions", [])}
    out = {}
    for sym in marches:
        out[sym] = regime_actif(sym, "1h", 100)
    return out


def snapshot():
    """Snapshot des regimes -> regime_history.jsonl (pour tracking temporel)."""
    regs = regimes_actuels()
    entry = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "regimes": {s: r.get("regime") for s, r in regs.items()}}
    try:
        with open(REGIME_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def main():
    import sys
    if len(sys.argv) > 2:
        sym, interv = sys.argv[1], sys.argv[2]
        r = regime_actif(sym, interv)
        print(f"{sym} [{interv}]: {r['regime']} | trend={r.get('trend_strength')} "
              f"vol={r.get('vol')} sma20={r.get('sma20')} sma50={r.get('sma50')}")
        return
    # tous les marches
    regs = regimes_actuels()
    print("=" * 55)
    print("REGIMES DE MARCHE ACTUELS")
    print("=" * 55)
    for sym, r in sorted(regs.items()):
        print(f"  {sym:<12} {r.get('regime','?'):<16} "
              f"trend={r.get('trend_strength',0):.2f}% vol={r.get('vol',0):.2f}%")
    snapshot()


if __name__ == "__main__":
    main()
