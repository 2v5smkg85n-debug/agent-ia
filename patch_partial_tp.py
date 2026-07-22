#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_partial_tp.py — Partial take-profit (encaisse 50% à +1%, garde le reste).

Améliore l'exit avancé: au lieu de tout fermer au TP/SL, on encaisse une fraction
du gain dès que le trade atteint PARTIAL_TP_SEUIL. Le reste de la position continue
à courir protégé par le trailing stop -> capture les gros mouvements sans risque.

Toggle: PARTIAL_TP=0 pour désactiver.
Idempotent: skip si PARTIAL_TP_SEUIL déjà présent.
"""
import re, os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trading.py")
src = open(P).read()
edits = 0

# --- Edit 1: constantes ---
if "PARTIAL_TP_SEUIL" not in src:
    src = src.replace(
        "TRAIL_PCT = 1.0            # trail 1.0% sous le pic (lock profit, laisse respirer)",
        "TRAIL_PCT = 1.0            # trail 1.0% sous le pic (lock profit, laisse respirer)\n"
        "PARTIAL_TP_SEUIL = 1.0     # +1.0% -> encaisse une fraction du gain, garde le reste\n"
        "PARTIAL_FRACTION = 0.5      # fraction clôturée au partial TP (50% lock, 50% runner)",
    )
    edits += 1
    print("[paper] edit1: constantes partial TP")

# --- Edit 2: fonction fermer_position_partielle (avant fermer_position) ---
if "def fermer_position_partielle" not in src:
    func = (
        'def fermer_position_partielle(pf, position, prix_actuel, fraction, raison, variation):\n'
        '    """Clôture une FRACTION de la position (partial take-profit).\n'
        '    Réalise le gain sur la partie vendue, réduit quantité + cost-basis,\n'
        '    garde la position OUVERTE (le reste ride le trailing stop)."""\n'
        '    if fraction <= 0 or fraction >= 1.0:\n'
        '        return\n'
        '    quantite_vendue = position["quantite"] * fraction\n'
        '    if quantite_vendue <= 0:\n'
        '        return\n'
        '    montant_recu = quantite_vendue * prix_actuel\n'
        '    frais = montant_recu * FRAIS_TRANSACTION\n'
        '    pf["liquidites"] += montant_recu - frais\n'
        '    pf["total_frais"] += frais\n'
        '    cout_partie = position["montant_eur"] * fraction   # cost-basis de la partie vendue\n'
        '    gain = (montant_recu - frais) - cout_partie\n'
        '    # réduit la position (le reste reste ouvert)\n'
        '    position["quantite"] -= quantite_vendue\n'
        '    position["montant_eur"] -= cout_partie\n'
        '    position["partiellement_clote"] = True\n'
        '    trade = {\n'
        '        "symbole": position["symbole"],\n'
        '        "nom": position.get("nom", position["symbole"]),\n'
        '        "marche": position.get("marche", "?"),\n'
        '        "prix_entree": position["prix_entree"],\n'
        '        "prix_sortie": prix_actuel,\n'
        '        "quantite": quantite_vendue,\n'
        '        "montant_eur": cout_partie,\n'
        '        "gain_eur": gain,\n'
        '        "variation_pct": variation,\n'
        '        "raison": raison,\n'
        '        "signal_raison": position.get("signal_raison", ""),\n'
        '        "strategie": position.get("strategie", position.get("source", "")),\n'
        '        "source": position.get("source", "") + "_PARTIAL",\n'
        '        "frais_total": position["frais_entree"] * fraction + frais,\n'
        '        "date_ouverture": position["date_ouverture"],\n'
        '        "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M"),\n'
        '    }\n'
        '    pf["trades_fermes"].append(trade)\n'
        '    print(f"  [PARTIAL-TP] {position[\'symbole\']}: {fraction*100:.0f}% @ {variation:+.2f}% (gain {gain:+.2f}€) | reste {position[\'quantite\']:.6f} en position")\n\n\n'
    )
    src = src.replace("def fermer_position(pf, position, prix_actuel, raison, variation):", func + "def fermer_position(pf, position, prix_actuel, raison, variation):")
    edits += 1
    print("[paper] edit2: fermer_position_partielle()")

# --- Edit 3: check partial TP dans la boucle d'exit (entre TP et Stop) ---
ancien = (
    '        # Take-profit: encaisse des que +_tp%\n'
    '        if variation >= _tp:\n'
    '            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"\n'
    '            positions_a_fermer.append((pos, prix_actuel, raison, variation))\n'
    '        # Stop: trailing / breakeven / fixe\n'
    '        elif prix_actuel <= _sl_price:\n'
    '            positions_a_fermer.append((pos, prix_actuel, f"STOP-{_sl_regle.upper()}", variation))'
)
nouveau = (
    '        # Take-profit: encaisse des que +_tp% (tout fermer)\n'
    '        if variation >= _tp:\n'
    '            raison = "TAKE-PROFIT-EXTEND" if extend_actif else "TAKE-PROFIT"\n'
    '            positions_a_fermer.append((pos, prix_actuel, raison, variation))\n'
    '        # Partial TP: lock PARTIAL_FRACTION du gain à +1.0% (UNE fois),\n'
    '        # le reste reste ouvert et ride le trailing stop (capture les gros moves)\n'
    '        elif (os.getenv("PARTIAL_TP", "1") != "0" and variation >= PARTIAL_TP_SEUIL\n'
    '              and not pos.get("partiellement_clote") and variation < _tp):\n'
    '            try:\n'
    '                fermer_position_partielle(pf, pos, prix_actuel, PARTIAL_FRACTION, "PARTIAL-TP", variation)\n'
    '            except Exception as _e:\n'
    '                print(f"  [PARTIAL-TP erreur: {_e}]")\n'
    '        # Stop: trailing / breakeven / fixe\n'
    '        elif prix_actuel <= _sl_price:\n'
    '            positions_a_fermer.append((pos, prix_actuel, f"STOP-{_sl_regle.upper()}", variation))'
)
if ancien in src and "PARTIAL-TP" not in src:
    src = src.replace(ancien, nouveau)
    edits += 1
    print("[paper] edit3: check partial TP dans boucle exit")

open(P, "w").write(src)
print(f"\n=== PARTIAL TP APPLIQUÉ ===  ({edits} edits)")
print(f"Partial TP à +{1.0}% | Fraction lock: 50% | Reste ride le trailing | Toggle PARTIAL_TP=0")
