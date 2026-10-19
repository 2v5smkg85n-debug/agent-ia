"""Recree les deux positions ouvertes par l'IA le 19/10 et effacees par l'ecrasement du fichier portefeuille.
Usage (services arretes) : python3 restaurer_positions_19_10.py
Les valeurs viennent des messages Telegram d'ouverture ; la date vient du journal du cerveau si elle y est.
"""
import json, os
from datetime import datetime

D = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(D, "paper_trading.json")
J = os.path.join(D, "journal_decisions.json")

A_RESTAURER = [
    {"symbole": "ETHUSDT", "prix_entree": 2143.43, "montant_eur": 61.0, "sl": 1.63, "tp": 2.44},
    {"symbole": "BTCUSDT", "prix_entree": 73198.505, "montant_eur": 92.0, "sl": 0.8, "tp": 1.2},
]

pf = json.load(open(F))
try:
    decs = json.load(open(J)).get("decisions", [])
except Exception:
    decs = []
maintenant = datetime.now().strftime("%Y-%m-%d %H:%M")
for r in A_RESTAURER:
    if any(p.get("symbole") == r["symbole"] for p in pf.get("positions", [])):
        print(f"{r['symbole']}: deja presente, rien a faire")
        continue
    dates = [x.get("date") for x in decs if x.get("action") == "ACHAT" and x.get("sym") == r["symbole"]]
    date_ouv = (dates[-1] if dates else maintenant)[:16]
    frais = r["montant_eur"] * 0.002
    pos = {
        "symbole": r["symbole"], "nom": r["symbole"], "marche": "crypto",
        "prix_entree": r["prix_entree"], "prix_actuel": r["prix_entree"], "montant_eur": r["montant_eur"],
        "quantite": (r["montant_eur"] - frais) / r["prix_entree"], "frais_entree": frais,
        "date_ouverture": date_ouv, "timestamp": date_ouv + ":00",
        "sl_adaptatif": r["sl"], "tp_adaptatif": r["tp"], "sl_risque": r["sl"], "tp_risque": r["tp"], "barriere_h": 24,
        "sl": -r["sl"], "tp": r["tp"], "score": 7,
        "strategie": "ia_autonome", "source": "ouverture_ia_chat",
        "raison": "Restauration 19/10 (position effacee par l'ecrasement du fichier)", "signal_raison": "Ouverture auto par l'IA (restauree)",
    }
    pf.setdefault("positions", []).append(pos)
    pf["liquidites"] = float(pf.get("liquidites", 0)) - r["montant_eur"]
    print(f"{r['symbole']}: restauree @ {r['prix_entree']} ({r['montant_eur']:.0f} EUR, SL {r['sl']}% / TP {r['tp']}%, ouverte {date_ouv})")
json.dump(pf, open(F, "w"), ensure_ascii=False, indent=2)
print(f"Liquidites: {pf['liquidites']:.2f} EUR | positions: {[p['symbole'] for p in pf['positions']]}")
