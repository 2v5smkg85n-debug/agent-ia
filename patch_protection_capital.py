#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_protection_capital.py — Intègre le circuit breaker au début de
ouvrir_position. Avant tout sizing, vérifie si le trading doit être suspendu
(drawdown >= 12% ou 5 pertes consecutives). Toggle: PROTECTION_CAPITAL=0."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()

ANCHOR = '''def ouvrir_position(pf, signal, prix_actuel):
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False
    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire'''

NEW = '''def ouvrir_position(pf, signal, prix_actuel):
    if len(pf["positions"]) >= MAX_POSITIONS:
        return False
    # CIRCUIT BREAKER (protection capital): suspend les entrées en cas de drawdown
    # profond (>=12%) ou de pertes consecutives (>=5). Leçon #1: "survis aux bears".
    # Toggle: PROTECTION_CAPITAL=0 pour désactiver (en paper par défaut actif).
    if os.getenv("PROTECTION_CAPITAL", "1") != "0":
        try:
            from protection_capital import verifier_pause
            _pause, _raison = verifier_pause(pf)
            if _pause:
                print(f"  [CIRCUIT BREAKER] entrées suspendues — {_raison}")
                return False
        except ImportError:
            pass  # module absent -> pas de protection (paper)
        except Exception:
            pass
    # SIZING DYNAMIQUE (Phase 2): remplace le 20% fixe par Kelly fractionnaire'''

if "from protection_capital import verifier_pause" in p:
    print("[paper] circuit breaker déjà intégré - skip")
elif ANCHOR in p:
    p = p.replace(ANCHOR, NEW, 1)
    print("[paper] circuit breaker intégré au début de ouvrir_position")
else:
    print("[paper] ERREUR ancre ouvrir_position introuvable"); sys.exit(1)

open(f, "w", encoding="utf-8").write(p)
print("\n=== PATCH PROTECTION CAPITAL APPLIQUE ===")
print("Circuit breaker: drawdown>=12% ou 5 pertes consecutives -> pause entrées")
print("Toggle: PROTECTION_CAPITAL=0 | Auto-resume quand drawdown<6% et 0 pertes consec")
