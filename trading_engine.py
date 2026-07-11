import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# Importe l'agent (meme dossier)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import agent, charger_memoire, sauver_memoire, ajouter, instruction_memoire, disponible, MODELS

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_JOURNAL = os.path.join(DOSSIER, "journal_trades.json")
FICHIER_STRATEGIES = os.path.join(DOSSIER, "strategies.json")

# ============================================
# MARCHES SUIVIS
# ============================================
MARCHES = {
    "crypto": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
    "forex": ["EUR/USD", "GBP/USD", "USD/JPY", "USD/MXN"],
    "actions": ["AAPL", "TSLA", "NVDA", "MSFT"],
    "matieres_premieres": ["Or (XAU/USD)", "Petrole (WTI)", "Argent (XAG/USD)"],
    "indices": ["S&P 500", "Nasdaq 100", "CAC 40", "DAX"]
}

# ============================================
# JOURNAL DES TRADES (apprentissage)
# ============================================
def charger_journal():
    if os.path.exists(FICHIER_JOURNAL):
        try:
            with open(FICHIER_JOURNAL) as f: return json.load(f)
        except: pass
    return {"trades": [], "lecons": []}

def sauver_journal(j):
    with open(FICHIER_JOURNAL, "w") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)

def charger_strategies():
    if os.path.exists(FICHIER_STRATEGIES):
        try:
            with open(FICHIER_STRATEGIES) as f: return json.load(f)
        except: pass
    return {}

def sauver_strategies(s):
    with open(FICHIER_STRATEGIES, "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def ajouter_lecon(texte):
    j = charger_journal()
    j["lecons"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "lecon": texte})
    sauver_journal(j)

# ============================================
# ANALYSE D'UN MARCHE
# ============================================
def analyser_marche(categorie, actif):
    """L'agent analyse un actif et propose une strategie."""
    memoire = instruction_memoire()
    journal = charger_journal()
    lecons_recentes = " | ".join(l["lecon"] for l in journal["lecons"][-5:])
    strategies_passees = charger_strategies().get(categorie, [])

    prompt = (
        (memoire if memoire else "") +
        f"LECONS APPRISES (trade passes): {lecons_recentes if lecons_recentes else 'aucune'}\n"
        f"STRATEGIES DEJA UTILISEES sur {categorie}: {strategies_passees[-3:] if strategies_passees else 'aucune'}\n\n"
        f"Analyse le marche {categorie.upper()} sur l'actif {actif}.\n"
        f"1. Donne la tendance actuelle (hausse/baisse/range)\n"
        f"2. Identifie 1 opportunite de trade (long ou short)\n"
        f"3. Donne: point d'entree, stop-loss, take-profit, ratio risque/rendement\n"
        f"4. Explique le raisonnement en 3 lignes max\n"
        f"5. Note ta confiance de 1 a 10\n"
        f"Sois concret et precis. Reponds en francais."
    )
    print(f"  -> Analyse {actif}...", end="", flush=True)
    res = agent(prompt, reflechir=True)
    print(f" OK")
    return res["final"]

# ============================================
# ENREGISTREMENT D'UN TRADE PROPOSE
# ============================================
def enregistrer_trade(categorie, actif, analyse):
    j = charger_journal()
    j["trades"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "marche": categorie,
        "actif": actif,
        "analyse": analyse[:500],
        "resultat": "en_cours",
        "performance": None
    })
    sauver_journal(j)

# ============================================
# APPRENTISSAGE AUTOMATIQUE
# ============================================
def apprendre_des_trades():
    """L'agent analyse ses trades passes et en tire des lecons."""
    j = charger_journal()
    trades_fermes = [t for t in j["trades"] if t["resultat"] != "en_cours"]
    if not trades_fermes:
        return "Aucun trade ferme a analyser pour l'instant."

    resume = "\n".join(
        f"- {t['actif']} ({t['marche']}): {t['resultat']} | perf: {t.get('performance','?')} | {t['analyse'][:100]}"
        for t in trades_fermes[-10:]
    )
    prompt = (
        f"Voici mes trades recents:\n{resume}\n\n"
        f"Analyse ce qui a marche et ce qui a echoue. "
        f"Tire 3 lecons concretes pour ameliorer mes futures strategies. "
        f"Sois precis et technique."
    )
    res = agent(prompt, reflechir=True)
    ajouter_lecon(res["final"][:1000])
    return res["final"]

# ============================================
# SCAN COMPLET DE TOUS LES MARCHES
# ============================================
def scan_complet():
    print("="*60)
    print("SCAN MULTI-MARCHES - " + datetime.now().strftime("%d/%m/%Y %H:%M"))
    print("="*60)

    opportunistes = []
    for categorie, actifs in MARCHES.items():
        print(f"\n=== {categorie.upper()} ===")
        # Prends les 2 premiers actifs de chaque marche pour le scan
        for actif in actifs[:2]:
            try:
                analyse = analyser_marche(categorie, actif)
                print(f"\n[{actif}]")
                print(analyse[:600])
                enregistrer_trade(categorie, actif, analyse)
                opportunistes.append((categorie, actif, analyse))
            except Exception as e:
                print(f"  Erreur sur {actif}: {e}")

    # Synthese : l'agent choisit la meilleure opportunite
    print("\n" + "="*60)
    print("SYNTHESE")
    print("="*60)
    resume_opp = "\n".join(f"- {a} ({c})" for c,a,_ in opportunistes)
    synthese = agent(
        f"Voici les opportunites trouvees aujourd'hui:\n{resume_opp}\n\n"
        f"Quelle est la MEILLEURE opportunite et pourquoi ? "
        f"Donne aussi la 2e meilleure. Sois decisif.",
        reflechir=True
    )
    print(synthese["final"])
    return synthese["final"]

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if mode == "scan":
        # Scan complet de tous les marches
        scan_complet()

    elif mode == "marche":
        # Analyse un marche precis: python trading_engine.py marche crypto
        cat = sys.argv[2] if len(sys.argv) > 2 else "crypto"
        if cat not in MARCHES:
            print(f"Marches disponibles: {list(MARCHES.keys())}")
        else:
            print(f"\n=== ANALYSE {cat.upper()} ===")
            for actif in MARCHES[cat]:
                print(f"\n[{actif}]")
                a = analyser_marche(cat, actif)
                print(a[:700])
                enregistrer_trade(cat, actif, a)

    elif mode == "apprendre":
        # Tire des lecons des trades passes
        print("Apprentissage a partir des trades passes...")
        lecons = apprendre_des_trades()
        print(lecons)

    elif mode == "journal":
        # Affiche le journal
        j = charger_journal()
        print(f"\n=== JOURNAL DES TRADES ({len(j['trades'])} trades) ===")
        for t in j["trades"][-10:]:
            print(f"\n{t['date']} | {t['actif']} ({t['marche']}) | {t['resultat']}")
            print(f"  {t['analyse'][:150]}...")
        print(f"\n=== LECONS APPRISES ({len(j['lecons'])}) ===")
        for l in j["lecons"][-5:]:
            print(f"\n{l['date']}: {l['lecon'][:200]}")

    else:
        print("Commandes:")
        print("  python trading_engine.py scan      - Scan tous les marches")
        print("  python trading_engine.py marche crypto  - Analyse un marche precis")
        print("  python trading_engine.py apprend   - Apprend des trades passes")
        print("  python trading_engine.py journal   - Affiche le journal")
