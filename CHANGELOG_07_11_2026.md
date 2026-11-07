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
