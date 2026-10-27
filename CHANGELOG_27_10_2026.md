# Changements du 27 octobre 2026 — pourquoi plus aucun trade

## Diagnostic
- 23 → 26/10 : `ia_autonome` retirée par le registre (impasse corrigée le 26).
- Depuis le 26/10 : le cerveau propose à confiance 65, seuil adaptatif 70 (tranche 60-69 : 11 TP / 34 SL = 24 %, sous le hasard 2:1). Le seuil fait son travail : non modifié.
- Stratégies classiques muettes depuis le 28/09 : le journal montre `[BLACKLIST] … strategie 'macd_cross' bloquee` pour chaque signal technique. Cause : `indicateurs.py` écrit toujours une ligne « MACD: … » (même « MACD: neutre ») et la première règle de nommage était `"MACD" in s` → tout signal technique était baptisé `macd_cross` (stratégie retirée) et bloqué. rsi_oversold, pattern_reversal et volume_spike ne pouvaient plus jamais être nommées, donc jamais ouvrir ni être jugées.

## Correctif (paper_trading.py)
- `_strategies_detectees()` : ne retient que les conditions réellement présentes (« RSI: survente », « BOUGIE: », « VOLUME: », « MACD … croisement haussier », etc.), stratégies prouvées en premier.
- `_nommer_strategie_technique()` : choisit la première stratégie détectée qui a le droit d'ouvrir et n'est pas retirée (registre), sinon la première détectée. Le registre juge ensuite chaque stratégie sur ses propres trades, comme avant.
- Tests : `tests/test_nommage_technique.py` (5 tests, 26 au total).

## Retour arrière
`git checkout cda5a65 -- paper_trading.py` (ou wget de l'ancienne version) puis redémarrage.
