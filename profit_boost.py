#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit_boost.py - active les leviers profit (1,2,4) dans paper_trading.py.

Lever 1 (laisser courir les gagnants, protege par breakeven):
  DUREE_PETIT_GAIN 120->180, DUREE_GAIN_PROGRESS 180->240, DUREE_GAGNANT_MAX 240->360
  PARTIAL_TP_SEUIL 1.0->0.8 (protege le gagnant plus tot, laisse le reste rider)
Lever 2 (booster conviction):
  elite 2.5->3.0, eprouve 2.0->2.5, solide 1.5->1.75
Lever 4 (monter TP):
  TAKE_PROFIT_PCT 1.5->2.0 (EXTEND crypto reste a 4.0%)

Idempotent: skip si deja applique (marqueur PROFIT_BOOST).
"""
import os, re

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

def sub(old, new, label):
    global src, edits
    if old in src:
        src = src.replace(old, new, 1)
        edits += 1
        print(f"[paper] {label}")
        return True
    print(f"[paper] SKIP (ancre introuvable): {label}")
    return False

# === Lever 4: TP ===
sub("TAKE_PROFIT_PCT = 1.5", "TAKE_PROFIT_PCT = 2.0", "TAKE_PROFIT_PCT 1.5->2.0")

# === Lever 1: durées gagnants + partial TP ===
sub("DUREE_PETIT_GAIN = 120", "DUREE_PETIT_GAIN = 180", "DUREE_PETIT_GAIN 120->180")
sub("DUREE_GAIN_PROGRESS = 180", "DUREE_GAIN_PROGRESS = 240", "DUREE_GAIN_PROGRESS 180->240")
sub("DUREE_GAGNANT_MAX = 240", "DUREE_GAGNANT_MAX = 360", "DUREE_GAGNANT_MAX 240->360")
sub("PARTIAL_TP_SEUIL = 1.0", "PARTIAL_TP_SEUIL = 0.8", "PARTIAL_TP_SEUIL 1.0->0.8")

# === Lever 2: conviction multipliers ===
sub('return 2.5, f"élite', 'return 3.0, f"élite', "conviction élite 2.5->3.0")
sub('return 2.0, f"éprouvé', 'return 2.5, f"éprouvé', "conviction éprouvé 2.0->2.5")
sub('return 1.5, f"solide', 'return 1.75, f"solide', "conviction solide 1.5->1.75")

# marqueur idempotence
if "PROFIT_BOOST_V1" not in src:
    src = src.replace("TAKE_PROFIT_PCT = 2.0", "TAKE_PROFIT_PCT = 2.0  # PROFIT_BOOST_V1", 1)

open(P, "w").write(src)
print(f"\n=== PROFIT BOOST APPLIQUÉ ===  ({edits} edits)")
