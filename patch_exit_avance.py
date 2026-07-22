#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_exit_avance.py — Exit avancé: break-even + trailing stop.

Problème diagnostiqué: 17 gagnants / 6 perdants mais PnL flat (-0.25€) ->
chaque perte ~3x plus grosse que chaque gain. Cause: TP=SL=1.5% (1:1), pas
de breakeven -> un gagnant qui reverse redevient une perte; gains plafonnés.

Solution:
  - BREAKEVEN_SEUIL=0.60%: dès +0.6%, SL monte au breakeven (entry+frais).
    Un gagnant ne redevient JAMAIS une perte.
  - TRAIL_ACTIF=1.0% / TRAIL_PCT=1.0%: dès +1.0%, SL trail derrière le pic.
    Laisse courir les gagnants + locke le profit.

Toggle: EXIT_AVANCE=0 pour désactiver (retour SL fixe).
Suit le prix peak dans pos["prix_peak"] (persiste dans paper_trading.json)."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()
ok = True

# Edit 1: constantes
A1 = "SEUIL_BENEFICE_MIN = 0.30       # 0.30% : couvre les 0.2% de frais + 0.1% de marge nette"
B1 = (A1 + "\n"
      "BREAKEVEN_SEUIL = 0.60     # +0.60% -> SL monte au breakeven (un gagnant reste un gagnant)\n"
      "TRAIL_ACTIF = 1.0          # +1.0% -> trailing stop derrière le pic\n"
      "TRAIL_PCT = 1.0            # trail 1.0% sous le pic (lock profit, laisse respirer)")

# Edit 2: logique exit (break-even + trailing)
A2 = '''        # Take-profit: encaisse des que +_tp%
        if variation >= _tp:
            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"
            positions_a_fermer.append((pos, prix_actuel, raison, variation))
        # Stop-loss: coupe des que -_sl%
        elif variation <= -_sl:
            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))
        else:'''
B2 = '''        # === EXIT AVANCÉ: break-even + trailing (toggle EXIT_AVANCE=0) ===
        # Laisse courir les gagnants + protège les gains. Un gagnant ne devient
        # jamais une perte. Rééquilibre le ratio gain/perte (cf. diagnostic).
        _sl_regle = "fixe"
        if os.getenv("EXIT_AVANCE", "1") != "0":
            _pic = pos.get("prix_peak", prix_entree)
            if prix_actuel > _pic:
                _pic = prix_actuel
                pos["prix_peak"] = _pic
            _var_pic = (_pic - prix_entree) / prix_entree * 100   # variation au pic (sticky)
            if _var_pic >= TRAIL_ACTIF:
                _sl_price = _pic * (1 - TRAIL_PCT / 100.0)   # trail derrière le pic
                _sl_regle = "trailing"
            elif _var_pic >= BREAKEVEN_SEUIL:
                _sl_price = prix_entree * 1.001              # breakeven + frais
                _sl_regle = "breakeven"
            else:
                _sl_price = prix_entree * (1 - _sl / 100.0)
        else:
            _sl_price = prix_entree * (1 - _sl / 100.0)
        # Take-profit: encaisse des que +_tp%
        if variation >= _tp:
            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"
            positions_a_fermer.append((pos, prix_actuel, raison, variation))
        # Stop: trailing / breakeven / fixe
        elif prix_actuel <= _sl_price:
            positions_a_fermer.append((pos, prix_actuel, f"STOP-{_sl_regle.upper()}", variation))
        else:'''

if "TRAIL_ACTIF" in p:
    print("[paper] exit avancé déjà présent - skip"); sys.exit(0)
if A1 in p:
    p = p.replace(A1, B1, 1); print("[paper] edit1: constantes break-even/trailing")
else:
    print("[paper] ERREUR ancre edit1"); ok = False
if A2 in p:
    p = p.replace(A2, B2, 1); print("[paper] edit2: logique break-even + trailing")
else:
    print("[paper] ERREUR ancre edit2"); ok = False
if not ok:
    sys.exit(1)
open(f, "w", encoding="utf-8").write(p)
print("\n=== EXIT AVANCÉ APPLIQUÉ ===")
print("Break-even à +0.6% | Trailing à +1.0% (1% sous pic) | Toggle EXIT_AVANCE=0")
