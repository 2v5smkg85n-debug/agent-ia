#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_meta_profit.py — rend le méta-évolveur ORIENTÉ PROFIT.

L'agent se code déjà tout seul (plugins via LLM + 3 gates + auto-apply).
Cette amélioration lui donne un DIAGNOSTIC DE RENTABILITÉ: où exactement le
système gagne/perd de l'argent (P&L par raison de sortie + par stratégie),
et la plus grosse fuite identifiée comme CIBLE PRIORITAIRE. Le prompt lui
demande alors de coder un plugin qui réduit CONCRÈTEMENT cette fuite.

=> Auto-codage orienté profit: l'agent cible ses améliorations sur les vraies pertes.

Idempotent: skip si _diagnostic_profit déjà présent.
"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meta_evolver.py")
src = open(P).read()
edits = 0

# --- Edit 1: fonction _diagnostic_profit + appel dans _etat_systeme ---
if "def _diagnostic_profit" not in src:
    bloc = (
        '    infos.append(_diagnostic_profit())\n'
        '    return "\\n".join(infos)\n\n\n'
        'def _diagnostic_profit(trades=None):\n'
        '    """Diagnostic de rentabilité: où le système gagne/perd de l\'argent.\n'
        '    P&L par raison de sortie + par stratégie + plus grosse fuite (cible prioritaire).\n'
        '    L\'objectif: orienter l\'auto-codage du méta-évolveur vers les VRAIES pertes."""\n'
        '    try:\n'
        '        if trades is None:\n'
        '            pt = json.load(open(os.path.join(DOSSIER, "paper_trading.json")))\n'
        '            trades = pt.get("trades_fermes", [])\n'
        '        if not trades:\n'
        '            return "(pas encore de trades fermés — diagnostic non disponible)"\n'
        '        from collections import defaultdict\n'
        '        par_raison = defaultdict(lambda: [0, 0.0])\n'
        '        par_strat = defaultdict(lambda: [0, 0.0])\n'
        '        for t in trades:\n'
        '            r = (t.get("raison") or "?").split(" (")[0]\n'
        '            g = t.get("gain_eur", 0) or 0\n'
        '            par_raison[r][0] += 1; par_raison[r][1] += g\n'
        '            s = t.get("strategie") or t.get("source") or "?"; s = s.replace("_PARTIAL", "")\n'
        '            par_strat[s][0] += 1; par_strat[s][1] += g\n'
        '        lignes = ["DIAGNOSTIC RENTABILITÉ (où l\'argent est gagné/perdu):"]\n'
        '        lignes.append("  Par raison de sortie (trié du pire au meilleur):")\n'
        '        for r, (n, p) in sorted(par_raison.items(), key=lambda x: x[1][1]):\n'
        '            lignes.append(f"    {r:20s}: {n:2d} trades, {p:+.2f}EUR (avg {p/n:+.3f})")\n'
        '        lignes.append("  Par stratégie (3 pires + 3 meilleures):")\n'
        '        strats = sorted(par_strat.items(), key=lambda x: x[1][1])\n'
        '        for s, (n, p) in strats[:3] + strats[-3:]:\n'
        '            lignes.append(f"    {s[:24]:24s}: {n:2d}t, {p:+.2f}EUR")\n'
        '        pires = sorted(par_raison.items(), key=lambda x: x[1][1])\n'
        '        if pires and pires[0][1][1] < 0:\n'
        '            lignes.append(f"  >>> CIBLE PRIORITAIRE (plus grosse fuite): {pires[0][0]} "\n'
        '                          f"= {pires[0][1][1]:+.2f}EUR sur {pires[0][1][0]} trades -> "\n'
        '                          f"code un plugin qui réduit CETTE fuite en priorité")\n'
        '        return "\\n".join(lignes)\n'
        '    except FileNotFoundError:\n'
        '        return "(paper_trading.json absent — diagnostic non disponible)"\n'
        '    except Exception as e:\n'
        '        return f"(diagnostic indispo: {e})"\n\n\n'
    )
    ancien = '    return "\\n".join(infos)\n\n\n# ============================================\n# PROMPT'
    if ancien in src:
        src = src.replace(ancien, bloc + "# ============================================\n# PROMPT")
        edits += 1
        print("[meta] edit1: fonction _diagnostic_profit() + injection dans _etat_systeme")
    else:
        print("[meta] edit1: ANCRE INTROUVABLE (vérifier _etat_systeme return)")

# --- Edit 2: prompt orienté profit (cibler la plus grosse fuite) ---
ancien_obj = 'OBJECTIF: propose UNE amélioration qui augmente la rentabilité ou la robustesse. Idées: filtre anti-bear (veto en régime de crash), score de conviction multi-signal qui ajuste la taille, veto quand la corrélation BTC/ETH explose, réduction de taille en volatilité extrême, veto après N pertes sur un actif, etc. Le module sera AUTO-APPLIQUÉ dans plugins/ s\'il passe les 3 gates. Évite de dupliquer les propositions récentes.'
nouveau_obj = 'OBJECTIF: AUGMENTE LES BÉNÉFICES en ciblant CONCRÈTEMENT la CIBLE PRIORITAIRE du diagnostic ci-dessus (la plus grosse fuite de P&L). Si STOP-LOSS est la fuite principale, code un filtre qui réduit les entrées risquées (veto en forte volatilité, après N pertes consécutives sur un actif, en régime de crash, corrélation BTC/ETH explosive, etc.). Si une stratégie perd, code un veto ou sizing réduit pour cette stratégie. Si les sorties par temps sont trop petites, code un sizing plus gros sur les bons setups. CIBLE LA FUITE RÉELLE, ne propose pas du générique. Le module sera AUTO-APPLIQUÉ dans plugins/ s\'il passe les 3 gates (puis auto-rollback par plugin_sante si il nuit). Évite de dupliquer les propositions récentes.'
if ancien_obj in src and "AUGMENTE LES BÉNÉFICES" not in src:
    src = src.replace(ancien_obj, nouveau_obj)
    edits += 1
    print("[meta] edit2: prompt orienté profit (cible la plus grosse fuite)")

open(P, "w").write(src)
print(f"\n=== META-ÉVOLVEUR ORIENTÉ PROFIT ===  ({edits} edits)")
print("L'agent reçoit maintenant le diagnostic de rentabilité + cible la plus grosse fuite de P&L")
