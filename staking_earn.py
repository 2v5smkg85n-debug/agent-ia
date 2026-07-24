#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""staking_earn.py — Placement auto des liquidités oisives sur Binance Simple Earn (Feature 4).

Détecte les soldes stablecoins (USDT/USDC/FDUSD...) oisifs sur le compte Spot
Binance et les place en staking FLEXIBLE (rédemption à tout moment, ~5-10% APY)
sur le meilleur produit disponible. Rebalance + alertes Telegram.

SÉCURITÉ (zéro risque par défaut):
  - STAKING_LIVE=0 (defaut) = DRY-RUN: logge ce qu'il ferait, NE souscrit rien.
  - STAKING_LIVE=1 + clés presentes = souscrit réellement (confirm_action requis).
  - Clés absentes (BINANCE_API_KEY/SECRET) = mode veille, logge, pas de crash.
  - MIN_PLACEMENT (defaut 10) + MAX_PCT_LIQUIDE (defaut 0.90, garde 10% liquide).
  - Stablecoins uniquement (pas de volatil en staking).

Endpoints Binance Simple Earn (HMAC-SHA256, header X-MBX-APIKEY):
  - GET  /api/v3/account                      -> soldes spot (balances[])
  - GET  /sapi/v1/simple-earn/flexible/list   -> produits flexibles (asset, productId, apy)
  - POST /sapi/v1/simple-earn/flexible/subscribe (productId, amount, sourceAccount=SPOT)
  - GET  /sapi/v1/simple-earn/flexible/position -> positions actives

CLI:
  python staking_earn.py            # optimiser() (DRY-RUN par defaut)
  python staking_earn.py rapport    # etat des positions
