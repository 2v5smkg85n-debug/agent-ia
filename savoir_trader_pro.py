#!/usr/bin/env python3
"""
Savoir Trader Pro — Base de connaissances des traders professionnels.
Compile a partir du scan de dizaines de sources web sur le trading crypto.
Injecte dans le prompt de l'IA pour ameliorer ses decisions.

Sources:
- Blockchain Council: 15 regles de risk management pro
- Bitunix Academy: La regle du 1% et position sizing
- Thrive.fi: Routine quotidienne du trader crypto
- Backtrex: Guide de backtesting 2026
- TheLedgerMind: Backtesting et profit factor
"""

# ====================================================================
# 1. GESTION DU RISQUE (15 regles pro)
# ====================================================================
RISQUE_PRO = """
GESTION DU RISQUE — REGLES PROFESSIONNELLES:

1. RISQUE PAR TRADE: 1% a 2% du capital maximum. Jamais plus de 5%.
   - Capital 1000EUR -> risque max 10-20EUR par trade
   - Le risque = (prix_entree - stop_loss) * quantite
   - Ne pas sizing par confiance, la confiance n'est pas une metrique de risque

2. STOP-LOSS OBLIGATOIRE: Chaque trade a un stop-loss. Un trade sans stop = exposition non controlee.
   - Stop-loss = niveau ou l'idee de trade est invalidee
   - Le stop doit etre techniquement valide (support, structure), pas arbitraire

3. RATIO RISQUE/RECOMPENSE minimum 2:1, ideal 3:1.
   - Un WR de 40% peut etre profitable si: gain moyen = 3R, perte moyenne = 1R
   - Definir le stop d'abord (risque), puis la cible (recompense)
   - Ne trader que si le ratio respecte la regle

4. POSITION SIZING: Position = (Capital * risque%) / (entree - stop_loss)
   - Stop large -> position plus petite
   - Stop serre -> position plus grande (si techniquement valide)
   - Ne pas rapprocher le stop juste pour agrandir la position

5. COOLDOWN APRES PERTE: Apres un SL, attendre avant de re-ouvrir sur la meme crypto.
   - Ne pas faire de revenge trading (vouloir se refaire immediatement)
   - Une perte de -2% a -3% dans la journee = arret pour la journee

6. SCALING: On peut scale-in (entrer en plusieurs fois) si le risque total reste dans la limite.
   - Scaling-out: prendre des profits partiels pour reduire le risque ouvert

7. FRAIS ET SLIPPAGE: Toujours inclure les frais (0.2% aller-retour) et le slippage (0.1-0.5%).
   - Si les frais peuvent pousser la perte au-dela de 1%, reduire la position

8. DRAWDOWN: Un trader qui risque 1% par trade peut perdre 10 trades d'affilee et garder la majorite du capital.
   - Risque 10% par trade -> drawdown catastrophique, recovery quasi impossible
   - Le risque baisse automatiquement quand le capital baisse (1% d'un compte plus petit)

9. JOURNAL DE TRADING: Noter chaque trade avec entree, stop, taille, P&L, frais, slippage, etat emotionnel (1-10).
   - Grader le process, pas le resultat: un trade bien execute peut perdre, un mal execute peut gagner

10. NE JAMAIS DEPLACER UN STOP pour eviter une perte. Le stop reste ou il a ete place.
"""

# ====================================================================
# 2. REGLES D'ENTREE
# ====================================================================
ENTREE_PRO = """
REGLES D'ENTREE — QUAND OUVRIR UNE POSITION:

1. CONFLUENCE: Ne pas trader sur un seul indicateur. Attendre 2-3 confirmations:
   - RSI < 35 (survente) + MACD haussier + volume > 2x moyenne = signal fort
   - Support touche + bougie de reversal (marteau, engulfing) + RSI < 40 = bon signal
   - Plus de confirmations = plus de conviction

2. TIMEFRAME HIGHER: Toujours verifier la tendance sur le timeframe superieur.
   - Tendance 4h/1d haussiere -> chercher des longs sur 1h
   - Tendance 4h/1d baissiere -> eviter les longs ou attendre un rebond fort

3. BTC LEAD: BTC et ETH menent le marche. Verifier leur tendance avant d'acheter un altcoin.
   - Si BTC chute, les altcoins chutent plus fort
   - Si BTC est stable/haussier, les altcoins peuvent performer

4. FEAR & GREED:
   - Extreme Fear (0-25): historiquement des creux de cycle. Accumuler en tranches.
   - Fear (25-45): zone d'achat prudente. Bon entrees.
   - Neutral (45-55): marche indecis. Attendre une direction.
   - Greed (55-75): prudence. Ne pas FOMO. TP plus serres.
   - Extreme Greed (75-100): risque de correction. Reduire l'exposition.

5. VOLUME: Un mouvement sans volume est suspect.
   - Breakout avec volume > 2x moyenne = valide
   - Breakout sans volume = probablement faux
   - Volume spike haussier = confirmation d'entree

6. PATTERNS DE BOUGIES (reversal haussier):
   - Marteau (hammer): longue mirette basse, petit corps = rejet a la baisse
   - Engulfing haussier: grosse bougie verte qui avale la bougie rouge precedente
   - Doji en survente: indecision apres une chute = possible reversal
   - Morning star: 3 bougies (rouge, petite, verte) = retournement haussier

7. NE PAS CHASER: Si le mouvement a deja fait +5% sans toi, ne pas entrer.
   - Attendre un pullback vers un support ou une EMA
   - Mieux vaut rater un trade que d'entrer trop tard
"""

