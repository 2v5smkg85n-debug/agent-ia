#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PATCH OBSERVABILITE (Phase 5). Idempotent. Backup automatique.

1. paper_trading.py: pic_capital calcule sur le capital TOTAL (liquidites + positions)
   au lieu de liquidites seules (etait faux: pic explosait a chaque fermeture).
2. performance.py: remplace le graphique equity casse (lisait pf['historique'] qui
   contient les trades, pas le capital) par la section observabilite complete
   (vraie courbe d'equity + metriques de risque + breakdown par strategie/marche).

Equity snapshots: assures par cron (observabilite.py snapshot) - non invasif.
"""
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def patch_fichier(fichier, ancien, nouveau, marqueur):
    chemin = os.path.join(DOSSIER, fichier)
    if not os.path.exists(chemin):
        print(f"ERREUR: {fichier} introuvable")
        return False
    with open(chemin, "r", encoding="utf-8") as f:
        src = f.read()
    if marqueur in src:
        print(f"  {fichier}: deja patche")
        return True
    if ancien not in src:
        print(f"  {fichier}: ancrage introuvable - fichier modifie?")
        return False
    bak = chemin + ".bak_obs"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(src)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(src.replace(ancien, nouveau, 1))
    print(f"  {fichier}: patch applique (backup {os.path.basename(bak)})")
    return True


def main():
    print("=" * 60)
    print("PATCH OBSERVABILITE (Phase 5)")
    print("=" * 60)

    # 1. paper_trading.py — pic_capital sur capital total
    print("\n1. paper_trading.py — pic_capital sur capital total")
    ancien1 = '    pf["pic_capital"] = max(pf.get("pic_capital", pf.get("capital_initial", 1000.0)), pf["liquidites"])'
    nouveau1 = (
        '    _cap_total = pf["liquidites"] + sum(p.get("montant_eur", 0) for p in pf.get("positions", []))\n'
        '    pf["pic_capital"] = max(pf.get("pic_capital", pf.get("capital_initial", 1000.0)), _cap_total)'
    )
    patch_fichier("paper_trading.py", ancien1, nouveau1, "_cap_total = pf[\"liquidites\"]")

    # 2. performance.py — section observabilite
    print("\n2. performance.py — section observabilite sur /perf")
    ancien2 = '''    # chart
    chart = ""
    if live["hist"]:
        chart = f"<h3>Évolution du capital (live)</h3>{render_chart(live['hist'])}"'''
    nouveau2 = '''    # chart + metriques + breakdown (observabilite Phase 5)
    try:
        import observabilite
        chart = observabilite.render_section_obs(live["trades"], token)
    except Exception as e:
        chart = f"<p class='muted'>Observabilite indispo: {e}</p>"
        chart = ""  # fallback silencieux'''
    # marqueur unique
    patch_fichier("performance.py", ancien2, nouveau2, "observabilite.render_section_obs")

    print("\n" + "=" * 60)
    print("Termine. La route /perf affiche maintenant:")
    print("  - vraie courbe d'equity (depuis equity_history.jsonl)")
    print("  - metriques de risque (Sharpe, Sortino, expectancy, streaks, max DD)")
    print("  - breakdown live par strategie et par marche")
    print("\nProchaine etape: cron snapshots + restart dashboard")
    print("  sudo systemctl restart dashboard.service")


if __name__ == "__main__":
    main()
