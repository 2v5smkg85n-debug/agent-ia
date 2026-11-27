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
