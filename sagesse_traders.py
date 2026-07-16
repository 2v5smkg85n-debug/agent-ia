# -*- coding: utf-8 -*-
"""Sagesse des grands traders — principes injectés dans la réflexion quotidienne.

Chaque principe est associé à comment le système peut l'appliquer concrètement
(couper une stratégie perdante, ajuster TP/SL, sizing, diversification, etc.).
Le LLM de réflexion reçoit ce corpus et doit l'utiliser pour analyser la performance."""

# (trader, principe, application concrète dans le système)
SAGESSE = [
    ("Jesse Livermore",
     "Coupe tes pertes, laisse courir tes gains",
     "Ne jamais moyenner à la baisse sur une position perdante. Si une strategie "
     "est net negative, coupe-la (l'auto-pruning le fait ; confirme-le)."),

    ("Paul Tudor Jones",
     "Ratio gain/risque minimum 5:1 ; l'ego est l'ennemi",
     "Un trade gagnant doit rapporter plusieurs fois la perte potentielle. Verifie "
     "TP vs SL : si TP <= SL, le ratio est mauvais. TP devrait etre >= 2x SL "
     "(ex: SL 2.5% -> TP >= 5.0%). Coupe si ratio < 1."),

    ("Richard Dennis / Turtle Traders",
     "Risque fixe de 1-2% du capital par trade ; trend following",
     "Ne jamais surcharger un seul trade. Le CAP_ACTIF et drawdown_scaler "
     "appliquent ce principe. En regime TREND, garde l'exposition ; en "
     "QUIET, reduis-la."),

    ("Ray Dalio",
     "Pain + Reflection = Progress ; diversification all-weather",
     "Chaque perte est une lecon : identifie la cause racine de chaque strategie "
     "perdante (regime inadapte ? TP/SL mal regle ? actif trop volatile ?). "
     "Diversifie pour qu'aucun actif correle ne domine le risque."),

    ("George Soros",
     "Ce n'est pas d'avoir raison qui compte, mais combien tu gagnes quand tu as "
     "raison et perds quand tu as tort",
     "Concentre-toi sur l'expectative (pnl_total), PAS sur le win_rate seul. "
     "Une strategie a 70% de win mais pnl negatif est a COUPER : les pertes "
     "moyennes depassent les gains. C'est le ratio gain/perte qui compte."),

    ("Stanley Druckenmiller",
     "La taille des positions est aussi importante que la direction",
     "Quand une strategie est gagnante et fiable (win_rate eleve ET pnl positif), "
     "augmente sa taille ; quand elle perd, reduis-la avant de la couper."),

    ("Ed Seykota",
     "Trend following + risk management ; tout le monde obtient ce qu'il veut du "
     "marche",
     "En regime QUIET/range, les strategies trend-following (Donchian, breakout) "
     "souffrent ; privilegie mean-reversion (RSI). En TREND, l'inverse. Adapte."),

    ("Larry Hite",
     "Ne risque jamais plus de 1% par trade ; diversifie pour reduire le risque "
     "non-systematique",
     "Verifie la correlation entre tes positions ouvertes : si 2+ positions sont "
     "sur des actifs tres correles (ex: BTC+ETH+SOL), c'est un risque cache. "
     "Le CAP_SECTEUR limite deja ca."),

    ("Mark Douglas",
     "Pense en probabilites, pas en certitudes ; un seul trade n'a pas d'importance",
     "Ce qui compte c'est l'expectative sur 50+ trades, pas le dernier trade. "
     "Ne desactive pas une strategie sur 1 seul trade perdu (n<3 = bruit). "
     "Mais n'attends pas non plus 20 trades pour reagir."),

    ("Warren Buffett",
     "Regle 1: ne perds pas d'argent. Regle 2: n'oublie pas la regle 1",
     "Le drawdown protection est priorite absolue. Si drawdown > seuil, reduis "
     "l'exposition globalement. La preservation du capital prime sur le profit."),
]


def sagesse_prompt():
    """Retourne le corpus formaté pour injection dans le prompt de réflexion."""
    lignes = []
    for i, (trader, principe, appli) in enumerate(SAGESSE, 1):
        lignes.append(f"{i}. [{trader}] {principe}\n   -> {appli}")
    return "\n".join(lignes)


if __name__ == "__main__":
    print(sagesse_prompt())
