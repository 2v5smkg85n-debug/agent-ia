# Évolution de ton agent IA de trading

## Vue d'ensemble

- **297 commits** depuis la création
- **103 trades fermés**, win rate **58%** (60W / 43L)
- **Capital** : 996.51 EUR (démarré à 1000 EUR)
- **Frais payés** : 14.89 EUR
- **P&L brut** : +11.40 EUR (le P&L net négatif est dû aux frais, pas aux pertes de trading)

---

## Phase 1 — Les fondations (commits 1-50)

Le bot a commencé simple : quelques indicateurs de base (RSI, MACD, moyennes mobiles), un capital virtuel de 1000 EUR, et une boucle de trading basique.

**Ajouts clés :**
- Pont Revolut X (prix en EUR, kill switch, limite trades/jour)
- Auto-mesure + meta-evolveur (l'agent apprend de ses trades)
- Consensus multi-modèles (vote majorité sur les décisions IA)
- Gate sentiment (bloque les achats en euphorie)
- Staking des liquidités oisives
- Backups automatiques quotidiens
- Stratégies evolved (strategy_evolver)

---

## Phase 2 — Intelligence technique (commits 50-100)

L'agent a grandi avec de vrais indicateurs techniques calculés en Python, pas via IA.

**Ajouts clés :**
- Apprentissage des bougies japonaises (patterns)
- Apprentissage continu 24/7 sans API externe
- Sélection dynamique top 10 cryptos
- Stratégie momentum (achète quand la crypto monte)
- 20 nouvelles cryptos haute volatilité
- Meta-intelligence (apprentissage sans limite)
- Trailing stop + seuil strict + smart exit
- Backtest walk-forward (72% win rate)
- Filtre tendance (n'achète qu'en tendance haussière)

---

## Phase 3 — Optimisation profit (commits 100-150)

Focus sur la rentabilité : plus de positions, meilleur TP/SL, sizing adaptatif.

**Ajouts clés :**
- 15 positions simultanées, TP 4%, boucle 3 min
- Partial TP + breakeven/trailing plus tardifs
- Stop suiveur progressif (le SL suit le prix)
- Sizing dynamique selon spread Revolut X
- Objectif 100 EUR/jour
- 36 cryptos pour backtest horaire

---

## Phase 4 — Sécurité et stabilité (commits 150-200)

Correction des bugs critiques, nettoyage du code, sécurisation.

**Ajouts clés :**
- Fix 14 bugs critiques + 10 medium
- Blacklist PEPE + MATIC (prix trop petits)
- Fix positions fantômes (prix = 0)
- Sizing dynamique sentiment × score (80-500 EUR)
- Backtest contrarien vs trend-following
- Nettoyage : 247 fichiers supprimés (code mort)

---

## Phase 5 — Multi-agents IA (commits 200-230)

L'agent devient vraiment intelligent avec 8 agents IA qui analysent chaque signal.

**Ajouts clés :**
- 4 agents IA initiaux (technique, macro, sentiment, stratège)
- Intégration Perplexity API (web access) + Gemini fallback
- Extension à 8 agents (+risque, +contrarien, +momentum, +liquidité)
- Pipeline : Technique → Apprentissage → Trader Pro → Multi-Agents → Master Traders → Intel Pro → ML → Exécution

---

## Phase 6 — Session actuelle (commits 230-297)

Optimisations ciblées pour maximiser le win rate et éliminer les SL-RETARD.

### Améliorations profit (commits 230-240)
- TP 4% → 3.5% (backtest a montré 4% trop greedy)
- Trail 2% → 1.5%, anti-churn, score min 4
- 8 améliorations : fermeture intelligente, TP ATR, filtre volume, S/R, rotation logs, boost temporel, dashboard 30s, backtest
- Fix rotation logs : copy+truncate (garde fd systemd)
- Fix SL-RETARD : check 20s, rate-limit 1s, hard stop -1.5%
- Gestion position live : analyse adaptative continue (momentum, RSI, volume, S/R)
- Spread blacklist BNB/AAVE/SUI

### Scanner et diagnostic (commits 240-250)
- Scanner bot : 10 sections de diagnostic (service, portfolio, logs, modules, config, spreads, dashboard, telegram)
- Fix config via grep (pas d'import), telegram sans dotenv
- Fix rate limit Revolut X : retry 429 après 2s + CoinGecko retry
- Spread blacklist +XRP, DOGE, AVAX, LINK

### Plus de trades (commits 250-260)
- 8 positions max, 40 trades/jour, sizing 10-20%
- Plancher 200 EUR de liquidité
- Fix filtre volume : ignore volume=0 (Revolut X)
- Fix OHLCV : Binance en priorité (vrais volumes), Revolut X en fallback
- Filtre volume : pénalité score au lieu de blocage dur

### Win rate (commits 260-270)
- Filtre tendance 4h (HTF) : +1 si haussière, -2 si baissière
- Pénalité RSI 65-70 (surachat modéré)
- Prix sur-étendu : -2 si > 5% au-dessus SMA20
- Score minimum 5 (avant 4) = plus sélectif

### Fix SL-RETARD définitif (commit 297)
- Binance batch : 1 seul appel API pour tous les symboles
- Check 10s au lieu de 20s (Binance = instantané, pas de rate limit)
- Conversion EUR via taux BTC EUR/USDT (cache 5 min)

---

## Évolution des métriques

| Métrique | Début | Session actuelle |
|---|---|---|
| Win rate | ~33% (momentum) | **58%** (60W / 43L) |
| Positions max | 1 | **8** |
| Trades/jour max | 5 | **40** |
| TP | 1.0% | **3.5%** (ATR dynamique) |
| SL | 0.8% | **1.0%** |
| SL check | 60s (Revolut X) | **10s** (Binance batch) |
| SL-RETARD | fréquents (-2% à -3%) | **0** |
| Agents IA | 0 | **8** |
| Modules | 3 | **11** |
| Filtres entrée | 1 (score) | **14 couches** |
| Gestion live | aucune | **adaptative continue** |
| Sources prix | 1 (Binance) | **3** (Binance + Revolut X + CoinGecko) |
| Dashboard | statique | **auto-refresh 30s** |
| Scanner | aucun | **10 sections** |

---

## Pipeline de signaux actuel (14 couches)

```
1.  Indicateurs techniques (RSI, MACD, SMA, Bollinger, VWAP, ATR)
2.  Apprentissage bougies japonaises
3.  Filtre stratégie perdante (poids dynamique)
4.  Filtre sentiment (Fear & Greed)
5.  Filtre macro calendar (events high impact)
6.  Meta-intelligence (backtest instantané)
7.  Plugins (hooks d'entrée)
8.  Filtre confluence multi-timeframe (HTF 4h)
9.  Spread blacklist Revolut X
10. Filtre volume (pénalité score)
11. Filtre support/résistance
12. Score minimum (≥ 5)
13. Multi-agents IA (8 agents consensus)
14. Sizing dynamique (sentiment × score)
```

---

## Ce que l'agent fait aujourd'hui

1. **Analyse 30+ cryptos** avec 7 indicateurs techniques chaque 5 min
2. **8 agents IA** analysent chaque signal (technique, macro, sentiment, risque, contrarien, momentum, liquidité, stratège)
3. **14 filtres** valident chaque entrée avant exécution
4. **Gestion live** analyse les positions ouvertes toutes les 10s (momentum, RSI, volume, support/résistance)
5. **SL instantané** via Binance batch (1 appel pour tous les symboles)
6. **TP dynamique** basé sur l'ATR (3% min, 8% max)
7. **Trailing stop** progressif (0.5% à 1.5% selon le profit)
8. **Partial TP** à +2.5% (encaisse 50%, laisse courir le reste)
9. **Scanner bot** pour diagnostiquer tous les problèmes
10. **Dashboard** avec auto-refresh 30s
11. **Telegram** pour alerts en temps réel
12. **Briefing crypto** quotidien à 6h + scan opportunités à 12h et 18h
