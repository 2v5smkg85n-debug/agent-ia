#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""live_confluence.py - test live du filtre confluence contre la vraie API Binance."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filtre_confluence_htf as fc
for sym, tf in [("BTCUSDT", "1h"), ("ETHUSDT", "4h"), ("SOLUSDT", "15m"), ("ARBUSDT", "1h")]:
    t = fc._trend_htf(sym, "crypto", tf)
    print(sym, "base", tf, "-> trend HTF =", t)