# ====================================================================
# 3. REGLES DE SORTIE
# ====================================================================
SORTIE_PRO = """
REGLES DE SORTIE — QUAND FERMER UNE POSITION:

1. TAKE-PROFIT: Definir la cible avant l'entree.
   - TP = distance a la resistance la plus proche (2% a 5%)
   - Si la strategie gagne regulierement, TP peut monter progressivement (+0.5% par palier)

2. PARTIAL TP: Prendre 50% de profit a +3% pour securiser le gain.
   - Laisser le reste courir vers le TP principal
   - Reduit le risque ouvert tout en gardant le potentiel de gain

3. TRAILING STOP: Quand le gain atteint +3%, trailing a 1.2% sous le pic.
   - Quand le gain atteint +5%, trailing a 0.8% sous le pic (serre)
   - Le trailing protege les gains tout en laissant courir

4. BREAKEVEN: A +2% de gain, monter le SL au breakeven (prix d'entree).
   - Un gagnant qui renverse ne devient pas une perte
   - Legerement au-dessus du breakeven pour couvrir les frais

5. CUT-STAGNATION: Si la position stagne a -0.3% ou pire pendant 120+ minutes:
   - Verifier le momentum (MACD) avant de couper
   - Si le momentum est toujours negatif, couper
   - Si le momentum se retourne, garder

6. STOP-LOSS ABSOLU: -1.5% maximum, quoi qu'il arrive.
   - Empeche les SL-retard de -5% a -7%
   - Le SL normal (-1%) doit etre verifie en premier

7. NE PAS DEPLACER LE STOP: Le stop reste ou il a ete place.
   - Deplacer le stop pour eviter une perte = la plus grosse erreur d'un trader
   - Accepter la petite perte plutot que la grosse

8. TIME-BASED EXIT: Si une position stagne trop longtemps (6h+):
   - Le capital est bloque et ne travaille pas
   - Mieux vaut fermer et attendre une meilleure opportunite
"""

# ====================================================================
# 4. GESTION DE POSITION
# ====================================================================
POSITION_PRO = """
GESTION DE POSITION — GERER UN TRADE OUVERT:

1. PYRAMIDAGE: On peut ajouter a un gagnant (pyramider), jamais a un perdant.
   - Si la position est en gain +1% et un nouveau signal apparait -> ajouter
   - Si la position est en perte et on veut average down -> NE PAS FAIRE
   - Le risque total du pyramidge doit rester dans la limite (1-2%)

2. 90/10 RULE: Les pros passent 90% de leur temps a attendre, 10% a executer.
   - Ne pas overtrader. Moins de trades de meilleure qualite = mieux
   - Attendre les setups A+ plutot que de forcer des setups B

3. MID-SESSION CHECK (toutes les 2-3h):
   - Le marche a-t-il change depuis l'entree?
   - Le momentum initial est-il toujours present?
   - Y a-t-il eu une news qui change la these?

4. ADAPTATION AU REGIME:
   - Marche haussier (Greed 55-75): TP plus larges (3-5%), trailing patient
   - Marche baissier (Fear 25-45): TP plus serres (2-3%), SL serres
   - Marche lateral (Neutral 45-55): Trader les ranges, TP aux bandes
   - Extreme Greed (75+): Reduire l'exposition, TP serres, ne pas ouvrir
   - Extreme Fear (0-25): Accumuler en tranches, TP larges

5. MULTI-TIMEFRAME:
   - 1d: tendance generale (ne pas aller contre)
   - 4h: structure du marche (HH/HL = haussier, LH/LL = baissier)
   - 1h: entree et gestion fine
   - Si 1d et 4h sont haussiers, chercher des longs sur 1h
   - Si 1d est baissier, attendre un vrai bottom avant d'acheter
"""

