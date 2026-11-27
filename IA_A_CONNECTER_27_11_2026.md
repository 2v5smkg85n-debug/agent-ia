# Les IA à connecter au bot — 27 novembre 2026

Demande : trouver, domaine par domaine, la meilleure IA à brancher sur le bot pour l'aider à évoluer, sans bug et sans panne.
Contrainte gardée : aucune nouvelle clé ni nouvel abonnement. Tout ce qui suit tourne sur le VPS, hors ligne.

## L'essentiel

1. Aucune IA de cette liste ne rend un bot rentable à elle seule. Les essais publics le montrent : sur le concours Alpha Arena, où de grands modèles ont tradé de l'argent réel sur Hyperliquid, 31 comptes sur 38 ont fini en perte ([TradingAgentStack](https://tradingagentstack.com/alpha-arena-results/)), et 4 modèles sur 6 étaient dans le rouge à la fin de la première saison ([Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)).
2. Trois branchements valent la peine, dans cet ordre : un modèle « tabulaire » pour estimer la chance qu'un trade gagne (TabPFN), un modèle de bougies en observation (Kronos ou Chronos-Bolt), un modèle de volatilité pour régler les stops (TTM).
3. Chaque IA ajoutée entre comme un professeur : elle donne un avis, le laboratoire la juge sans argent, elle n'a jamais le droit d'ouvrir. C'est la règle déjà posée pour les professeurs.
4. « Sans bug » ne vient pas d'une IA mais d'un contrôle automatique du code. Il est en place depuis aujourd'hui et a trouvé un bug dès son premier passage (voir la fin).

## Ce que le bot utilise déjà

| Rôle | Ce qui est branché | Où |
|---|---|---|
| Cerveau (décision, critique, chat) | Routeur : Groq, OpenRouter et Gemini s'il y a une clé, fournisseurs sans clé coupés par `LLM_LIBRE=0`, puis modèle local Ollama | `llm_router.py` |
| Modèle local | `qwen3.5:4b` (décision) et `llama3.2:3b` (critique) par défaut | `llm_router.py` |
| Sentiment | Indice Fear & Greed, sans clé | `sentiment_marche.py` |
| Mémoire | Recherche des trades passés similaires par vecteurs d'indicateurs, sans modèle | `memoire_episodique.py` |
| Professeurs | Traders Hyperliquid, avis seulement | `professeur_hyperliquid.py` |

