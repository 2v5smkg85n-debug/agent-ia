#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test evolutia_profit.py — valide le ledger avant/après + revert."""
import os
import sys
import json
import shutil
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evolutia_profit as ep

# --- mock dirs ---
TMP = tempfile.mkdtemp(prefix="evolutia_test_")
ep.DOSSIER = TMP
ep.PT_FILE = os.path.join(TMP, "paper_trading.json")
ep.LEDGER_FILE = os.path.join(TMP, "evolutia_ledger.jsonl")
ep.PLUGINS_DIR = os.path.join(TMP, "plugins")
ep.DISABLED_DIR = os.path.join(TMP, "plugins_disabled")
os.makedirs(ep.PLUGINS_DIR)
ep.TELEGRAM_TOKEN = ""  # pas de notif
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

def backdate_last(days=0, minutes=25):
    recs = ep._read_ledger()
    recs[-1]["apply_time"] = (datetime.utcnow() - timedelta(days=days, minutes=minutes)).isoformat(timespec="seconds")
    ep._write_ledger(recs)

def mk_trade(min_ago, var_pct, gain_eur, strat="S1"):
    dt = datetime.utcnow() - timedelta(minutes=min_ago)
    return {"date_fermeture": dt.strftime("%Y-%m-%d %H:%M"),
            "variation_pct": var_pct, "gain_eur": gain_eur,
            "strategie": strat, "raison": "TAKE-PROFIT", "nom": "BTC", "marche": "crypto"}

print("=" * 60)
print("TEST 1: enregistrer_application snapshot baseline")
# 40 trades gagnants (baseline saine, avg +0.40%)
trades = [mk_trade(1440 - i, 0.40, 1.2) for i in range(40)]
json.dump({"trades_fermes": trades, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep._write_ledger([])
ok = ep.enregistrer_application("meta_test_plugin.py", "plugin test")
backdate_last(minutes=25)  # plugin appliqué il y a 25min
recs = ep._read_ledger()
check("enregistrer retourne True", ok)
check("1 record dans ledger", len(recs) == 1, str(len(recs)))
check("statut EN_EVALUATION", recs[0]["statut"] == "EN_EVALUATION", recs[0]["statut"])
check("baseline n=40", recs[0]["baseline"]["n"] == 40, str(recs[0]["baseline"]["n"]))
check("baseline avg_gain +0.40%", abs(recs[0]["baseline"]["avg_gain_pct"] - 0.40) < 0.01,
      str(recs[0]["baseline"]["avg_gain_pct"]))

print("\nTEST 2: evaluer GARDE (post meilleur que baseline)")
# plugin file présent
open(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py"), "w").write("# plugin")
# add 20 post trades gagnants +0.60% (meilleur que baseline +0.40)
post_trades = [mk_trade(20 - i, 0.60, 1.8) for i in range(20)]
all_trades = trades + post_trades
json.dump({"trades_fermes": all_trades, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
actions = ep.evaluer()
recs = ep._read_ledger()
check("statut GARDE", recs[0]["statut"] == "GARDE", recs[0]["statut"])
check("plugin reste dans plugins/", os.path.isfile(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py")))
check("post n>=15", recs[0]["post"]["n"] >= 15, str(recs[0]["post"]["n"]))

print("\nTEST 3: evaluer REVERT (post régresse nettement)")
# reset ledger, re-apply, puis post trades perdants -0.30% (<< baseline +0.40 - 0.30 = +0.10)
ep._write_ledger([])
open(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py"), "w").write("# plugin")
ep.enregistrer_application("meta_test_plugin.py", "plugin test")
backdate_last(minutes=25)
# baseline = 40 trades +0.40%; post = 18 trades à -0.30% (régression nette)
post_bad = [mk_trade(20 - i, -0.30, -0.9) for i in range(18)]
json.dump({"trades_fermes": trades + post_bad, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep.evaluer()
recs = ep._read_ledger()
check("statut REVERT", recs[-1]["statut"] == "REVERT", recs[-1]["statut"])
check("plugin déplacé vers plugins_disabled/",
      os.path.isfile(os.path.join(ep.DISABLED_DIR, "meta_test_plugin.py")))
check("plugin absent de plugins/",
      not os.path.isfile(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py")))

print("\nTEST 4: data insuffisante -> reste EN_EVALUATION, puis EN_ATTENTE")
ep._write_ledger([])
open(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py"), "w").write("# plugin")
# baseline = 40 trades il y a 20 jours (AVANT apply)
base_old = [mk_trade(20*1440 - i, 0.40, 1.2) for i in range(40)]
json.dump({"trades_fermes": base_old, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep.enregistrer_application("meta_test_plugin.py", "plugin test")
backdate_last(days=15, minutes=0)  # apply il y a 15 jours
# seulement 5 post trades il y a 5 jours (dans la fenêtre, après apply)
post_few = [mk_trade(5*1440 - i*60, 0.50, 1.5) for i in range(5)]
json.dump({"trades_fermes": base_old + post_few, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep.evaluer()
recs = ep._read_ledger()
check("statut EN_ATTENTE (15j, <15 trades post)", recs[-1]["statut"] == "EN_ATTENTE", recs[-1]["statut"])
check("plugin reste dans plugins/ (pas de revert hâtif)",
      os.path.isfile(os.path.join(ep.PLUGINS_DIR, "meta_test_plugin.py")))

print("\nTEST 5: rapport() ne crash pas")
try:
    ep.rapport()
    check("rapport() OK", True)
except Exception as e:
    check("rapport() OK", False, str(e))

print("\nTEST 6: 2 plugins — fenêtre attribuée correctement (pas de chevauchement)")
ep._write_ledger([])
open(os.path.join(ep.PLUGINS_DIR, "p_a.py"), "w").write("# a")
open(os.path.join(ep.PLUGINS_DIR, "p_b.py"), "w").write("# b")
ep.enregistrer_application("p_a.py", "plugin A")
backdate_last(minutes=25)
# 16 trades après A (régression)
post_a = [mk_trade(20 - i, -0.30, -0.9) for i in range(16)]
json.dump({"trades_fermes": trades + post_a, "capital_initial": 1000, "liquidites": 1000, "positions": []},
          open(ep.PT_FILE, "w"))
ep.evaluer()  # devrait REVERT A
ep.enregistrer_application("p_b.py", "plugin B")
recs = ep._read_ledger()
check("A reverté", recs[0]["statut"] == "REVERT", recs[0]["statut"])
check("B en évaluation (récent)", recs[1]["statut"] == "EN_EVALUATION", recs[1]["statut"])

shutil.rmtree(TMP)
print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
