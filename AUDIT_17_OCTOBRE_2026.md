# Audit complet du bot et de l'IA — 17 octobre 2026

Analyse du code (185 fichiers, 35 500 lignes de Python), des 403 trades, nettoyage, récupération des stratégies gagnantes, remise du capital virtuel à 1 000 €, et recherche web sur ce qui ferait progresser le bot et l'IA. Chaque chiffre vient soit du code, soit de vos propres données, soit d'une source citée.

---

## 1. Résumé en dix lignes

1. Le bot a perdu 85 € sur 403 trades. Une seule cause pèse plus que toutes les autres : 206 stops touchés (51 % des trades) pour -238 €, avec un stop fixe à 0,5 % en dessous du bruit normal des bougies 1h. Corrigé le 16/10 (stop ATR 0,5-1 %, risque fixe 1 €).
2. Deux stratégies seulement sont gagnantes à vie : **ia_autonome** (55 trades, 65 %, +3,6 €) et **rsi_oversold** (44 trades, 68 %, +2,8 €). Toutes les sorties « intelligentes » (TP, TP partiel, sortie pattern, stop suiveur, live-exit) sont positives : +166 €. Ce sont les entrées qui perdent, pas les sorties.
3. Le bot « n'apprenait pas » parce qu'il a **douze systèmes d'apprentissage qui ne partagent aucune mémoire** (60 fichiers d'état JSON différents) et que la remise à zéro du 13/10 a effacé le casier des stratégies. Depuis le 16/10 : registre à vie + journal des erreurs + cerveau auto-évalué.
4. Quatre bugs silencieux corrigés aujourd'hui : le filtre d'historique des prix renvoyait toujours vide, la fermeture « stagnation » ne fonctionnait jamais, un calcul de taille plantait dans un cas limite, une commande Telegram plantait.
5. Les sécurités « codées en dur » (lundi interdit, 6 cryptos interdites, heures 14h/3h/11h) datent d'un bilan de 211 trades et contredisent parfois les règles apprises (le boost « fort volume » favorise 12h-13h et 16h-17h, alors que 12h-16h perd -46 €). Rien n'a été retiré : c'est à vous de décider.
6. Un mécanisme caché est dangereux : les « objectifs de survie » (10 000 € la première année, soit x10) déclenchent un « mode évolution » qui change la stratégie quand la cible n'est pas atteinte. C'est une source d'erreurs reproduites. À désactiver avec votre accord.
7. Le nouveau départ à 1 000 € est prêt : l'historique est archivé, pas effacé ; le registre et le journal continuent de lire les 403 trades.
8. Le nettoyage range 50 fichiers morts (sauvegardes .bak, scripts d'analyse ponctuels, anciens scripts de déploiement) dans archive/ ; rien n'est supprimé et tout est réversible.
9. Les stratégies gagnantes sont « récupérables » en une commande : le registre peut rendre le droit d'ouvrir à rsi_oversold, avec toutes les nouvelles protections. Par défaut, rien ne change (seule ia_autonome ouvre, comme vous l'avez demandé).
10. La recherche web confirme la direction prise et donne 14 améliorations concrètes, classées par priorité en section 9.

---

## 2. Ce que disent vos 403 trades (net -85,35 €)

### Par stratégie

| Stratégie | Trades | Réussite | Net | Verdict |
|---|---:|---:|---:|---|
| macd_cross | 140 | 45 % | -21,7 € | retirée |
| essai_bougies | 71 | 35 % | -32,8 € | arrêtée le 16/10 |
| **ia_autonome** | 55 | **65 %** | **+3,6 €** | active |
| **rsi_oversold** | 44 | **68 %** | **+2,8 €** | active, sans droit d'ouverture |
| consensus_tendance | 30 | 53 % | -14,4 € | retirée |
| pattern_reversal | 22 | 45 % | -5,5 € | probation |
| consensus_patterns | 19 | 42 % | -13,0 € | retirée |
| consensus_reversion | 17 | 47 % | -5,5 € | probation |
| volume_spike | 3 | 100 % | +3,7 € | trop peu de trades |
| bollinger_bounce | 2 | 50 % | -2,6 € | trop peu de trades |

### Par type de sortie

