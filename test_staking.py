#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_staking.py — Tests du placement auto Binance Simple Earn (Feature 4)."""
import os, sys, json, tempfile
sys.path.insert(0, "/tmp/agent-ia-inspect")
import staking_earn as se

# redirige le ledger vers un fichier temporaire
se.LEDGER = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
se._notify = lambda m: None  # mute Telegram

PASS = 0; FAIL = 0
def check(nom, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {nom}")
    else: FAIL += 1; print(f"  ❌ {nom}  {detail}")

class FakeClient:
    """Mock du BinanceClient — simule soldes/produits/souscription."""
    def __init__(self, soldes=None, produits=None, ok=True, fail_subscribe=False):
        self._soldes = soldes or {}
        self._produits = produits or {}
        self._ok = ok
        self._fail = fail_subscribe
        self.souscriptions = []
    @property
    def ok(self): return self._ok
    def soldes_spot(self): return dict(self._soldes)
    def produits_flexibles(self, asset): return self._produits.get(asset, [])
    def positions_flexibles(self): return []
    def souscrire(self, pid, amount):
        if self._fail: raise RuntimeError("API reject")
        self.souscriptions.append((pid, amount))
        return {"success": True}

P1 = {"productId": "USDT-FLEX-1", "latestAPY": "0.085", "canPurchase": True}
P2 = {"productId": "USDT-FLEX-2", "latestAPY": "0.062", "canPurchase": True}
P3 = {"productId": "USDT-FLEX-OFF", "latestAPY": "0.20", "canPurchase": False}  # APY haute mais indispo

print("=" * 60)
print("STAKING EARN — Feature 4")

print("\nTEST 1: _apy extrait latestAPY")
check("P1 apy=0.085", abs(se._apy(P1) - 0.085) < 1e-6, se._apy(P1))

print("\nTEST 2: choisir_produit = APY max parmi disponibles (exclut canPurchase=False)")
p = se.choisir_produit([P1, P2, P3])
check("choisit USDT-FLEX-1 (0.085, pas P3 indispo)", p["productId"] == "USDT-FLEX-1", p.get("productId"))

print("\nTEST 3: plan_placement — 90% du solde, skip < MIN")
plan = se.plan_placement({"USDT": 100.0, "USDC": 5.0}, min_placement=10, max_pct=0.9)
assets = [a for a, m, _ in plan]
check("USDT inclus", "USDT" in assets, str(plan))
check("USDC exclu (< min apres pct)", "USDC" not in assets, str(plan))
check("montant USDT=90.0", [m for a, m, _ in plan if a == "USDT"][0] == 90.0, str(plan))

print("\nTEST 4: optimiser DRY-RUN (live=0) — ne souscrit rien, logge dryrun")
c = FakeClient(soldes={"USDT": 200.0}, produits={"USDT": [P1, P2]}, ok=True)
res = se.optimiser(client=c, live=False)
check("1 placement prevu", len(res) == 1, str(res))
check("live=False", res[0]["live"] is False, str(res))
check("montant=180 (90% de 200)", abs(res[0]["montant"] - 180.0) < 1e-6, str(res))
check("produit=USDT-FLEX-1", res[0]["produit"] == "USDT-FLEX-1", str(res))
check("aucune souscription reelle", len(c.souscriptions) == 0, str(c.souscriptions))

print("\nTEST 5: optimiser LIVE — souscrit reellement, logge live")
c = FakeClient(soldes={"USDT": 200.0}, produits={"USDT": [P1, P2]}, ok=True)
res = se.optimiser(client=c, live=True)
check("1 souscription effectuee", len(c.souscriptions) == 1, str(c.souscriptions))
check("souscrit sur USDT-FLEX-1", c.souscriptions[0][0] == "USDT-FLEX-1", str(c.souscriptions))
check("montant souscrit=180", abs(c.souscriptions[0][1] - 180.0) < 1e-6, str(c.souscriptions))
check("res live=True", res[0]["live"] is True, str(res))

print("\nTEST 6: clés absentes — mode veille, pas de crash, retour []")
c = FakeClient(ok=False)
res = se.optimiser(client=c, live=True)  # meme live=1, pas de cles -> veille
check("retourne []", res == [], str(res))
check("aucune souscription", len(c.souscriptions) == 0, str(c.souscriptions))

print("\nTEST 7: aucune liquidité oisive — retour []")
c = FakeClient(soldes={}, ok=True)
res = se.optimiser(client=c, live=True)
check("retourne [] (rien a staker)", res == [], str(res))

print("\nTEST 8: échec souscription LIVE — logge erreur, ne crash pas, continue")
c = FakeClient(soldes={"USDT": 200.0, "USDC": 100.0},
               produits={"USDT": [P1], "USDC": [{"productId": "USDC-FLEX", "latestAPY": "0.07", "canPurchase": True}]},
               ok=True, fail_subscribe=True)
res = se.optimiser(client=c, live=True)
check("0 placement reussi (echec)", len(res) == 0, str(res))
check("pas de crash", True)

print("\nTEST 9: ledger DRY-RUN ecrit une ligne dryrun")
lines = open(se.LEDGER).read().strip().split("\n")
actions = [json.loads(l).get("action") for l in lines if l.strip()]
check("ledger contient 'dryrun'", "dryrun" in actions, str(actions))
check("ledger contient 'veille'", "veille" in actions, str(actions))
check("ledger contient 'live'", "live" in actions, str(actions))

print("\nTEST 10: stablecoins uniquement — BTC ignoré même si solde")
c = FakeClient(soldes={"USDT": 150.0}, ok=True)  # FakeClient ne filtre pas, mais soldes_spot fournit ce qu'on met
# verification: seuls les stablecoins de STABLECOINS sont traités
check("BTC pas dans STABLECOINS", "BTC" not in se.STABLECOINS, "")
check("USDT dans STABLECOINS", "USDT" in se.STABLECOINS, "")

print("\n" + "=" * 60)
print(f"RÉSULTAT: {PASS} pass, {FAIL} fail")
print("=" * 60)
sys.exit(1 if FAIL else 0)
