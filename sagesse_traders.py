#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sagesse_traders.py — Base de connaissances: sagesse des 10 plus grands traders.

Encode les principes intemporels de chaque maitre trader et comment ils
s'appliquent (ou pas) au systeme IA (mean-reversion, intraday crypto/matieres
premieres). Le module reflection_gemini peut citer cette base pour generer des
hypothese testables.

DISCIPLINE: chaque principe est une HYPOTHESE a backtester avant deploiement.
Le systeme etant mean-reversion, les principes trend-following (Turtle/Dennis,
'let profits run') sont susceptibles d'etre rejetes en regime QUIET (comme ADX,
trailing, EXTEND-breakeven). Les principes contrarian (Buffett, Rogers, Soros)
sont alignes et prometteurs.
"""

SAGESSE = {
    "Warren Buffett": {
        "principe": "Acheter des actifs sous-evalues, long terme, concentration, 'sois craintif quand les autres sont avides'",
        "application_ia": "Contrarian: acheter les creux profonds (RSI tres bas), ne pas acheter dans l'euphorie. Le gate dip-buying bloque deja les bougies haussieres = ne pas acheter l'euphorie. Concentration = peu de trades haute conviction.",
        "aligne": "OUI (mean-reversion = acheter sous-evalue)",
        "test": "deep_contrarian: RSI<20 (creux profond) vs RSI<30, win rate?",
    },
    "George Soros": {
        "principe": "Reflexivite (feedback prix/perception), parier gros quand conviction, 'je suis riche parce que je sais quand j'ai tort'",
        "application_ia": "Cut losses fast (savoir qu'on a tort). Position sizing par conviction (score). Reflexivite: les mouvements auto-entretenus en crypto.",
        "aligne": "PARTIEL (cut losers utile; sizing limite par caps 10€/trade)",
        "test": "cut_losers: exit plus rapide sur position perdante, ameliore PnL?",
    },
    "James Simons (Medallion)": {
        "principe": "Quantitatif, reconnaissance de patterns, data-driven, diversification massive, court terme. 39%/an depuis 1988.",
        "application_ia": "C'est DEJA ce qu'est le systeme (quant + backtest + patterns). Lecon: miner plus de patterns, diversifier les strategies, laisser les donnees decider.",
        "aligne": "OUI (coeur du systeme)",
        "test": "deja applique (research_loop 24/7 mine les patterns)",
    },
    "John Paulson": {
        "principe": "Paris asymetriques sur les bulles (short subprimes). Macro evenementiel.",
        "application_ia": "Difficile a appliquer en intraday crypto. Principe: chercher l'asymetrie (gros gain potentiel, risque limite). EXTEND_TP est deja un paris asymetrique (TP 4% vs SL 2.5%).",
        "aligne": "PARTIEL (asymetrie deja via EXTEND_TP)",
        "test": "non prioritaire (macro evenementiel hors scope intraday)",
    },
    "Steven Cohen": {
        "principe": "Multi-strategie, short-selling, intuition + data, execution rapide.",
        "application_ia": "Multi-strategie = deja (RSI/MACD/SMA/Bollinger). Ajouter short-selling (VENTE) en regime baissier pourrait etre une piste.",
        "aligne": "PARTIEL (multi-strat deja; short = piste future)",
        "test": "future: strat VENTE en regime DOWN",
    },
    "Jim Rogers": {
        "principe": "Matieres premieres, contrarian, 'achete quand il y a du sang dans les rues'.",
        "application_ia": "Contrarian sur matieres premieres (GC, NG, HG, ZW que le systeme trade). Acheter les creux extremes. Alignement total avec mean-reversion.",
        "aligne": "OUI (contrarian + commodities)",
        "test": "deep_contrarian (avec Buffett)",
    },
    "Richard Dennis (Turtle Traders)": {
        "principe": "Systeme trend-following rules-based, breakout Donchian 20 jours. 'N'importe qui peut apprendre a trader.'",
        "application_ia": "Donchian breakout = trend-following. ATTENTION: le systeme est mean-reversion et a rejete ADX/trailing (trend) en QUIET. A tester honnetement - probablement rejete en range mais peut-etre utile en TREND.",
        "aligne": "NON en QUIET, peut-etre en TREND",
        "test": "turtle_breakout: Donchian 20-bar breakout, backtest honnete",
    },
    "Ray Dalio": {
        "principe": "Pure Alpha, all-weather, diversifier les flux de rendement non-correles, comprendre le cycle economique, 'principles'.",
        "application_ia": "All-weather = strategies conditionnees au regime (deja via regime.py). Diversifier across regimes (QUIET/TREND/VOL).",
        "aligne": "OUI (regime-conditionnel = all-weather)",
        "test": "deja applique (regime_fit dans le classement)",
    },
    "Paul Tudor Jones": {
        "principe": "Contrarian aux points de retournement, R:R 5:1, 'loser averages losers' (jamais ajouter a un perdant), risk management d'abord.",
        "application_ia": "Jamais ajouter a une position perdante (deja le cas: 1 trade par actif). R:R 5:1 = TP>>SL (EXTEND_TP fait 4% vs 2.5% SL = 1.6:1, peut-etre pousser). Cut losers fast.",
        "aligne": "OUI (risk management)",
        "test": "cut_losers + R:R plus eleve",
    },
    "Jeff Yass (SIG)": {
        "principe": "Options, edge dans la probabilite, expected value. 'La chose la plus importante est la valeur attendue.'",
        "application_ia": "Ne trader que quand l'EV est positive (expectancy). Le backtest mesure deja le retour moyen = proxy EV. Classement par score = bet on positive EV.",
        "aligne": "OUI (EV-based)",
        "test": "deja applique (score = backtest*fit*live = proxy EV)",
    },
}

# Synthese: quels principes tester maintenant (alignes + testables)
A_TESTER = [
    ("deep_contrarian", "Buffett + Rogers + Soros", "RSI<20 (creux profond) gagne-t-il plus que RSI<30?"),
    ("cut_losers", "Soros + Paul Tudor Jones", "Exit plus rapide des perdants ameliore-t-il le PnL?"),
    ("turtle_breakout", "Richard Dennis", "Donchian breakout: trend en QUIET = probable rejet (honneste)"),
]


def afficher():
    print("=" * 74)
    print("SAGESSE DES 10 MAITRES TRADERS (base de connaissances IA)")
    print("=" * 74)
    for nom, s in SAGESSE.items():
        print(f"\n{nom}")
        print(f"  principe: {s['principe']}")
        print(f"  applique: {s['application_ia'][:90]}")
        print(f"  aligne: {s['aligne']}")
    print("\n" + "=" * 74)
    print("A TESTER MAINTENANT (alignes + testables):")
    for key, src, q in A_TESTER:
        print(f"  - {key} [{src}]: {q}")
    print("=" * 74)


def sagesse_prompt():
    """Retourne la sagesse des maitres traders formatee pour le prompt de reflection."""
    L = ["Sagesse des 10 maitres traders (principes + application au systeme):"]
    for nom, s in SAGESSE.items():
        L.append(f"- {nom}: {s['principe']}")
        L.append(f"    applique: {s['application_ia']}")
        L.append(f"    alignement: {s['aligne']}")
    L.append("")
    L.append("Tests backtest realises (backtest_sagesse.py):")
    for key, src, q in A_TESTER:
        L.append(f"- {key} [{src}]: {q}")
    L.append("Resultats:")
    L.append("- deep_contrarian REJETE: RSI<20 = couteau tombant (33% win). RSI 20-30 (creux modere) gagne 83%.")
    L.append("- cut_losers REJETE: couper les perdants vite detruit le PnL (-7%). La patience paie en mean-reversion.")
    L.append("- turtle_breakout NUANCE: expectancy positive (55% win) mais qualite 4x inferieure en QUIET. Piste regime TREND uniquement.")
    L.append("")
    L.append("META-PATTERN CRITICAL: le systeme est MEAN-REVERSION. La sagesse classique du trading est")
    L.append("souvent INVERSEE ici: il faut de la PATIENCE et des creux MODERES, pas les extremes ni les")
    L.append("coupes rapides. Le trend-following (ADX, trailing, bougies haussieres, Turtle) nuit en QUIET.")
    L.append("Le contrarian modere (RSI 20-30, gate dip-buying) est valide. Ne re-propose PAS les principes")
    L.append("deja rejetes (deep contrarian, cut losers fast, trend en QUIET).")
    return "\n".join(L)


if __name__ == "__main__":
    afficher()
