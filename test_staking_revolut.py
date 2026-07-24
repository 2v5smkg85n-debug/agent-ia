#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_staking_revolut.py — Tests du moniteur staking Revolut (lecture seule)."""
import os, sys, json, tempfile
sys.path.insert(0, "/tmp/agent-ia-inspect")
import staking_revolut_monitor as srm

# ledger temporaire + mute telegram (compteur)
srm.LEDGER = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
_NOTIF = {"n": 0, "msgs": []}
def _fake_notify(msg): _NOTIF["n"] += 1; _NOTIF["msgs"].append(msg)
srm._notify = _fake_notify

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

class FakeClient:
    def __init__(self, balances, tickers=None):
        self._balances = balances
        self._tickers = tickers or {"data": [{"symbol": "ETH/EUR", "last_price": "2000"},
                                          {"symbol": "SOL/EUR", "last_price": "150"}]}
    def get_balances(self): return self._balances
    def get_ticker(self, symbol=None): return self._tickers

BAL_AUCUN = [{"currency": "EUR", "available": "50.00", "total": "50.00"},
             {"currency": "BTC", "available": "0.001", "total": "0.001"}]
BAL_ETH = [{"currency": "ETH", "available": "10", "reserved": "0", "staked": "32", "total": "42"},
           {"currency": "EUR", "available": "50.00", "total": "50.00"}]

print("=" * 60)
print("STAKING REVOLUT MONITOR — Feature 4 (adapté)")

print("\nTEST 1: _parse_balances normalise (list / dict balances / dict values)")
check("list -> list", isinstance(srm._parse_balances(BAL_ETH), list) and len(srm._parse_balances(BAL_ETH)) == 2)
check("dict balances -> list", len(srm._parse_balances({"balances": BAL_ETH})) == 2)
check("dict values -> list", len(srm._parse_balances({"ETH": {"a": 1}, "BTC": {"a": 2}})) == 2)

print("\nTEST 2: lire_staking — extrait staked>0 + EUR libre")
c = FakeClient(BAL_ETH)
stk, eur = srm.lire_staking(c)
check("ETH staké détecté", "ETH" in stk and abs(stk["ETH"]["staked"] - 32.0) < 1e-9, str(stk))
check("BTC ignoré (pas staké)", "BTC" not in stk, str(stk))
check("EUR libre=50", abs(eur - 50.0) < 1e-9, str(eur))

print("\nTEST 3: lire_staking sans staking → staking vide, EUR libre OK")
c = FakeClient(BAL_AUCUN)
stk, eur = srm.lire_staking(c)
check("staking vide", stk == {}, str(stk))
check("EUR libre=50", abs(eur - 50.0) < 1e-9, str(eur))

print("\nTEST 4: changements — nouveau stake (pas de precedent)")
snap = {"staking": {"ETH": {"staked": 32, "available": 10, "reserved": 0, "total": 42}}, "eur_libre": 50}
chg = srm.changements(snap, None)
check("1 changement nouveau_stake", len(chg) == 1 and chg[0][0] == "nouveau_stake", str(chg))

print("\nTEST 5: changements — récompense (staked up, available stable)")
prec = {"staking": {"ETH": {"staked": 32, "available": 10, "reserved": 0, "total": 42}}, "eur_libre": 50}
actu = {"staking": {"ETH": {"staked": 32.5, "available": 10, "reserved": 0, "total": 42.5}}, "eur_libre": 50}
chg = srm.changements(actu, prec)
check("recompense détectée", len(chg) == 1 and chg[0][0] == "recompense", str(chg))

print("\nTEST 6: changements — stake manuel (staked up, available down ~ montant)")
prec = {"staking": {"ETH": {"staked": 32, "available": 10, "reserved": 0, "total": 42}}, "eur_libre": 50}
actu = {"staking": {"ETH": {"staked": 42, "available": 0, "reserved": 0, "total": 42}}, "eur_libre": 40}
chg = srm.changements(actu, prec)
check("stake_manuel détecté", len(chg) == 1 and chg[0][0] == "stake_manuel", str(chg))

print("\nTEST 7: changements — unstake (staked down)")
prec = {"staking": {"ETH": {"staked": 32, "available": 10, "reserved": 0, "total": 42}}, "eur_libre": 50}
actu = {"staking": {"ETH": {"staked": 20, "available": 22, "reserved": 0, "total": 42}}, "eur_libre": 50}
chg = srm.changements(actu, prec)
check("unstake détecté", len(chg) == 1 and chg[0][0] == "unstake", str(chg))

