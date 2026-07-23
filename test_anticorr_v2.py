#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_anticorr_v2.py - valide la garde ANTI-CORR resserree."""
import os, sys, io
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import paper_trading
importlib.reload(paper_trading)

paper_trading.notify_ifft = lambda *a, **k: None

def _pf(): return {"capital_initial":1000.0,"liquidites":1000.0,"positions":[],"historique":[],"total_frais":0.0,"dernier_tick":""}
def _sig(sym, strat="Bollinger Breakout"): return {"symbole":sym,"nom":sym,"marche":"crypto","action":"ACHAT","strategie":strat}
def _pos(sym, age_min, strat="Bollinger Breakout"):
    dt=(datetime.now()-timedelta(minutes=age_min)).strftime("%Y-%m-%d %H:%M")
    return {"symbole":sym,"nom":sym,"strategie":strat,"date_ouverture":dt,"prix_entree":1.0,"montant_eur":50.0,"quantite":50.0,"frais_entree":0.05,"frais_total":0.1,"prix_peak":1.0}

def run(pf, sig):
    buf=io.StringIO(); old=sys.stdout; sys.stdout=buf
    try: r=paper_trading.ouvrir_position(pf, sig, 1.0)
    except Exception as e: r=f"EXC:{type(e).__name__}"
    finally: sys.stdout=old
    return r, buf.getvalue()

os.environ["ANTI_CORR"]="1"
ok=True

# Cas1: meme strat, ARB 10min -> bloque (120min)
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",10))
r,out=run(pf,_sig("ARBUSDT"))
print(f"Cas1 (meme strat, 10min): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" in out

# Cas2: meme strat, ARB 70min -> bloque (70<=120)
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",70))
r,out=run(pf,_sig("ARBUSDT"))
print(f"Cas2 (meme strat, 70min): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" in out

# Cas3: meme strat, ARB 130min -> autorise (>120)
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",130))
r,out=run(pf,_sig("ARBUSDT"))
print(f"Cas3 (meme strat, 130min): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out

# Cas4: strat differente, ARB 70min -> autorise (>60)
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",70,"Evolved 00955"))
r,out=run(pf,_sig("ARBUSDT","RSI Mean Reversion"))
print(f"Cas4 (strat diff, 70min): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out

# Cas5: strat differente, ARB 40min -> bloque (<=60)
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",40,"Evolved 00955"))
r,out=run(pf,_sig("ARBUSDT","RSI Mean Reversion"))
print(f"Cas5 (strat diff, 40min): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" in out

# Cas6: BTC avec ARB ouvert 10min -> autorise
pf=_pf(); pf["positions"].append(_pos("ARBUSDT",10))
r,out=run(pf,_sig("BTCUSDT"))
print(f"Cas6 (BTC, ARB ouvert): bloque={'[ANTI-CORR]' in out}")
assert "[ANTI-CORR]" not in out

print("\n=== TESTS ANTI-CORR v2 PASSÉS ===")
