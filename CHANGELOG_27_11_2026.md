# Changements du 27 novembre 2026 — le professeur TabPFN, en observation seule

## En une phrase

Une IA de plus regarde chaque candidat de la porte et lui donne une note ; ses notes sont comparées aux résultats. Elle ne bloque rien, n'ouvre rien, et le service de trading n'a pas été modifié.

## Ce que le VPS permet

Mesuré le 27/11 : 6 cœurs, 11 Go de mémoire dont 5,8 Go disponibles, 44 Go de disque libres. C'est suffisant pour TabPFN (mesuré de mon côté : 0,6 à 0,8 Go de mémoire, 1,4 Go de disque, une dizaine de secondes par journée notée sur 2 cœurs).

## Ce qui a été ajouté

| Fichier | Rôle |
|---|---|
| `professeur_tabpfn.py` | Le professeur : lit ce que la porte écrit déjà, note, fait le bilan |
| `installer_professeur_tabpfn.sh` | Installation en une commande, désinstallation en une commande |
| `page_porte.py` | Une section « Professeur TabPFN — observation seule » sur la page /porte |
| `tests/test_professeur_tabpfn.py` | 6 tests, dont « il ne voit jamais le futur » |

## Comment il travaille

- **Matière première** : `porte_entree_log.jsonl` (une vingtaine de mesures par candidat : tendance lente, régime, ADX, flux d'ordres, liquidité, chaleur, cadence, stratégie, heure) et `porte_entree_eval.jsonl` (ce que le trade aurait donné 8 h après). Aucune nouvelle source, aucune clé.
- **Une ligne par crypto, stratégie et heure** : un signal qui insiste pendant une heure ne compte qu'une fois.
- **Étiquette** : gagnant si le résultat en R, frais déduits, est positif.
- **Pas de triche avec le temps** : pour noter les candidats du jour J, le modèle ne voit que les candidats datés d'au moins 12 h avant J 00:00 UTC. Une note écrite n'est jamais recalculée.
- **Un témoin** : une régression logistique simple est notée sur les mêmes données. Si TabPFN ne fait pas mieux, le bilan le dit.
- **Tant qu'il y a moins de 150 exemples** (ou moins de 10 gagnants ou 10 perdants), il ne note pas : il apprend.

## Le verdict, écrit à l'avance

- moins de 200 candidats notés ou de 10 jours : « trop peu de recul » ;
- AUC d'au moins 0,55 et borne basse du R net de ses « retenus » au-dessus de 0 (intervalle calculé par jour) : « prouvé en observation » ;
- sinon : « pas de preuve ».

« Retenu » = note supérieure au taux de réussite de son jeu d'apprentissage + 0,05.

Même « prouvé », il ne reçoit aucun droit tout seul. Lui donner un rôle (par exemple nourrir l'IA avec sa note) reste une décision à prendre ensemble, sur ses chiffres.

## Pourquoi il ne peut pas casser le bot

- Il tourne dans son propre processus, lancé par un minuteur à part (toutes les 3 h), priorité basse, 2 cœurs et 2,5 Go de mémoire au plus, 15 minutes au plus.
- Ses bibliothèques sont dans `~/agent-ia/.tabpfn_libs`, un dossier à part : celles du bot ne sont ni mises à jour ni remplacées.
- `paper_trading.py`, `porte_entree.py`, `journal_erreurs.py`, `kraken_paper.py` et `stop_atr.py` ne l'importent pas (un test le vérifie).
- S'il est absent, en panne ou trop lent, il écrit l'erreur dans son fichier d'état et rien d'autre ne change.
- Une fois les poids téléchargés (29 Mo), il ne fait plus aucun appel réseau.

## Interrupteurs

| Action | Commande |
|---|---|
| Voir le bilan | `cd ~/agent-ia && python3 professeur_tabpfn.py; echo fin` |
| Voir les données | `cd ~/agent-ia && python3 professeur_tabpfn.py donnees; echo fin` |
| Couper | `PROF_TABPFN=0` dans `.env` |
| Désinstaller | `cd ~/agent-ia && bash installer_professeur_tabpfn.sh desinstaller; echo fin` |

## Ce qui a été vérifié, et ce qui ne l'est pas

- Vérifié de mon côté : installation avec la même version de `pip` que le VPS, démarrage du modèle sans compte ni clé, notation complète sur des données inventées (1 021 candidats, 34 jours, 349 s sur 2 cœurs), affichage sur la page, 110 tests.
- **Non vérifié** : le comportement sur les vraies données du VPS. Je ne connais pas le nombre de candidats jugés ; s'il y en a moins de 150, il restera en apprentissage.
- Sur les données inventées, le verdict était « prouvé » parce que j'y avais caché un signal. Cela prouve que la mécanique fonctionne, pas que le modèle trouvera quelque chose dans le marché.
- Les mesures de la porte décrivent surtout l'état du marché (BTC), commun à tous les candidats d'une même journée. Le nombre de preuves indépendantes est plus proche du nombre de jours que du nombre de candidats ; c'est pour cela que l'intervalle est calculé par jour.
- Le bilan est relu toutes les 3 h : à force de regarder, un « prouvé » peut apparaître par chance. Il faudra qu'il tienne plusieurs semaines.

## Licence

Poids TabPFN v2 : licence Prior Labs (Apache 2.0 avec obligation de citation), [dépôt TabPFN](https://github.com/PriorLabs/TabPFN). Les versions 2.5 et suivantes sont réservées à un usage non commercial et ne sont pas utilisées.

---

# Ajout du soir — le rejeu historique : tout ce que l'étude proposait, d'un seul coup

## En une phrase

Les vraies stratégies du bot sont rejouées sur huit ans de bougies Kraken, avec les garde-fous statistiques, la mesure des ordres limite, LightGBM, Optuna et un signal de tendance multi-horizons. Tout est en observation seule : rien n'ouvre, rien ne bloque, aucun réglage n'est modifié, le service de trading n'est ni touché ni redémarré.

## Ce qui a été ajouté

| Fichier | Rôle |
|---|---|
| `rejeu_historique.py` | Télécharge les bougies, rejoue les stratégies avec le code du bot, écrit le bilan |
| `rejeu_modeles.py` | LightGBM (filtre appris) et Optuna (réglages), dans un processus à part |
| `installer_rejeu.sh` | Installation et lancement en une commande, désinstallation en une commande |
| `tests/test_rejeu_historique.py` | 22 tests (134 au total avec les anciens) |

## Les six briques de l'étude

| Brique | Ce qui est fait |
|---|---|
| Historique Kraken | Bougies 1 h en euros de 37 cryptos, de 2018 au 30/09/2026, lues directement dans l'[archive officielle de Kraken](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data) : 78 Mo téléchargés au lieu de 9 Go |
| Rejeu des vraies stratégies | `analyser_actif`, `stop_atr` et `strategies_tendance` du bot sont appelés tels quels, heure par heure, sans voir le futur |
| Garde-fous | Intervalle à 95 % par jour, [Sharpe dégonflé](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551), [probabilité de surapprentissage](https://escholarship.org/uc/item/4w1110bb), résultat année par année et épisode de baisse par épisode |
| Ordres limite | Pour chaque signal : ordre au cours et ordre 0,25 ATR plus bas, valables 3 h, frais 0,1 % au lieu de 0,2 % |
| LightGBM | Filtre appris en marche avant, année par année, avec 7 jours d'écart et une régression témoin |
| Optuna | 60 essais (52 réglages distincts) de stop, objectif et durée, vérifiés sur 12 mois jamais vus |
| Tendance multi-horizons | Nouveau signal `tendance_multi` (9 horizons), rejoué à côté de `donchian_breakout` et `tsmom` |

## Ce que le rejeu a donné de mon côté

Mesuré dans mon environnement de test le 27/11 sur les 37 cryptos : 1 797 957 bougies, 459 105 trades virtuels, 5,6 minutes sur 2 cœurs. Le VPS doit donner les mêmes chiffres, c'est à confirmer par sa propre sortie.

| Stratégie | Trades | R avant frais | R net [intervalle 95 %] | Années gagnantes | Verdict |
|---|---|---|---|---|---|
| `pattern_reversal` | 64 022 | −0,002 | −0,116 [−0,14 ; −0,09] | 0/9 | perdante |
| `volume_spike` | 49 884 | −0,003 | −0,120 [−0,15 ; −0,09] | 0/9 | perdante |
| `rsi_oversold` | 38 254 | −0,039 | −0,158 [−0,19 ; −0,12] | 0/9 | perdante |
| `macd_cross` | 54 846 | +0,017 | −0,098 [−0,13 ; −0,07] | 0/9 | perdante |
| `donchian_breakout` | 6 526 | +0,087 | −0,003 [−0,07 ; +0,07] | 5/9 | pas de preuve |
| `tendance_multi` | 1 805 | +0,092 | −0,009 [−0,12 ; +0,10] | 4/8 | pas de preuve |
| `tsmom` | 2 756 | −0,027 | −0,128 [−0,22 ; −0,03] | 2/9 | perdante |

Les sept autres stratégies techniques sont entre −0,10 et −0,18, toutes perdantes ; aucune des dix stratégies principales n'a une seule année gagnante sur neuf.

- **Le problème est les frais, pas le sens des signaux.** Avant frais, les dix stratégies techniques principales sont à zéro (entre −0,04 et +0,02 R) : elles ne prédisent rien, et les frais de 0,2 % par aller-retour coûtent environ 0,12 R par trade.
- **`volume_spike` en marché baissier** : −0,146 [−0,18 ; −0,11], gagnante sur 2 épisodes de baisse sur 20, aucun avec confiance. La règle fixée (gagnante sur au moins trois épisodes distincts avant de passer la garde de baisse) n'est pas remplie. Ses +0,449 R sur 7 jours en réel ne pèsent pas lourd face à huit ans.
- **Ordres limite** : ils sont servis 86 à 91 % du temps et font gagner 3 à 4,5 R pour 100 signaux, mais le résultat reste négatif. Les signaux que l'ordre limite manque sont justement les meilleurs (+0,3 à +0,5 R s'ils avaient été pris au marché).
- **LightGBM** : pouvoir de tri 0,526 (0,50 = hasard ; témoin 0,516). Les trades qu'il retient perdent moins (−0,039 [−0,09 ; +0,01] contre −0,116) mais ne gagnent pas.
- **Optuna** : le meilleur réglage trouvé (stop 4 × ATR, objectif 4 × stop, 72 h) fait −0,094 [−0,20 ; +0,01] sur les 12 mois jamais vus. Verdict : ne rien changer.
- **Tendance** : `donchian_breakout` et `tendance_multi` sont les seules à avoir un avantage avant frais (+0,09 R), que les frais annulent.

## Ce que cela veut dire

Sur huit ans, aucune des stratégies du bot ne gagne après frais, et aucun des outils ajoutés (ordres limite, filtre appris, réglages) ne suffit à inverser cela. Les deux seules pistes où il reste quelque chose à mesurer sont le suivi de tendance (avantage avant frais, à rejouer avec des frais plus bas et le stop suiveur) et les frais eux-mêmes. Rien de tout cela ne justifie de passer en réel.

## Limites

- Bougies sans carnet d'ordres ni écart achat-vente ; prix Kraken en euros, pas Revolut X.
- Décisions prises sur bougies closes ; la porte d'entrée n'est pas rejouée (stratégies nues).
- `ia_autonome` et les professeurs externes ne sont pas rejouables ; le stop suiveur de tendance n'est pas rejoué.
- Seuils actuels de `strat_params.json` ; l'historique s'arrête au 30/09/2026.
- Un signal est ignoré si plus de 6 heures sur les 24 dernières n'ont eu aucun échange.
- Non vérifié : l'installation sur le VPS lui-même.

## Pourquoi il ne peut pas casser le bot

- Service à part (`rejeu-historique`), un seul passage, priorité la plus basse, 2 cœurs et 2,5 Go au plus. Pas de minuteur.
- Bibliothèques dans `~/agent-ia/.rejeu_libs` (250 Mo) : celles du bot ne sont ni mises à jour ni remplacées.
- `paper_trading.py` n'est pas importé ; les modules du bot utilisés sont lus sans écrire dans aucun de ses fichiers ; le réseau est coupé dès le téléchargement terminé.
- Il n'écrit que `rejeu_data/`, `rejeu_etat.json`, `rejeu_bilan.txt`, `rejeu_bilan.json`, `rejeu_modeles.json` et `rejeu_journal.log`.

## Interrupteurs

| Action | Commande |
|---|---|
| Voir l'avancement | `cd ~/agent-ia && python3 rejeu_historique.py etat; echo fin` |
| Voir le bilan | `cd ~/agent-ia && python3 rejeu_historique.py bilan; echo fin` |
| Bilan année par année | `cd ~/agent-ia && python3 rejeu_historique.py bilan detail; echo fin` |
| Relancer | `sudo systemctl start --no-block rejeu-historique.service; echo fin` |
| Couper | `REJEU=0` dans `.env` |
| Désinstaller | `cd ~/agent-ia && bash installer_rejeu.sh desinstaller; echo fin` |
