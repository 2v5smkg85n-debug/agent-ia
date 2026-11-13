# Modèles à vendre (n8n, marketplace de créateurs vérifiés) — fiches de publication

Statut : les deux fichiers JSON ci-contre s'importent dans n8n (Workflows → Import from file).
Les tester dans un n8n réel (identifiants Telegram, URL du chatbot) avant publication. La vente
sur la marketplace n8n demande un compte créateur vérifié (3 modèles approuvés) et se fait via
son propre lien de paiement (Stripe / Lemon Squeezy / Gumroad) ; en attendant, Gumroad suffit.

Repères de prix observés : médiane 25 $, le gros des modèles payants entre 25 et 49 $ ; ce qui
attire le plus de vues : automatisation de contenu / vidéo et bots de messagerie.

## 1. Agent Telegram avec IA locale (Ollama) — sans API payante · 29 €

Titre : « Un assistant Telegram pour votre entreprise, 100 % sur votre serveur, 0 € d'API »
Description : Répond aux questions de vos clients ou de votre équipe dans Telegram avec un
modèle local (Ollama). Aucune donnée ne quitte votre serveur, aucune facture d'API. Inclus : le
nœud de « battement » pour être alerté si le bot cesse de répondre. Prérequis : n8n + Ollama
sur le même serveur (un VPS à 5 €/mois suffit pour un modèle 3B).
Fichier : `agent_telegram_ollama_local.json`

## 2. Supervision d'un chatbot — détecter les pannes silencieuses · 39 €

Titre : « Votre chatbot répond encore. Mais dit-il encore vrai ? »
Description : Toutes les 5 minutes, pose une question test à votre chatbot, vérifie le code
HTTP, le délai, la présence des mots attendus et l'absence de mots d'erreur, et vous alerte sur
Telegram. Inclus : le battement vers un veilleur externe (pour être prévenu même si n8n lui-même
est tombé). Prérequis : un chatbot joignable en HTTP, un bot Telegram.
Fichier : `supervision_chatbot_panne_silencieuse.json`

## 3. Mode ombre pour règles anti-fraude e-commerce (webhook) · 59 € — à produire

Workflow : webhook « commande créée » (Shopify / WooCommerce) → calcule les règles du marchand
→ POST vers `regles_ombre.py` (/evaluer) ; webhook « litige » → POST /juger ; rapport
hebdomadaire Telegram via GET /rapport. Se construit en une heure à partir des deux précédents ;
c'est aussi l'outil de l'offre « audit des règles ».

## 4. Scanner de leads Codeur → Telegram (version n8n) · 29 € — à produire

Lecture du flux RSS Codeur toutes les 2 h, filtre par mots-clés, note, message Telegram.
Version simplifiée de `scanner_leads.py` pour les non-développeurs.

## Fiche créateur (profil marketplace)

« Je fais tourner depuis des mois un système d'agents IA autonomes qui se surveillent, se
mesurent et désarment eux-mêmes leurs mauvaises règles. Mes modèles sont ceux que j'utilise :
IA locale, zéro API payante, supervision incluse. »
