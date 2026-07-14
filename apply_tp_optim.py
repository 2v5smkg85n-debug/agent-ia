#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Applique le TP/SL optimal (backtest grid search) aux cryptos dans params_tuning.json.
TP 1.5->2.0, SL 1.5->2.5 (valide: +7.36% PnL, win 69->77% sur 500h x 5 cryptos).
Forex/actions non touches (volatilite faible, default 1.5/1.5 conserve)."""
import os
import json
from datetime import datetime

DOSSIER = os.getcwd()
PARAMS_FILE = os.path.join(DOSSIER, "params_tuning.json")
CRYPTOS = ["BTCUSDT", "SOLUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]
TP_OPT, SL_OPT = 2.0, 2.5

try:
    data = json.load(open(PARAMS_FILE, encoding="utf-8"))
except Exception:
    data = {"params": {}, "dernier_cycle": None}
params = data.setdefault("params", {})
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
nb = 0
for sym in CRYPTOS:
    p = params.get(sym, {"tp": 1.5, "sl": 1.5, "historique": []})
    avant_tp, avant_sl = float(p.get("tp", 1.5)), float(p.get("sl", 1.5))
    p["tp"] = TP_OPT
    p["sl"] = SL_OPT
    p["ajuste_le"] = now
    p["raison"] = "[backtest grid search] optimal TP/SL: +7.36% PnL, win 69%->77% (500h x 5 cryptos)"
    p["source"] = "backtest_tp_optim"
    p["historique"] = p.get("historique", []) + [{
        "ts": now, "tp": TP_OPT, "sl": SL_OPT,
        "raison": f"grid search optimal (avant {avant_tp}/{avant_sl})",
        "source": "backtest_tp_optim"}]
    params[sym] = p
    nb += 1
data["params"] = params
data["dernier_cycle"] = now
json.dump(data, open(PARAMS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[OK] {nb} cryptos mis a TP={TP_OPT}% SL={SL_OPT}% dans params_tuning.json")
print("     verifier_sorties lira ces valeurs au prochain tick (via tp_sl_actif).")
print("     Forex/actions restent a 1.5/1.5 (default).")