Le modèle local par défaut est déjà le bon choix pour une machine de 8 Go : `qwen3.5:4b` est le modèle recommandé à ce niveau de mémoire, pour 3,4 Go de téléchargement ([Arct](https://www.arct.cloud/blog/best-ollama-models-cpu)).

## Les meilleures IA par domaine

### 1. Estimer la chance qu'un trade gagne — TabPFN

- **Ce que c'est** : un modèle de fondation pour les tableaux de données ([dépôt TabPFN](https://github.com/PriorLabs/TabPFN)).
- **Pourquoi lui** : sur processeur seul, il accepte jusqu'à 1 000 lignes pour les anciennes versions et 5 000 pour les récentes ([dépôt TabPFN](https://github.com/PriorLabs/TabPFN)). Les 490 trades du bot entrent donc sans carte graphique.
- **Licence** : les poids de TabPFN-2 sont sous licence Prior Labs (Apache 2.0 avec obligation de citation) ; les versions 2.5 et suivantes sont réservées à un usage non commercial ([dépôt TabPFN](https://github.com/PriorLabs/TabPFN)). Il faudrait donc TabPFN-2 pour un passage en réel.
- **Besoin** : Python 3.10 ou plus, ce qui est la version du VPS ([dépôt TabPFN](https://github.com/PriorLabs/TabPFN)).
- **Preuve** : dans une évaluation sur les rendements quotidiens, les modèles tabulaires classiques (CatBoost, LightGBM) font mieux que les grands modèles de séries temporelles ([arXiv 2511.18578](https://ar5iv.labs.arxiv.org/html/2511.18578)). C'est la famille de modèles qui a le plus d'éléments en sa faveur.
- **Verdict** : premier à brancher, comme second avis à côté du méta-modèle de la porte.

### 2. Lire les bougies — Kronos, Chronos, TimesFM

| Modèle | Taille | Licence | Processeur seul | Source |
|---|---|---|---|---|
| Kronos-mini / small | 4,1 M / 24,7 M de paramètres | MIT | non précisé sur la page | [dépôt Kronos](https://github.com/shiyu-coder/Kronos) |
| Chronos-Bolt tiny / mini / small | 9 M / 21 M / 48 M | Apache 2.0 | oui | [Chronos-Bolt](https://huggingface.co/amazon/chronos-bolt-small) |
| Chronos-2 | 120 M | Apache 2.0 | oui | [Chronos-2](https://huggingface.co/amazon/chronos-2) |
| TimesFM 2.5 | 200 M | Apache 2.0 | non précisé sur la page | [dépôt TimesFM](https://github.com/google-research/timesfm) |

- **Kronos** est le seul entraîné sur des bougies de marché : données de plus de 45 places de marché, publication acceptée à AAAI 2026 ([dépôt Kronos](https://github.com/shiyu-coder/Kronos)).
- **TimesFM 3.0** est à écarter : ses poids sont réservés à un usage non commercial et hors production ([dépôt TimesFM](https://github.com/google-research/timesfm)).
- **La limite, clairement** : dans une évaluation préenregistrée sur les contrats à terme Nasdaq et S&P, cinq modèles de ce type (dont Chronos-Bolt, Chronos-2 et TimesFM 2.5) n'ont battu la prévision « le prix ne bouge pas » dans aucune des 160 configurations testées ([arXiv 2611.12141](https://arxiv.org/pdf/2611.12141)). Sur les rendements quotidiens d'actions, Chronos donne une direction correcte à peine au-dessus de 51 % ([arXiv 2511.18578](https://ar5iv.labs.arxiv.org/html/2511.18578)).
- **Les auteurs de Kronos** préviennent eux-mêmes que leur exemple n'est pas un système de trading prêt pour la production ([dépôt Kronos](https://github.com/shiyu-coder/Kronos)).
- **Verdict** : à brancher en observation seulement. Kronos-mini d'abord (le plus petit, le seul spécialisé), jugé par le laboratoire comme une stratégie de plus.

### 3. Prévoir la volatilité — TTM (IBM)

- **Ce que c'est** : de très petits modèles de prévision, environ 805 000 paramètres, sous licence Apache 2.0, qui tournent sur une machine sans carte graphique ([TTM](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2)).
- **Preuve** : sur 50 actifs, c'est le seul modèle de fondation qui fait mieux que la référence économétrique à tous les horizons, avec une marge étroite de 1,6 % à un jour ([arXiv 2607.05291](https://arxiv.org/pdf/2607.05291)). L'étude porte sur des actions, des devises et des contrats à terme, pas sur des cryptos.
- **À quoi ça sert** : régler la largeur des stops et la taille des positions, pas deviner la direction. Les 30 stops du bot coûtent −37,50 € : c'est là que se trouve la perte.
- **Verdict** : utile, en troisième. À comparer d'abord au calcul actuel (ATR) sans rien changer.

### 4. Sentiment des textes — CryptoBERT plutôt que FinBERT

| Modèle | Ce qu'il lit | Licence | Source |
|---|---|---|---|
| CryptoBERT | messages crypto des réseaux sociaux, classés baissier / neutre / haussier, entraîné sur plus de 3,2 millions de messages | MIT | [CryptoBERT](https://huggingface.co/ElKulako/cryptobert) |
| FinBERT | textes financiers, classés positif / négatif / neutre | CC BY-NC-SA 4.0, usage commercial restreint | [FinBERT](https://huggingface.co/ProsusAI/finbert) |

- Les deux ne lisent que l'anglais ([CryptoBERT](https://huggingface.co/ElKulako/cryptobert), [FinBERT](https://huggingface.co/ProsusAI/finbert)).
- Les données d'entraînement de CryptoBERT datent de 2018 à 2022 ([CryptoBERT](https://huggingface.co/ElKulako/cryptobert)).
- **Verdict** : possible mais secondaire. Le bot a déjà le Fear & Greed, et il faudrait une source de textes gratuite et fiable pour l'alimenter.

### 5. Cerveau local — rester sur Qwen 3.5, changer seulement le critique

| Mémoire du VPS | Modèle conseillé | Téléchargement | Vitesse mesurée sur 16 cœurs |
|---|---|---|---|
| 8 Go | `qwen3.5:4b` | 3,4 Go | 13,43 tokens par seconde |
| 16 Go | `qwen3.5:9b` | 6,6 Go | 7,78 tokens par seconde |

Source du tableau : [Arct](https://www.arct.cloud/blog/best-ollama-models-cpu).

- **Second avis** : `phi4-mini` pèse 2,5 Go et est présenté comme fort en raisonnement et en mathématiques ([Ollama, phi4-mini](https://ollama.com/library/phi4-mini)). `granite4.2:3b` pèse 2,2 Go, sous licence Apache 2.0, avec sortie JSON structurée ([Ollama, granite4.2](https://ollama.com/library/granite4.2)).
- **Idée** : le critique sert à contredire le décideur. Deux modèles de la même famille se trompent souvent ensemble ; un critique d'une autre famille (Phi ou Granite) à la place de `llama3.2:3b` est un essai simple. Je n'ai pas trouvé de mesure qui le prouve : ce serait à juger sur les décisions du bot.
- **Verdict** : rien à ajouter tant que je ne connais pas la mémoire du VPS.

### 6. Mémoire en langage naturel — EmbeddingGemma

| Modèle | Taille | Langues | Source |
|---|---|---|---|
| `embeddinggemma` | 622 Mo, 300 M de paramètres | plus de 100 | [Ollama, embeddinggemma](https://ollama.com/library/embeddinggemma) |
| `bge-m3` | 1,2 Go | plus de 100 | [Ollama, bge-m3](https://ollama.com/library/bge-m3) |
| `nomic-embed-text` | 274 Mo | non vérifié | [Arct](https://www.arct.cloud/blog/best-ollama-models-cpu) |

- **À quoi ça sert** : permettre au chat de retrouver une leçon passée par son sens (« pourquoi on a baissé la mise ») dans les journaux et les comptes rendus.
- **Verdict** : confort pour le chat, aucun effet attendu sur les gains.

### 7. Une IA qui corrige le code toute seule — non

- Le seul modèle de code qui tient dans 8 Go est `granite4.2:8b`, 5,3 Go ([Hashnode](https://hashnode.com/blog/best-local-llm-for-coding)).
- Sur processeur seul, un long texte de code prend de 183 à 254 secondes à lire, et la source conseille de garder un modèle local pour les questions courtes ([Arct](https://www.arct.cloud/blog/best-ollama-models-cpu)).
- **Verdict** : ne pas laisser un petit modèle modifier le bot sans relecture. C'est la cause la plus probable de nouveaux bugs, pas un remède.

### 8. Un grand modèle qui décide des trades — non

- Sur vingt ans et plus de 100 titres, l'avantage annoncé des stratégies pilotées par un grand modèle de langage se dégrade nettement ; elles sont trop prudentes en marché haussier et trop agressives en marché baissier, où elles perdent lourdement ([arXiv 2505.07078](https://arxiv.org/html/2505.07078)).
- **Verdict** : le cerveau du bot garde son rôle de filtre et d'analyste, pas de pilote.

## Ordre proposé

1. **TabPFN** en second avis de la porte, en observation : il note chaque candidat, on compare ses notes aux résultats pendant 60 trades virtuels.
2. **Kronos-mini** comme professeur dans le laboratoire, sans droit d'ouvrir.
3. **TTM** pour la volatilité, comparé à l'ATR actuel.
4. Le reste (sentiment, mémoire, critique d'une autre famille) seulement si la mémoire du VPS le permet.

Règles de branchement, pour que rien ne casse :

- chaque IA a son interrupteur dans `.env` et un délai maximum ; si elle ne répond pas, le bot continue sans elle ;
- elle tourne dans son propre processus, pas dans celui qui gère les positions ;
- aucune ne reçoit le droit d'ouvrir ; seule une preuve mesurée par le laboratoire peut changer cela.

## « Sans bug » : ce qui est fait aujourd'hui

- **Contrôle automatique** : un nouveau test lit tout le code sans l'exécuter et refuse toute variable ou fonction inconnue. Ce type d'erreur ne se voit qu'au moment où la ligne s'exécute ([documentation Ruff](https://docs.astral.sh//ruff/rules/undefined-name/)), et le bot en a déjà eu deux en octobre.
- **Bug trouvé au premier passage** : sur le tableau de bord, la ligne « filtres désarmés par les faits » ne s'affichait jamais (variable inconnue, erreur avalée en silence). C'est la ligne qui indique quels filtres le bot a désarmés, dont le filtre de tendance vu le 25/11. Corrigé.
- Ce contrôle tourne de mon côté avant chaque envoi. Il ne garantit pas l'absence de bug ; il supprime une famille d'erreurs.

## Limites de ce document

- Les tailles et vitesses viennent des pages citées, pas de mesures sur le VPS.
- Je ne connais pas la mémoire ni le nombre de cœurs du VPS : c'est ce qui décide de ce qui peut tourner.
- Les études citées portent surtout sur des actions et des contrats à terme ; les résultats sur les cryptos peuvent différer.
- Rien n'est installé à ce stade, sauf le contrôle du code et la correction du tableau de bord.
