#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_niveau_profit.py — paliers progressifs de conviction liés à la performance.

À chaque palier de +5% de PnL réalisé (5%, 10%, 15%...), les multiplicateurs de
conviction gagnent +0.5. L'agent parie donc de plus en plus gros AU FUR ET À MESURE
qu'il prouve sa rentabilité — mais seulement sur les stratégies déjà prouvées
(base > 1.0). Auto-protectif: si le PnL redescend sous un palier, le bonus saute.

  PnL 0-5%:   base (élite x2.5, éprouvé x2.0, solide x1.5)
  PnL 5-10%:  +0.5 (élite x3.0, éprouvé x2.5, solide x2.0)
  PnL 10-15%: +1.0 (élite x3.5, éprouvé x3.0, solide x2.5)
  PnL 15-20%: +1.5 ...

Idempotent: skip si _niveau_performance déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: fonction _niveau_performance (avant _conviction_mult) ---
if "def _niveau_performance" not in src:
    func = (
        'def _niveau_performance(pf):\n'
        '    """Niveau de confiance global basé sur la performance RÉALISÉE du portefeuille.\n'
        '    Chaque palier de +5% de PnL ajoute +0.5 aux multiplicateurs de conviction.\n'
        '    Auto-protectif: si le PnL redescend sous un palier, le bonus est retiré."""\n'
        '    try:\n'
        '        cap = pf.get("capital_initial", 1000)\n'
        '        liq = pf.get("liquidites", 0)\n'
        '        pos = pf.get("positions", [])\n'
        '        val = liq + sum(p.get("quantite", 0) * p.get("prix_actuel", p.get("prix_entree", 0)) for p in pos)\n'
        '        pnl_pct = (val / cap - 1) * 100 if cap else 0\n'
        '        niveau = max(0, int(round(pnl_pct, 4) // 5))   # 0-4.99%->0, 5-9.99%->1, 10-14.99%->2...\n'
        '        bonus = niveau * 0.5\n'
        '        return niveau, bonus, pnl_pct\n'
        '    except Exception:\n'
        '        return 0, 0.0, 0.0\n\n\n'
    )
    src = src.replace("def _conviction_mult(signal, cs):", func + "def _conviction_mult(signal, cs):")
    edits += 1
    print("[paper] edit1: fonction _niveau_performance()")

# --- Edit 2: appliquer le bonus de palier dans le bloc CONVICTION ---
ancien = (
    '            _cs = json.load(open("classement_strategies.json"))\n'
    '            _mult, _craison = _conviction_mult(signal, _cs)\n'
    '            if _mult != 1.0:\n'
    '                _avant = montant\n'
    '                montant = montant * _mult\n'
    '                print(f"  [CONVICTION] {signal.get(\'nom\', signal[\'symbole\'])}: x{_mult:.2f} {_craison} ({_avant:.0f}->{montant:.0f}EUR)")'
)
nouveau = (
    '            _cs = json.load(open("classement_strategies.json"))\n'
    '            _mult, _craison = _conviction_mult(signal, _cs)\n'
    '            # PALIER PROGRESSIF: +0.5 par palier de +5% de PnL (auto-protectif, seulement sur gagnants prouvés)\n'
    '            _niv, _bonus, _pnl_pct = _niveau_performance(pf)\n'
    '            if _mult > 1.0 and _bonus > 0:\n'
    '                _mult = _mult + _bonus\n'
    '                _craison += f" +palier{_niv}(PnL {_pnl_pct:+.1f}%)"\n'
    '            if _mult != 1.0:\n'
    '                _avant = montant\n'
    '                montant = montant * _mult\n'
    '                print(f"  [CONVICTION] {signal.get(\'nom\', signal[\'symbole\'])}: x{_mult:.2f} {_craison} ({_avant:.0f}->{montant:.0f}EUR)")'
)
if ancien in src and "PALIER PROGRESSIF" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] edit2: application palier progressif dans le bloc CONVICTION")

open(P, "w").write(src)
print(f"\n=== PALIERS PROGRESSIFS APPLIQUÉS ===  ({edits} edits)")
print("+0.5 au conviction par palier de +5% de PnL (auto-protectif, gagnants prouvés uniquement)")
