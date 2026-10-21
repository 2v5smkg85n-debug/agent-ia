# Toutes les améliorations encore possibles — 21 octobre 2026

Point de départ honnête : le rapport du 18 octobre listait 25 améliorations ; 21 ont été installées le jour même (routeur LLM, porte d'entrée à 8 filtres, stop 2×ATR avec objectif 2:1 et barrière 24 h, mémoire épisodique, registre bayésien, triple barrière, méta-modèle, SQLite, WebSocket Kraken, hikkake, glissement, tests). Les 4 restantes sont des décisions humaines (clé Revolut X, réel, HTTPS, crédits OpenRouter). Le 19 octobre, les premières ouvertures de l'IA (ETH 61 €, BTC 92 €) ont fonctionné, puis le conflit d'écriture entre les deux services a été corrigé.

Ce qui manque aujourd'hui n'est donc plus une liste de fonctionnalités : c'est la **mesure** de ce que ces 21 fonctionnalités font vraiment, plus une dizaine d'incohérences héritées et quelques idées neuves. Ce rapport est classé dans cet ordre.

---

## 1. Installé aujourd'hui : la porte se juge elle-même (commit 21e7cbc)

La porte bloque la majorité des signaux et notait seulement le premier filtre qui bloquait. Personne ne vérifiait ensuite ce que le trade bloqué aurait donné. C'est exactement le trou décrit par la méthode « post-rejection follow-up sampling » : enregistrer l'état d'un candidat rejeté et revenir mesurer ce qui s'est passé ensuite ; dans l'étude, la logique de stop s'est révélée trop sensible, une part notable des positions stoppées remontant ensuite au-dessus de seuils significatifs ([MPRA, 2026](https://mpra.ub.uni-muenchen.de/128870/1/MPRA_paper_128870.pdf)).

Maintenant :
- chaque passage à la porte enregistre le **verdict de chacun des 8 filtres** (passe / bloquerait / sauté), pas seulement le premier qui bloque ;
- 8 h plus tard, chaque passage (ouvert ou bloqué) est rejoué sur les bougies 1h : objectif 2×stop touché d'abord, stop d'abord, ou neutre, exprimé en R (1 R = le risque d'un trade) ;
- un bilan par filtre dit s'il a **évité** plus de R qu'il n'en a **coûté** : « utile », « à revoir », ou « trop peu de cas » (< 10). Rien n'est retiré automatiquement, conformément à votre règle.

Où le voir : page `/porte` du dashboard (nouvelle section) ou `python3 porte_entree.py bilan`. C'est la source de vérité pour toutes les décisions de la section 4 : on ne touche à un filtre que quand ce tableau le justifie avec ≥ 10 cas.

Effet secondaire utile : le bot apprend sur **tous** les candidats (une vingtaine par jour) au lieu des 1 ou 2 trades réellement ouverts. Dix fois plus de données, zéro risque.

---

## 2. Ce qui reste incohérent dans le code (à corriger, sans débat)

| # | Problème | Où | Pourquoi ça compte |
|---|---|---|---|
| 1 | **Quatre systèmes d'heures qui se contredisent** : `HEURES_FAIBLE_LIQUIDITE` 14h/3h/11h ; `HEURES_FORT_VOLUME` qui donne un bonus à 12-13h et 16-17h ; porte 13h-15h ; journal « heures perdantes » 13h-14h | paper_trading.py l.70-73, porte, journal | Le bonus « fort volume » favorise des heures que la porte et le journal considèrent perdantes. Une seule table, apprise par le journal, révisée chaque semaine |
| 2 | Liste noire en dur de 6 cryptos (LDO, ADA, DOT, PEPE, AVAX, BNB) et lundi interdit | paper_trading.py l.1023-1029 | Bilan de 211 trades jamais réévalué ; le registre bayésien sait maintenant juger par crypto. À convertir en règles mesurées |
| 3 | `OBJECTIFS_ANNUES = [10 000, 100 000, …]` + `_verifier_evolution()` | chat_naturel.py l.149, l.359 | Un objectif x10/an non atteint déclenche une « évolution » : c'est la source des erreurs reproduites. À désactiver (l'IA reste vivante) |
| 4 | `MAX_TRADES_PAR_JOUR = 5` ne s'applique qu'au chemin bot | paper_trading.py l.65 | Le chemin IA n'a pas de plafond journalier propre (la chaleur de portefeuille limite à 2-3 positions, mais pas le nombre d'ouvertures/jour) |
| 5 | Deux services écrivent le même `paper_trading.json` | paper_trading + chat_naturel | Corrigé par fusion à la sauvegarde le 19/10, mais c'est un pansement : un seul écrivain (paper_trading) et une file de demandes d'ouverture pour chat_naturel supprime la classe de bug |
| 6 | Caps durs TP 1,5 % / SL 0,8 % encore présents pour les positions sans `tp_risque` | paper_trading.py l.1879-1881 | Les positions du chemin bot restent limitées à 1,5 % alors que le stop ATR peut aller à 3 % : ratio < 1:1 possible |
| 7 | Historique 1 min téléchargé depuis Binance Vision | donnees_1m.py | Vous avez dit ne pas vouloir passer par Binance. Ce sont des fichiers publics sans compte ni clé, mais c'est à vous de confirmer. Alternative : bougies Kraken via l'API publique (plus courtes, 720 par appel) |
| 8 | Fournisseurs LLM publics « sans clé » (OVH, LLM7, Pollinations) | llm_router.py | Conformes à « pas de nouvelle clé », mais vos dossiers d'analyse (symboles, indicateurs, positions virtuelles) sortent vers des services tiers non garantis. `LLM_LIBRE=0` les coupe si vous préférez |
| 9 | `try/except` silencieux par dizaines | partout | Quatre bugs morts en silence trouvés le 17/10 ; il y en a d'autres. Journaliser l'exception dans les chemins critiques |
| 10 | Méta-modèle inactif tant que < 150 exemples étiquetés et AUC ≥ 0,55 | meta_modele.py | Normal, mais il faut lancer `etiquetage_triple_barriere.py` sur les 403 trades archivés pour qu'il ait une chance d'apprendre |
| 11 | Scans Perplexity « RSI < 35 sur 10 actifs » | automatisation | Redondants avec le bot (qui a RSI + 8 filtres) et ne lui parlent pas. À reconvertir (section 5, idée 6) ou arrêter |
| 12 | Dashboard HTTP, token dans l'URL | dashboard | Suffisant en virtuel, bloquant avant tout réel |

---

## 3. Ce que vos données disent de l'avantage réel

Trois faits qui bornent tout « boost » :

1. **Le bot sait sortir, pas entrer.** Sur 403 trades, les sorties intelligentes (TP, TP partiel, sortie pattern, stop suiveur, live-exit) totalisent +153 € ; les 206 stops, -238 €. Les 21 améliorations du 18/10 visent presque toutes l'entrée et le stop : c'est le bon endroit.
2. **Le risque est à 1 € par trade sur 1 000 €** (0,1 %). Avec un objectif 2:1 et 50 % de réussite, l'espérance est de 0,5 € par trade. Même parfait, le bot ne peut pas « booster » le résultat en euros sans augmenter le risque par trade. Les pros sont entre 0,5 et 2 % ; la route raisonnable est 1 € → 3 € → 5 € (0,5 %) uniquement quand la borne basse de l'intervalle bayésien à 90 % du registre dépasse le point mort frais compris, sur ≥ 30 trades indépendants.
3. **Le bot est acheteur uniquement, filtré par la tendance lente de BTC.** Quand BTC passe sous son EMA 84 jours, la porte ferme tout. C'est voulu et sain, mais cela signifie des semaines sans trade en marché baissier. La seule alternative sans vente à découvert (impossible en spot Revolut X) est une stratégie de rebond (rsi_oversold) à risque réduit, autorisée seulement si le bilan contrefactuel du filtre « tendance lente » montre qu'il coûte plus qu'il n'évite. À mesurer d'abord.

Sur la gestion de position, une idée populaire à **ne pas** installer : passer le stop à l'équilibre après +1 R. Sur une simulation à cible 3 R / stop 1 R, cette règle fait passer le taux de réussite de 30 % à 20 % et réduit l'espérance de 44 % ([Conflux Method](https://confluxmethod.com/learn/lab/breakeven-stop)). Votre stop suiveur actuel (déclenché sur un pic de gain) est mieux conçu que ça ; laissez-le.

---

## 4. Améliorations à faire, par priorité

### P0 — cette semaine, sans décision à prendre

1. **Déployer le bilan contrefactuel** (fait, commande en section 6) et le laisser accumuler 7 jours.
2. **Étiqueter les 403 trades archivés** (`python3 etiquetage_triple_barriere.py`) pour donner au méta-modèle ses 150 premiers exemples.
3. **Journaliser les exceptions** dans `ouvrir_position`, `verifier_sorties`, `preparer_entree`, `cerveau.decider` (une ligne par `except`).
4. **Un seul écrivain du portefeuille** : chat_naturel dépose ses demandes d'ouverture dans `demandes_ouverture.jsonl`, paper_trading les exécute au tick suivant. Fin définitive des positions effacées.

### P1 — après 7 jours de données contrefactuelles

5. **Unifier les heures** : supprimer `HEURES_FAIBLE_LIQUIDITE` et `HEURES_FORT_VOLUME`, garder la porte (fenêtres) alimentée par la table horaire du journal (net par tranche sur 60 jours, ≥ 10 trades par tranche). Décision sur le tableau `/porte`, pas sur des constantes de septembre.
6. **Convertir la liste noire et le lundi** en règles du journal, révisables ; le registre bayésien juge chaque crypto avec un intervalle.
7. **Supprimer le caps TP 1,5 % pour toutes les positions** : toute ouverture passe par `stop_atr` (objectif = 2 × stop), chemin bot compris.
8. **Plafond journalier commun** (bot + IA) : 4 ouvertures/jour, réglable `MAX_OUVERTURES_JOUR`.
9. **Désactiver le mode évolution** et retirer `OBJECTIFS_ANNUES` (avec votre accord explicite).

### P2 — intelligence du cerveau (quand les quotas le permettent)

10. **Vote de plusieurs analystes** : au lieu d'un analyste puis un critique, interroger 3 fournisseurs en parallèle (Groq, OVH, Gemini) avec le même dossier et ne proposer un achat que si ≥ 2 sur 3 disent ACHAT avec confiance ≥ seuil. Sur des tâches de classification, un ensemble à vote majoritaire a amélioré le F1 jusqu'à 65 % par rapport au meilleur modèle seul ([arXiv 2511.15714](https://arxiv.org/html/2511.15714v1)). Coût : 2 appels de plus par candidate, absorbable par le routeur (le cerveau n'analyse que 1 à 3 candidates par cycle).
11. **Mémoire des réussites, pas seulement des échecs** : la mémoire épisodique montre ≥ 2 pertes parmi 5 cas similaires ; ajouter systématiquement le cas gagnant le plus proche, pour que l'analyste raisonne par contraste (ce qui différenciait le gagnant du perdant).
12. **Taux de financement des perpétuels Kraken comme contexte** (pas comme signal) : l'endpoint `/historical-funding-rates?symbol=PF_BTCUSD` est public, sans authentification ([Kraken Developers](https://docs.kraken.com/api-reference/historical-funding-rates/historical-funding-rates)). Un financement très positif = foule acheteuse à effet de levier = achat au sommet probable ; à mettre dans le dossier de l'analyste et comme feature du méta-modèle. Aucune clé, aucun compte.
13. **Force relative par rapport à BTC** dans la présélection : préférer, à signal égal, la crypto qui surperforme BTC sur 7 jours (ratio alt/BTC en hausse). Les études de momentum crypto construisent leurs signaux sur des EMA courte/longue normalisées par la volatilité pour comparer des actifs entre eux ([Vilnius University, BATP](https://www.journals.vu.lt/BATP/en/article/download/44540/42590/138419)). C'est un tri, pas un filtre : il ne bloque rien.
14. **Régime par vote de modèles** : le régime actuel (ADX + percentile ATR) est une règle ; un classifieur de régime combinant HMM et arbres votants, nourri d'indicateurs techniques et macro, est la direction prise par la recherche récente ([Data Science in Finance and Economics, 2025](https://www.aimspress.com/article/doi/10.3934/DSFE.2025019)). À faire seulement quand les bougies 1 min sont là et que le méta-modèle est actif.

### P3 — avant le réel (décisions humaines)

15. Validation statistique (permutation p < 0,05, efficacité walk-forward > 0,5) sur ≥ 100 trades indépendants ; HTTPS (Caddy) ; plafonds (100 € total, 20 €/trade, clé sans retrait, stop -10 €) ; Revolut X seulement (0,09 % taker) : avec 0,8 % taker Kraken palier 1, un aller-retour coûte 1,6 % pour un objectif de 1,5-2 %.

---

## 5. Idées neuves à coût nul (hors code du bot)

1. **Conseil de révision hebdomadaire automatisé** : une automatisation Perplexity qui lit chaque dimanche `/api/porte` et `/api/cerveau`, résume le bilan contrefactuel, la calibration du cerveau et le registre, et propose au plus 3 changements de paramètres, chacun justifié par ≥ 10 cas, que vous validez ou non. C'est la gouvernance qui manquait : l'IA propose, vous tranchez, rien ne mute seul.
2. **Reconvertir les scans RSI** (automatisation actuelle, 2 fois par jour) en « calendrier macro + funding + dominance BTC », les trois informations que le bot ne calcule pas lui-même.
3. **Horaire du briefing** : il tourne à 06:00 UTC (08:00 Paris, 00:00 Querétaro). Dites l'heure locale voulue et je le règle.

---

## 6. Commandes (une ligne chacune)

**Déployer le bilan contrefactuel** :

```
cd ~/agent-ia && for f in porte_entree.py paper_trading.py page_porte.py; do wget -q -O $f https://raw.githubusercontent.com/2v5smkg85n-debug/agent-ia/main/$f; done && python3 -m py_compile porte_entree.py paper_trading.py page_porte.py && find ~/agent-ia -name "*.pyc" -delete && sudo systemctl restart paper_trading.service dashboard.service && echo DEPLOYE
```

**Étiqueter les 403 trades archivés pour le méta-modèle** :

```
cd ~/agent-ia && python3 etiquetage_triple_barriere.py 2>&1 | tail -8 && python3 meta_modele.py entrainer 2>&1 | tail -4
```

**Lire le bilan dans 24 h, puis chaque semaine** :

```
cd ~/agent-ia && python3 porte_entree.py bilan && python3 cerveau.py rapport 2>/dev/null | head -10 && python3 registre_strategies.py | head -8
```

**Couper les fournisseurs LLM publics si vous ne voulez pas que les dossiers sortent** (optionnel) :

```
cd ~/agent-ia && grep -q LLM_LIBRE .env || echo "LLM_LIBRE=0" >> .env && sudo systemctl restart chat_naturel.service paper_trading.service && echo COUPE
```

---

## 7. Décisions qui vous appartiennent

1. Désactiver le mode « évolution » et les objectifs x10 ?
2. Garder l'historique 1 min de Binance Vision (fichiers publics, sans compte) ou le remplacer par Kraken ?
3. Garder les fournisseurs LLM publics sans clé ?
4. Rendre le droit d'ouvrir à rsi_oversold en marché baissier (seulement si le bilan contrefactuel du filtre « tendance lente » le justifie) ?
5. Heure locale du briefing du matin ?

Sources citées : [MPRA, post-rejection follow-up sampling](https://mpra.ub.uni-muenchen.de/128870/1/MPRA_paper_128870.pdf) · [Conflux Method, stop à l'équilibre](https://confluxmethod.com/learn/lab/breakeven-stop) · [arXiv 2511.15714, ensembles LLM](https://arxiv.org/html/2511.15714v1) · [Kraken Developers, funding rates](https://docs.kraken.com/api-reference/historical-funding-rates/historical-funding-rates) · [Vilnius University, momentum crypto](https://www.journals.vu.lt/BATP/en/article/download/44540/42590/138419) · [DSFE 2025, régimes par vote HMM](https://www.aimspress.com/article/doi/10.3934/DSFE.2025019)
