# Leads — comment les travailler et comment les vendre

Le scanner (`scanner_leads.py`) note chaque projet de 0 à 100. Un lead CHAUD (≥ 75) est un
besoin d'automatisation / IA avec un budget annoncé ; un TIÈDE (50-74) mérite un œil ;
le reste est du bruit qu'on garde pour les statistiques.

## 1. Y répondre soi-même (dès la micro-entreprise ouverte)

Codeur.com demande un statut pour déposer un devis ; en attendant, le scanner mémorise
tout et on prépare les réponses. Trois réponses types, à adapter en 2 minutes.

**A. Projet « agent IA / chatbot » (le cas « Concepteur d'agent IA, 500 à 1 000 € »)**

> Bonjour,
> Je conçois des agents IA qui tournent sur un serveur dédié (pas de dépendance à un abonnement
> SaaS), avec une IA locale quand c'est possible pour que vos données restent chez vous. Mon
> propre système fait tourner 24 h/24 plusieurs agents qui se surveillent et se corrigent seuls
> depuis plusieurs mois.
> Pour vos 5-6 premiers agents : je propose une première étape à [700 €] — un agent complet
> branché sur votre site + l'architecture pour ajouter les suivants à [150 €] pièce, livraison
> en 10 jours. Chaque agent est livré avec sa supervision : vous êtes alerté s'il se met à
> répondre de travers.
> Dites-moi quelles sont les 2 tâches qui vous prennent le plus de temps, je vous réponds avec un
> schéma précis sous 24 h.

**B. Projet « automatisation / n8n / Make »**

> Bonjour,
> J'automatise ce type de flux en Python ou n8n sur un serveur dédié, avec journal de chaque
> exécution et alerte Telegram en cas de panne (y compris les pannes silencieuses : le flux
> tourne mais produit du faux). Forfait [X €] pour la mise en place, puis supervision en option
> à [39 €/mois]. Quel outil est au centre de votre flux (CRM, Sheets, boutique, mail) ?

**C. Projet « contenu IA vidéo / TikTok en masse »**

> Bonjour,
> Je produis des contenus courts avec génération d'images et de vidéos IA et des personnages
> cohérents d'une vidéo à l'autre, montés et planifiés automatiquement. Je peux vous livrer un
> test de 3 vidéos sur un de vos comptes pour [150 €] avant tout engagement de volume.

Règles : toujours un prix, toujours un délai, toujours une question pour relancer.

## 2. Les vendre à des agences (possible avant la micro-entreprise, en préparant le fichier)

Les agences d'automatisation IA et les formateurs cherchent exactement ces signaux. Produit :
un fichier hebdomadaire (`python3 revenus/leads/scanner_leads.py csv`) filtré CHAUD + TIÈDE,
livré le lundi matin par mail, 10 à 30 leads qualifiés avec budget et lien.

Prix repères : 149 €/mois l'abonnement hebdo, ou 20 € le lead chaud à l'unité ; au-delà de
5 abonnés, c'est un revenu récurrent sans production supplémentaire. Les données sont
publiques ; ce qu'on vend, c'est le tri, la note et la rapidité (alerte dans les 2 heures).

**Message aux agences (LinkedIn ou mail, 6 lignes)**

> Bonjour [Prénom],
> Chaque semaine, des PME françaises publient des demandes d'automatisation et d'agents IA avec
> leur budget. Je les détecte en moins de 2 heures et je les note. Voici gratuitement les 5
> meilleures de cette semaine : [coller 5 lignes titre / budget / lien].
> Si ça vous intéresse, la liste complète chaque lundi (20 à 30 leads notés) c'est 149 €/mois,
> sans engagement. On essaie un mois ?

Où trouver les agences : Nodva, Fyliz, Foxpilot et les ~200 agences n8n/Make françaises
visibles sur les annuaires de partenaires n8n et Make ; les formateurs IA sur Malt et LinkedIn.

## 3. Pour soi : le scanner nourrit les autres idées

- Projets « e-commerce » + « fraude / paiement refusé » → prospects pour l'audit des règles.
- Projets « maintenance / panne / VPS / bot » → prospects pour le veilleur.
- Projets « formation IA » → prospects pour la journée de formation.
