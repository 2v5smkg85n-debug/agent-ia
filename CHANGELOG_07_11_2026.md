# Changements du 7 novembre 2026 — le cerveau du chat

## Constat
Réponses Telegram génériques, coupées, inventées (« 10 sous-agents à 50 k€ », NFT/ICO, « Bonne chance ! 🚀 »). Cause : Gemini en échec (quota) → le chat tombait sur le dernier secours, Ollama qwen2.5:7b, avec un prompt obsolète (« TP 0,9 %, crée des sous-agents, tu dois évoluer »), SANS le contexte du bot, et 200 mots max (`num_predict=200`) → coupures.

## Correctifs (chat_naturel.py, llm_router.py)
- Le chat passe par `llm_router` (rôle `chat` : Gemini 2.5 Flash → Llama 3.3 70B OVH (sans clé) → DeepSeek LLM7 (sans clé) → gpt-oss-120b → Groq/OpenRouter si clés → Pollinations → local). Tous reçoivent le même prompt complet avec l'état réel du bot. Aucune clé ajoutée.
- `_verite_chiffree()` : quand le message vise un montant dans un délai (« 10 milliards en 5 ans »), le taux composé nécessaire est calculé en Python et injecté dans le prompt avec le réel mesuré du bot et des références (Medallion ~40 %/an). Le modèle ne peut plus inventer : il doit dire « hors de portée » puis proposer un plan depuis le capital réel.
- Longueur adaptative : 2-5 phrases par défaut ; « détaille / plan / explique / de A à Z » → 6-14 phrases en paragraphes, 1 400 tokens. Interdits : emojis, listes, markdown, flatterie, promesses, capitaux/outils inventés.
- Telegram : découpage aux paragraphes au lieu de « … (tronqué) ».
- Secours Ollama : même prompt complet, 500-1 400 tokens, prompt obsolète supprimé.
- `_nettoyer_reponse()` : enlève markdown, emojis, balises <think>.
- Tests : `tests/test_chat_cerveau.py` (7), 38 au total. Test réel sandbox (Llama 70B OVH) : réponse honnête, chiffrée, complète.

## Retour arrière
`git checkout b6b340b -- chat_naturel.py llm_router.py` puis redémarrage de chat_naturel.service.