# ====================================================================
# 5. PSYCHOLOGIE ET DISCIPLINE
# ====================================================================
PSYCHO_PRO = """
PSYCHOLOGIE ET DISCIPLINE:

1. PAS DE REVENGE TRADING: Apres une perte, ne pas ouvrir immediatement un autre trade pour "se refaire".
   - Cooldown de 90 min apres un SL
   - Une perte de -2% a -3% dans la journee = arret pour la journee

2. PAS DE FOMO: Si une crypto fait deja +10% et tu n'es pas entre, ne pas chaser.
   - Attendre un pullback
   - Le FOMO est la cause n1 des pertes des traders debutants

3. ACCEPTER LA PERTE: Une perte de -1% est normale. C'est le cout du business.
   - 10 pertes de -1% = -10% du capital, recuperable
   - 1 perte de -10% = difficile a recuperer
   - 1 perte de -50% = quasi impossible a recuperer

4. PROCESS > RESULTAT: Grader le process, pas le resultat.
   - Un trade bien execute (bon setup, bon stop, bon TP) peut perdre -> c'est OK
   - Un trade mal execute (FOMO, pas de stop, TP deplace) peut gagner -> c'est DANGEREUX
   - Sur le long terme, le bon process gagne

5. ETAT EMOTIONNEL (1-10):
   - 1-3: fatigue, stress, peur -> NE PAS TRADER
   - 4-6: neutre, calme -> trader normalement
   - 7-10: euphorie, excitation -> prudence, reduire la taille
   - Noter l'etat emotionnel dans le journal a chaque trade

6. NE PAS OVERTRADER:
   - Max 5 positions simultanees
   - Max 3-5 trades par jour
   - Attendre les setups de qualite, pas forcer
   - 90% du temps a attendre, 10% a executer
"""

# ====================================================================
# 6. BACKTESTING ET VALIDATION
# ====================================================================
BACKTEST_PRO = """
BACKTESTING ET VALIDATION:

1. TESTER SUR UN CYCLE COMPLET: La strategie doit etre testee sur:
   - Phase haussiere (bull market)
   - Phase baissiere (bear market)
   - Phase laterale (consolidation)
   - Rentable dans au moins 2 des 3 phases = robuste

2. OUT-OF-SAMPLE: Optimiser sur 70% des donnees, valider sur 30%.
   - Si la strategie echoue sur les 30% de validation = overfitting
   - Overfitting = la strategie marche sur le passe mais pas sur le futur

3. METRIQUES CLES:
   - Win rate: % de trades gagnants (55%+ = bon)
   - Profit factor: gains totaux / pertes totales (>1.3 = bon, >2 = excellent)
   - Max drawdown: plus grosse chute du capital (<20% = acceptable)
   - Sharpe ratio: rendement ajuste au risque (>1 = bon)
   - Calmar ratio: rendement / drawdown (>2 = bon)
   - Un WR de 80% peut perdre de l'argent si les 20% de pertes sont catastrophiques

4. FRAIS ET SLIPPAGE: Toujours inclure dans le backtest.
   - Frais: 0.10% maker, 0.10% taker (aller-retour 0.20%)
   - Slippage: 0.1-0.5% pour les majors, 0.5-2% pour les altcoins illiquides
   - Ajouter 0.2% minimum de penalite par trade meme sur exchange zero-frais

5. SURVIVORSHIP BIAS: Ne pas tester uniquement sur les cryptos qui ont survecu.
   - 60% des tokens listes depuis 2017 sont inactifs ou delistes
   - Inclure les tokens delistes dans le backtest pour des resultats realistes

6. LOOK-AHEAD BIAS: Utiliser close[1] (bougie confirmee), pas close[0] (bougie en cours).
   - Ne jamais utiliser une information du futur pour declencher un signal
"""