| Sortie | Trades | Net |
|---|---:|---:|
| SL-EXEC (stop) | 183 | **-190,5 €** |
| SL-URGENCE-ABSOLU | 23 | -47,7 € |
| CUT-STAGNATION | 19 | -18,0 € |
| TP | 32 | +48,6 € |
| PATTERN-SORTIE | 37 | +36,3 € |
| PARTIAL-TP | 40 | +32,2 € |
| LIVE-EXIT Momentum | 17 | +21,6 € |
| STOP-SUIVEUR | 15 | +15,6 € |
| TEMPS-stale | 32 | +8,2 € |

Lecture : les 206 stops coûtent 238 €. Tout le reste rapporte +153 €. Le bot sait sortir ; il entre mal et se fait sortir par le bruit.

### Par heure (UTC) et par mois

| Tranche | Trades | Net |
|---|---:|---:|
| 0h-4h | 62 | -21,6 € |
| **4h-8h** | 85 | **+15,8 €** |
| 8h-12h | 67 | -20,7 € |
| **12h-16h** | 83 | **-46,4 €** |
| 16h-20h | 51 | -12,3 € |
| 20h-24h | 55 | -0,2 € |

Septembre : 181 trades, -4,5 €. Octobre : 222 trades, -80,9 €. L'hémorragie est récente et coïncide avec l'essai « 1 trade / 2 min » et le passage de macd_cross en volume.

Ce que dit la littérature sur les heures : une étude de l'université de Mannheim sur 1 940 paires et 38 bourses montre que le volume, la volatilité et l'illiquidité culminent entre 16h et 17h UTC, et que l'activité est la plus faible tôt le matin ([Mannheim, « The crypto world trades at tea time »](https://madoc.bib.uni-mannheim.de/72942/1/s11156-024-01304-1.pdf?rs=true&wid=)). Vos meilleures heures (4h-8h UTC) sont justement les heures calmes : un stop à 0,5 % y survit mieux. Vos pires heures (12h-16h) sont celles où la volatilité monte avec l'ouverture américaine.

---

## 3. Problèmes trouvés dans le code

### 3.1 Bugs réels (corrigés aujourd'hui, commit d6c520a)

| Fichier | Bug | Effet |
|---|---|---|
| historique_prix.py | variable `sym` inexistante (`symbole` attendu) | le filtre MTF/pullback recevait toujours un historique vide : la fonctionnalité était morte en silence |
| paper_trading.py | `STAGNATION_PERTE_SEULE` au lieu de `STAGNATION_PERTE_SEUIL` | la « fermeture intelligente » d'une position qui stagne plantait à chaque tick (avalé par un try/except) |
| gestion_risque.py | `dispo_actif`/`dispo_secteur` inexistants dans le fallback Kelly | plantage dans le cas « Kelly = 0 mais stratégie gagnante » |
| chat_naturel.py | `_rapide_deploy` inexistant | la commande Telegram « deploy » plantait |

Ces quatre bugs ont un point commun : ils étaient cachés par des `try/except` silencieux. Le bot en compte des dizaines. Recommandation : journaliser systématiquement l'exception dans ces blocs (une ligne `print`), sinon les fonctionnalités meurent sans prévenir.

### 3.2 Réglages incohérents (non modifiés, à décider)

