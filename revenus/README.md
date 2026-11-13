# Revenus hors trading — tout ce qui est construit, et dans quel ordre s'en servir

Six sources de revenus, zéro capital, construites avec ce que le bot sait déjà faire
(entonnoir mesuré, Telegram, IA locale, scanners, VPS). Tout est dans ce dossier, tout tourne
sur le VPS à côté du bot, rien ne touche au trading.

| # | Type de revenu | Outil | Dossier | Peut démarrer |
|---|---|---|---|---|
| 1 | Commission sur résultat (20 % des ventes récupérées) | audit contrefactuel + mode ombre des règles anti-fraude e-commerce | `audit_regles/` | audits gratuits tout de suite ; facturation après SIREN |
| 2 | Abonnement récurrent (49-390 €/mois) | Veilleur : supervision des agents IA et automatisations, pannes silencieuses | `veilleur/` | 30 jours offerts tout de suite |
| 3 | Vente de leads (149 €/mois ou 20 €/lead) | Scanner : PME françaises qui publient un besoin IA/automatisation avec budget | `leads/` | collecte tout de suite ; vente après SIREN |
| 4 | Produits numériques (29-59 €) | modèles n8n + fiches de publication | `modeles/` | Gumroad tout de suite (statut requis pour encaisser durablement) |
| 5 | Journées de formation (500-900 € HT) | programme, tarifs, pitch | `formation/` | sessions offertes tout de suite ; facturation après SIREN |
| 6 | Apport d'affaires / affiliation (500 € par journée Axion-IA, commissions) | messages, programmes, convention | `apport/` | après SIREN |
| — | Prospection : les 30 premiers contacts vérifiés (agences, e-commerçants, clubs/CCI/experts-comptables), messages prêts, 5 envois par jour, suivi `prospection.sh` | `CONTACTS_30.md` | tout de suite |
| — | Micro-entreprise (étape finale) | mode d'emploi, chiffres 2026 | `MICRO_ENTREPRISE.md` | quand un premier client veut payer |

## Installation sur le VPS (une seule ligne)

```
cd ~/agent-ia && curl -sL https://github.com/2v5smkg85n-debug/agent-ia/archive/refs/heads/main.tar.gz | tar xz --strip-components=1 agent-ia-main/revenus agent-ia-main/tests/test_revenus.py && bash revenus/installer.sh
```

Ça installe des timers systemd indépendants du bot :
- `revenus-leads.timer` : scanner toutes les 2 h, leads chauds sur Telegram ;
- `revenus-veilleur.timer` : passe de contrôle toutes les 5 min, alerte à la panne et au rétablissement ;
- `revenus-veilleur-rapport.timer` : rapport de disponibilité à 8 h ;
- `revenus-veilleur-serveur.service` : reçoit les battements des workflows (port 8791) ;
- `revenus-ombre.service` : reçoit les webhooks des marchands (port 8790).
Deux jetons (`VEILLEUR_TOKEN`, `OMBRE_TOKEN`) sont générés dans `.env`. Désinstallation :
`bash revenus/installer.sh desinstaller`.

Ouvrir les ports 8790 et 8791 seulement quand un client externe en a besoin
(`sudo ufw allow 8791/tcp`).

## Commandes du quotidien

```
python3 revenus/leads/scanner_leads.py liste 10      # les 10 meilleurs leads
python3 revenus/leads/scanner_leads.py csv           # fichier à envoyer aux agences
python3 revenus/leads/scanner_leads.py stats
python3 revenus/veilleur/veilleur.py test            # état de tous les contrôles
python3 revenus/veilleur/veilleur.py rapport test    # rapport 24 h sans l'envoyer
nano revenus/veilleur/clients.json                   # ajouter un client / un contrôle
python3 revenus/audit_regles/audit_regles.py demo    # rapport d'audit sur une boutique fictive
python3 revenus/audit_regles/audit_regles.py export_client.csv "Nom boutique"
python3 revenus/audit_regles/regles_ombre.py rapport nom_client
```

Réglages dans `.env` : `LEADS_SEUIL_TELEGRAM=60`, `LEADS_IA=1` (avis Ollama sur les leads
chauds), `ADZUNA_APP_ID/ADZUNA_APP_KEY` (source d'offres d'emploi, clé gratuite, optionnelle),
`FT_CLIENT_ID/FT_CLIENT_SECRET` (France Travail, si l'accès rouvre), `REVENUS_TELEGRAM=0` pour
couper les envois, `REVENUS_OLLAMA=0` pour couper les jugements IA.

## L'ordre conseillé

1. **Aujourd'hui** : installer ; laisser le scanner tourner ; lire `leads/MESSAGES.md`.
2. **Semaine 1** : envoyer les 5 meilleurs leads gratuitement à 10 agences (message dans
   `leads/MESSAGES.md`) ; proposer 30 jours de Veilleur offerts à 5 agences (`veilleur/OFFRE.md`).
3. **Semaines 2-4** : 10 audits de règles gratuits à des marchands trouvés par le scanner et sur
   LinkedIn (`audit_regles/OFFRE.md`) ; le premier qui veut passer en mode ombre payant déclenche
   la micro-entreprise.
4. **Mois 2** : première session de formation offerte à un club d'entrepreneurs pour avoir un
   témoignage (`formation/`) ; publier les deux modèles n8n.
5. **Dès le SIREN** : facturer, s'inscrire chez Axion-IA, activer les affiliations (`apport/`).

## Ce qui n'est pas garanti

Les prix sont des repères de marché, pas des promesses. L'audit des règles exige que le
marchand ait un journal des règles déclenchées ; sans lui, le mode ombre doit tourner 4 à 8
semaines avant de conclure. Les modèles n8n doivent être testés dans un n8n réel avant mise en
vente. Codeur.com demande un statut pour déposer un devis.
