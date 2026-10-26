# Changements du 26 octobre 2026 — retour des gagnantes, sous contrôle du registre

Ce que l'historique (septembre → octobre) désigne comme gagnant, remis en service de façon mesurée et réversible.

## 1. Stratégies remises en service (probation)
`consensus_reversion` (peak_fader : RSI 1h qui sort de survente, +15,48 € sur 10 trades le 21/09), `pattern_reversal` (+20,22 € sur 43 trades le 23/09), `volume_spike` (3/3).
- Droit d'ouvrir rendu via le registre (`droit <strat> on`), **probation** : 1 position à la fois, risque du palier (1 € aujourd'hui), stop ATR et objectif 2:1 comme tout le monde, porte, casier et cadence inchangés.
- **Jugées sur une nouvelle époque** (trades depuis le 26/10) : 30 trades de probation, puis les règles normales du registre s'appliquent à cette époque (active si prouvée, retirée si perdante avec confiance). Le passé reste affiché, il ne juge plus.
- Réglable : `REGISTRE_REPRISES="consensus_reversion:2026-10-26,pattern_reversal:2026-10-26,volume_spike:2026-10-26"` dans .env ; retour arrière : `python3 registre_strategies.py droit <strat> off`.

## 2. Stop suiveur après l'objectif (`TRAILING_APRES_TP`, défaut 1)
Les meilleures journées venaient de gains laissés courir derrière un stop suiveur (18/09 : +35 € sur 9 trades, 9 gagnants ; 21/09 : +55 €). Le trailing avait été coupé parce qu'il remplaçait le TP par des sorties précoces. Nouvelle version : il ne s'arme **qu'une fois l'objectif 2:1 atteint**, garantit au moins 90 % de l'objectif et suit le pic à 0,5 × stop (mini 0,4 %). Il ne peut donc qu'ajouter par rapport au TP sec. Sortie étiquetée `TP-SUIVI`. `TRAILING_APRES_TP=0` pour revenir au TP sec.

## 3. downshift_rider redevient votant (`PROF_MOMENTUM`, défaut 1)
Le professeur Momentum (croisement MACD 4h + EMA20 + bougie 1h verte) revient dans le consensus et le dossier du cerveau, **sans pouvoir être la stratégie dominante** d'un signal (sinon le signal serait étiqueté consensus_momentum, bloqué, et volerait l'ouverture aux autres). `PROF_MOMENTUM=0` pour le couper.

## Ce qui ne change pas
rsi_oversold active, ia_autonome véhicule du cerveau, NASOS/E0V1E/NFI professeurs, porte auto-calibrée, casier mesuré, palier de risque, plafond 6 ouvertures/jour, 200 € de liquidités minimum.
