#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nouveau_depart.py — Remet le portefeuille virtuel a 1000 EUR SANS perdre la memoire.

- Les trades fermes sont deplaces dans trades_archive.json (le registre des strategies et le
  journal des erreurs lisent archive + courant : le casier a vie est conserve).
- Les positions encore ouvertes sont fermees virtuellement au prix d'entree (neutre) et archivees.
- Les etats de protection (peak de capital, circuit breaker, pauses) repartent de 1000.
- Le palier de mise de l'IA repart a 200 (de toute facon ecrase par le risque fixe 1 EUR).
- Une copie integrale de l'ancien paper_trading.json est gardee dans archives/.

Usage: python3 nouveau_depart.py            (demande confirmation)
       python3 nouveau_depart.py --oui      (sans confirmation)
"""
import json
import os
import shutil
import sys
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PT = os.path.join(DOSSIER, "paper_trading.json")
ARCHIVE = os.path.join(DOSSIER, "trades_archive.json")
CAPITAL = 1000.0


def main():
    if not os.path.exists(PT):
        print("paper_trading.json introuvable"); return 1
    pf = json.load(open(PT))
    trades = pf.get("trades_fermes", [])
    positions = pf.get("positions", [])
    net = sum(float(t.get("gain_eur", 0) or 0) for t in trades)
    print(f"Portefeuille actuel: liquidites {pf.get('liquidites', 0):.2f} EUR | {len(positions)} positions | {len(trades)} trades fermes | net {net:+.2f} EUR")
    if "--oui" not in sys.argv:
        rep = input("Nouveau depart a 1000 EUR ? L'historique est ARCHIVE (pas efface). [oui/non] ").strip().lower()
        if rep not in ("oui", "o", "yes", "y"):
            print("Annule."); return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(os.path.join(DOSSIER, "archives"), exist_ok=True)
    shutil.copy(PT, os.path.join(DOSSIER, "archives", f"paper_trading_{stamp}.json"))

    # 1. archive des trades (dedoublonnee par date_fermeture+symbole+gain)
    try:
        arch = json.load(open(ARCHIVE))
    except Exception:
        arch = {"cree_le": datetime.now().strftime("%Y-%m-%d %H:%M"), "departs": [], "trades": []}
    cles = {(t.get("date_fermeture"), t.get("symbole"), round(float(t.get("gain_eur", 0) or 0), 4)) for t in arch["trades"]}
    ajoutes = 0
    for t in trades:
        k = (t.get("date_fermeture"), t.get("symbole"), round(float(t.get("gain_eur", 0) or 0), 4))
        if k not in cles:
            arch["trades"].append(t); cles.add(k); ajoutes += 1
    # positions ouvertes -> archivees comme fermees "NOUVEAU-DEPART" (gain 0, hors statistiques de strategie)
    for p in positions:
        arch["trades"].append({**p, "prix_sortie": p.get("prix_entree"), "variation_pct": 0.0, "gain_eur": 0.0,
                               "raison": "NOUVEAU-DEPART (position ouverte archivee, non comptee)", "strategie": "nouveau_depart",
                               "date_fermeture": datetime.now().strftime("%Y-%m-%d %H:%M")})
    arch["departs"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "trades_archives": ajoutes, "positions_archivees": len(positions),
                            "liquidites_avant": pf.get("liquidites"), "net_avant": round(net, 2)})
    json.dump(arch, open(ARCHIVE, "w"), indent=1, ensure_ascii=False)

    # 2. nouveau portefeuille
    nouveau = {
        "capital_initial": CAPITAL, "liquidites": CAPITAL, "positions": [], "trades_fermes": [], "total_frais": 0.0,
        "historique": [{"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "valeur": CAPITAL}],
        "dernier_tick": datetime.now().strftime("%Y-%m-%d %H:%M") + " (NOUVEAU DEPART)",
        "circuit_breaker": {"consecutive_losses": 0}, "pertes_consecutives": 0,
        "nouveau_depart": {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "archive": ARCHIVE, "trades_archives_total": len(arch["trades"])},
    }
    # conserve les cles inconnues utiles (ex: etoiles, parametres) sauf celles liees au capital
    for k, v in pf.items():
        if k not in nouveau and k not in ("positions", "trades_fermes", "liquidites", "historique", "total_frais"):
            nouveau[k] = v
    json.dump(nouveau, open(PT, "w"), indent=2, ensure_ascii=False)

    # 3. protections: peak et pauses a zero
    pc = os.path.join(DOSSIER, "protection_capital.json")
    try:
        s = json.load(open(pc)) if os.path.exists(pc) else {}
        s.update({"peak": CAPITAL, "paused": False, "raison": "", "consecutive_losses": 0, "pause_start": 0})
        json.dump(s, open(pc, "w"), indent=1)
        print("protection_capital.json: peak remis a 1000, pause levee")
    except Exception as e:
        print(f"protection_capital.json: {e}")
    lt = os.path.join(DOSSIER, "learning_trader.json")
    try:
        if os.path.exists(lt):
            l = json.load(open(lt)); l["montant_ia"] = 200; json.dump(l, open(lt, "w"), indent=1, ensure_ascii=False)
            print("learning_trader.json: palier de mise IA remis a 200")
    except Exception as e:
        print(f"learning_trader.json: {e}")

    # 4. registre + journal relisent l'archive
    try:
        import registre_strategies as rs
        rs.mettre_a_jour(verbose=True)
        print(f"Registre recalcule sur {len(rs.tous_les_trades())} trades (archive + courant)")
    except Exception as e:
        print(f"registre: {e}")
    print(f"\nNOUVEAU DEPART OK: 1000.00 EUR, 0 position. {ajoutes} trades archives dans trades_archive.json, copie complete dans archives/paper_trading_{stamp}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