print("\nTEST 8: changements — fin de staking (actif disparu)")
prec = {"staking": {"ETH": {"staked": 32, "available": 10, "reserved": 0, "total": 42}}, "eur_libre": 50}
actu = {"staking": {}, "eur_libre": 50}
chg = srm.changements(actu, prec)
check("fin_staking détecté", len(chg) == 1 and chg[0][0] == "fin_staking", str(chg))

print("\nTEST 9: changements — aucun (staked identique)")
chg = srm.changements(prec, prec)
check("0 changement", len(chg) == 0, str(chg))

print("\nTEST 10: snapshot écrit dans le ledger")
c = FakeClient(BAL_ETH)
snap = srm.snapshot(c)
check("snapshot a ts", "ts" in snap, str(snap))
check("snapshot a staking", "ETH" in snap["staking"], str(snap))
lines = open(srm.LEDGER).read().strip().split("\n")
check("ledger a 1 ligne", len(lines) == 1, str(len(lines)))

print("\nTEST 11: _dernier_snapshot_excluding — retourne le précédent différent")
c = FakeClient(BAL_ETH)
s1 = srm.snapshot(c)
import time; time.sleep(0.01)
s2 = srm.snapshot(c)  # même balances, ts différent
prec = srm._dernier_snapshot_excluding(s2)
check("retourne s1 (différent de s2)", prec is not None and "ts" in prec, str(prec))

print("\nTEST 12: cycle sans changement → 0 alerte")
_NOTIF["n"] = 0
c = FakeClient(BAL_ETH)
srm.snapshot(c)  # snapshot initial
_NOTIF["n"] = 0
chg = srm.cycle(client=c)
check("0 changement (stable)", len(chg) == 0, str(chg))
check("pas d'alerte Telegram", _NOTIF["n"] == 0, str(_NOTIF["n"]))

print("\nTEST 13: cycle avec récompense → 1 alerte Telegram")
# reset ledger propre
open(srm.LEDGER, "w").close()
c = FakeClient(BAL_ETH)
srm.snapshot(c)  # staked=32
_NOTIF["n"] = 0
c2 = FakeClient([{"currency": "ETH", "available": "10", "staked": "32.7", "total": "42.7"},
                 {"currency": "EUR", "available": "50", "total": "50"}])
chg = srm.cycle(client=c2)
check("1 changement recompense", len(chg) == 1 and chg[0][0] == "recompense", str(chg))
check("alerte Telegram envoyée", _NOTIF["n"] == 1, str(_NOTIF["n"]))

print("\nTEST 14: client None → cycle retourne [] (pas de crash)")
srm._client = lambda: None
chg = srm.cycle(client=None)
check("retourne [] sans crash", chg == [], str(chg))

print("\nTEST 15: conseil — EUR oisif >= seuil → suggestion + alerte")
_NOTIF["n"] = 0
c = FakeClient(BAL_AUCUN)  # 50 EUR oisif, pas de staking
srm.conseil(client=c)
check("alerte conseil envoyée (50>=20)", _NOTIF["n"] == 1, str(_NOTIF["n"]))

print("\nTEST 16: conseil — EUR oisif < seuil → pas d'alerte")
_NOTIF["n"] = 0
c = FakeClient([{"currency": "EUR", "available": "5", "total": "5"}])
srm.conseil(client=c)
check("pas d'alerte (5<20)", _NOTIF["n"] == 0, str(_NOTIF["n"]))

print("\nTEST 17: rapport — valeur EUR estimée du staking (paire EUR)")
c = FakeClient(BAL_ETH)  # tickers defaut: ETH/EUR=2000
stk = srm.rapport(client=c)
check("ETH présent dans rapport", "ETH" in stk, str(stk))

print("\nTEST 18: _val_eur — fallback USD si pas de paire EUR")
pmap = {"ETH": {"USD": 2160.0}}  # 2160 USD / 1.08 = 2000 EUR
c = FakeClient(BAL_ETH)
val = srm._val_eur(c, "ETH", 1.0, pmap=pmap)
check("val EUR = 2160/1.08 = 2000", abs(val - 2000.0) < 1e-6, str(val))

print("\nTEST 19: _val_eur — actif absent de la map → 0")
val = srm._val_eur(c, "XYZ", 100.0, pmap=pmap)
check("val = 0 (actif inconnu)", val == 0.0, str(val))

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
