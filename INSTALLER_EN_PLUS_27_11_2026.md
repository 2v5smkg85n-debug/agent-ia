# Ce qu'on peut installer de plus pour viser le bénéfice — 27 novembre 2026

Demande : trouver tout ce qui pourrait vraiment amener le bot à finir en bénéfice.
Ce document complète `IA_A_CONNECTER_27_11_2026.md` (les modèles d'IA) sans le répéter. Contraintes gardées : aucune clé, aucun abonnement, rien par Binance, aucune sécurité retirée.

## L'essentiel

1. **Aucune installation ne garantit un bénéfice.** Sur le marché à terme brésilien, 97 % des particuliers qui ont fait du day trading pendant plus de 300 jours ont perdu de l'argent ([Chague, De-Losso et Giovannetti](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101)). Sur les grandes plateformes crypto, une majorité d'utilisateurs a perdu sur ses bitcoins entre 2015 et 2022 dans presque tous les pays ([Banque des règlements internationaux](https://www.bis.org/publications/bulletin-69-crypto-shocks-and-retail-losses)). Le bot en est à 490 trades et −109,61 €.
2. **Ce qui manque au bot n'est pas une IA de plus, c'est de la preuve.** La porte ne juge qu'une dizaine de candidats par jour. La seule stratégie gagnante (`volume_spike`) repose sur un seul épisode de trois jours. À ce rythme il faut des mois pour trancher une seule question.
3. **L'installation la plus utile est donc un historique de plusieurs années et un rejeu des vraies stratégies du bot dessus.** Kraken le donne gratuitement. Tout le reste de la liste dépend de cette brique.
4. **Les frais pèsent autant que l'avantage mesuré.** Revolut X ne prend rien sur les ordres limite et 0,09 % sur les ordres au marché. C'est un réglage à tester, pas un logiciel à installer.

## Vue d'ensemble

| Rang | Quoi | À quoi ça sert | Poids | Verdict |
|---|---|---|---|---|
| 1 | Historique Kraken + rejeu des stratégies du bot | Obtenir en quelques heures les preuves que la porte mettrait des années à réunir | 9,5 Go à télécharger, ou appels KuCoin sans clé | À faire en premier |
| 2 | Garde-fous statistiques (ratio de Sharpe dégonflé, probabilité de surapprentissage, validation purgée) | Ne pas prendre un coup de chance pour une stratégie | Quelques dizaines de lignes, pas de bibliothèque lourde | Avec le rejeu |
| 3 | Entrées en ordre limite sur Revolut X | Diviser les frais et l'écart achat-vente | Aucun | À mesurer en observation |
| 4 | LightGBM | Filtrer les signaux une fois qu'il y a des milliers d'exemples | 3,5 Mo | Après le rejeu |
| 5 | Optuna | Chercher les bons réglages | Léger | Seulement sous les garde-fous du rang 2 |
| 6 | Signal de tendance multi-horizons | Le signal le mieux documenté trouvé dans cette recherche | Aucun | Professeur à tester dans le rejeu |
| — | Freqtrade, NautilusTrader, vectorbt, backtesting.py | Bots et moteurs de test complets | Lourd | Déconseillés ici (voir plus bas) |

## 1. L'historique complet de Kraken et le rejeu des vraies stratégies

**Ce qui existe**

- Kraken fournit des fichiers CSV de bougies pour chaque paire, du premier jour de cotation jusqu'au 30 septembre 2026, aux pas de 1, 5, 15, 60, 240, 720 et 1 440 minutes ([aide Kraken](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)).
- Le téléchargement complet est découpé en cinq parties d'environ 2 Go, avec les commandes Linux fournies ; des mises à jour trimestrielles existent en un seul fichier ([aide Kraken](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)).
- J'ai relevé la taille des cinq parties sur le serveur de Kraken : 9,55 Go au total. Le VPS a 44 Go libres ; il suffit d'en extraire les bougies d'une heure des paires en euros.
- Par l'interface de programmation, Kraken ne rend que les 720 dernières bougies, sans retour en arrière possible ([documentation Kraken](https://docs.kraken.com/api-reference/market-data/get-ohlc-data.md)). En bougies d'une heure, cela fait 30 jours : c'est pour cela que le bot ne peut pas se tester plus loin aujourd'hui.
- Solution plus légère : KuCoin, que le bot interroge déjà, rend jusqu'à 1 500 bougies par appel public et se parcourt page par page dans le temps ([documentation KuCoin](https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines)).

**Ce que ferait le rejeu**

- Il appelle le code du bot tel qu'il est pour les stratégies calculées sur des bougies (`volume_spike`, `rsi_oversold`, `pattern_reversal`, `donchian_breakout`, `tsmom`), bougie par bougie, sur plusieurs années, hausses et krachs compris.
- Même jugement que le laboratoire : entrée à l'ouverture de la bougie suivante, stop, objectif, limite de temps, frais déduits, résultat en R, intervalle calculé par jour.
- Il sort aussi le résultat épisode par épisode. La règle fixée pour `volume_spike` (gagnante sur au moins trois épisodes de garde de baisse armée) serait tranchée tout de suite au lieu d'attendre les prochaines chutes.
- Aujourd'hui, `backtest_moteur.py` teste quatre stratégies génériques sur 365 jours, pas celles que le bot utilise.

**Pourquoi c'est urgent pour `volume_spike`**

- Une étude sur les cryptos trouve que, contrairement aux actions, un volume anormalement élevé annonce des rendements futurs plus faibles tant que la vente à découvert est difficile ([Garfinkel, Hsiao et Hu](https://iro.uiowa.edu/esploro/outputs/workingPaper/The-Negative-Abnormal-Volume-Return-Relation/9984414059502771)). La page ne précise ni l'horizon ni l'échantillon.
- C'est l'inverse de ce que le bot a mesuré sur 88 candidats (+0,449 R). Les deux peuvent être vrais (horizon et définition différents), mais cela interdit d'ouvrir la garde de baisse sur la foi d'un seul épisode.

**Limites du rejeu**

- Les bougies ne contiennent ni l'écart achat-vente ni le flux d'ordres : les filtres qui s'en servent ne sont pas rejouables.
- La stratégie `ia_autonome` dépend du modèle de langage et ne se rejoue pas.
- Ce sont les prix de Kraken, pas ceux de Revolut X.

## 2. Les garde-fous contre les faux résultats

Plus on teste de variantes, plus on en trouve une qui gagne par hasard. Trois outils reconnus :

- **Ratio de Sharpe dégonflé** : il corrige le gonflement des performances dû au choix du meilleur essai parmi beaucoup et aux rendements non normaux ([Bailey et López de Prado](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)).
- **Probabilité de surapprentissage du backtest** : un cadre général pour l'estimer, par validation croisée combinatoire ([Bailey, Borwein, López de Prado et Zhu](https://escholarship.org/uc/item/4w1110bb)).
- **Validation croisée combinatoire purgée** : elle retire de l'apprentissage les observations qui chevauchent le test et celles qui le suivent immédiatement ; la bibliothèque skfolio, sous licence BSD, la fournit ([skfolio](https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html)).

Preuves que cela compte en crypto :

- Sur 10 cryptos pendant les deux krachs de mai-juin 2022, les agents les moins surappris ont eu un meilleur rendement que les plus surappris et que l'indice de marché ([arXiv 2209.05559](https://arxiv.org/html/2209.05559)).
- Sur 14 919 règles techniques, la prévisibilité était significative dans l'échantillon mais nulle pour le Bitcoin hors échantillon ([Hudson et Urquhart](https://link.springer.com/article/10.1007/s10479-019-03357-1)).

Verdict : ce sont des formules, à écrire directement dans le rejeu. Pas besoin d'installer skfolio pour commencer.

## 3. Payer moins : les ordres limite sur Revolut X

- Revolut X facture 0 % au teneur de marché (ordre limite qui attend) et 0,09 % au preneur (ordre au marché), pour l'entité européenne ([barème Revolut X](https://cdn.revolut.com/terms_and_conditions/pdf/crypto_exchange_fees_95c20100_1.0.1_1790578423_en.pdf)).
- Le bot compte 0,2 % de frais aller-retour. Exemple de mon calcul : avec un stop à 3 %, cela fait 0,07 R par trade, soit autant que le R moyen net de tous les candidats jugés (+0,059).
- Une étude sur le Bitcoin en bougies d'une heure (2018-2026) conclut que les stratégies d'apprentissage automatique s'effondrent dès 0,10 % de coût parce qu'elles tradent trop souvent ([arXiv 2606.00060](https://arxiv.org/html/2606.00060)).
- Le revers : un ordre limite n'est pas toujours servi, et il l'est plus souvent quand le prix continue de baisser. Il faut donc le mesurer en observation (entrée virtuelle au prix acheteur, servie seulement si le marché y revient) avant de changer quoi que ce soit.
- Pour le passage en réel sur Kraken : le barème enregistré dans le bot en octobre donne 0,40 % et 0,80 % au premier palier de Kraken Pro. Je n'ai pas pu le revérifier aujourd'hui ([la page de Kraken](https://www.kraken.com/features/fee-schedule) renvoie à un barème séparé). Si c'est toujours le cas, le réel sur Kraken coûterait plusieurs fois plus cher que sur Revolut X.

## 4. LightGBM, quand il y aura assez d'exemples

- Installation : 3,5 Mo, processeur seul, Python 3.10 ou plus ([PyPI](https://pypi.org/project/lightgbm/)). Rien à voir avec les 1,4 Go de TabPFN.
- Les modèles à arbres restent la référence sur des tableaux de taille moyenne, autour de 10 000 lignes ([Grinsztajn et coauteurs](https://arxiv.org/html/2207.08815)).
- Dans l'étude sur le Bitcoin horaire, XGBoost (même famille) fait mieux que les deux réseaux de neurones, mais l'écart ne résiste pas aux tests statistiques après correction ([arXiv 2606.00060](https://arxiv.org/html/2606.00060)).
- Sur l'ensemble des cryptos, le gain apporté par des modèles plus complexes est limité : la prévisibilité vient de quelques caractéristiques simples (prix, illiquidité, momentum) et se concentre sur les petites cryptos difficiles à traiter ([Cakici et coauteurs](https://ideas.repec.org/a/eee/finana/v94y2024ics1057521924001765.html)).
- Usage prévu : le « méta-étiquetage », une couche qui se pose sur une stratégie de base pour écarter les faux signaux et régler la taille des positions ([Joubert](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4032018)).
- Verdict : inutile aujourd'hui. Avec 283 exemples, aucun modèle n'apprend (TabPFN classe à l'envers, la régression fait 0,485). Avec les milliers d'exemples du rejeu, il devient le bon outil.

## 5. Optuna, seulement sous garde-fous

- Outil de recherche automatique de réglages, licence MIT, Python 3.10 ou plus ([dépôt Optuna](https://github.com/optuna/optuna)).
- Chaque essai supplémentaire augmente le risque de trouver un réglage qui ne gagne que sur le passé. Il ne vaut quelque chose qu'avec le rang 2 en place.

## 6. Un signal à tester : la tendance sur plusieurs horizons

- Un facteur de tendance qui combine prix et volume sur plusieurs horizons prédit les rendements sur plus de 3 000 cryptos, résiste aux coûts de transaction et tient sur les grandes cryptos liquides ([Fieberg et coauteurs, JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178)).
- Des règles techniques simples, sélectionnées après coûts et correction des essais multiples, peuvent battre la détention simple du Bitcoin hors échantillon, surtout en rapport rendement-risque ([Deprez et Frömmel](https://ideas.repec.org/a/eee/reveco/v93y2024ipbp858-874.html)).
- Verdict : à coder comme une stratégie de plus dans le rejeu, puis comme professeur sans droit d'ouvrir. Le bot a déjà `donchian_breakout` et `tsmom` dans cette famille ; ils n'ont que 4 candidats jugés, tous perdants, ce qui ne prouve rien.

## Ce que je déconseille d'installer

- **Freqtrade** : un bot complet avec test historique et optimisation, mais Revolut X n'est pas dans ses places de marché (Kraken y est), et ses auteurs le présentent comme un logiciel à but éducatif ([dépôt Freqtrade](https://github.com/freqtrade/freqtrade/)). Ce serait un second bot à entretenir, et il ne testerait pas le code du vôtre.
- **NautilusTrader** : demande Python 3.13 à 3.15 ([dépôt NautilusTrader](https://github.com/nautechsystems/nautilus_trader)) ; le VPS est en 3.10.
- **vectorbt et backtesting.py** : rapides, mais il faudrait réécrire les stratégies dans leur format, donc tester une copie et non ce qui tourne. Licences à surveiller : Apache 2.0 avec clause « Commons » pour l'un ([dépôt vectorbt](https://github.com/polakowo/vectorbt)), AGPL-3.0 pour l'autre ([dépôt backtesting.py](https://github.com/kernc/backtesting.py)).
- **Un modèle de langage plus gros ou un de plus** : voir le document de ce matin, les essais publics sont négatifs.
- **Kronos et TTM** : toujours repoussés, pour la même raison que TabPFN n'apprend rien (trop peu de données jugées).

## Ordre proposé

1. Le rejeu sur l'historique, en lecture seule, à basse priorité, avec son interrupteur. Il ne donne aucun droit à personne.
2. Les garde-fous statistiques dans le même module.
3. La mesure des entrées en ordre limite, en observation dans le simulateur Kraken.
4. LightGBM sur les exemples du rejeu, comparé à TabPFN et à la régression.
5. Optuna en dernier, s'il reste quelque chose à régler.

Règle à fixer avant de lancer le rejeu : une stratégie n'obtient ou ne garde le droit d'ouvrir que si elle est positive, frais déduits, sur plusieurs épisodes distincts du passé, puis confirmée par la porte en conditions réelles. Un bon résultat du rejeu seul ne suffit pas.

## Ordre de grandeur, pour rester lucide

Calcul de ma part, avec un avantage supposé et non mesuré : à 1 € de risque par trade, un avantage de +0,1 R et 6 ouvertures par jour donnent 0,60 € par jour, environ 18 € par mois. L'intérêt de ces étapes est de savoir si un avantage existe avant d'augmenter la mise, pas de gagner beaucoup tout de suite.

## Limites de ce document

- Rien de ce qui précède n'est installé ni testé sur le VPS. Les tailles viennent des pages citées et des serveurs de téléchargement.
- Les études citées sont lues par leur résumé ; plusieurs portent sur le Bitcoin seul ou sur des horizons différents de ceux du bot.
- Un test sur le passé ne prédit pas l'avenir. Il sert surtout à éliminer ce qui ne marchait déjà pas.
