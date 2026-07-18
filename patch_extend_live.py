#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_extend_live.py — Implemente EXTEND_TP dans paper_trading.py (live).

EXTEND_TP (valide backtest +13.35% sur crypto): quand une position crypto atteint
+0.5% de gain, on monte le TP de 2.0% a 4.0% pour laisser courir les gagnants.
SL fixe (pas de breakeven). Forex/or/matieres: TP fixe (non valide, resultats mitiges).

Subtilite: le live ferme par TEMPS a 90 min. Sans ajustement, une crypto a +0.5%
apres 90 min fermerait avant d'atteindre 4.0%. Donc on etend aussi le cap duree a 8h
(EXTEND_DUREE_MAX) pour les positions extended, et le seuil mini a +0.5%.
"""
import os

D = os.getcwd()
PT = os.path.join(D, "paper_trading.py")
src = open(PT, encoding="utf-8").read()

# 1) Constantes EXTEND apres STOP_LOSS_PCT
old_cst = "STOP_LOSS_PCT = 1.5             # -1.5% -> coupe la perte"
new_cst = old_cst + """
# EXTEND_TP (backtest +13.35% sur crypto): monte le TP quand la position crypto
# est en profit, pour laisser courir les gagnants. SL fixe (pas de breakeven).
# Idee utilisateur + valide par backtest elargi (9 marches, 30 trades, plateau a tp_ext=4).
EXTEND_CRYPTOS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
EXTEND_SEUIL = 0.5        # active l'extension a partir de +0.5% de gain
EXTEND_TP_PCT = 4.0       # TP monte (2.0% -> 4.0%) une fois en profit
EXTEND_DUREE_MAX = 480    # cap duree des positions extended (8h, vs 90min normal)"""
assert old_cst in src, "ancrage constante STOP_LOSS_PCT introuvable"
src = src.replace(old_cst, new_cst, 1)

# 2) Logique EXTEND dans verifier_sorties
old_log = """        # Take-profit: encaisse des que +_tp%
        if variation >= _tp:
            positions_a_fermer.append((pos, prix_actuel, "TAKE-PROFIT", variation))
        # Stop-loss: coupe des que -_sl%
        elif variation <= -_sl:
            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))
        else:
            # Sortie par duree: UNIQUEMENT si la position est en gain SUFFISANT.
            # Anti-churn : on ne ferme pas a +0.05% car les frais (0.2% AR) =>
            # perte nette. On attend gain >= SEUIL_BENEFICE_MIN (0.30%).
            # Si en perte, on garde (elle attend TP/SL) -> evite de fermer a perte.
            try:
                dt_ouv = datetime.strptime(pos.get("date_ouverture", ""), "%Y-%m-%d %H:%M")
                age_min = (maintenant - dt_ouv).total_seconds() / 60
                if age_min >= SORTIE_DUREE_MIN and variation >= SEUIL_BENEFICE_MIN:
                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))
            except Exception:
                pass"""

new_log = """        # EXTEND_TP (valide backtest +13.35% crypto): si position crypto en profit
        # >= +0.5%, on monte le TP a 4.0% pour laisser courir les gagnants.
        # SL fixe (pas de breakeven). Forex/or/matieres: TP fixe (non valide).
        extend_actif = sym in EXTEND_CRYPTOS and variation >= EXTEND_SEUIL
        if extend_actif:
            _tp = EXTEND_TP_PCT
        # Take-profit: encaisse des que +_tp%
        if variation >= _tp:
            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"
            positions_a_fermer.append((pos, prix_actuel, raison, variation))
        # Stop-loss: coupe des que -_sl%
        elif variation <= -_sl:
            positions_a_fermer.append((pos, prix_actuel, "STOP-LOSS", variation))
        else:
            # Sortie par duree: UNIQUEMENT si la position est en gain SUFFISANT.
            # Anti-churn : on ne ferme pas a +0.05% car les frais (0.2% AR) =>
            # perte nette. On attend gain >= SEUIL_BENEFICE_MIN (0.30%).
            # Si en perte, on garde (elle attend TP/SL) -> evite de fermer a perte.
            try:
                dt_ouv = datetime.strptime(pos.get("date_ouverture", ""), "%Y-%m-%d %H:%M")
                age_min = (maintenant - dt_ouv).total_seconds() / 60
                # EXTEND: cap duree plus long (8h) pour laisser le TP etendu se realiser
                duree_min = EXTEND_DUREE_MAX if extend_actif else SORTIE_DUREE_MIN
                seuil_min = EXTEND_SEUIL if extend_actif else SEUIL_BENEFICE_MIN
                if age_min >= duree_min and variation >= seuil_min:
                    positions_a_fermer.append((pos, prix_actuel, f"TEMPS+benefice ({variation:+.2f}%)", variation))
            except Exception:
                pass"""
assert old_log in src, "ancrage logique verifier_sorties introuvable"
src = src.replace(old_log, new_log, 1)

open(PT, "w", encoding="utf-8").write(src)
import py_compile
py_compile.compile(PT, doraise=True)
print("✅ paper_trading.py: EXTEND_TP implemente (crypto TP 2.0%->4.0% a +0.5% profit, SL fixe, cap 8h)")
print("✅ compile OK")
print("   - EXTEND_CRYPTOS =", {"BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT"})
print("   - EXTEND_SEUIL=0.5%, EXTEND_TP_PCT=4.0%, EXTEND_DUREE_MAX=480min")
print("   - raison fermeture: 'TAKE-PROFIT-EXTEND' (distinct de 'TAKE-PROFIT' pour suivi)")