## Correctif du soir : plus de réponse après le déploiement
Avec `LLM_LIBRE=0` (choix de l'utilisateur : les modèles publics sans clé sont coupés) et Gemini en pause quota, le chat tombait sur le modèle local avec le prompt complet (~6 000 tokens, num_ctx 8192) : 4 minutes de calcul CPU dans le routeur, puis 4 autres dans le secours, pendant lesquelles la boucle Telegram était bloquée. Résultat : silence.
- Le modèle local sort du rôle `chat` du routeur ; il est appelé une seule fois par le chat, avec un prompt compact (`_prompt_compact_local` : consigne + capital/positions/stats réduits + calcul vérifié + question + règles, ~3 000 car.), num_ctx 4096, 700 tokens max, timeout 150 s (`CHAT_TIMEOUT_LOCAL`), modèle du routeur (qwen3.5:4b, plus léger que qwen2.5:7b).
- Les questions passent dans un fil séparé : `status`, `pnl`, `positions` répondent pendant qu'un modèle réfléchit ; après 25 s sans réponse (`CHAT_ACCUSE_S`), un accusé de réception est envoyé au lieu d'un silence.
- Tests : 39.

## Droit d'ouvrir pour les stratégies éprouvées (soir, décision de l'utilisateur)
Suite au rapport « Stratégies qui ont fait leurs preuves sur des années » : deux stratégies de suivi de tendance entrent dans le bot avec le droit d'ouvrir, en probation du registre (1 position max chacune, jugées sur leurs propres trades, retirables par `python3 registre_strategies.py droit <s> off`).

- `strategies_tendance.py` (nouveau) :
  - `donchian_breakout` : clôture 4 h TERMINÉE au-dessus du plus haut des 20 bougies précédentes, volume de la bougie ≥ moyenne 20, prix au-dessus de son EMA 84 jours. Sortie propre : clôture 4 h sous le plus bas des 10 bougies précédentes (règle Turtle). Sources : Boring Edge 2017-2026 (https://boringedge.com/bitcoin-donchian-channel-breakout-turtle-trading-backtest/), CoinQuant 10 ans (https://www.coinquant.ai/blog/bitcoin-trading-strategy-5-approaches-backtested-over-7-years), Hudson & Urquhart (https://link.springer.com/article/10.1007/s10479-019-03357-1).
  - `tsmom` : rendement 20 j > 0 ET 90 j > 0 ET prix > SMA 200 j, et le rendement 20 j vient de repasser positif (≤ 5 jours) — on prend le retournement, pas la hausse déjà vieille. Sortie propre : rendement 20 j < 0. Sources : Review of Asset Pricing Studies 2026 (https://academic.oup.com/raps/advance-article-abstract/doi/10.1093/rapstu/raag011/8914819), Backtest Everything (https://www.backtesteverything.com/blog/backtesting-crypto-momentum-strategies).
  - Score de tendance 9 canaux Donchian 5-360 j (Catching Crypto Trends, https://studylib.net/doc/27985947/catching-crypto-trends;-a-tactical-approach-for-bitcoin-a...) : +0,5 / -0,5 dans le tri de présélection du cerveau et ligne « TENDANCE » dans le dossier de l'analyste.
  - `TENDANCE=0` dans .env coupe tout ; réglages `DONCHIAN_ENTREE/SORTIE/VOL`, `TSMOM_COURT/LONG/SMA/FRAICHEUR`, `TENDANCE_TP_RATIO` (3), `TENDANCE_BARRIERE_H` (168).
- `paper_trading.py` : `analyser_signaux_tendance()` évalué à CHAQUE cycle (pas seulement en secours des indicateurs) ; ces signaux sautent les couches conçues pour le retour à la moyenne (apprentissage, trader_pro, maîtres, intel, TradingView, news — un RSI « surachat » est normal sur une cassure), comme le professeur virtuel, mais passent le registre, le stop ATR, la porte, les sous-agents et la protection du capital. En position : stop 2×ATR, objectif 3:1 puis stop suiveur, sortie propre « SORTIE-TENDANCE », barrière 7 jours ; les sorties « 24 h » (live-exit, pattern, stale) ne s'appliquent pas à elles.
- `journal_erreurs.py` : pour ces stratégies, objectif 3:1 et barrière 168 h ; les règles apprises `achat_sommet` et `mauvaise_heure` (apprises sur des trades de 24 h) ne s'appliquent pas à elles ; `contre_btc` et `cascade` restent.
- `porte_entree.py` : « fenêtres » et « CUSUM » jugés mais non bloquants pour la tendance ; NOUVEAU filtre `PORTE_ADX_RANGE` pour les stratégies de retour à la moyenne (rsi_oversold, consensus_reversion, pattern_reversal, bollinger_bounce…) : pas d'achat à contre-tendance si ADX(14) 4 h > 25 (`ADX_RANGE_MAX`). Source : Vantixs 2023-2025, facteur de profit 1,11 → 1,78 (https://vantixs.com/blog/bollinger-mean-reversion-crypto-bot). Mesuré par le bilan contrefactuel, désarmable automatiquement (PORTE_AUTO), `PORTE_ADX_RANGE=0` coupe.
- Droits : `python3 registre_strategies.py droit donchian_breakout on` et `droit tsmom on` (dans la commande de déploiement).
- À surveiller : les stratégies de tendance ont 55-65 % de trades perdants par nature (petites pertes, rares gros gains) ; le coupe-circuit « 5 pertes consécutives » (protection_capital) peut se déclencher plus souvent. Laissé tel quel pour mesurer.
- Tests : `tests/test_strategies_tendance.py` (10), 49 au total. Test réel (07/11 soir) : BTC/ETH/SOL sans signal (rendement 20 j négatif, sous le plus haut 20) — cohérent avec le marché baissier du moment.

## Retour arrière (tendance)
`.env` : `TENDANCE=0` + redémarrage, ou `python3 registre_strategies.py droit donchian_breakout off` / `droit tsmom off`. Complet : `git checkout 0e38ecd -- paper_trading.py journal_erreurs.py porte_entree.py cerveau.py chat_naturel.py`.
