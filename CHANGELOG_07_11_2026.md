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
