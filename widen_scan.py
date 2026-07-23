#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""widen_scan.py - elargit le scan (lever 3): ajoute des actifs crypto.

Ajoute 6 actifs liquides a MARCHES_PAPER + EXTEND_CRYPTOS pour plus
d'opportunites. Les nouveaux actifs seront backtestes par backtest_engine
(quotidien) puis genereront des strategies -> l'edge gate laissera passer
les trades uniquement sur edge prouve.

Nouveaux: DOGEUSDT, AVAXUSDT, LINKUSDT, OPUSDT, INJUSDT, NEARUSDT.
Idempotent: skip si DOGEUSDT deja present.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

NOUVEAUX = [
    ('DOGEUSDT', 'Dogecoin'),
    ('AVAXUSDT', 'Avalanche'),
    ('LINKUSDT', 'Chainlink'),
    ('OPUSDT', 'Optimism'),
    ('INJUSDT', 'Injective'),
    ('NEARUSDT', 'NEAR Protocol'),
]

# --- Edit 1: ajoute les entrees MARCHES_PAPER apres ARBUSDT ---
ancien_arb = '    "ARBUSDT": {"nom": "Arbitrum", "marche": "crypto", "source": "binance"},'
if "DOGEUSDT" not in src:
    lignes = []
    for sym, nom in NOUVEAUX:
        lignes.append(f'    "{sym}": {{"nom": "{nom}", "marche": "crypto", "source": "binance"}},')
    insert = ancien_arb + "\n" + "\n".join(lignes)
    src = src.replace(ancien_arb, insert, 1)
    edits += 1
    print(f"[paper] edit1: {len(NOUVEAUX)} actifs ajoutes a MARCHES_PAPER")

# --- Edit 2: ajoute les symbols a EXTEND_CRYPTOS ---
ancien_ext = 'EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LDOUSDT", "AAVEUSDT", "UNIUSDT", "PENDLEUSDT", "ARBUSDT"}'
if "DOGEUSDT" in src and "DOGEUSDT" not in ancien_ext:
    nouveaux_syms = ", ".join(f'"{s}"' for s, _ in NOUVEAUX)
    nouveau_ext = ancien_ext[:-1] + ", " + nouveaux_syms + "}"
    src = src.replace(ancien_ext, nouveau_ext, 1)
    edits += 1
    print(f"[paper] edit2: {len(NOUVEAUX)} symbols ajoutes a EXTEND_CRYPTOS")

open(P, "w").write(src)
print(f"\n=== WIDEN SCAN APPLIQUÉ ===  ({edits} edits)")
print(f"Nouveaux actifs: {', '.join(s for s,_ in NOUVEAUX)}")
