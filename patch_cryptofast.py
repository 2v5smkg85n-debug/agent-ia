#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_cryptofast.py - check crypto SL mi-boucle (15 min).

tick() complet reste a 30 min (anti-churn entrees), MAIS mi-boucle on
fetch QUE les prix des positions crypto ouvertes et appelle verifier_sorties.
SL crypto rattrape 2x plus vite (fix ETH -3.19% vs -1.5%). Idempotent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

FN = [
'def _check_crypto_sl_rapide():',
'    """Check crypto mi-boucle (15 min): rattrape les SL crypto 2x plus vite.',
'    Evite overshoot du SL sur mouvements rapides crypto (cf ETH -3.19% vs -1.5%).',
'    Ne fetch QUE les prix des positions crypto ouvertes -> pas de churn entree."""',
'    pf = charger_portefeuille()',
'    if not pf or not pf.get("positions"):',
'        return',
'    _crypto_syms = []',
'    _seen = set()',
'    for _p in pf["positions"]:',
'        _s = _p["symbole"]',
'        if _s in _seen:',
'            continue',
'        if MARCHES_PAPER.get(_s, {}).get("source") == "binance":',
'            _crypto_syms.append(_s)',
'            _seen.add(_s)',
'    if not _crypto_syms:',
'        return',
'    prix = {}',
'    for _s in _crypto_syms:',
'        _p = prix_binance(_s)',
'        if _p:',
'            prix[_s] = _p',
'    if not prix:',
'        return',
'    verifier_sorties(pf, prix)',
'    sauver_portefeuille(pf)',
'    print(f"[crypto-check] {len(prix)} actif(s) crypto verifie(s) (mi-boucle SL rapide)")',
'',
]
fn = "\n".join(FN) + "\n"

ancien_b = "def boucle():"
if "_check_crypto_sl_rapide" not in src:
    src = src.replace(ancien_b, fn + ancien_b, 1)
    edits += 1
    print("[paper] edit1: fonction _check_crypto_sl_rapide ajoutee")

ancien_sleep = (
    '        prochaine = datetime.now() + timedelta(seconds=INTERVALLE_BOUCLE)\n'
    '        print(f"\\nProchaine verification: {prochaine.strftime(\'%H:%M\')}")\n'
    '        time.sleep(INTERVALLE_BOUCLE)'
)
nouveau_sleep = (
    '        prochaine = datetime.now() + timedelta(seconds=INTERVALLE_BOUCLE)\n'
    '        print(f"\\nProchaine verification: {prochaine.strftime(\'%H:%M\')} (crypto SL check a +{INTERVALLE_BOUCLE//2//60}min)")\n'
    '        _demi = INTERVALLE_BOUCLE // 2\n'
    '        time.sleep(_demi)\n'
    '        try:\n'
    '            _check_crypto_sl_rapide()\n'
    '        except Exception as _e:\n'
    '            print(f"[crypto-check] erreur: {_e}")\n'
    '        time.sleep(_demi)'
)
if "crypto SL check" not in src and ancien_sleep in src:
    src = src.replace(ancien_sleep, nouveau_sleep, 1)
    edits += 1
    print("[paper] edit2: boucle() -> sleep demi + check crypto + sleep demi")
else:
    print("[paper] edit2: SKIP (deja patche ou ancre introuvable)")

open(P, "w").write(src)
print(f"\n=== CRYPTO-FAST APPLIQUE ===  ({edits} edits)")