# ====================================================================
# 7. STRATEGIES SPECIFIQUES
# ====================================================================
STRATEGIES_PRO = """
STRATEGIES SPECIFIQUES:

1. MEAN REVERSION (survente):
   - RSI < 35 + prix touche support = signal d'achat
   - TP = retour vers la moyenne (EMA20 ou bande moyenne Bollinger)
   - SL = sous le support le plus proche
   - Marche mieux en marche lateral ou legerement baissier

2. MOMENTUM (trend following):
   - EMA20 > EMA50 + RSI 50-65 (fort mais pas surachte) = signal
   - TP = trailing stop (laisser courir)
   - SL = sous EMA20
   - Marche mieux en marche haussier

3. BREAKOUT:
   - Prix casse une resistance avec volume > 2x moyenne = signal
   - TP = distance egale a la hauteur du range casse
   - SL = sous la resistance cassee (qui devient support)
   - Attention aux faux breakouts (sans volume = probablement faux)

4. BOLLINGER SQUEEZE:
   - Bandes serrees (volatilite tres faible) + prix au-dessus milieu = breakout imminent
   - Attendre la cassure de bande pour entrer
   - TP = bande opposee
   - SL = sous le milieu

5. DIVERGENCE RSI:
   - Prix fait un plus bas, RSI fait un plus haut = divergence haussiere (reversal)
   - Confirmer avec une bougie de reversal avant d'entrer
   - TP = retour vers EMA20
   - SL = sous le plus bas recent

6. VOLUME SPIKE:
   - Volume > 2x moyenne + bougie haussiere = confirmation de momentum
   - Entrer dans la direction du volume
   - TP = resistance la plus proche
   - SL = sous le bas de la bougie a volume eleve

7. ACCUMULATION EN TRANCHES (Extreme Fear):
   - Fear & Greed < 25 = accumulation progressive
   - Ne pas tout acheter d'un coup, echelonner sur plusieurs jours
   - Attendre une confirmation technique (bougie de reversal, RSI > 30)
   - TP larges (5-10%), car le recovery peut etre long
"""

# ====================================================================
# 8. ROUTINE QUOTIDIENNE
# ====================================================================
ROUTINE_PRO = """
ROUTINE QUOTIDIENNE DU TRADER PRO:

PHASE 1 — PRE-MARKET (15-30 min avant):
- Verifier les news crypto majeures (hacks, regulations, annonces)
- BTC et ETH d'abord: tendance, niveaux cles, support/resistance
- Fear & Greed index: adapter la strategie au sentiment
- Scanner la watchlist: mouvements overnight, setups en developpement

PHASE 2 — SESSION START (15 premieres minutes):
- Observer le range d'ouverture
- Les 15 premieres minutes = zone de non-trading (bruit, faux mouvements)
- Confirmer ou invalider la these pre-market

PHASE 3 — TRADING ACTIF:
- Suivre le plan, ne pas improviser
- 90% du temps a attendre, 10% a executer
- Ne pas chaser les mouvements manques
- Gerer les positions ouvertes (trailing, partial TP)

PHASE 4 — END OF DAY (15-20 min apres fermeture):
- Logger chaque trade: entree, sortie, stop, taille, P&L, etat emotionnel (1-10)
- Calculer le P&L journalier et le WR
- Identifier UNE lecon apprise aujourd'hui
- Preparer la watchlist de demain

PHASE 5 — WEEKEND (1-2h):
- Review de la semaine: P&L total, WR, setup performance
- Pattern recognition: quels jours/heures marchent le mieux?
- Ajuster la strategie si necessaire
"""

# ====================================================================
# FONCTION POUR INJECTER DANS LE PROMPT
# ====================================================================

def get_savoir_compact():
    """Version compacte pour injection dans le prompt de l'IA."""
    return f"""{RISQUE_PRO}

{ENTREE_PRO}

{SORTIE_PRO}

{POSITION_PRO}

{PSYCHO_PRO}

{STRATEGIES_PRO}"""


def get_savoir_complet():
    """Version complete avec routine et backtesting."""
    return f"""{RISQUE_PRO}

{ENTREE_PRO}

{SORTIE_PRO}

{POSITION_PRO}

{PSYCHO_PRO}

{BACKTEST_PRO}

{STRATEGIES_PRO}

{ROUTINE_PRO}"""


if __name__ == "__main__":
    print(get_savoir_complet())
    print(f"\n=== STATS ===")
    print(f"Risque: {len(RISQUE_PRO)} chars")
    print(f"Entree: {len(ENTREE_PRO)} chars")
    print(f"Sortie: {len(SORTIE_PRO)} chars")
    print(f"Position: {len(POSITION_PRO)} chars")
    print(f"Psycho: {len(PSYCHO_PRO)} chars")
    print(f"Backtest: {len(BACKTEST_PRO)} chars")
    print(f"Strategies: {len(STRATEGIES_PRO)} chars")
    print(f"Routine: {len(ROUTINE_PRO)} chars")
    print(f"Total: {len(get_savoir_complet())} chars")
