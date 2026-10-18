#!/usr/bin/env python3
"""
ws_kraken.py — flux de prix temps reel Kraken (WebSocket v2, canal ticker) -> prix_ws.json.

Pourquoi : le bot interroge KuCoin/CoinGecko en HTTP toutes les 3-10 s pour verifier ses stops ; entre deux appels
le prix peut traverser le stop (les "SL-RETARD" du bilan). Un WebSocket pousse chaque changement de prix en < 1 s,
sans quota HTTP. prix_revolut.get_prix_kucoin_batch lit prix_ws.json en priorite s'il a moins de 15 s.

Service optionnel (setup_infra.sh le cree) : ws_kraken.service. Si le flux tombe, le bot retombe tout seul sur HTTP.
Dependance : pip install websockets   (deja dans la plupart des venv ; sinon le script le dit et s'arrete).
Doc : https://docs.kraken.com/api/docs/websocket-v2/ticker
"""
import asyncio
import json
import os
import time
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(DOSSIER, "prix_ws.json")
URL = "wss://ws.kraken.com/v2"
_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}
_ALIAS_INV = {v: k for k, v in _ALIAS.items()}


def symboles_du_bot():
    try:
        import donnees_1m
        return donnees_1m.symboles_du_bot()
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _paire_ws(sym):
    base = sym.upper().replace("USDT", "").replace("EUR", "")
    return f"{base}/EUR"


def _sym_bot(paire):
    base = paire.split("/")[0]
    return f"{_ALIAS_INV.get(base, base)}USDT"


async def boucle(symboles):
    try:
        import websockets
    except ImportError:
        print("Module 'websockets' absent : /home/ubuntu/agent-ia/venv/bin/pip install websockets")
        return
    prix, derniere_ecriture = {}, 0.0
    paires = [_paire_ws(s) for s in symboles]
    while True:
        try:
            async with websockets.connect(URL, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "ticker", "symbol": paires}}))
                print(f"{datetime.now():%H:%M:%S} connecte, {len(paires)} paires demandees")
                async for msg in ws:
                    m = json.loads(msg)
                    if m.get("method") == "subscribe" and not m.get("success", True):
                        continue                                     # paire inconnue sur Kraken : ignoree
                    if m.get("channel") != "ticker":
                        continue
                    for t in m.get("data", []):
                        try:
                            prix[_sym_bot(t["symbol"])] = {"last": float(t["last"]), "bid": float(t["bid"]), "ask": float(t["ask"]), "ts": time.time()}
                        except Exception:
                            continue
                    if time.time() - derniere_ecriture >= 1.0:
                        _ecrire(prix)
                        derniere_ecriture = time.time()
        except Exception as e:
            print(f"{datetime.now():%H:%M:%S} deconnecte ({str(e)[:80]}), reconnexion dans 5 s")
            await asyncio.sleep(5)


def _ecrire(prix):
    now = time.time()
    frais = {s: v["last"] for s, v in prix.items() if now - v["ts"] < 120}
    tmp = SORTIE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"maj": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "n": len(frais), "prix": frais,
                   "spread_pct": {s: round((v["ask"] - v["bid"]) / v["last"] * 100, 4) for s, v in prix.items() if v["last"]}}, f)
    os.replace(tmp, SORTIE)


if __name__ == "__main__":
    syms = symboles_du_bot()
    print(f"Flux Kraken WebSocket v2 -> {SORTIE} ({len(syms)} symboles)")
    asyncio.run(boucle(syms))
