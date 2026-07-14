#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_tuning.py — Auto-tuning des seuils TP/SL par actif (self-improvement).

Ajuste automatiquement les take-profit / stop-loss par actif selon les perf live,
avec garde-fous stricts (anti-overfitting + caps durs):
  - min 5 trades par actif pour tuner
  - pas de 0.25%, bounds: TP [1.0, 3.0], SL [0.5, 2.5]
  - win_rate > 60% + gains moyens < TP actuel -> elargir TP (capturer plus)
  - win_rate < 40% -> serrer SL (couper les pertes plus tot)
  - win_rate < 30% -> aussi serrer TP (encaisser plus vite)

Fichier d'etat: params_tuning.json {symbole: {tp, sl, ajuste_le, raison}}
Integration: verifier_sorties lit tp_sl_actif(sym) (fallback constantes globales).

CLI:
  python meta_tuning.py            # cycle de tuning + rapport
  python meta_tuning.py etat       # voir les params actuels
"""
import os
import json
import logging
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT_FILE = os.path.join(DOSSIER, "paper_trading.json")
PARAMS_FILE = os.path.join(DOSSIER, "params_tuning.json")
LOG_FILE = os.path.join(DOSSIER, "meta_tuning_log.jsonl")

# Defaults (matchent TAKE_PROFIT_PCT / STOP_LOSS_PCT de paper_trading)
TP_DEFAUT = 1.5
SL_DEFAUT = 1.5

# Garde-fous
MIN_TRADES = 5
PAS = 0.25
TP_MIN, TP_MAX = 1.0, 3.0
SL_MIN, SL_MAX = 0.5, 2.5
WR_HAUT = 60.0    # win rate -> elargir TP
WR_BAS = 40.0     # win rate -> serrer SL
WR_TRES_BAS = 30.0  # -> serrer TP aussi

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("meta_tuning")


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tel(msg):
    try:
        from telegram_alerte import envoyer_telegram
        envoyer_telegram(msg)
    except Exception:
        pass


def _log_jsonl(entry):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def init_params():
    if not os.path.exists(PARAMS_FILE):
        _save(PARAMS_FILE, {"params": {}, "dernier_cycle": None})
    return _load(PARAMS_FILE, {"params": {}})


def tp_sl_actif(symbole):
    """Importe par verifier_sorties. Retourne (tp, sl) pour un actif.
    Fallback aux defaults si non tune."""
    try:
        data = _load(PARAMS_FILE, {})
        p = data.get("params", {}).get(symbole)
        if p:
            return float(p.get("tp", TP_DEFAUT)), float(p.get("sl", SL_DEFAUT))
    except Exception:
        pass
    return TP_DEFAUT, SL_DEFAUT


# ---------------------------------------------------------------- STATS
def stats_par_actif():
    """Perf live par symbole depuis trades_fermes."""
    pf = _load(PT_FILE, {})
    trades = pf.get("trades_fermes", [])
    stats = {}
    for t in trades:
        sym = t.get("symbole", "")
        if not sym:
            continue
        var = float(t.get("variation_pct") or 0)
        s = stats.setdefault(sym, {"n": 0, "wins": 0, "variations": [],
                                   "wins_var": []})
        s["n"] += 1
        s["variations"].append(var)
        if var > 0:
            s["wins"] += 1
            s["wins_var"].append(var)
    for s in stats.values():
        s["win_rate"] = round(100.0 * s["wins"] / s["n"], 1) if s["n"] else 0.0
        s["avg_win"] = round(sum(s["wins_var"]) / len(s["wins_var"]), 3) if s["wins_var"] else 0.0
        s["avg_var"] = round(sum(s["variations"]) / len(s["variations"]), 3) if s["variations"] else 0.0
    return stats


# ---------------------------------------------------------------- LOGIQUE
def _borne(val, lo, hi):
    return max(lo, min(hi, val))


def tuner():
    """Cycle de tuning. Ajuste TP/SL par actif selon perf live."""
    data = init_params()
    params = data.get("params", {})
    stats = stats_par_actif()
    changements = []
    maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for sym, s in stats.items():
        if s["n"] < MIN_TRADES:
            continue
        p = params.get(sym, {"tp": TP_DEFAUT, "sl": SL_DEFAUT,
                             "historique": []})
        tp, sl = float(p.get("tp", TP_DEFAUT)), float(p.get("sl", SL_DEFAUT))
        wr = s["win_rate"]
        nouveau_tp, nouveau_sl = tp, sl
        raison = ""
        # win_rate haut + gains moyens petits -> elargir TP
        if wr >= WR_HAUT and s["avg_win"] < tp - 0.3:
            nouveau_tp = _borne(tp + PAS, TP_MIN, TP_MAX)
            if nouveau_tp != tp:
                raison = f"wr {wr}%>= {WR_HAUT}% et gain moyen {s['avg_win']}%< TP-{0.3}: elargir TP"
        # win_rate tres bas -> serrer TP (encaisser plus vite)
        elif wr < WR_TRES_BAS:
            nouveau_tp = _borne(tp - PAS, TP_MIN, TP_MAX)
            if nouveau_tp != tp:
                raison = f"wr {wr}%< {WR_TRES_BAS}%: serrer TP"
        # win_rate bas -> serrer SL (couper pertes plus tot)
        if wr < WR_BAS:
            nouveau_sl = _borne(sl + PAS, SL_MIN, SL_MAX)
            if nouveau_sl != sl:
                raison = (raison + " | " if raison else "") + \
                         f"wr {wr}%< {WR_BAS}%: serrer SL"

        if nouveau_tp == tp and nouveau_sl == sl:
            continue  # pas de changement
        p["tp"] = nouveau_tp
        p["sl"] = nouveau_sl
        p["ajuste_le"] = maintenant
        p["raison"] = raison
        p["historique"] = p.get("historique", []) + [{
            "ts": maintenant, "tp": nouveau_tp, "sl": nouveau_sl, "raison": raison,
            "stats": {"n": s["n"], "wr": wr, "avg_win": s["avg_win"]}}]
        params[sym] = p
        changements.append((sym, tp, sl, nouveau_tp, nouveau_sl, raison))

    data["params"] = params
    data["dernier_cycle"] = maintenant
    _save(PARAMS_FILE, data)

    for sym, tp, sl, ntp, nsl, raison in changements:
        msg = (f"🔧 META-TUNING {sym}: TP {tp}%→{ntp}%, SL {sl}%→{nsl}%\n{raison}")
        log.info(msg)
        _tel(msg)
        _log_jsonl({"ts": maintenant, "symbole": sym, "tp_avant": tp, "tp_apres": ntp,
                    "sl_avant": sl, "sl_apres": nsl, "raison": raison})
    return changements, stats, data


def cmd_etat():
    data = init_params()
    stats = stats_par_actif()
    params = data.get("params", {})
    print("=" * 60)
    print("META-TUNING — TP/SL par actif (perf live)")
    print(f"Defaults: TP={TP_DEFAUT}% SL={SL_DEFAUT}% | bounds TP[{TP_MIN},{TP_MAX}] SL[{SL_MIN},{SL_MAX}]")
    print(f"min {MIN_TRADES} trades pour tuner | pas {PAS}%")
    print("=" * 60)
    for sym, s in sorted(stats.items(), key=lambda x: -x[1]["n"]):
        p = params.get(sym, {})
        tp = p.get("tp", TP_DEFAUT)
        sl = p.get("sl", SL_DEFAUT)
        tune = "🔧 tune" if p else "default"
        print(f"  {sym:<12} n={s['n']:<3} wr={s['win_rate']}% "
              f"avgWin={s['avg_win']}% | TP={tp}% SL={sl}% {tune}")
    print("=" * 60)
    print(f"Dernier cycle: {data.get('dernier_cycle','jamais')}")


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "etat":
        cmd_etat()
        return
    changements, stats, data = tuner()
    print(f"Cycle tuning termine. {len(changements)} ajustement(s).")
    cmd_etat()


if __name__ == "__main__":
    main()
