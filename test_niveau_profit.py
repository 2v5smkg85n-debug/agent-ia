#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_niveau_profit.py — vérifie les paliers progressifs de conviction."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from paper_trading import _niveau_performance, _conviction_mult

cs = {"BTCUSDT": {"strategies": [
    {"strategie": "RSI Mean Reversion", "live_n": 5, "live_wr": 75, "live_pnl": 1.32},  # éprouvé x2.0
    {"strategie": "Neuve", "live_n": 1, "live_wr": 100, "live_pnl": 0.10},              # neutre x1.0
]}}

def pf_at(pnl_pct, cap=1000):
    """Portefeuille simulé à un PnL% donné (100% liquide, pas de position)."""
    return {"capital_initial": cap, "liquidites": cap * (1 + pnl_pct/100), "positions": []}

print("=== paliers de performance ===")
cas = [(-5, 0, 0.0), (0, 0, 0.0), (3, 0, 0.0), (5, 1, 0.5), (8, 1, 0.5),
       (10, 2, 1.0), (14.9, 2, 1.0), (15, 3, 1.5), (25, 5, 2.5)]
ok = True
for pnl, niv_att, bonus_att in cas:
    niv, bonus, p = _niveau_performance(pf_at(pnl))
    mark = "OK" if (niv == niv_att and abs(bonus - bonus_att) < 1e-9) else "** FAIL **"
    if niv != niv_att or abs(bonus - bonus_att) >= 1e-9: ok = False
    print(f"  PnL {p:+5.1f}% -> palier {niv}, bonus +{bonus:.1f} {mark}")

print("\n=== conviction multipliée par palier (RSI éprouvé, base x2.0) ===")
for pnl in [0, 5, 10, 15, 20, 25]:
    niv, bonus, _ = _niveau_performance(pf_at(pnl))
    base, raison = _conviction_mult({"symbole":"BTCUSDT","nom":"RSI Mean Reversion"}, cs)
    total = base + (bonus if base > 1.0 else 0)
    print(f"  PnL {pnl:3d}% -> base x{base:.1f} + bonus {bonus:+.1f} = x{total:.1f}  (100€ -> {100*total:.0f}€)")

print("\n=== vérif: stratégie NEUVE (non prouvée) ne reçoit pas le bonus ===")
for pnl in [0, 10, 25]:
    niv, bonus, _ = _niveau_performance(pf_at(pnl))
    base, _ = _conviction_mult({"symbole":"BTCUSDT","nom":"Neuve"}, cs)
    total = base + (bonus if base > 1.0 else 0)
    print(f"  PnL {pnl:3d}% -> base x{base:.1f} (neuve) + bonus {bonus if base>1.0 else 0:+.1f} = x{total:.1f} (non amplifiée)")

print("\n>>> CAS CLÉ: à PnL +25%, RSI éprouvé = x4.5")
niv, bonus, _ = _niveau_performance(pf_at(25))
base, _ = _conviction_mult({"symbole":"BTCUSDT","nom":"RSI Mean Reversion"}, cs)
print(f"    palier {niv}, bonus +{bonus:.1f} -> x{base+bonus:.1f} (un trade à +1.5% sur 100€ = +{1.5*(base+bonus):.2f}€)")

# auto-protection
print("\n>>> AUTO-PROTECTION: PnL monte à +12% (palier 2) puis redescend à +3%")
niv1, b1, _ = _niveau_performance(pf_at(12))
niv2, b2, _ = _niveau_performance(pf_at(3))
print(f"    à +12%: palier {niv1}, bonus +{b1:.1f} | à +3%: palier {niv2}, bonus +{b2:.1f} (bonus retiré)")

print("\n" + ("OK - paliers progressifs validés" if ok else "** ÉCHEC **"))
