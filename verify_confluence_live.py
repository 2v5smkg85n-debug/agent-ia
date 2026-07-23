#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_confluence_live.py - preuve end-to-end que la porte CONFLUENCE bloque.

Appelle ouvrir_position (la vraie fonction integree) avec un signal ACHAT sur
SOLUSDT (HTF basse connue) -> doit etre bloque par [CONFLUENCE].
BLOQUE tôt (avant sizing/write) -> aucun effet sur paper_trading.json.
N'appelle PAS sauver_portefeuille -> zero mutation.
"""
import sys, os, io, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_trading as pt
pt.notify_ifft = lambda *a, **k: None  # securite: pas de notif reseau

def prix_binance(sym):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=10)
        return float(r.json()["price"])
    except Exception:
        return None

pf = pt.charger_portefeuille()
print(f"Portefeuille charge: {len(pf['positions'])} positions, {pf['liquidites']:.2f}EUR liquide")

for sym, tf in [("SOLUSDT", "15m"), ("ARBUSDT", "1h")]:
    prix = prix_binance(sym)
    if not prix:
        print(f"{sym}: prix indispo, skip")
        continue
    # trend HTF attendu basse (verifie au test live)
    import filtre_confluence_htf as fc
    trend = fc._trend_htf(sym, "crypto", tf)
    sig = {"symbole": sym, "nom": sym, "marche": "crypto", "action": "ACHAT",
           "strategie": "RSI Mean Reversion", "backtest_stats": {"intervalle": tf},
           "prix_entree": prix}
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        res = pt.ouvrir_position(pf, sig, prix)
    except Exception as e:
        res = f"EXC:{e}"
    finally:
        sys.stdout = old
    out = buf.getvalue()
    bloque = "[CONFLUENCE]" in out
    print(f"\n{sym} (base {tf}, HTF={trend}): ouvrir_position={res}")
    print(f"  bloque par CONFLUENCE: {bloque}")
    if bloque:
        for line in out.splitlines():
            if "[CONFLUENCE]" in line:
                print(f"  LOG: {line.strip()}")

# verification qu'aucune position ajoutee (doit rester identique)
pf2 = pt.charger_portefeuille()
print(f"\nPositions avant/apres: {len(pf['positions'])}/{len(pf2['positions'])} (doivent etre egales -> aucun effet de bord)")
