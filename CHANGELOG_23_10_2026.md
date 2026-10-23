# Changements du 23 octobre 2026

## Correctifs (0990e69)
- Sorties live et pattern relatives au stop/objectif de la position (plus de coupe des gagnants à +1 % ni des perdants à -1,5 % ; le stop ATR fait foi).
- Registre : `ia_autonome` est le véhicule du cerveau, jugée sur l'époque courante (`REGISTRE_EPOQUE`, défaut 2026-10-19), jamais retirée (probation au pire). Fin de l'impasse « retirée du registre ».
- Cerveau : barre de réussite par tranche 45 % (point mort 2:1 ≈ 40 % frais compris) au lieu de 55 %.

## Professeurs externes (nouveau module `professeurs_externes.py`)
Trois stratégies open source parmi les mieux classées sur 2022-2025 (classement Freqle, 6 146 stratégies : https://freqle.org/ranking), portées en Python pur, en **mode professeur** : elles votent, elles n'ouvrent rien.

| Professeur | Source | Cœur de la règle portée (5 min) |
|---|---|---|
| NASOS | https://github.com/devilsinthedetail/shafqatsuri/blob/main/NotAnotherSMAOffsetStrategy.py | RSI4 < 35, prix < EMA14 × 0,975 et < EMA24 × 0,991, EWO (EMA50-EMA200) > 2,327 (ewo1) ; variantes ewo2 (RSI14 < 25) et ewolow (EWO < -20,99) |
| E0V1E | https://github.com/ssssi/freqtrade_strs/blob/main/binance/dry_run/E0V1EN.py | RSI20 en baisse, RSI4 < 40, RSI14 > 42, prix < SMA15 × 0,973, CTI20 < 0,69, variation 24 h entre -15 % et +50 % ; variante buy_new |
| NFI | https://github.com/iterativv/NostalgiaForInfinity/blob/main/NostalgiaForInfinityX6.py | Protection « pas en pleine chute » (RSI3 5m et 15m > 3) ; #1 : prix sous la Bollinger basse avec écart EMA26/EMA12 > 3,4 % ; #2 : Aroon up < 25 (5m et 15m), StochRSI < 20, prix < EMA20 × 0,944 |

- Chaque vote est journalisé (`professeurs_externes.json`, un vote par professeur et par crypto toutes les 2 h) et **jugé par la barrière du bot** : stop 2×ATR 1h (0,8-3 %), objectif 2:1, 24 h.
- L'analyste du cerveau voit les votes du moment et la fiabilité **mesurée chez nous** de chaque professeur.
- Influence gagnée : +0,5 à la présélection par professeur fiable (≥ 20 votes tranchés, ≥ 45 % d'objectifs), plafond +1. Avant cela, lecture seule.
- Section « Professeurs externes » sur la page /cerveau. CLI : `python3 professeurs_externes.py` (rapport), `test SOLUSDT`, `evaluer`.
- Coupe-circuit : `PROFESSEURS_EXTERNES=0` dans .env.
- Indicateurs vérifiés contre pandas (EMA, RSI Wilder, CTI, Bollinger, Aroon, StochRSI : identiques).
- Attendu honnête : ces stratégies sont sélectives (NASOS 813 trades en 3 ans sur 33 paires en backtest) ; sur un rejeu de 5 jours × 10 cryptos, 1 seul vote. Quelques votes par semaine, pas par heure.

## KuCoin
- `indicateurs._historique_kucoin` : au-delà de 100 bougies, la fenêtre est précisée (`startAt/endAt`, max 1500) ; auparavant KuCoin ne renvoyait que 100 bougies quel que soit le nombre demandé.
