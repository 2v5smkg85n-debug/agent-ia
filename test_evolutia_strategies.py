#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test evolutia_profit.py — extension stratégies evolved (strategy_evolver).

Valide: enregistrer_strategie, _decide_strategie, evaluer (type=strategie),
_revert_strategie, _regen_evolved_module, force_revert (type-aware), rapport.
"""
import os
import sys
import json
import shutil
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evolutia_profit as ep

# --- mock dirs ---
TMP = tempfile.mkdtemp(prefix="evolutia_strat_test_")
ep.DOSSIER = TMP
ep.PT_FILE = os.path.join(TMP, "paper_trading.json")
ep.LEDGER_FILE = os.path.join(TMP, "evolutia_ledger.jsonl")
ep.PLUGINS_DIR = os.path.join(TMP, "plugins")
ep.DISABLED_DIR = os.path.join(TMP, "plugins_disabled")
ep.EVOLVED_JSON = os.path.join(TMP, "strategies_evolved.json")
ep.EVOLVED_PY = os.path.join(TMP, "strategies_evolved.py")
os.makedirs(ep.PLUGINS_DIR)
ep.TELEGRAM_TOKEN = ""
ep.TELEGRAM_CHAT = ""

PASS = 0
FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {nom}")
    else:
        FAIL += 1
        print(f"  ❌ {nom}  {detail}")

def mk_trade(min_ago, var_pct, gain_eur, strat="RSI Mean Reversion"):
    dt = datetime.utcnow() - timedelta(minutes=min_ago)
    return {"date_fermeture": dt.strftime("%Y-%m-%d %H:%M"),
            "variation_pct": var_pct, "gain_eur": gain_eur,
            "strategie": strat, "raison": "TAKE-PROFIT",
            "nom": "BTC", "marche": "crypto"}

def backdate_last(days=0, minutes=25):
    recs = ep._read_ledger()
    recs[-1]["apply_time"] = (datetime.utcnow() - timedelta(days=days, minutes=minutes)).isoformat(timespec="seconds")
    ep._write_ledger(recs)

def mk_evolved_json(name="Evolved 00955", func_name="strat_evolved_00955"):
    """Crée un strategies_evolved.json avec une stratégie."""
    strats = [{"name": name, "func_name": func_name,
               "code": f"def {func_name}(i, d):\n    return None",
               "date": "2026-07-24 05:00", "oos_avg": 2.5, "is_avg": 3.0,
               "win_rate": 60.0, "trades": 8, "llm_source": "gemini",
               "parent": None}]
    json.dump(strats, open(ep.EVOLVED_JSON, "w"), indent=2, ensure_ascii=False)
    return strats


print("=" * 60)
print("TEST 1: enregistrer_strategie crée un record type=strategie")
# 40 trades baseline (portefeuille sain)
trades_base = [mk_trade(1440 - i, 0.40, 1.2, strat="RSI Mean Reversion") for i in range(40)]
json.dump({"trades_fermes": trades_base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep._write_ledger([])
ok = ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
recs = ep._read_ledger()
check("retourne True", ok)
check("1 record dans ledger", len(recs) == 1, str(len(recs)))
check("type=strategie", recs[0].get("type") == "strategie", str(recs[0].get("type")))
check("strategie='Evolved 00955'", recs[0].get("strategie") == "Evolved 00955")
check("statut EN_EVALUATION", recs[0]["statut"] == "EN_EVALUATION")
check("oos_avg=2.5", recs[0].get("oos_avg") == 2.5, str(recs[0].get("oos_avg")))
check("oos_win=0.60", recs[0].get("oos_win") == 0.60, str(recs[0].get("oos_win")))
check("oos_trades=8", recs[0].get("oos_trades") == 8, str(recs[0].get("oos_trades")))
check("baseline n=40", recs[0]["baseline"]["n"] == 40, str(recs[0]["baseline"]["n"]))

print("\nTEST 2: _decide_strategie REVERT sur perte nette (pnl_eur < 0)")
post_loss = {"n": 12, "avg_gain_pct": -0.15, "pnl_eur": -1.85,
             "win_rate": 0.40, "trades_per_day": 1.0, "std_gain": 0.3,
             "pnl_per_trade": -0.154}
baseline = {"avg_gain_pct": 0.059, "win_rate": 0.722}
statut, verdict = ep._decide_strategie(baseline, post_loss, oos_win=0.60)
check("statut REVERT", statut == "REVERT", statut)
check("verdict mentionne perte nette", "perte nette" in verdict.lower(), verdict)

print("\nTEST 3: _decide_strategie GARDE sur profit positif")
post_win = {"n": 12, "avg_gain_pct": 0.50, "pnl_eur": 2.40,
            "win_rate": 0.66, "trades_per_day": 1.0, "std_gain": 0.3,
            "pnl_per_trade": 0.20}
statut, verdict = ep._decide_strategie(baseline, post_win, oos_win=0.60)
check("statut GARDE", statut == "GARDE", statut)

print("\nTEST 4: _decide_strategie REVERT sur win rate dégradé (vs OOS)")
# pnl positif mais win rate << OOS
post_lowwin = {"n": 12, "avg_gain_pct": 0.10, "pnl_eur": 0.50,
               "win_rate": 0.30, "trades_per_day": 1.0, "std_gain": 0.5,
               "pnl_per_trade": 0.04}
statut, verdict = ep._decide_strategie(baseline, post_lowwin, oos_win=0.70)
check("statut REVERT (win rate)", statut == "REVERT", statut)
check("verdict mentionne win rate", "win rate" in verdict.lower(), verdict)

print("\nTEST 5: _regen_evolved_module génère un .py valide depuis JSON")
strats = mk_evolved_json("Evolved 12345", "strat_evolved_12345")
ep._regen_evolved_module(strats)
check(".py créé", os.path.isfile(ep.EVOLVED_PY))
py_content = open(ep.EVOLVED_PY).read()
check(".py contient EVOLVED_STRATEGIES", "EVOLVED_STRATEGIES" in py_content)
check(".py contient 'Evolved 12345'", "Evolved 12345" in py_content)
check(".py contient strat_evolved_12345", "strat_evolved_12345" in py_content)
# Vérifie que le .py généré est importable
ns = {}
exec(compile(open(ep.EVOLVED_PY).read(), ep.EVOLVED_PY, "exec"), ns)
check("EVOLVED_STRATEGIES dict dans le .py", "EVOLVED_STRATEGIES" in ns)
check("1 stratégie dans le dict", len(ns["EVOLVED_STRATEGIES"]) == 1)

print("\nTEST 6: _revert_strategie retire du JSON + régénère le .py")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
removed = ep._revert_strategie("Evolved 00955", "test revert")
check("retourne True (removed)", removed)
strats_after = json.load(open(ep.EVOLVED_JSON))
check("JSON vide après revert", len(strats_after) == 0, str(len(strats_after)))
py_after = open(ep.EVOLVED_PY).read()
check(".py régénéré avec dict vide", "EVOLVED_STRATEGIES = {\n}" in py_after)

print("\nTEST 7: _revert_strategie sur stratégie absente (no-op)")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
removed = ep._revert_strategie("Evolved NonExistent", "test")
check("retourne False (absente)", not removed)

print("\nTEST 8: evaluer REVERT une stratégie perdante (filtre par nom)")
# Setup: JSON avec la stratégie + baseline saine + post trades perdants TAGGÉS
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
# Baseline: 40 trades gagnants RSI (portefeuille sain)
base = [mk_trade(1440 - i, 0.40, 1.2, strat="RSI Mean Reversion") for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
backdate_last(minutes=25)
# Post: 12 trades "Evolved 00955" perdants + 10 trades RSI gagnants (ne doivent PAS être comptés)
post_strat = [mk_trade(20 - i, -0.15, -0.30, strat="Evolved 00955") for i in range(12)]
post_rsi = [mk_trade(18 - i, 0.50, 1.5, strat="RSI Mean Reversion") for i in range(10)]
json.dump({"trades_fermes": base + post_strat + post_rsi, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
actions = ep.evaluer()
recs = ep._read_ledger()
check("1 action évaluée", len(actions) == 1, str(len(actions)))
check("statut REVERT", recs[-1]["statut"] == "REVERT", recs[-1]["statut"])
check("post n=12 (filtré par strat)", recs[-1]["post"]["n"] == 12,
      str(recs[-1]["post"].get("n")))
check("post pnl négatif", recs[-1]["post"]["pnl_eur"] < 0,
      str(recs[-1]["post"]["pnl_eur"]))
# Stratégie retirée du JSON + .py
strats_after = json.load(open(ep.EVOLVED_JSON))
check("stratégie retirée du JSON", len(strats_after) == 0, str(len(strats_after)))

print("\nTEST 9: evaluer GARDE une stratégie gagnante")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
base = [mk_trade(1440 - i, 0.40, 1.2, strat="RSI Mean Reversion") for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
backdate_last(minutes=25)
# Post: 12 trades "Evolved 00955" gagnants
post_good = [mk_trade(20 - i, 0.50, 1.2, strat="Evolved 00955") for i in range(12)]
json.dump({"trades_fermes": base + post_good, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.evaluer()
recs = ep._read_ledger()
check("statut GARDE", recs[-1]["statut"] == "GARDE", recs[-1]["statut"])
check("post pnl positif", recs[-1]["post"]["pnl_eur"] > 0,
      str(recs[-1]["post"]["pnl_eur"]))
# Stratégie reste dans le JSON
strats_after = json.load(open(ep.EVOLVED_JSON))
check("stratégie reste dans JSON", len(strats_after) == 1, str(len(strats_after)))

print("\nTEST 10: evaluer EN_ATTENTE si peu de trades (< MIN_POST_STRATEGIE)")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
base = [mk_trade(20*1440 - i, 0.40, 1.2, strat="RSI Mean Reversion") for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
backdate_last(days=15, minutes=0)  # 15 jours
# Seulement 5 post trades (stratégie peu active)
post_few = [mk_trade(5*1440 - i*60, 0.50, 1.5, strat="Evolved 00955") for i in range(5)]
json.dump({"trades_fermes": base + post_few, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.evaluer()
recs = ep._read_ledger()
check("statut EN_ATTENTE", recs[-1]["statut"] == "EN_ATTENTE", recs[-1]["statut"])
# Stratégie reste (pas de revert hâtif)
strats_after = json.load(open(ep.EVOLVED_JSON))
check("stratégie reste dans JSON", len(strats_after) == 1, str(len(strats_after)))

print("\nTEST 11: force_revert type-aware (stratégie)")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
base = [mk_trade(1440 - i, 0.40, 1.2) for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
ep.force_revert("Evolved 00955")
recs = ep._read_ledger()
check("statut REVERT (force)", recs[-1]["statut"] == "REVERT", recs[-1]["statut"])
strats_after = json.load(open(ep.EVOLVED_JSON))
check("stratégie retirée du JSON (force_revert)", len(strats_after) == 0,
      str(len(strats_after)))

print("\nTEST 12: force_garde type-aware (stratégie)")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
base = [mk_trade(1440 - i, 0.40, 1.2) for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
ep.force_garde("Evolved 00955")
recs = ep._read_ledger()
check("statut GARDE (force)", recs[-1]["statut"] == "GARDE", recs[-1]["statut"])

print("\nTEST 13: evaluer mixte plugin + stratégie (coexistence)")
mk_evolved_json("Evolved 00955", "strat_evolved_00955")
ep._regen_evolved_module(json.load(open(ep.EVOLVED_JSON)))
ep._write_ledger([])
base = [mk_trade(1440 - i, 0.40, 1.2, strat="RSI") for i in range(40)]
json.dump({"trades_fermes": base, "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
# Plugin EN_EVALUATION
open(os.path.join(ep.PLUGINS_DIR, "meta_plugin.py"), "w").write("# plugin")
ep.enregistrer_application("meta_plugin.py", "plugin test")
backdate_last(minutes=25)
# Stratégie EN_EVALUATION
ep.enregistrer_strategie("Evolved 00955", oos_avg=2.5, win_rate=0.60, trades_count=8)
# Backdate les deux
recs = ep._read_ledger()
for r in recs:
    r["apply_time"] = (datetime.utcnow() - timedelta(minutes=25)).isoformat(timespec="seconds")
ep._write_ledger(recs)
# Post: plugin trades (tous) perdants + stratégie trades gagnants
post_all_bad = [mk_trade(20 - i, -0.50, -1.5, strat="RSI") for i in range(18)]
post_strat_good = [mk_trade(18 - i, 0.50, 1.2, strat="Evolved 00955") for i in range(12)]
json.dump({"trades_fermes": base + post_all_bad + post_strat_good,
           "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep.evaluer()
recs = ep._read_ledger()
plugin_rec = [r for r in recs if r.get("type") != "strategie"]
strat_rec = [r for r in recs if r.get("type") == "strategie"]
check("plugin REVERT (tous trades perdants)",
      len(plugin_rec) > 0 and plugin_rec[-1]["statut"] == "REVERT",
      plugin_rec[-1]["statut"] if plugin_rec else "no plugin rec")
check("stratégie GARDE (ses trades gagnants)",
      len(strat_rec) > 0 and strat_rec[-1]["statut"] == "GARDE",
      strat_rec[-1]["statut"] if strat_rec else "no strat rec")
check("stratégie post n=12 (filtré)", strat_rec[-1]["post"]["n"] == 12,
      str(strat_rec[-1]["post"]["n"]))

print("\nTEST 14: rapport() affiche stratégies sans crash")
try:
    ep.rapport()
    check("rapport() OK avec stratégies", True)
except Exception as e:
    check("rapport() OK avec stratégies", False, str(e))

print("\nTEST 15: enregistrer_strategie sur fichier trades vide (safe)")
ep._write_ledger([])
json.dump({"trades_fermes": [], "capital_initial": 1000,
           "liquidites": 1000, "positions": []}, open(ep.PT_FILE, "w"))
ok = ep.enregistrer_strategie("Evolved 00001", oos_avg=1.0, win_rate=0.55, trades_count=5)
recs = ep._read_ledger()
check("retourne True (safe sur empty)", ok)
check("baseline n=0", recs[-1]["baseline"]["n"] == 0, str(recs[-1]["baseline"]["n"]))

shutil.rmtree(TMP)
print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