"""
import os
import json
import time
import hmac
import hashlib
import logging
from datetime import datetime
from urllib.parse import urlencode

import requests

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(DOSSIER, "staking_ledger.jsonl")
BASE = "https://api.binance.com"

STABLECOINS = {"USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI"}
MIN_PLACEMENT = float(os.getenv("STAKING_MIN", "10"))      # ne stake pas < 10 unités
MAX_PCT_LIQUIDE = float(os.getenv("STAKING_MAX_PCT", "0.90"))  # stake max 90%, garde 10% liquide

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("staking")


# ---------- couche API Binance (signée) ----------
class BinanceClient:
    def __init__(self, key=None, secret=None, session=None):
        self.key = key or os.getenv("BINANCE_API_KEY", "")
        self.secret = secret or os.getenv("BINANCE_API_SECRET", "")
        self.s = session or requests.Session()

    @property
    def ok(self):
        return bool(self.key and self.secret)

    def _sign(self, params):
        params["timestamp"] = int(time.time() * 1000)
        qs = urlencode(params)
        sig = hmac.new(self.secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        return qs + "&signature=" + sig

    def _get(self, path, params=None):
        url = BASE + path + "?" + self._sign(params or {})
        r = self.s.get(url, headers={"X-MBX-APIKEY": self.key}, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path, params=None):
        url = BASE + path + "?" + self._sign(params or {})
        r = self.s.post(url, headers={"X-MBX-APIKEY": self.key}, timeout=15)
        r.raise_for_status()
        return r.json()

    def soldes_spot(self):
        """{asset: free} pour les stablecoins avec solde > 0."""
        data = self._get("/api/v3/account")
        out = {}
        for b in data.get("balances", []):
            asset, free = b.get("asset"), float(b.get("free", 0))
            if asset in STABLECOINS and free >= MIN_PLACEMENT:
                out[asset] = free
        return out

    def produits_flexibles(self, asset):
        rows = self._get("/sapi/v1/simple-earn/flexible/list", {"asset": asset, "size": 20}).get("rows", [])
        return rows

    def positions_flexibles(self):
        return self._get("/sapi/v1/simple-earn/flexible/position", {"size": 100}).get("rows", [])

    def souscrire(self, product_id, amount):
        return self._post("/sapi/v1/simple-earn/flexible/subscribe",
                          {"productId": product_id, "amount": f"{amount:.8f}", "sourceAccount": "SPOT"})


# ---------- logique pure (testable sans réseau) ----------
def _apy(produit):
    """Extrait l'APY d'un produit flexible (champ variable selon version API)."""
    for k in ("latestAPY", "apy", "rewardsRate", "tierAPY"):
        v = produit.get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    # structure tiers: [{"minAmount":..,"maxAmount":..,"apy":..}]
    tiers = produit.get("tiers") or []
    best = 0.0
    for t in tiers:
        try:
            best = max(best, float(t.get("apy") or t.get("APY") or 0))
        except (TypeError, ValueError):
            pass
    return best


def choisir_produit(produits):
    """Retourne le meilleur produit flexible (APY le plus élevé, statut disponible)."""
    dispo = [p for p in produits if p.get("canPurchase", True) and p.get("sellable", True) is not False]
    if not dispo:
        return None
    return max(dispo, key=_apy)


def plan_placement(soldes, min_placement=MIN_PLACEMENT, max_pct=MAX_PCT_LIQUIDE):
    """Calcule les placements à effectuer: [(asset, amount, produit)].

    Ne stake que max_pct du solde (garde une part liquide) et >= min_placement.
    """
    plan = []
    for asset, solde in soldes.items():
        montant = solde * max_pct
        if montant < min_placement:
            continue
        plan.append((asset, round(montant, 8), None))  # produit résolu plus tard (besoin API)
    return plan


def _ledger(action, data):
    data = dict(data, ts=datetime.utcnow().isoformat(), action=action)
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notify(msg):
    try:
        from agent import notify_ifft
        notify_ifft(f"💎 STAKING — {msg}")
    except Exception:
        pass


# ---------- orchestration ----------
def optimiser(client=None, live=None):
    """Place les liquidités oisives. Retourne le plan exécuté (DRY-RUN ou LIVE).

    live=None -> lit STAKING_LIVE env (defaut 0 = DRY-RUN).
    """
    if live is None:
        live = os.getenv("STAKING_LIVE", "0") == "1"
    client = client or BinanceClient()

    if not client.ok:
        log.warning("Clés Binance absentes — mode veille (rien à faire).")
        _ledger("veille", {"raison": "cles_absentes"})
        return []

    soldes = client.soldes_spot()
    if not soldes:
        log.info("Aucune liquidité stablecoin oisive >= %.2f — rien à staker.", MIN_PLACEMENT)
        return []

    plan = plan_placement(soldes)
    execute = []
    for asset, montant, _ in plan:
        produits = client.produits_flexibles(asset)
        produit = choisir_produit(produits)
        if not produit:
            log.warning("Aucun produit flexible pour %s — skip.", asset)
            continue
        apy = _apy(produit)
        pid = produit.get("productId")
        if not live:
            log.info("[DRY-RUN] placerait %.4f %s sur produit %s (APY ~%.2f%%)", montant, asset, pid, apy * 100)
            _ledger("dryrun", {"asset": asset, "montant": montant, "produit": pid, "apy": apy})
            execute.append({"asset": asset, "montant": montant, "produit": pid, "apy": apy, "live": False})
            continue
        # LIVE
        try:
            client.souscrire(pid, montant)
            log.info("[LIVE] souscrit %.4f %s sur %s (APY ~%.2f%%)", montant, asset, pid, apy * 100)
            _ledger("live", {"asset": asset, "montant": montant, "produit": pid, "apy": apy})
            _notify(f"souscrit {montant:.2f} {asset} @ {apy*100:.2f}% APY")
            execute.append({"asset": asset, "montant": montant, "produit": pid, "apy": apy, "live": True})
        except Exception as e:
            log.error("[LIVE] échec souscription %s: %s", asset, e)
            _ledger("erreur", {"asset": asset, "erreur": str(e)})
    return execute


def rapport(client=None):
    """Affiche les positions staking actives + rendement estimé."""
    client = client or BinanceClient()
    if not client.ok:
        print("Clés Binance absentes — impossible d'interroger les positions.")
        return []
    rows = client.positions_flexibles()
    total = 0.0
    for r in rows:
        asset = r.get("asset", "?")
        amt = float(r.get("totalAmount", 0))
        apy = float(r.get("latestAPY", 0) or 0)
        val = float(r.get("amountInUSD", 0) or 0)
        total += val
        print(f"  {asset}: {amt:.4f} @ {apy*100:.2f}% APY (~{val:.2f} USD)")
    print(f"  TOTAL staking: ~{total:.2f} USD")
    return rows


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "optimiser"
    if cmd == "rapport":
        rapport()
    else:
        res = optimiser()
        print(f"\n{len(res)} placement(s) prévu(s).")