- `SEUIL_BENEFICE_MIN = 0.9` et `ATR_TP_MIN = 0.9` sont commentés « alignés avec TP 0,9 % » alors que le TP est à 1,5 % depuis le 16/10.
- `HEURES_FAIBLE_LIQUIDITE = 14h, 3h, 11h UTC` (bilan de 211 trades) et `HEURES_FORT_VOLUME` qui donne un bonus à 12h-13h et 16h-17h : contredit la règle apprise 12h-16h (-46 €). Deux systèmes d'heures qui ne se parlent pas.
- Liste noire de 6 cryptos (LDO, ADA, DOT, PEPE, AVAX, BNB) et « lundi interdit » : basées sur un bilan ancien, jamais réévaluées. Le registre et le journal savent maintenant le faire ; ces listes en dur devraient devenir des règles du journal, mesurées et révisables.
- `MAX_TRADES_PAR_JOUR = 5` ne s'applique qu'au chemin « bot » (paper_trading) ; le chemin IA (chat_naturel) ne le vérifie pas.
- Sizing « paliers » 200 → 5 000 € avec 70 % du capital en compounding dans chat_naturel : code mort depuis le risque fixe, mais dangereux s'il était réactivé. À supprimer.
- `datetime.now()` sans fuseau (40 occurrences) mélangé à des dates UTC : fonctionne parce que le VPS est en UTC, mais fragile.
- Frais modélisés à 0,1 % par côté. Revolut X facture 0 % maker et 0,09 % taker ([Revolut X](https://www.revolut.com/revolut-x/)) : le modèle est légèrement pessimiste, c'est bien. Kraken Pro palier 1 : 0,40 % maker / 0,80 % taker ([Kraken](https://www.kraken.com/features/fee-schedule)), déjà pris en compte par le Kraken virtuel.

### 3.3 Problèmes d'architecture (la vraie cause du « n'apprend pas »)

- **56 modules vivants, 35 000 lignes, 60 fichiers d'état.** super_intelligence, intelligence_pro, meta_intelligence, meta_tuning, auto_evolution, agents_consensus, consensus_ia, social_consensus, master_traders, professeur_virtuel, trader_pro, strategies_evolved, strategies_phase4, ml_filtre, ml_pipeline, apprentissage_trader, apprentissage_continu, candlestick_learning… Chacun « apprend » dans son coin (strategy_weights.json, genome_strategies.json, memoire_profonde.json, pattern_learning.json, learning_trader.json, lecons.json, kelly_state.json…). Aucun ne lit les autres. Résultat : l'IA se souvenait de tout et de rien.
- **Six modules appellent Gemini** (agent, agents_consensus, auto_evolution, consensus_ia, social_consensus, super_intelligence) en plus de chat_naturel et du cerveau. Le niveau gratuit de Gemini 2.5 Flash est annoncé à 10 requêtes/minute et 250 requêtes/jour par plusieurs sources de début 2026 ([récapitulatif GitHub, janv. 2026](https://github.com/sambhrantbisi-lab/AWS-SMARTHACKATHON/blob/main/GEMINI_RATE_LIMITS_2026.md), [Zenn, fév. 2026](https://zenn.dev/shinseitaro/books/crewai-hands-on/viewer/gemini-free-tier)) ; la page officielle précise que les quotas sont par projet et se réinitialisent à minuit heure du Pacifique ([Google AI](https://ai.google.dev/gemini-api/docs/rate-limits)). Quand le quota est atteint, tout bascule sur Ollama local (plus lent, plus faible) sans que vous le sachiez.
- **Objectifs de survie x10 par an + mode évolution.** `OBJECTIFS_ANNUES = [10000, 100000, 1000000, 10000000]` : si la cible n'est pas atteinte, l'IA « évolue » (change de stratégie). Changer de méthode parce qu'un objectif irréaliste n'est pas atteint, c'est exactement reproduire des erreurs. L'IA ne doit pas mourir (votre consigne) ; elle ne doit pas non plus muter au hasard.
- **Analyse automatique après chaque fermeture** : une position se ferme, l'IA analyse et rouvre. C'est le mécanisme des cascades de stops. Le journal des erreurs classe maintenant les cascades et finira par les bloquer, mais le déclencheur reste.
- **Aucun test automatisé, aucun backtest walk-forward des règles actuelles.** Les 11 fichiers backtests*.json testent d'anciennes versions.
- **Sécurité** : le dashboard est en HTTP avec le token dans l'URL. Suffisant pour du virtuel, pas pour du réel.

---

## 4. Ce qui a été fait aujourd'hui (commit d6c520a)

1. **nouveau_depart.py** : capital 1 000 €, 0 position, trades archivés dans trades_archive.json, copie complète dans archives/, peak de protection remis à 1 000, palier de mise IA remis à 200. Le registre et le journal lisent archive + courant : le casier à vie est conservé.
2. **nettoyage.py** : range 50 fichiers morts dans archive/<date>/ ; protège tout fichier cité par le crontab, un service systemd ou importé par un module vivant ; simulation par défaut ; retour arrière en une commande.
3. **Droits d'ouverture configurables** : `python3 registre_strategies.py droit rsi_oversold on` rend le droit d'ouvrir à une stratégie. La liste noire de paper_trading consulte le registre. Par défaut, rien ne change.
4. **Quatre bugs corrigés** (section 3.1).
5. **Cerveau** : réponses JSON forcées côté Gemini (`responseMimeType: application/json`, conforme à la doc [Google AI](https://ai.google.dev/gemini-api/docs/structured-output)) et côté Ollama (`format: json`, conforme à la doc [Ollama](https://docs.ollama.com/capabilities/structured-outputs)), plus un petit budget de raisonnement (512 tokens) pour l'analyste au lieu de zéro.

Pour mémoire, le 16/10 : arrêt de l'essai, registre à vie, journal des erreurs avec règles apprises, stop ATR + risque fixe 1 €, Kraken virtuel sur toute crypto, cerveau v3 (présélection, dossiers, analyste à checklist, avocat du diable, porte à seuil adaptatif, auto-évaluation 4h après).

---

## 5. Stratégies gagnantes : comment elles sont récupérées

- **ia_autonome** (65 %, +3,6 €) : garde le droit d'ouvrir, maintenant via le cerveau v3.
- **rsi_oversold** (68 %, +2,8 €) : le registre la marque « active » et signale « mérite une réactivation ». Elle n'ouvre pas tant que vous ne le décidez pas. Si vous dites oui, elle ouvrira avec le stop ATR, le risque fixe 1 €, les règles apprises et la surveillance du registre (qui la retirera automatiquement si elle redevient perdante). Sa logique (RSI < 30-35 en survente) est aussi ce que le scan d'opportunités du 16/10 a relevé sur XRP.
- **volume_spike** (3/3, +3,7 €) : trop peu de trades pour conclure ; reste en probation (1 position max), ce qui est la bonne façon de l'évaluer.
- **Les sorties gagnantes** (sortie pattern, TP partiel, stop suiveur, live-exit momentum) sont toutes positives : à conserver telles quelles, ne pas les « optimiser ».
- **Les professeurs** continuent de nourrir l'IA sans ouvrir, conformément à votre consigne. Le cerveau reçoit leurs signaux dans le dossier de chaque candidate.

---

## 6. Ce que dit la recherche, et ce que ça change pour le bot

**Chandeliers.** Une étude publiée en 2026 dans Research in International Business and Finance a testé 55 patterns de retournement sur près de 400 cryptos, 2 000 paires, 36 bourses et 200 millions d'observations en bougies 1h (2018-2022) : les patterns **Harami haussier et Hikkake** précèdent des hausses statistiquement significatives, le Harami baissier et le Pendu des baisses, avec une robustesse vérifiée par un test de « superior predictive ability » contre le data-snooping ([IDEAS/RePEc](https://ideas.repec.org/a/eee/reveco/v108y2026ics1059056026002716.html)). Votre détecteur connaît le harami mais pas le hikkake, et donne beaucoup de poids au doji (14 occurrences dans le code), que l'étude ne retient pas. Changement : pondérer les patterns selon cette évidence, ajouter le hikkake.

**Agents LLM en débat.** Le framework TradingAgents (UCLA/MIT, 2024-2025) organise des analystes spécialisés, des chercheurs « bull » et « bear » qui débattent, un trader qui tranche et des gestionnaires de risque, et rapporte de meilleurs rendements cumulés, un meilleur Sharpe et un drawdown plus faible que les modèles de référence ([arXiv 2412.20138](https://arxiv.org/abs/2412.20138)). Le cerveau v3 est déjà construit sur ce principe (analyste + avocat du diable + porte). Prochaine étape naturelle : un vrai débat en deux tours plutôt qu'une seule critique.

**Protections.** Freqtrade, le bot open-source de référence, formalise quatre protections : StoplossGuard (bloque tout après 4 stops sur 24 bougies, pendant 4 bougies), MaxDrawdown (stop si drawdown > 20 % sur 20 trades/48 bougies), LowProfitPairs (bloque une paire dont les 2 derniers trades sur 6 bougies rapportent moins de 2 %), CooldownPeriod (interdit de rentrer sur une paire pendant 2 bougies après une fermeture) ([Freqtrade](https://www.freqtrade.io/en/2024.1/includes/protections/)). Votre bot a l'équivalent des deux premières (anti-cascade, circuit breaker), pas des deux dernières. Le CooldownPeriod est exactement l'antidote à « l'analyse auto après fermeture ».

**Taille de position.** La méthode professionnelle : fixer le risque par trade (0,5-2 % du capital), placer le stop à une distance volatile (par exemple 1,5 × ATR), puis déduire la taille = risque ÷ distance du stop, avec une limite de perte journalière ([For Traders](https://fortraders.com/blog/manage-risk-professional-trader)). C'est ce qui a été implémenté le 16/10 (1 € par trade, 1,2 × ATR). Le risque de 1 € sur 1 000 € (0,1 %) est très prudent ; les pros sont entre 0,5 et 2 %. À augmenter seulement une fois le taux de réussite confirmé sur 30 trades.

**Papier contre réel.** En réel, un ordre limite liquide glisse de 0,01 à 0,05 %, un ordre au marché peut dépasser 0,5 % en période volatile ; il faut modéliser 0,05-0,1 % de glissement par trade, gérer les remplissages partiels, les coupures et la réconciliation de l'état au redémarrage, et valider statistiquement avant le réel (test de permutation p < 0,05, efficacité walk-forward > 0,5) ([Bot versus Bot, 2026](https://botversusbot.com/articles/paper-trading-vs-live-trading-crypto-bots-2026/)). Le Kraken virtuel modélise déjà ask/bid et frais taker ; il manque le glissement et la validation statistique.

**Sur-apprentissage.** Plus de 90 % des stratégies ML backtestées échouent en réel à cause du data-snooping ; il faut des découpages chronologiques (60-70 % entraînement, 15-20 % validation, 15-20 % test jamais touché), un embargo entre les périodes, et faire confiance au walk-forward plutôt qu'au backtest simple ([TradeAlgo](https://www.tradealgo.com/trading-guides/ai-trading/machine-learning-backtesting-guide)). Le méta-tuning quotidien qui ajustait TP/SL sur les derniers jours est exactement le piège décrit.

---

## 7. Plan d'amélioration de A à Z, par priorité

### P0 — cette semaine (sans nouvelle API, sans risque)

1. **Lancer le déploiement + nouveau départ + nettoyage** (commandes en section 8).
2. **CooldownPeriod** : interdire toute réouverture sur la même crypto pendant 2 bougies 1h après une fermeture, et supprimer « l'analyse auto après fermeture ». Coupe les cascades à la racine.
3. **Désactiver le « mode évolution »** des objectifs de survie (garder l'IA vivante, supprimer les mutations). Nécessite votre accord.
4. **Journaliser les exceptions** dans tous les `try/except` silencieux des chemins critiques.
5. **Compteur de quota Gemini** : compter les appels du jour, afficher sur le dashboard, et répartir le budget (cerveau prioritaire, les six autres modules Gemini en second).

### P1 — deux semaines

6. **Unifier les heures** : remplacer HEURES_FAIBLE_LIQUIDITE / HEURES_FORT_VOLUME par une seule table apprise par le journal (net par tranche sur 60 jours), révisée chaque semaine. Même traitement pour la liste des cryptos interdites et le lundi : des règles du journal, mesurées, pas des constantes.
7. **Pondération des patterns** selon l'évidence (Harami, Hikkake en haut ; doji neutre), et ajout du Hikkake au détecteur.
8. **Glissement dans le Kraken virtuel** : 0,05 % par trade (0,1 % sur les petites cryptos).
9. **Débat à deux tours** dans le cerveau : l'analyste répond à la faille de l'avocat du diable avant la porte.
10. **Un seul fichier de mémoire** : déprécier les modules d'apprentissage parallèles (strategy_weights, genome, memoire_profonde, pattern_learning, kelly_state…) au profit du trio registre / journal / décisions du cerveau. Les garder en lecture, ne plus les laisser écrire.

### P2 — un mois

11. **Backtest walk-forward des règles actuelles** (stop ATR, règles du journal, filtres du cerveau) sur les bougies 1h des 6 derniers mois, avec découpage chronologique et embargo, pour obtenir une mesure honnête avant de parler de réel.
12. **Tests automatiques** sur les fonctions critiques (ouverture, sorties, stop, règles) pour que les prochains correctifs ne cassent rien en silence.
13. **Risque par trade** : passer de 1 € à 3-5 € (0,3-0,5 %) seulement si le taux de réussite ≥ 55 % se confirme sur 30 trades du nouveau départ.

### P3 — avant tout passage en réel

14. **Validation statistique** (permutation, efficacité walk-forward), HTTPS sur le dashboard, réconciliation d'état au redémarrage, plafonds (100 € total, 20 €/trade, clé sans retrait, stop -10 €), et votre confirmation explicite. Rappel : avec 0,8 % taker Kraken palier 1, un aller-retour coûte 1,6 % pour un TP de 1,5 % : le réel n'a de sens qu'en maker (ordres limite) ou sur Revolut X (0,09 %).

---

## 8. Commandes (une ligne chacune, depuis Termius)

**A. Déployer tout** (inclut cerveau v3 et les correctifs d'aujourd'hui) :

```
cd ~/agent-ia && for f in paper_trading.py chat_naturel.py journal_erreurs.py registre_strategies.py dashboard_premium.py cerveau.py historique_prix.py gestion_risque.py nouveau_depart.py nettoyage.py; do wget -q -O $f https://raw.githubusercontent.com/2v5smkg85n-debug/agent-ia/main/$f; done && find ~/agent-ia -name "*.pyc" -delete && sudo systemctl restart paper_trading.service chat_naturel.service dashboard.service && echo DEPLOYE
```

**B. Nouveau départ à 1 000 €** (historique archivé, services arrêtés le temps de l'opération) :

```
cd ~/agent-ia && sudo systemctl stop paper_trading.service chat_naturel.service && python3 nouveau_depart.py --oui && sudo systemctl start paper_trading.service chat_naturel.service && python3 registre_strategies.py | head -8
```

**C. Nettoyage** (d'abord la simulation, puis `--go` si la liste vous convient) :

```
cd ~/agent-ia && python3 nettoyage.py
```
```
cd ~/agent-ia && python3 nettoyage.py --go
```

**D. Rendre le droit d'ouvrir à rsi_oversold** (optionnel, votre décision) :

```
cd ~/agent-ia && python3 registre_strategies.py droit rsi_oversold on "68 pct de reussite sur 44 trades, reactivee avec stop ATR" | head -6
```

**E. Vérifier que tout tourne** (après 10 minutes) :

```
cd ~/agent-ia && systemctl is-active paper_trading chat_naturel dashboard && grep -E "CERVEAU|REGLE|RISQUE|REGISTRE|ACHAT" paper_trading.log chat_naturel.log | tail -15
```

---

## 9. Trois décisions qui vous appartiennent

1. **rsi_oversold** : lui rendre le droit d'ouvrir (commande D) ou la garder en professeur ?
2. **Mode évolution** des objectifs de survie : le désactiver (l'IA reste vivante, elle arrête de muter) ?
3. **Sécurités en dur** (lundi, 6 cryptos, heures 14h/3h/11h) : les transformer en règles mesurées du journal, révisables, ou les garder figées ?

Sources citées : [Revolut X](https://www.revolut.com/revolut-x/) · [Kraken fee schedule](https://www.kraken.com/features/fee-schedule) · [Google AI rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) · [Google AI structured output](https://ai.google.dev/gemini-api/docs/structured-output) · [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) · [Étude chandeliers crypto 2026](https://ideas.repec.org/a/eee/reveco/v108y2026ics1059056026002716.html) · [TradingAgents, arXiv](https://arxiv.org/abs/2412.20138) · [Freqtrade protections](https://www.freqtrade.io/en/2024.1/includes/protections/) · [For Traders, gestion du risque](https://fortraders.com/blog/manage-risk-professional-trader) · [Bot versus Bot, papier vs réel](https://botversusbot.com/articles/paper-trading-vs-live-trading-crypto-bots-2026/) · [TradeAlgo, sur-apprentissage](https://www.tradealgo.com/trading-guides/ai-trading/machine-learning-backtesting-guide) · [Mannheim, heures de trading crypto](https://madoc.bib.uni-mannheim.de/72942/1/s11156-024-01304-1.pdf?rs=true&wid=) · [Quotas Gemini 2026 (GitHub)](https://github.com/sambhrantbisi-lab/AWS-SMARTHACKATHON/blob/main/GEMINI_RATE_LIMITS_2026.md) · [Quotas Gemini 2026 (Zenn)](https://zenn.dev/shinseitaro/books/crewai-hands-on/viewer/gemini-free-tier)
