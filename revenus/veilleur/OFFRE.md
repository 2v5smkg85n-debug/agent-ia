# Offre — Veilleur : « vos agents IA tournent-ils encore, et disent-ils encore vrai ? »

## Le problème qu'on vend

Une agence qui a livré 20 automatisations n8n / Make et 5 chatbots à ses clients les facture
souvent une « supervision » mensuelle (90 à 280 € par unité sur le marché français). En
pratique, elle découvre les pannes quand le client appelle. Et les pires pannes sont
silencieuses : le workflow renvoie « succès » mais n'envoie plus rien, le chatbot répond poliment
avec des horaires périmés, l'export tourne mais sur un fichier vide.

Le Veilleur contrôle toutes les 5 minutes, depuis un serveur indépendant :
- que la chose tourne (service, battement du workflow, fraîcheur d'un fichier) ;
- que la réponse est bonne (mots attendus, mots interdits, délai) ;
- que la réponse est sensée (question posée à une IA locale : « cette réponse donne-t-elle bien
  des horaires d'ouverture ? » → OUI/NON), sans envoyer les données du client à un service tiers.

Alerte Telegram dans le groupe de l'agence (et du client s'il le souhaite) à la panne et au
rétablissement ; rapport quotidien de disponibilité ; page d'état JSON par client.

## À qui le vendre, à quel prix

Cible 1 : les agences d'automatisation / IA (en marque blanche — l'agence revend la
supervision à son prix, on lui facture le gros).

| Formule | Contenu | Prix |
|---|---|---|
| Agence 10 | jusqu'à 10 contrôles, alertes Telegram, rapport quotidien | 49 €/mois |
| Agence 50 | jusqu'à 50 contrôles, groupes Telegram par client, page d'état | 149 €/mois |
| Agence 200 | 200 contrôles, jugement sémantique sur tous les chatbots, SLA de réponse 1 h | 390 €/mois |

Cible 2 : les PME qui ont fait développer un agent IA et n'ont plus de prestataire : 29 €/mois
par agent supervisé, installation 90 €.

Marge : le VPS coûte déjà ; 10 agences à 149 € = 1 490 €/mois pour une passe de contrôle
toutes les 5 minutes.

## Mise en place côté client (10 minutes)

1. L'agence envoie la liste de ses contrôles (URL du chatbot et question type, workflows à
   surveiller, bots Telegram). On remplit `clients.json`.
2. Pour chaque workflow n8n / Make : un nœud HTTP en fin de flux qui appelle
   `http://VPS:8791/battement/<cle>?token=...`. S'il n'appelle plus → alerte.
3. On crée un groupe Telegram agence + nous, on met son `telegram_chat_id` dans la config.
4. Premier rapport le lendemain 8 h.

## Message aux agences

> Bonjour [Prénom],
> Vous facturez la supervision de vos automatisations, mais qui vous prévient quand un
> workflow renvoie « succès » sans rien faire, ou quand un chatbot répond n'importe quoi ?
> Je fais tourner un veilleur indépendant qui contrôle chaque agent toutes les 5 minutes
> (battement, réponse, cohérence jugée par une IA locale) et vous alerte sur Telegram avant
> le client. Je supervise gratuitement 3 de vos agents pendant 30 jours ; si vous ne recevez
> aucune alerte utile, on arrête là.

## Pourquoi nous et pas un Healthchecks / UptimeRobot

Ces outils vérifient qu'un ping arrive ou qu'une page répond 200. Ils ne lisent pas la
réponse et ne savent pas qu'un agent IA s'est mis à dire des bêtises. Le jugement sémantique
local, l'alerte Telegram par client et le rapport en français sont la différence, et le tout
tourne déjà pour nos propres agents depuis des mois.
