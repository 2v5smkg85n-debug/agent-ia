# Rapport d'analyse des strategies

_Genere le 10/07/2026 a 00:15_

Base: 84 backtests reels (365 jours de donnees, execution deterministe)

## Bilan global

- 84 strategies testees: **40 gagnantes** (48%), 39 perdantes, 5 neutres
- Retour moyen: **+0.23%**
- Meilleur: +22.80% | Pire: -20.46%

## Performances par marche

| Marche | Tests | Gagnantes | Win rate | Retour moyen | Drawdown moyen |
|---|---|---|---|---|---|
| actions | 16 | 9 | 56% | +3.54% | 6.7% |
| crypto | 20 | 6 | 30% | -4.50% | 17.0% |
| forex | 16 | 8 | 50% | +0.30% | 3.8% |
| indices | 16 | 10 | 62% | +1.08% | 4.1% |
| matieres | 16 | 7 | 44% | +1.92% | 6.0% |

## Performances par strategie

| Strategie | Tests | Gagnantes | Win rate | Retour moyen |
|---|---|---|---|---|
| Bollinger Breakout | 21 | 10 | 48% | +1.03% |
| MACD Momentum | 21 | 11 | 52% | +0.95% |
| RSI Mean Reversion | 21 | 10 | 48% | -1.58% |
| SMA Crossover | 21 | 9 | 43% | +0.51% |

## Pourquoi chaque strategie marche (ou pas)

### Bollinger Breakout (win rate 48%, retour moyen +1.03%)

- **Principe**: Achete quand le prix touche la bande basse (deviation extreme) -> retour vers la moyenne.
- **Marche quand**: Actions volatiles (Tesla, Nvidia) et indices (DAX) ou les ecarts extremes se corrigent vite.
- **Echoue quand**: Breakout veritable (le prix sort de la bande et continue) -> on achete dans le vide.

### MACD Momentum (win rate 52%, retour moyen +0.95%)

- **Principe**: Achete quand le MACD croise la ligne de signal vers le haut = momentum haussier.
- **Marche quand**: Actions et matieres premieres avec trends soutenues (Apple, Petrole, Cuivre).
- **Echoue quand**: Marches choppy -> croisements multiples qui ne mennent nulle part.

### RSI Mean Reversion (win rate 48%, retour moyen -1.58%)

- **Principe**: Achete quand le RSI<30 (survente) en pariant sur un rebond vers la moyenne.
- **Marche quand**: Marches stables et ranges (forex, or) ou les prix reviennent a la moyenne.
- **Echoue quand**: Marches en forte tendance (crypto bull) -> le prix peut rester survendu longtemps et continuer a baisser.

### SMA Crossover (win rate 43%, retour moyen +0.51%)

- **Principe**: Achete quand la moyenne mobile courte (20j) depasse la longue (50j) = tendance haussiere confirmee.
- **Marche quand**: Marches en tendance claire (actions, matieres premieres avec cycles).
- **Echoue quand**: Marches ranges/volatiles (crypto) -> beaucoup de faux signaux.

## Top 10 des meilleures strategies

1. **[matieres] NG=F x SMA Crossover** -> +22.80% (win rate 100.0%, drawdown 0.83%)
2. **[actions] TSLA x Bollinger Breakout** -> +21.23% (win rate 72.7%, drawdown 3.53%)
3. **[actions] NVDA x Bollinger Breakout** -> +13.60% (win rate 70.0%, drawdown 4.59%)
4. **[actions] MSFT x RSI Mean Reversion** -> +12.65% (win rate 70.0%, drawdown 5.14%)
5. **[actions] AAPL x MACD Momentum** -> +12.04% (win rate 63.6%, drawdown 3.86%)
6. **[actions] NVDA x MACD Momentum** -> +12.04% (win rate 63.6%, drawdown 4.0%)
7. **[matieres] ZW=F x Bollinger Breakout** -> +11.40% (win rate 100.0%, drawdown 0.89%)
8. **[indices] ^GDAXI x Bollinger Breakout** -> +10.55% (win rate 77.8%, drawdown 2.41%)
9. **[matieres] BZ=F x MACD Momentum** -> +10.35% (win rate 58.3%, drawdown 10.44%)
10. **[crypto] XRPUSDT x Bollinger Breakout** -> +9.59% (win rate 61.1%, drawdown 25.68%)

## Strategies a eviter (pire 5)

1. **[crypto] SOLUSDT x RSI Mean Reversion** -> -20.46% (win rate 36.8%, drawdown 30.28%)
2. **[crypto] BTCUSDT x RSI Mean Reversion** -> -17.69% (win rate 43.8%, drawdown 25.47%)
3. **[crypto] ETHUSDT x RSI Mean Reversion** -> -15.98% (win rate 43.8%, drawdown 26.6%)
4. **[crypto] ETHUSDT x Bollinger Breakout** -> -12.76% (win rate 41.2%, drawdown 22.64%)
5. **[crypto] BTCUSDT x Bollinger Breakout** -> -11.26% (win rate 55.0%, drawdown 19.82%)

## Meilleure strategie par marche

- **actions**: TSLA x Bollinger Breakout (+21.23%, win 72.7%)
- **crypto**: XRPUSDT x Bollinger Breakout (+9.59%, win 61.1%)
- **forex**: GC=F x RSI Mean Reversion (+7.69%, win 100.0%)
- **indices**: ^GDAXI x Bollinger Breakout (+10.55%, win 77.8%)
- **matieres**: NG=F x SMA Crossover (+22.80%, win 100.0%)

## Conseils tires des donnees

1. **Strategie la plus fiable**: MACD Momentum (52% de win rate global)
2. **Marche le plus rentable**: indices (62% de win rate)
3. **Marche le plus difficile**: crypto (30% de win rate) -> a eviter ou optimiser