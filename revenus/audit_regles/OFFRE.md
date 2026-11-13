# Offre — « Vos règles anti-fraude vous coûtent des ventes. On les mesure, on ne touche à rien sans preuve. »

## Le pitch en 30 secondes

Chaque boutique en ligne a des règles qui refusent des commandes : montant trop élevé, pays de
livraison différent, email suspect, plusieurs tentatives de carte. Ces règles ont été posées un
jour, souvent après une fraude, et plus personne ne les a jamais mesurées. Or les faux refus
coûtent aux marchands plus que la fraude elle-même, et 4 clients refusés à tort sur 10 ne
reviennent jamais.

Nous faisons pour vos règles ce qu'un bot de trading fait pour ses propres filtres : chaque
règle est jugée a posteriori sur ce qu'elle a bloqué et sur ce qui s'est réellement passé.
Résultat en 48 h : la liste de vos règles, celles qui protègent, celles qui vous coûtent, et
combien. Puis on passe les règles douteuses en « mode ombre » (elles journalisent sans bloquer)
pendant 4 à 8 semaines, et on ne garde que ce qui a fait ses preuves.

Rémunération : 20 % des ventes récupérées nettes (ventes supplémentaires acceptées moins la
fraude supplémentaire subie), mesurées chaque mois, pendant 12 mois. Zéro récupéré, zéro payé.

## Qui cibler en premier

- Boutiques françaises à 300 000 € – 10 M€ de CA/an sur Shopify, PrestaShop ou WooCommerce
  avec un module anti-fraude (Shopify Fraud Filter / Flow, Stripe Radar, FraudLabs Pro, Signifyd
  en « règles », module PrestaShop maison) : assez de volume pour mesurer, pas de data scientist.
- Secteurs à panier élevé et fraude réelle : high-tech, sneakers, parfums, pièces auto, bijoux.
- Signal d'entrée : le marchand se plaint des « paiements refusés », du « taux de conversion
  au paiement », ou a un taux de refus > 3 %.

## Les 4 étapes

1. **Qualification (15 min, visio ou mail)** — questions ci-dessous. Si le taux de refus est
   < 1 % ou s'il n'y a pas de journal des règles, on passe.
2. **Audit (48 h)** — le marchand exporte un CSV de 3 à 6 mois de commandes avec la décision
   (acceptée / refusée / revue), les règles déclenchées, et le sort (chargeback ou non). On lance
   `audit_regles.py` et on livre le rapport Markdown/PDF. Gratuit : c'est le produit d'appel.
3. **Mode ombre (4 à 8 semaines)** — on branche le webhook « commande créée » et « litige »
   du marchand sur `regles_ombre.py` (serveur sur le VPS, port 8790) ou on lui donne la
   bibliothèque Python. Les règles coûteuses journalisent sans bloquer. Le marchand voit chaque
   semaine le rapport : précision réelle, ventes récupérées, fraude subie.
4. **Décision et suivi (12 mois)** — on retire / assouplit / exempte les clients connus, on
   mesure chaque mois le net récupéré, on facture 20 %.

## Questions de qualification

1. Combien de commandes par mois, panier moyen ?
2. Quel outil décide d'accepter ou refuser une commande ? Journalise-t-il les règles déclenchées ?
3. Taux de refus actuel ? Taux de chargeback ?
4. Un client qui a déjà commandé 3 fois peut-il être refusé par vos règles aujourd'hui ?
5. Pouvez-vous exporter 6 mois de commandes avec statut et litiges (Shopify : Commandes → Exporter ;
   PrestaShop : SQL Manager ; WooCommerce : extension d'export ; Stripe : Radar → exports) ?

## Mail de prospection (à froid)

> Objet : vos règles anti-fraude refusent des clients qui voulaient payer
>
> Bonjour [Prénom],
> Sur une boutique de la taille de [Boutique], entre 2 et 5 % des commandes sont refusées par
> des règles anti-fraude. Dans la plupart des audits, la majorité de ces refus sont des clients
> légitimes, et 4 sur 10 ne reviennent jamais.
> Je mesure, règle par règle, ce que chacune bloque et ce qu'elle protège vraiment, à partir de
> votre export de commandes. L'audit est gratuit et prend 48 h ; ensuite je ne suis payé que sur
> les ventes effectivement récupérées (20 % du net, mesuré chaque mois).
> Si vous m'envoyez votre taux de refus actuel, je vous dis en une ligne si ça vaut le coup.
> [Prénom Nom] — [téléphone]

## Contrat — les clauses qui comptent (à faire relire avant signature)

- Objet : mission d'analyse et d'optimisation des règles de validation des commandes.
- Base de calcul : « ventes récupérées nettes » = CA des commandes acceptées qui auraient été
  refusées par les règles en vigueur à la date de signature (identifiées par le journal mode
  ombre), moins le montant des chargebacks et remboursements pour fraude sur ces mêmes commandes,
  moins les frais de chargeback.
- Rémunération : 20 % de la base, calculée mensuellement sur les commandes de plus de 60 jours
  (délai de contestation), payable à 30 jours. Plancher : aucun. Plafond : à négocier au-delà
  de 5 000 €/mois (pour rassurer le marchand).
- Durée : 12 mois à compter de la première règle modifiée ; résiliable par le marchand à tout
  moment avec préavis d'un mois, les commandes déjà acceptées restant dues.
- Accès aux données : lecture seule, exports anonymisés (pas de numéro de carte ; emails hachés
  si le marchand le souhaite). RGPD : sous-traitant, clause de confidentialité, suppression des
  données à la fin.
- Responsabilité : le marchand reste seul décideur des règles en production ; nous recommandons,
  il applique. Aucune garantie de résultat chiffrée, d'où le paiement au résultat.

## Pourquoi c'est nouveau

Les outils anti-fraude vendent la détection ; le « mode ombre » n'existe que chez des
fintechs pour grandes entreprises ; aucun prestataire francophone ne vend aux PME un audit
contrefactuel payé au pourcentage des ventes récupérées. La méthode est celle de l'entonnoir
du bot : chaque filtre est présumé coupable jusqu'à preuve mesurée.
